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
CONSOLE_ROOT=/var/www/ai-pos-console
SITE_ROOT=/var/www/ai-pos-site

echo "==> Packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update
# Node.js 20 from NodeSource already includes npm. Ubuntu's npm package conflicts with it.
apt-get install -y \
  git rsync curl build-essential python3.12-venv python3-dev \
  postgresql postgresql-contrib nginx certbot netfilter-persistent iptables-persistent \
  redis-server nodejs
if ! command -v npm >/dev/null; then
  echo "Node.js is installed without npm. Install Node.js 20 from NodeSource; it includes npm." >&2
  exit 1
fi

echo "==> Redis (localhost only; port 6379 stays closed)"
systemctl enable --now redis-server

echo "==> Firewall (Oracle images reject everything but SSH by default)"
for port in 80 443; do
  if ! iptables -C INPUT -p tcp -m state --state NEW --dport "$port" -j ACCEPT 2>/dev/null; then
    iptables -I INPUT 6 -p tcp -m state --state NEW --dport "$port" -j ACCEPT
  fi
done
netfilter-persistent save

echo "==> Directories"
mkdir -p "$APP_ROOT/apps/api" "$APP_ROOT/packages" "$APP_ROOT/downloads/pos" "$WEB_ROOT" "$CONSOLE_ROOT" "$SITE_ROOT"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_ROOT" "$WEB_ROOT" "$CONSOLE_ROOT" "$SITE_ROOT"

if [[ ! -x "$APP_ROOT/apps/api/.venv/bin/python" ]]; then
  echo "==> Python virtual environment"
  sudo -u "$DEPLOY_USER" python3.12 -m venv "$APP_ROOT/apps/api/.venv"
  sudo -u "$DEPLOY_USER" "$APP_ROOT/apps/api/.venv/bin/pip" install -q --upgrade pip
fi

echo "==> PM2 (API, admin portal, and console; systemd no longer binds port 8000)"
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

echo "==> nginx (HTTP, plus HTTPS when the existing certificate is on this host)"
install -d /etc/nginx/snippets /var/www/html
SITE=/etc/nginx/sites-available/ai-pos.conf
SHARED=/etc/nginx/snippets/ai-pos.shared.conf
APEX=/etc/nginx/snippets/ai-pos.apex.conf
HTTPS_SNIPPET=/etc/nginx/snippets/ai-pos.https.conf
backup="$(mktemp -d)"
[[ -f "$SITE" ]] && cp "$SITE" "$backup/site"
[[ -f "$SHARED" ]] && cp "$SHARED" "$backup/shared"
[[ -f "$APEX" ]] && cp "$APEX" "$backup/apex"
[[ -f "$HTTPS_SNIPPET" ]] && cp "$HTTPS_SNIPPET" "$backup/https"
cp "$HERE/nginx/ai-pos.shared.conf" "$SHARED"
cp "$HERE/nginx/ai-pos.apex.conf" "$APEX"
CERT=/etc/letsencrypt/live/axizpos.com/fullchain.pem
KEY=/etc/letsencrypt/live/axizpos.com/privkey.pem
if [[ -f "$CERT" && -f "$KEY" ]]; then
  echo "Using the certificate already at $CERT"
  cp "$HERE/nginx/ai-pos.https.conf" "$HTTPS_SNIPPET"
else
  echo "Certificate files are not on this host; port 80 stays up and port 443 is not configured."
  printf '%s\n' '# No certificate on this host yet. Port 443 is configured once the files exist.' \
    > "$HTTPS_SNIPPET"
fi
cp "$HERE/nginx/ai-pos.conf" "$SITE"
rm -f /etc/nginx/sites-enabled/default
ln -sf "$SITE" /etc/nginx/sites-enabled/ai-pos.conf
# Another enabled site for the same names would make nginx reject the config.
disabled=()
for site in /etc/nginx/sites-enabled/*; do
  [[ "$(basename "$site")" == "ai-pos.conf" ]] && continue
  [[ -f "$site" ]] || continue
  if grep -qE 'server_name[[:space:]]+[^;]*axizpos\.com' "$site"; then
    echo "Disabling $site because it also serves axizpos.com"
    mv "$site" "$backup/$(basename "$site")"
    disabled+=("$(basename "$site")")
  fi
done
if ! nginx -t; then
  echo "nginx config test failed; the running site is unchanged." >&2
  [[ -f "$backup/site" ]] && cp "$backup/site" "$SITE" || rm -f "$SITE"
  [[ -f "$backup/shared" ]] && cp "$backup/shared" "$SHARED" || rm -f "$SHARED"
  [[ -f "$backup/apex" ]] && cp "$backup/apex" "$APEX" || rm -f "$APEX"
  [[ -f "$backup/https" ]] && cp "$backup/https" "$HTTPS_SNIPPET" || rm -f "$HTTPS_SNIPPET"
  for name in "${disabled[@]}"; do
    [[ -f "$backup/$name" ]] && mv "$backup/$name" "/etc/nginx/sites-enabled/$name"
  done
  rm -rf "$backup"
  exit 1
fi
rm -rf "$backup"
systemctl reload nginx

echo
echo "Done. Next: Postgres user + qios_control, $APP_ROOT/.env.production, first deploy, tenants."
