#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# cleanup_dev.sh  —  Tear down the local Deep Research dev environment
#
# Stops and removes:
#   • Docker containers  (Redis + Mock MCP)
#   • Docker volumes     (redis_data)
#   • Docker networks    (created by docker-compose)
#   • Optional: .env.dev  (pass --all to also delete local config)
#
# Usage:
#   ./deep_research/cleanup_dev.sh            # stop containers + volumes
#   ./deep_research/cleanup_dev.sh --all      # also delete .env.dev
#   ./deep_research/cleanup_dev.sh --help
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.dev.yml"
REMOVE_ENV=false

# ── Argument parsing ──────────────────────────────────────────────────────────
for arg in "$@"; do
  case "$arg" in
    --all)   REMOVE_ENV=true ;;
    --help)
      echo "Usage: $(basename "$0") [--all] [--help]"
      echo ""
      echo "  --all   Also delete deep_research/.env.dev"
      echo "  --help  Show this message"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg"
      exit 1
      ;;
  esac
done

# ── Check docker-compose file exists ─────────────────────────────────────────
if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "✗ docker-compose.dev.yml not found at: $COMPOSE_FILE"
  exit 1
fi

# ── Stop + remove containers and volumes ─────────────────────────────────────
echo "Stopping Deep Research dev containers…"
docker compose -f "$COMPOSE_FILE" down --volumes --remove-orphans 2>&1 | sed 's/^/  /'
echo ""

# ── Verify containers are gone ────────────────────────────────────────────────
CONTAINERS=$(docker ps -a --filter "name=deep_research_" --format "{{.Names}}" 2>/dev/null || true)
if [[ -n "$CONTAINERS" ]]; then
  echo "Forcing removal of lingering containers:"
  echo "$CONTAINERS" | xargs -r docker rm -f
fi

# ── Remove local Redis data volume (belt-and-suspenders) ─────────────────────
VOLUME=$(docker volume ls -q --filter "name=deep_research_redis_data" 2>/dev/null || true)
if [[ -n "$VOLUME" ]]; then
  echo "Removing volume: $VOLUME"
  docker volume rm "$VOLUME" || true
fi

# ── Optional: remove .env.dev ─────────────────────────────────────────────────
if [[ "$REMOVE_ENV" == "true" ]]; then
  ENV_FILE="${SCRIPT_DIR}/.env.dev"
  if [[ -f "$ENV_FILE" ]]; then
    rm "$ENV_FILE"
    echo "Removed: $ENV_FILE"
  else
    echo ".env.dev not found — nothing to remove"
  fi
fi

echo ""
echo "✓ Deep Research dev environment cleaned up."
echo ""
echo "To rebuild: docker compose -f deep_research/docker-compose.dev.yml up -d"
