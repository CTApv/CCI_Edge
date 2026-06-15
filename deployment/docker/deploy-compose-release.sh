#!/bin/sh
set -eu

BASE_DIR="${PV_EDGE_MANAGER_BASE_DIR:-/opt/pv-edge-manager-docker}"
ENV_DIR="${PV_EDGE_MANAGER_ENV_DIR:-/etc/pv-edge-manager}"
COMPOSE_ENV="${PV_EDGE_MANAGER_COMPOSE_ENV:-$ENV_DIR/compose.env}"
APP_ENV="${PV_EDGE_MANAGER_APP_ENV:-$ENV_DIR/app.env}"
REGISTRY_ENV="${PV_EDGE_MANAGER_REGISTRY_ENV:-$ENV_DIR/registry.env}"
RELEASE_ARCHIVE="${1:-${PV_EDGE_MANAGER_RELEASE_ARCHIVE:-}}"
RELEASE_ID="${PV_EDGE_MANAGER_RELEASE_ID:-}"
RELEASE_TAG="${PV_EDGE_MANAGER_RELEASE_TAG:-}"
RELEASE_VERSION="${PV_EDGE_MANAGER_RELEASE_VERSION:-}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root." >&2
  exit 1
fi

if [ -z "$RELEASE_ARCHIVE" ]; then
  echo "Usage: $0 /path/to/release.tar" >&2
  exit 1
fi

if [ ! -f "$RELEASE_ARCHIVE" ]; then
  echo "Release archive not found: $RELEASE_ARCHIVE" >&2
  exit 1
fi

if [ -z "$RELEASE_ID" ]; then
  RELEASE_ID="$(basename "$RELEASE_ARCHIVE" .tar | tr -c 'A-Za-z0-9._-' '-')"
fi

RELEASE_DIR="$BASE_DIR/releases/$RELEASE_ID"
CURRENT_LINK="$BASE_DIR/current"
COMPOSE_ENV_BACKUP=""
PREVIOUS_TARGET=""
if [ -L "$CURRENT_LINK" ]; then
  PREVIOUS_TARGET="$(readlink "$CURRENT_LINK")"
fi

read_env_value() {
  key="$1"
  if [ -f "$COMPOSE_ENV" ]; then
    awk -F= -v key="$key" '$1 == key {print substr($0, length(key) + 2)}' "$COMPOSE_ENV" | tail -n 1
  fi
}

upsert_env_value() {
  key="$1"
  value="$2"
  escaped_value="$(printf '%s' "$value" | sed 's/[\/&]/\\&/g')"
  if grep -q "^$key=" "$COMPOSE_ENV"; then
    sed -i "s/^$key=.*/$key=$escaped_value/" "$COMPOSE_ENV"
  else
    printf '\n%s=%s\n' "$key" "$value" >> "$COMPOSE_ENV"
  fi
}

validate_release_tag() {
  tag="$1"
  case "$tag" in
    [A-Za-z0-9_]*)
      ;;
    *)
      return 1
      ;;
  esac
  case "$tag" in
    *[!A-Za-z0-9_.-]*)
      return 1
      ;;
  esac
  [ "${#tag}" -le 128 ]
}

if [ -z "$RELEASE_VERSION" ]; then
  case "$RELEASE_TAG" in
    v[0-9]*)
      RELEASE_VERSION="$RELEASE_TAG"
      ;;
  esac
fi

retag_image() {
  image_ref="$1"
  tag="$2"
  image_base="${image_ref%@*}"
  image_name="${image_base##*/}"
  case "$image_name" in
    *:*)
      image_base="${image_base%:*}"
      ;;
  esac
  printf '%s:%s\n' "$image_base" "$tag"
}

backup_compose_env() {
  if [ -z "$COMPOSE_ENV_BACKUP" ]; then
    COMPOSE_ENV_BACKUP="$COMPOSE_ENV.bak-$(date -u +%Y%m%d%H%M%S)"
    cp "$COMPOSE_ENV" "$COMPOSE_ENV_BACKUP"
  fi
}

restore_compose_env() {
  if [ -n "$COMPOSE_ENV_BACKUP" ] && [ -f "$COMPOSE_ENV_BACKUP" ]; then
    cp "$COMPOSE_ENV_BACKUP" "$COMPOSE_ENV"
  fi
}

http_ok() {
  url="$1"
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 5 "$url" >/dev/null
  elif command -v wget >/dev/null 2>&1; then
    wget -q -T 5 -O /dev/null "$url" >/dev/null
  else
    echo "curl or wget is required for health checks." >&2
    return 1
  fi
}

registry_login() {
  if [ "${PV_EDGE_MANAGER_SKIP_REGISTRY_LOGIN:-false}" = "true" ]; then
    return 0
  fi

  if [ ! -f "$REGISTRY_ENV" ]; then
    echo "Registry env file not found: $REGISTRY_ENV" >&2
    echo "Private GHCR packages require PV_EDGE_MANAGER_GHCR_USERNAME and PV_EDGE_MANAGER_GHCR_TOKEN." >&2
    return 1
  fi

  # shellcheck disable=SC1090
  . "$REGISTRY_ENV"

  if [ -z "${PV_EDGE_MANAGER_GHCR_USERNAME:-}" ] || [ -z "${PV_EDGE_MANAGER_GHCR_TOKEN:-}" ]; then
    echo "PV_EDGE_MANAGER_GHCR_USERNAME and PV_EDGE_MANAGER_GHCR_TOKEN are required in $REGISTRY_ENV." >&2
    return 1
  fi

  printf '%s' "$PV_EDGE_MANAGER_GHCR_TOKEN" \
    | docker login ghcr.io -u "$PV_EDGE_MANAGER_GHCR_USERNAME" --password-stdin >/dev/null
}

compose_file() {
  compose_path="$1"
  shift
  docker compose --env-file "$COMPOSE_ENV" -f "$compose_path" "$@"
}

compose_current() {
  compose_file "$CURRENT_LINK/docker-compose.yml" "$@"
}

compose_release() {
  compose_file "$RELEASE_DIR/docker-compose.yml" "$@"
}

rollback() {
  restore_compose_env
  if [ -n "$PREVIOUS_TARGET" ]; then
    echo "Health check failed. Rolling back to $PREVIOUS_TARGET." >&2
    ln -sfn "$PREVIOUS_TARGET" "$CURRENT_LINK.next"
    mv -Tf "$CURRENT_LINK.next" "$CURRENT_LINK"
    compose_current up -d --no-build --remove-orphans || true
  else
    echo "Health check failed and no previous release is available." >&2
  fi
}

restore_compose_env_on_error() {
  exit_status="$?"
  if [ "$exit_status" -ne 0 ]; then
    restore_compose_env || true
  fi
  trap - EXIT
  exit "$exit_status"
}

trap restore_compose_env_on_error EXIT

mkdir -p "$BASE_DIR/releases" "$ENV_DIR" "$RELEASE_DIR"
tar -xf "$RELEASE_ARCHIVE" -C "$RELEASE_DIR"

if [ ! -f "$COMPOSE_ENV" ]; then
  cp "$RELEASE_DIR/deployment/docker/production.compose.env.example" "$COMPOSE_ENV"
  chmod 0640 "$COMPOSE_ENV"
fi

if [ ! -f "$APP_ENV" ]; then
  cp "$RELEASE_DIR/deployment/docker/app.env.example" "$APP_ENV"
  chmod 0640 "$APP_ENV"
fi

DATA_DIR="$(read_env_value PV_EDGE_MANAGER_DATA_DIR || true)"
LOG_DIR="$(read_env_value PV_EDGE_MANAGER_LOG_DIR || true)"
mkdir -p "${DATA_DIR:-/var/lib/pv-edge-manager}" "${LOG_DIR:-/var/log/pv-edge-manager}"

if [ -n "$RELEASE_TAG" ]; then
  if ! validate_release_tag "$RELEASE_TAG"; then
    echo "Invalid PV_EDGE_MANAGER_RELEASE_TAG: $RELEASE_TAG" >&2
    exit 1
  fi

  CURRENT_BACKEND_IMAGE="$(read_env_value PV_EDGE_MANAGER_BACKEND_IMAGE || true)"
  CURRENT_WEB_IMAGE="$(read_env_value PV_EDGE_MANAGER_WEB_IMAGE || true)"
  if [ -z "$CURRENT_BACKEND_IMAGE" ] || [ -z "$CURRENT_WEB_IMAGE" ]; then
    echo "PV_EDGE_MANAGER_BACKEND_IMAGE and PV_EDGE_MANAGER_WEB_IMAGE are required in $COMPOSE_ENV." >&2
    exit 1
  fi

  backup_compose_env
  upsert_env_value PV_EDGE_MANAGER_BACKEND_IMAGE "$(retag_image "$CURRENT_BACKEND_IMAGE" "$RELEASE_TAG")"
  upsert_env_value PV_EDGE_MANAGER_WEB_IMAGE "$(retag_image "$CURRENT_WEB_IMAGE" "$RELEASE_TAG")"
fi

if [ -n "$RELEASE_VERSION" ]; then
  if ! validate_release_tag "$RELEASE_VERSION"; then
    echo "Invalid PV_EDGE_MANAGER_RELEASE_VERSION: $RELEASE_VERSION" >&2
    exit 1
  fi
  backup_compose_env
  upsert_env_value PV_EDGE_MANAGER_VERSION "$RELEASE_VERSION"
fi

if ! compose_release config >/tmp/pv-guardian-compose-config.yml; then
  restore_compose_env
  exit 1
fi

if [ "${PV_EDGE_MANAGER_SKIP_PULL:-false}" != "true" ]; then
  if ! registry_login; then
    restore_compose_env
    exit 1
  fi
  if ! compose_release pull; then
    restore_compose_env
    echo "Image pull failed. Check GHCR package permissions and $REGISTRY_ENV." >&2
    exit 1
  fi
fi

if [ "${PV_EDGE_MANAGER_WRITE_BUILD_METADATA:-true}" != "false" ]; then
  backup_compose_env
  upsert_env_value PV_EDGE_MANAGER_BUILD_COMMIT "${PV_EDGE_MANAGER_RELEASE_COMMIT:-$RELEASE_ID}"
  upsert_env_value PV_EDGE_MANAGER_BUILD_TIME "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [ -n "${PV_EDGE_MANAGER_RELEASE_LABEL:-}" ]; then
    upsert_env_value PV_EDGE_MANAGER_BUILD_LABEL "$PV_EDGE_MANAGER_RELEASE_LABEL"
  fi
fi

ln -sfn "releases/$RELEASE_ID" "$CURRENT_LINK.next"
mv -Tf "$CURRENT_LINK.next" "$CURRENT_LINK"

if ! compose_current up -d --no-build --remove-orphans; then
  rollback
  exit 1
fi

API_BIND="$(read_env_value PV_EDGE_MANAGER_API_BIND || true)"
WEB_BIND="$(read_env_value PV_EDGE_MANAGER_WEB_BIND || true)"
HEALTH_URL="${PV_EDGE_MANAGER_HEALTH_URL:-http://127.0.0.1:${API_BIND:-8000}/api/health}"
WEB_URL="${PV_EDGE_MANAGER_WEB_URL:-http://127.0.0.1:${WEB_BIND:-80}/}"

i=0
until http_ok "$HEALTH_URL" && http_ok "$WEB_URL"; do
  i=$((i + 1))
  if [ "$i" -ge "${PV_EDGE_MANAGER_HEALTH_RETRIES:-30}" ]; then
    rollback
    exit 1
  fi
  sleep "${PV_EDGE_MANAGER_HEALTH_INTERVAL_SECONDS:-2}"
done

compose_current ps
if [ -n "$RELEASE_TAG" ]; then
  echo "PV_GUARDIAN image tag $RELEASE_TAG is active."
fi
if [ -n "$RELEASE_VERSION" ]; then
  echo "PV_GUARDIAN app version $RELEASE_VERSION is active."
fi
echo "PV_GUARDIAN release $RELEASE_ID is healthy."
