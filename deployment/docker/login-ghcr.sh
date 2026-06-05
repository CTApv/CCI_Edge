#!/bin/sh
set -eu

ENV_FILE="${1:-${PV_EDGE_MANAGER_REGISTRY_ENV:-/etc/pv-edge-manager/registry.env}}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root." >&2
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "Registry env file not found: $ENV_FILE" >&2
  exit 1
fi

# shellcheck disable=SC1090
. "$ENV_FILE"

if [ -z "${PV_EDGE_MANAGER_GHCR_USERNAME:-}" ] || [ -z "${PV_EDGE_MANAGER_GHCR_TOKEN:-}" ]; then
  echo "PV_EDGE_MANAGER_GHCR_USERNAME and PV_EDGE_MANAGER_GHCR_TOKEN are required." >&2
  exit 1
fi

printf '%s' "$PV_EDGE_MANAGER_GHCR_TOKEN" \
  | docker login ghcr.io -u "$PV_EDGE_MANAGER_GHCR_USERNAME" --password-stdin
