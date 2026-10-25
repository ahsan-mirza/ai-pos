# Deployment

- **API, admin portal, landing page, and console:** `.github/workflows/deploy.yml` runs after `CI` passes on `main` (or by hand from the Actions tab). It builds the portal, the marketing site, and the console, copies `apps/api` and `packages/catalog` to the server, installs Python packages, migrates the control and tenant databases, restarts `ai-pos-api`, waits for `/health`, and only then replaces the portal, landing page, and console files. `https://axizpos.com/` is the landing page. Sign-in is `https://axizpos.com/login` and signup is `https://axizpos.com/signup`. The console is at `/admin74246/`.
- **POS installer:** `.github/workflows/release-pos.yml` builds the Windows installers when a `v*.*.*` tag is pushed, attaches the `.exe` and `.msi` to a GitHub Release, and copies them to the server so Super Admins can download them from the portal's **Downloads** page.

Server layout:

| Path | Contents |
| --- | --- |
| `/opt/ai-pos/apps/api` | API code (synced by CI), `.venv`, and `storage/` (never touched by CI) |
| `/opt/ai-pos/.env.production` | API secrets (never touched by CI) |
| `/opt/ai-pos/packages/catalog` | seed data read by `app/seed.py` |
| `/opt/ai-pos/downloads/pos/<version>` | POS installers and `manifest.json`, published by the release workflow (`DOWNLOADS_DIR`) |
| `/var/www/ai-pos-admin` | built admin portal |
| `/var/www/ai-pos-site` | built landing page, served at `https://axizpos.com/` |
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

   On the public IP, the portal is at `http://<public-ip>/`. On `axizpos.com`, the landing page is `/` and sign-in is `/login`. Sign in with store code `client1` and the Super Admin from `ADMIN_*` in `/opt/ai-pos/.env.production`.

## Releasing the POS installer

1. Set the new version in `apps/desktop/VERSION` only, commit, and push. The release build copies that number into `package.json`, `tauri.conf.json`, and `Cargo.toml` before Tauri reads them.
2. Tag and push: `git tag v0.2.0 && git push origin v0.2.0`. The workflow fails if the tag and `apps/desktop/VERSION` disagree.
3. The workflow attaches the installers to the GitHub Release and copies them to `/opt/ai-pos/downloads/pos/<version>/` on the server. Every store's Super Admin then sees the new version under **Administration → Downloads** in the portal (also linked from Registers), with the SHA-256 of each file. Earlier versions stay listed.
4. The installers are unsigned, so Windows SmartScreen warns on first install until a code-signing certificate is added to the workflow.

Running **Release POS** by hand from the Actions tab builds the installers as a workflow artifact without creating a release or publishing them.

To publish an installer built elsewhere, copy it into `/opt/ai-pos/downloads/pos/<version>/` (for example `0.2.0`). A `manifest.json` is optional; without one the API computes the hashes itself.

## Shared operational database

New stores are rows in `DATABASE_URL`. The control database (`CONTROL_DATABASE_URL`, `qios_control`) still holds the tenant registry, operators, billing, and site settings. A tenant row with `data_plane=legacy` still opens the encrypted database URL. `shared` ignores that URL and uses `DATABASE_URL`.

The API process should connect as a role that does not own the tables and does not have `BYPASSRLS`. Alembic keeps using the owner role, which sets `app.bypass_rls` only while migrating. Create the application role once, then point `DATABASE_URL` at it:

```bash
sudo -u postgres psql -d ai_pos_db -c "CREATE ROLE ai_pos_app LOGIN PASSWORD '<strong password>';"
sudo -u postgres psql -d ai_pos_db -c "GRANT CONNECT ON DATABASE ai_pos_db TO ai_pos_app;"
sudo -u postgres psql -d ai_pos_db -c "GRANT USAGE ON SCHEMA public TO ai_pos_app;"
sudo -u postgres psql -d ai_pos_db -c "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ai_pos_app;"
sudo -u postgres psql -d ai_pos_db -c "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ai_pos_app;"
sudo -u postgres psql -d ai_pos_db -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ai_pos_app;"
```

Production Redis is the `redis-server` package on the API host. It listens on `127.0.0.1:6379` only; port 6379 is not opened in the firewall. `REDIS_URL=redis://127.0.0.1:6379/0` is required. Deploy adds that line to `/opt/ai-pos/.env.production` when it is missing. Cache misses fall through to PostgreSQL. Rate limits fail closed when Redis is down. Stock, payments, and the ledger are not cached.

nginx sets `Host` from the request host. The API resolves the store from `Host` or `X-Tenant-Domain` and does not trust `X-Forwarded-Host`. Keep the API bound so only nginx can reach it.

### Cutover

1. Back up the control database and every tenant database.
2. Deploy this code while every tenant is still `legacy`, and confirm registers and the portal still work.
3. Run `python -m app.tenancy.cli migrate-all` so `DATABASE_URL` and each legacy database are at head. Create `ai_pos_app`.
4. Freeze writes for one tenant. Run `python -m app.tenancy.cli merge-shared --tenant <slug>`, then the same command with `--commit`.
5. Read the JSON report. `--commit` sets `data_plane=shared` only when product counts, sale totals, tender totals, stock on hand, and customer balances match.
6. Smoke-test login, a sale, stock, and a console view of that tenant.
7. Repeat per tenant. Leave the legacy database in place until a later, explicit decision to drop it.
8. Before any sale is written on the shared database, rollback is `UPDATE tenants SET data_plane='legacy' WHERE slug='<slug>'`. After shared writes exist, restore the legacy backup instead of flipping the flag.

`merge-shared` does not drop a database and does not clear `database_url_encrypted`.

## Operations

```bash
sudo systemctl status ai-pos-api
journalctl -u ai-pos-api -f
cd /opt/ai-pos/apps/api && APP_ENV=production .venv/bin/python -m app.tenancy.cli list
```

To roll back, re-run **Deploy** from the Actions tab on an earlier successful run. Migrations are not reversed automatically.

## Search Console

The public site is `https://axizpos.com/`. Canonical URLs use that origin. `www.axizpos.com` serves the same files today; add the `https://axizpos.com` property in Google Search Console, not a localhost or staging host.

Verification is optional and is not configured in this repository. To add an HTML-tag token, set `VITE_GOOGLE_SITE_VERIFICATION` in the production build environment and redeploy the landing page. The token is written only into `<meta name="google-site-verification">`. Do not commit the token. This repository does not install an analytics tag.

After the property is verified, submit `https://axizpos.com/sitemap.xml`. The sitemap lists the homepage and the public industry pages. It does not list `/login`, `/signup`, or `/admin74246/`. The portal shell sends `noindex`. The console already sends `noindex`. `robots.txt` disallows `/admin74246/` and `/api/` and still allows the marketing pages and their CSS and JavaScript.

Search Console setup and indexing are manual. A deploy does not verify the property or submit the sitemap.
