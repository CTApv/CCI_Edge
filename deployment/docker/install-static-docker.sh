#!/bin/sh
set -eu

DOCKER_VERSION="${DOCKER_VERSION:-29.5.2}"
COMPOSE_VERSION="${COMPOSE_VERSION:-5.1.4}"
DOCKER_SHA256="${DOCKER_SHA256:-d1d9cb857c32c596ea96a9ca6b25d13621a97c83511e667868a33a320b2a707f}"
COMPOSE_SHA256="${COMPOSE_SHA256:-d4fb48b72857810314d3ee77123c89954101844efa4788031221f4c370495946}"

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PACKAGE_DIR="${1:-$SCRIPT_DIR}"
DOCKER_ARCHIVE="${PACKAGE_DIR}/docker-${DOCKER_VERSION}.tgz"
COMPOSE_BINARY="${PACKAGE_DIR}/docker-compose-linux-aarch64"
WORK_DIR="${PACKAGE_DIR}/docker-${DOCKER_VERSION}-extract"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root." >&2
  exit 1
fi

if [ ! -f "$DOCKER_ARCHIVE" ]; then
  echo "Missing Docker archive: $DOCKER_ARCHIVE" >&2
  exit 1
fi

if [ ! -f "$COMPOSE_BINARY" ]; then
  echo "Missing Docker Compose binary: $COMPOSE_BINARY" >&2
  exit 1
fi

printf '%s  %s\n' "$DOCKER_SHA256" "$DOCKER_ARCHIVE" | sha256sum -c -
printf '%s  %s\n' "$COMPOSE_SHA256" "$COMPOSE_BINARY" | sha256sum -c -

rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"
tar -xzf "$DOCKER_ARCHIVE" -C "$WORK_DIR"

install -m 0755 "$WORK_DIR"/docker/* /usr/local/bin/
mkdir -p /usr/local/lib/docker/cli-plugins
install -m 0755 "$COMPOSE_BINARY" /usr/local/lib/docker/cli-plugins/docker-compose
install -m 0644 "$SCRIPT_DIR/docker-static.service" /etc/systemd/system/docker.service

systemctl daemon-reload
systemctl enable --now docker.service

docker version
docker compose version
