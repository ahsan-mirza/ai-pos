#!/usr/bin/env bash
# Postgres is provisioned once on the server. Deploys do not create roles or databases.
# Schema changes run later as `python -m app.tenancy.cli init` and `migrate-all`.
echo "Postgres is already provisioned. Migrations run in the deploy install step."
exit 0
