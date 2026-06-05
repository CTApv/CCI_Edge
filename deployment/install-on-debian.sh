#!/bin/sh
set -eu

APP_ROOT="/opt/pv-edge-manager"
BACKEND_ROOT="$APP_ROOT/backend"
WEB_ROOT="/var/www/pv-edge-manager"
DEPLOY_TMP="/tmp/pv-edge-manager-deploy"
SERVICE_USER="pv-edge-manager"
SERVICE_FILE="/etc/systemd/system/pv-edge-manager-backend.service"
NGINX_SITE="/etc/nginx/sites-available/pv-edge-manager"
NGINX_SITE_ENABLED="/etc/nginx/sites-enabled/pv-edge-manager"
POLKIT_RULE="/etc/polkit-1/rules.d/49-pv-edge-manager-networkmanager.rules"

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y python3-pip python3-venv nginx

if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --user-group --shell /usr/sbin/nologin "$SERVICE_USER"
fi

if getent group dialout >/dev/null 2>&1; then
    usermod -aG dialout "$SERVICE_USER"
fi

mkdir -p "$APP_ROOT" "$WEB_ROOT"
rm -rf "$BACKEND_ROOT"
tar -xzf "$DEPLOY_TMP/backend.tar.gz" -C "$APP_ROOT"

rm -rf "$WEB_ROOT"/*
tar -xzf "$DEPLOY_TMP/frontend-dist.tar.gz" --strip-components=1 -C "$WEB_ROOT"
tar -xzf "$DEPLOY_TMP/deployment.tar.gz" -C "$DEPLOY_TMP"

python3 -m venv "$BACKEND_ROOT/.venv"
"$BACKEND_ROOT/.venv/bin/pip" install --upgrade pip
"$BACKEND_ROOT/.venv/bin/pip" install -r "$BACKEND_ROOT/requirements.txt"

install -m 0644 "$DEPLOY_TMP/deployment/pv-edge-manager-backend.service" "$SERVICE_FILE"
install -m 0644 "$DEPLOY_TMP/deployment/pv-edge-manager-nginx.conf" "$NGINX_SITE"
install -m 0644 "$DEPLOY_TMP/deployment/pv-edge-manager-networkmanager.rules" "$POLKIT_RULE"
ln -sf "$NGINX_SITE" "$NGINX_SITE_ENABLED"
rm -f /etc/nginx/sites-enabled/default

chown -R "$SERVICE_USER:$SERVICE_USER" "$BACKEND_ROOT"
chmod -R u+rwX,go+rX "$WEB_ROOT"

nginx -t
systemctl daemon-reload
systemctl enable --now pv-edge-manager-backend
systemctl restart nginx
