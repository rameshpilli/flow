#!/bin/bash
# Helios Deployment Script for Memory Store
# Based on RBC corporate deployment standards

set -e  # Exit on error

echo "=============================================================="
echo "Deploying Memory Store to namespace '${NAMESPACE}' on ${CLUSTER_HOST}..."
echo "Using CF release bundle version: ${WF_VERSION}"
echo "Image: ${CUSTOM_APP_IMAGE_NAME}:${CUSTOM_APP_IMAGE_TAG}"
echo "=============================================================="

readonly CHART_NAME="mem0"

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

# Update Vault path for Memory Store
VAULT_PATH="appcodes/ISA0/${VAULT_ENV_UPPER}/MEMORY-STORE"

echo ""
echo "Retrieving Vault token..."
VAULT_TOKEN=$(curl -sk \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d "{\"password\":\"${cf_service_account_password}\"}" \
  "${VAULT_URL}/auth/fg/login/${cf_service_account_id}" | jq -r .auth.client_token)

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
echo "$VAULT_SECRETS" | jq -r '"configuration:", (to_entries | map("  \(.key): \(.value | tojson)") | .[])' > "$HELM_ARTIFACTS_PATH/$CHART_NAME/environments/$ENVIRONMENT/vault_values.yaml"

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

echo ""
echo "Generic Artifact Path:"
echo "$GENERIC_ARTIFACTS_PATH"
ls -l "$GENERIC_ARTIFACTS_PATH"

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
  echo "Checking Memory Store health endpoint..."
  kubectl exec $POD_NAME -- python3 -c "
import httpx
try:
    response = httpx.get('http://localhost:8000/health', timeout=5.0)
    if response.status_code == 200:
        print('✓ Memory Store health check: PASSED')
        print('  Response:', response.json())
    else:
        print('✗ Memory Store health check: FAILED')
        print('  Status:', response.status_code)
        exit(1)
except Exception as e:
    print('✗ Memory Store health check: ERROR -', str(e))
    exit(1)
" || echo "[WARNING] Health check failed"

  echo ""
  echo "Memory Store logs (last 30 lines)..."
  kubectl logs $POD_NAME --tail=30
fi

echo ""
echo "Checking Qdrant deployment..."
QDRANT_POD=$(kubectl get pods -l app.kubernetes.io/name=mem0-qdrant -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [[ -n "$QDRANT_POD" ]]; then
  echo "✓ Qdrant pod found: $QDRANT_POD"
  kubectl get pod $QDRANT_POD
else
  echo "[WARNING] Qdrant pod not found"
fi

echo ""
echo "Checking Memgraph deployment (if enabled)..."
MEMGRAPH_POD=$(kubectl get pods -l app.kubernetes.io/name=mem0-memgraph -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [[ -n "$MEMGRAPH_POD" ]]; then
  echo "✓ Memgraph pod found: $MEMGRAPH_POD (GraphRAG enabled)"
  kubectl get pod $MEMGRAPH_POD
else
  echo "[INFO] Memgraph pod not found (GraphRAG disabled)"
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

# ------------------------------------------------------------------------------
# Deployment Summary
# ------------------------------------------------------------------------------

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
echo "Components:"
echo "  - Memory Store API: $POD_NAME"
if [[ -n "$QDRANT_POD" ]]; then
  echo "  - Qdrant Vector DB: $QDRANT_POD"
fi
if [[ -n "$MEMGRAPH_POD" ]]; then
  echo "  - Memgraph Graph DB: $MEMGRAPH_POD"
fi
echo ""
echo "Next Steps:"
echo "  1. Test API: kubectl port-forward svc/$CHART_NAME 8000:80"
echo "  2. View docs: http://localhost:8000/docs"
echo "  3. Check logs: kubectl logs -f deployment/$CHART_NAME"
echo ""
echo "For more information:"
echo "  - User Guide: docs/USER_GUIDE.md"
echo "  - Integration: docs/INTEGRATION.md"
echo "=============================================================="
