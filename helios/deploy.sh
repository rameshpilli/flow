#!/bin/bash

echo "=============================================================="
echo "Deploying to namespace '${NAMESPACE}' on ${CLUSTER_HOST}..."
echo "Using Databricks SQL MCP release version: ${WF_VERSION}"
echo "Image: ${CUSTOM_APP_IMAGE_NAME}:${CUSTOM_APP_IMAGE_TAG}"
echo "=============================================================="

readonly CHART_NAME="dbx-sql-mcp"

echo ""
echo "ENVIRONMENT: $ENVIRONMENT"
echo "CHART_NAME: $CHART_NAME"

# ------------------------------------------------------------------------------
# Vault Access Setup
# ------------------------------------------------------------------------------

VAULT_URL="https://vault.fg.rbc.com/v1"
VAULT_ENV_UPPER=$(echo "$ENVIRONMENT" | tr '[:lower:]' '[:upper:]')

if [[ "$VAULT_ENV_UPPER" == "QAT" ]]; then
  echo "Converting VAULT_ENV_UPPER from QAT to SAI..."
  VAULT_ENV_UPPER="SAI"
fi

VAULT_PATH="appcodes/ISA0/${VAULT_ENV_UPPER}/DATABRICKS-SQL-MCP"  # Update with your vault path

echo ""
echo "Retrieving Vault token..."
VAULT_TOKEN=$(curl -sk \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d "{\"password\":\"${dbx_service_account_password}\"}" \
  "${VAULT_URL}/auth/fg/login/${dbx_service_account_id}" | jq -r .auth.client_token)

if [[ -z "$VAULT_TOKEN" || "$VAULT_TOKEN" == "null" ]]; then
  echo "[ERROR] Failed to retrieve Vault token."
  exit 1
fi

echo "[SUCCESS] Vault token acquired."

echo ""
echo "Fetching secrets from Vault at path: ${VAULT_PATH}"
VAULT_RESPONSE=$(curl -s -H "X-Vault-Token: $VAULT_TOKEN" "${VAULT_URL}/${VAULT_PATH}")
VAULT_SECRETS=$(echo "$VAULT_RESPONSE" | jq -r .data)

if [[ -z "$VAULT_SECRETS" || "$VAULT_SECRETS" == "null" ]]; then
  echo "[ERROR] No data returned from Vault or path is invalid. Full response:"
  echo "$VAULT_RESPONSE"
  exit 1
fi

echo ""
echo "Vault secrets pulled successfully:"
echo "$VAULT_SECRETS" | jq .

# ------------------------------------------------------------------------------
# Write Vault Secrets to Helm values
# ------------------------------------------------------------------------------

echo ""
echo "Writing secrets to vault_values.yaml..."
echo "$VAULT_SECRETS" | jq -r '"vaultValues:", (to_entries | map("  \(.key): \(.value | tojson)") | .[])' > "$HELM_ARTIFACTS_PATH/$CHART_NAME/environments/$ENVIRONMENT/vault_values.yaml"

# ------------------------------------------------------------------------------
# Pre-deployment diagnostics
# ------------------------------------------------------------------------------

echo ""
echo "Kubernetes Context Info:"
kubectl config view | grep namespace

echo ""
echo "Pods Before Deployment:"
kubectl get pod -o wide

echo ""
echo "Helm Artifact Path:"
echo "$HELM_ARTIFACTS_PATH"
ls -l "$HELM_ARTIFACTS_PATH"
ls -l "$HELM_ARTIFACTS_PATH/$CHART_NAME"

# ------------------------------------------------------------------------------
# Helm Upgrade/Install
# ------------------------------------------------------------------------------

echo ""
echo "Running Helm Upgrade/Install..."

helm upgrade "$CHART_NAME" "$HELM_ARTIFACTS_PATH/$CHART_NAME"                       \
  --install                                                                         \
  --values "$HELM_ARTIFACTS_PATH/$CHART_NAME/environments/$ENVIRONMENT/values.yaml" \
  --values "$HELM_ARTIFACTS_PATH/$CHART_NAME/environments/$ENVIRONMENT/vault_values.yaml" \
  --set ghActionInput.imageTag="$CUSTOM_APP_IMAGE_TAG" \
  --set ghActionInput.imageName="$CUSTOM_APP_IMAGE_NAME"

# ------------------------------------------------------------------------------
# Post-Deployment Verification
# ------------------------------------------------------------------------------

echo ""
echo "=============================================================="
echo "POST-DEPLOYMENT VERIFICATION"
echo "=============================================================="

echo ""
echo "Waiting for rollout to complete..."
kubectl rollout status deployment/$CHART_NAME --timeout=5m

echo ""
echo "Checking pod status..."
kubectl get pods -l app.kubernetes.io/name=$CHART_NAME -o wide

# Get first pod name for detailed checks
POD_NAME=$(kubectl get pods -l app.kubernetes.io/name=$CHART_NAME -o jsonpath='{.items[0].metadata.name}')

if [[ -z "$POD_NAME" ]]; then
  echo "[WARNING] No pods found for $CHART_NAME"
else
  echo ""
  echo "Verifying container in pod: $POD_NAME"
  kubectl get pod $POD_NAME -o jsonpath='{range .status.containerStatuses[*]}{.name}{"\t"}{.ready}{"\t"}{.state}{"\n"}{end}'

  echo ""
  echo "Checking Redis (built into container)..."
  kubectl exec $POD_NAME -- redis-cli PING || echo "[WARNING] Redis PING failed"

  echo ""
  echo "Checking Redis connection from Python..."
  kubectl exec $POD_NAME -- python3 -c "
import redis
try:
    r = redis.Redis(host='localhost', port=6379, db=0, socket_connect_timeout=2)
    r.ping()
    print('✓ Redis connection: SUCCESS')
    print('  Redis keys count:', r.dbsize())
    print('  Redis memory:', r.info('memory')['used_memory_human'])
except Exception as e:
    print('✗ Redis connection: FAILED -', str(e))
    exit(1)
" || echo "[WARNING] Redis connection check failed"

  echo ""
  echo "MCP Server logs (last 30 lines)..."
  kubectl logs $POD_NAME --tail=30
fi

echo ""
echo "Checking Horizontal Pod Autoscaler..."
kubectl get hpa $CHART_NAME 2>/dev/null || echo "[INFO] HPA not found (autoscaling might be disabled)"

echo ""
echo "Checking service endpoints..."
kubectl get svc $CHART_NAME
kubectl get endpoints $CHART_NAME

echo ""
echo "Checking ingress..."
kubectl get ingress 2>/dev/null | grep $CHART_NAME || echo "[INFO] No ingress found"

echo ""
echo "=============================================================="
echo "DEPLOYMENT SUMMARY"
echo "=============================================================="
echo "Environment: $ENVIRONMENT"
echo "Namespace: $NAMESPACE"
echo "Chart: $CHART_NAME"
echo "Image: $CUSTOM_APP_IMAGE_NAME:$CUSTOM_APP_IMAGE_TAG"
echo ""
echo "✓ Deployment completed successfully!"
echo ""
echo "To monitor Redis cache performance:"
echo "  kubectl exec -it $POD_NAME -- redis-cli INFO stats"
echo ""
echo "To view real-time logs:"
echo "  kubectl logs -f deployment/$CHART_NAME"
echo "=============================================================="
