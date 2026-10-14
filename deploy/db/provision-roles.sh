#!/usr/bin/env bash
# Create/refresh the runtime database login (nlab_app) on an existing database
# volume. The owner/bootstrap login (nlab) and all data are untouched.
#
# Usage (from the repository root, the directory holding compose.yml):
#   deploy/db/provision-roles.sh
#
# The password never appears in argv or logs: it travels as the first stdin
# line to the container shell, which exports it for psql's \getenv.
set -euo pipefail
umask 077

cd "$(dirname "$0")/../.."   # repository root

if [[ ! -f .env ]]; then
    echo "provision-roles.sh: no .env next to compose.yml; copy .env.example and fill it in first" >&2
    exit 1
fi

get_env() {
    local key=$1 line
    line=$(grep -E "^${key}=" .env | tail -n 1 || true)
    printf '%s' "${line#*=}"
}

app_role=${NLAB_APP_ROLE:-nlab_app}
owner_role=${NLAB_DB_OWNER:-nlab}
db_name=${POSTGRES_DB:-nlab}
app_password=$(get_env POSTGRES_APP_PASSWORD)

for id in "$app_role" "$owner_role" "$db_name"; do
    if [[ ! $id =~ ^[a-z_][a-z0-9_]*$ ]]; then
        echo "provision-roles.sh: invalid identifier '$id'" >&2
        exit 1
    fi
done
if [[ -z $app_password || $app_password == *CHANGE_ME* || $app_password == *change-me* ]]; then
    echo "provision-roles.sh: POSTGRES_APP_PASSWORD is unset or a placeholder; set it in .env first" >&2
    exit 1
fi

{
    printf '%s\n' "$app_password"
    cat deploy/db/roles.sql
} | docker compose exec -T db sh -c '
    IFS= read -r password || exit 1
    export NLAB_APP_PASSWORD="$password"
    exec psql --set=ON_ERROR_STOP=1 \
        --set=app_role="$1" --set=owner_role="$2" --set=db_name="$3" \
        --username "$2" --dbname "$3"
' sh "$app_role" "$owner_role" "$db_name" >/dev/null

echo "provision-roles.sh: runtime role '$app_role' provisioned on database '$db_name'."
