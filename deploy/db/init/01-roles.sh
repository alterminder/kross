#!/usr/bin/env bash
# Runs INSIDE the db container on a fresh volume only (docker-entrypoint-initdb.d).
# Existing volumes never rerun init scripts: use provision-roles.sh on the host.
#
# Creates the runtime login and grants; the owner/bootstrap login and database
# already exist at this point (POSTGRES_USER / POSTGRES_DB).
set -euo pipefail

: "${POSTGRES_USER:?POSTGRES_USER not set}"
: "${POSTGRES_DB:?POSTGRES_DB not set}"
: "${POSTGRES_APP_PASSWORD:?POSTGRES_APP_PASSWORD not set}"
export NLAB_APP_PASSWORD="$POSTGRES_APP_PASSWORD"

psql --set=ON_ERROR_STOP=1 \
    --set=app_role=nlab_app \
    --set=owner_role="$POSTGRES_USER" \
    --set=db_name="$POSTGRES_DB" \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    < /usr/local/share/nlab/roles.sql
