#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-up}"
: "${KINLIN_DEPLOYMENT_ID:?Set KINLIN_DEPLOYMENT_ID before using dev.sh}"
: "${KINLIN_SECRETS_DIR:?Set KINLIN_SECRETS_DIR before using dev.sh}"
COMPOSE=(docker compose -f compose.yaml -f compose.dev.yaml)

case "$ACTION" in
  up|build|restart)
    python -m scripts.infra.preflight \
      --deployment-id "$KINLIN_DEPLOYMENT_ID" \
      --secrets-dir "$KINLIN_SECRETS_DIR" \
      --bind-address 127.0.0.1
    ;;
esac

case "$ACTION" in
  up)      "${COMPOSE[@]}" up -d --build --wait ;;
  down)    "${COMPOSE[@]}" down ;;
  build)   "${COMPOSE[@]}" build ;;
  restart) "${COMPOSE[@]}" down; "${COMPOSE[@]}" up -d --build --wait ;;
  logs)    "${COMPOSE[@]}" logs -f --tail=100 ;;
  *) echo "Usage: ./dev.sh {up|down|build|restart|logs}" >&2; exit 2 ;;
esac
