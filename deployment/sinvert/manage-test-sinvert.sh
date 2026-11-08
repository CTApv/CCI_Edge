#!/bin/sh
# Isolated test stack; never stops production containers or removes volumes.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
COMPOSE_FILE="$SCRIPT_DIR/compose.test-sinvert.yml"
ENV_FILE="${TEST_SINVERT_ENV_FILE:-$SCRIPT_DIR/test.compose.env}"
ACTION="${1:-help}"

if [ "$ACTION" = help ]; then
    echo "Usage: sh $0 check|start|status|stop"
    echo "First copy test.compose.env.example to test.compose.env."
    exit 0
fi
command -v docker >/dev/null 2>&1 || { echo "Docker is required on the IOT2050." >&2; exit 1; }
docker compose version >/dev/null
[ -f "$ENV_FILE" ] || { echo "Copy $SCRIPT_DIR/test.compose.env.example to $ENV_FILE first." >&2; exit 1; }

compose() {
    docker compose --project-name pv-guardian-test-sinvert --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

case "$ACTION" in
    check)
        compose config --quiet
        echo "TEST SINVERT configuration is valid. No containers changed."
        ;;
    start)
        case "$(uname -m)" in
            aarch64|arm64) ;;
            *) echo "These release images target Linux ARM64 / IOT2050." >&2; exit 1 ;;
        esac
        compose config --quiet
        # Refuse a port collision with an unrelated service. Existing containers
        # from this same stack are allowed for an in-place test update.
        for key in TEST_SINVERT_WEB_PORT TEST_SINVERT_API_PORT; do
            port=$(awk -F= -v key="$key" '$1 == key {gsub(/\r/, "", $2); print $2}' "$ENV_FILE" | tail -n 1)
            case "$port" in ''|*[!0-9]*) echo "Set a numeric $key in $ENV_FILE." >&2; exit 1 ;; esac
            if command -v ss >/dev/null 2>&1 && ss -ltnH | awk '{print $4}' | grep -Eq ":${port}$"; then
                if ! compose ps --format json | grep -q "${port}"; then
                    echo "Port $port is already used by another service. Choose alternative test ports; no service stopped." >&2
                    exit 1
                fi
            fi
        done
        compose pull
        compose up -d --no-build --wait --wait-timeout 180
        compose ps
        echo "TEST SINVERT started. Existing PV Guardian services and volumes were not modified."
        ;;
    status)
        compose ps
        ;;
    stop)
        compose down
        echo "TEST SINVERT stopped. Test data volumes are retained."
        ;;
    *) echo "Unknown action: $ACTION" >&2; exit 1 ;;
esac
