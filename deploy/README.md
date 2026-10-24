# Deployment

- **API, admin portal, and console:** `.github/workflows/deploy.yml` runs after `CI` passes on `main` (or by hand from the Actions tab). It builds the portal and the console, copies `apps/api` and `packages/catalog` to the server, installs Python packages, migrates the control and tenant databases, restarts `ai-pos-api`, waits for `/health`, and only then replaces the portal and console files. The console is at `/admin74246/`.
- **POS installer:** `.github/workflows/release-pos.yml` builds the Windows installers when a `v*.*.*` tag is pushed, attaches the `.exe` and `.msi` to a GitHub Release, and copies them to the server so Super Admins can download them from the portal's **Downloads** page.

Server layout:

| Path | Contents |
| --- | --- |
| `/opt/ai-pos/apps/api` | API code (synced by CI), `.venv`, and `storage/` (never touched by CI) |
| `/opt/ai-pos/.env.production` | API secrets (never touched by CI) |
| `/opt/ai-pos/packages/catalog` | seed data read by `app/seed.py` |
| `/opt/ai-pos/downloads/pos/<version>` | POS installers and `manifest.json`, published by the release workflow (`DOWNLOADS_DIR`) |
| `/var/www/ai-pos-admin` | built admin portal |
| `/var/www/ai-pos-console` | built console, served at `/admin74246/` |

## First-time server setup

1. **Oracle Cloud:** add ingress rules for TCP 80 and 443 from `0.0.0.0/0` to the subnet's Security List (or the instance's NSG).
2. **Address:** there is no domain yet. Use the VM's public IP. The portal and API are `http://<public-ip>/` (port 80). When a domain exists later, point it at this same IP and add TLS.
3. **Packages, firewall, systemd, nginx, sudoers:**

   ```bash
   scp -r deploy ubuntu@<server>:~/deploy
   ssh ubuntu@<server> 'sudo bash ~/deploy/server-setup.sh'
   ```

   The script is safe to re-run. nginx serves HTTP on port 80 immediately. When `/etc/letsencrypt/live/axizpos.com/fullchain.pem` and `privkey.pem` are already on the host, the same script also listens on 443 for `axizpos.com` and `www.axizpos.com`. The key is not copied into the repository. A host without those files keeps serving HTTP only.

4. **PostgreSQL:** the tenancy CLI creates one database per store, so the user needs `CREATEDB`.

   ```bash
   sudo -u postgres psql -c "CREATE USER ai_pos_user WITH PASSWORD '<strong password>' CREATEDB;"
   sudo -u postgres psql -c "ALTER ROLE ai_pos_user CREATEDB;"
   sudo -u postgres psql -c "CREATE DATABASE ai_pos_db OWNER ai_pos_user;"
   sudo -u postgres psql -c "CREATE DATABASE qios_control OWNER ai_pos_user;"
   ```

5. **Backend env file:** generate it on your own machine, so the secrets never pass through CI:

   ```bash
   node scripts/generate-secrets.mjs --env production
   ```

   `.env.production` at the repo root is the file the API reads. `DATABASE_URL` and `CONTROL_DATABASE_URL` are already set for Postgres on the VM (`ai_pos_db` and `qios_control` on localhost). Run the generator to replace the remaining `change-me` secrets; it does not touch the database URLs. Replace every `YOUR_VM_PUBLIC_IP` with the VM's public address. `TENANT_BASE_DOMAINS`, `TENANT_PUBLIC_URL_TEMPLATE`, and `PUBLIC_BASE_URL` must all use that IP, over `http://`. Leave `DEFAULT_TENANT` unset and `SIGNUP_ENABLED=false`. Then copy it up and lock it down:

   ```bash
   scp .env.production ubuntu@<server>:/opt/ai-pos/.env.production
   ssh ubuntu@<server> 'chmod 600 /opt/ai-pos/.env.production'
   ```

   Keep a copy somewhere safe. Rotating `ENCRYPTION_SECRET` or `PIN_SALT` later makes stored IMEIs and PINs unusable.

6. **TLS:** `axizpos.com` already has a certificate at `/etc/letsencrypt/live/axizpos.com/`. Re-running `server-setup.sh` enables it. Do not run Certbot again, and do not copy `privkey.pem` off the server. Port 80 keeps serving the site and `/.well-known/acme-challenge/` so renewal still works. After HTTPS answers, a redirect can be added on the port 80 server; leave it off until `https://axizpos.com` is reachable, including through the Oracle Cloud security list.

## GitHub setup

1. **Deploy key:** create a key used only by CI, on the server:

   ```bash
   ssh-keygen -t ed25519 -f ~/gh-deploy -N "" -C "github-deploy"
   cat ~/gh-deploy.pub >> ~/.ssh/authorized_keys
   cat ~/gh-deploy        # copy into the SSH_KEY secret, then: rm ~/gh-deploy ~/gh-deploy.pub
   ```

2. **Environment:** Settings, Environments, New environment `production`. Optionally add yourself as a required reviewer so each deploy waits for approval.
3. **Secrets** on the `production` environment:

   | Secret | Value |
   | --- | --- |
   | `SSH_HOST` | server public IP |
   | `SSH_USER` | `ubuntu` |
   | `SSH_KEY` | private key from step 1 |
   | `SSH_KNOWN_HOSTS` | output of `ssh-keyscan <server>` run from your machine |

## First deploy and first store

1. Actions, **Deploy**, Run workflow. It creates the control database schema (`app.tenancy.cli init`) on its first run.
2. Create a store:

   ```bash
   cd /opt/ai-pos/apps/api
   APP_ENV=production .venv/bin/python -m app.tenancy.cli create client1 --name "Client One"
   ```

   The portal is then at `http://<public-ip>/`. Sign in with store code `client1` and the Super Admin from `ADMIN_*` in `/opt/ai-pos/.env.production`.

## Releasing the POS installer

1. Set the new version in `apps/desktop/src-tauri/tauri.conf.json` (and `Cargo.toml`), commit, and push.
2. Tag and push: `git tag v0.2.0 && git push origin v0.2.0`. The workflow fails if the tag and `tauri.conf.json` disagree.
3. The workflow attaches the installers to the GitHub Release and copies them to `/opt/ai-pos/downloads/pos/<version>/` on the server. Every store's Super Admin then sees the new version under **Administration → Downloads** in the portal (also linked from Registers), with the SHA-256 of each file. Earlier versions stay listed.
4. The installers are unsigned, so Windows SmartScreen warns on first install until a code-signing certificate is added to the workflow.

Running **Release POS** by hand from the Actions tab builds the installers as a workflow artifact without creating a release or publishing them.

To publish an installer built elsewhere, copy it into `/opt/ai-pos/downloads/pos/<version>/` (for example `0.2.0`). A `manifest.json` is optional; without one the API computes the hashes itself.

## Operations

```bash
sudo systemctl status ai-pos-api
journalctl -u ai-pos-api -f
cd /opt/ai-pos/apps/api && APP_ENV=production .venv/bin/python -m app.tenancy.cli list
```

To roll back, re-run **Deploy** from the Actions tab on an earlier successful run. Migrations are not reversed automatically.
