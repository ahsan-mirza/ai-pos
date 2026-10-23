#!/usr/bin/env bash
# One-time (and re-runnable) setup of an Ubuntu 24.04 server for the API and admin portal.
#   scp -r deploy ubuntu@<server>:~/deploy && ssh ubuntu@<server> 'sudo bash ~/deploy/server-setup.sh'
# Installs system packages once. Routine deploys only sync code, pip-install the API, migrate, and restart.
# This host does not run the register: that is a Windows installer published by the release workflow.
# Postgres users, /opt/ai-pos/.env.production, and tenants stay manual (deploy/README.md).
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo." >&2
  exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_USER="${SUDO_USER:-ubuntu}"
APP_ROOT=/opt/ai-pos
WEB_ROOT=/var/www/ai-pos-admin

echo "==> Packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update
# Node.js 20 from NodeSource already includes npm. Ubuntu's npm package conflicts with it.
apt-get install -y \
  git rsync curl build-essential python3.12-venv python3-dev \
  postgresql postgresql-contrib nginx certbot netfilter-persistent iptables-persistent \
  nodejs
if ! command -v npm >/dev/null; then
  echo "Node.js is installed without npm. Install Node.js 20 from NodeSource; it includes npm." >&2
  exit 1
fi

echo "==> Firewall (Oracle images reject everything but SSH by default)"
for port in 80 443; do
  if ! iptables -C INPUT -p tcp -m state --state NEW --dport "$port" -j ACCEPT 2>/dev/null; then
    iptables -I INPUT 6 -p tcp -m state --state NEW --dport "$port" -j ACCEPT
  fi
done
netfilter-persistent save

echo "==> Directories"
mkdir -p "$APP_ROOT/apps/api" "$APP_ROOT/packages" "$APP_ROOT/downloads/pos" "$WEB_ROOT"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_ROOT" "$WEB_ROOT"

if [[ ! -x "$APP_ROOT/apps/api/.venv/bin/python" ]]; then
  echo "==> Python virtual environment"
  sudo -u "$DEPLOY_USER" python3.12 -m venv "$APP_ROOT/apps/api/.venv"
  sudo -u "$DEPLOY_USER" "$APP_ROOT/apps/api/.venv/bin/pip" install -q --upgrade pip
fi

echo "==> PM2 (API and admin portal; systemd no longer binds port 8000)"
if ! command -v pm2 >/dev/null; then
  npm install -g pm2
fi
systemctl disable --now ai-pos-api 2>/dev/null || true
pm2 startup systemd -u "$DEPLOY_USER" --hp "/home/$DEPLOY_USER" --service-name "pm2-$DEPLOY_USER"

echo "==> sudoers (CI may reload nginx, nothing else)"
SUDOERS=/etc/sudoers.d/ai-pos-deploy
cat > "$SUDOERS.tmp" <<EOF
$DEPLOY_USER ALL=(root) NOPASSWD: /usr/bin/systemctl reload nginx
EOF
chmod 440 "$SUDOERS.tmp"
visudo -cf "$SUDOERS.tmp"
mv "$SUDOERS.tmp" "$SUDOERS"

echo "==> nginx (HTTP on the public IP; TLS waits until a domain exists)"
cp "$HERE/nginx/ai-pos.conf" /etc/nginx/sites-available/ai-pos.conf
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/ai-pos.conf /etc/nginx/sites-enabled/ai-pos.conf
nginx -t
systemctl reload nginx

echo
echo "Done. Next: Postgres user + qios_control, $APP_ROOT/.env.production, first deploy, tenants."
