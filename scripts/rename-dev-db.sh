#!/usr/bin/env bash
# Rename a development PostgreSQL database and its owning role in place.
#
# Usage:
#   scripts/rename-dev-db.sh                       # spend_predictor -> steelyard
#   scripts/rename-dev-db.sh --from steelyard --to spend_predictor   # roll back
#   scripts/rename-dev-db.sh --container NAME      # a container outside compose
set -euo pipefail

FROM=spend_predictor
TO=steelyard
CONTAINER=""

usage() {
  sed -n '2,7p' "$0"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from)
      FROM="$2"
      shift 2
      ;;
    --to)
      TO="$2"
      shift 2
      ;;
    --container)
      CONTAINER="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

TMP="${TO}_rename_tmp"

psql_as() {
  local user="$1" db="$2"
  shift 2
  if [[ -n "$CONTAINER" ]]; then
    docker exec -i "$CONTAINER" psql -X -q -v ON_ERROR_STOP=1 -U "$user" -d "$db" "$@"
  else
    docker compose exec -T postgres psql -X -q -v ON_ERROR_STOP=1 -U "$user" -d "$db" "$@"
  fi
}

probe_user() {
  local candidate
  for candidate in "$FROM" "$TO" "$TMP"; do
    if psql_as "$candidate" postgres -tAc "select 1" >/dev/null 2>&1; then
      echo "$candidate"
      return
    fi
  done
  echo "no superuser named $FROM, $TO or $TMP can connect — is the right container running?" >&2
  exit 1
}

ADMIN="$(probe_user)"

exists() {
  local catalog="$1" column="$2" name="$3"
  [[ "$(psql_as "$ADMIN" postgres -tAc "select count(*) from $catalog where $column = '$name'")" == "1" ]]
}

already_renamed() {
  ! exists pg_roles rolname "$FROM" && exists pg_roles rolname "$TO" \
    && ! exists pg_database datname "$FROM" && exists pg_database datname "$TO"
}

if already_renamed; then
  if exists pg_roles rolname "$TMP"; then
    psql_as "$TO" postgres -c "drop role \"$TMP\""
  fi
  echo "Nothing to do: role and database are already named '$TO'."
  exit 0
fi

if ! exists pg_roles rolname "$FROM" || ! exists pg_database datname "$FROM"; then
  echo "Expected a role and a database named '$FROM'; found neither pair complete. Refusing." >&2
  exit 1
fi

if exists pg_roles rolname "$TO" || exists pg_database datname "$TO"; then
  echo "A role or database named '$TO' already exists beside '$FROM'. Refusing to merge them." >&2
  exit 1
fi

open_sessions="$(psql_as "$ADMIN" postgres -tAc \
  "select count(*) from pg_stat_activity where datname = '$FROM' and pid <> pg_backend_pid()")"
if [[ "$open_sessions" != "0" ]]; then
  echo "$open_sessions session(s) are connected to '$FROM'. Stop the web API, the runners" >&2
  echo "and any psql/IDE connections, then run this again." >&2
  exit 1
fi

echo "Renaming role and database '$FROM' -> '$TO'…"
if ! exists pg_roles rolname "$TMP"; then
  psql_as "$FROM" postgres -c "create role \"$TMP\" login superuser"
fi
psql_as "$TMP" postgres <<SQL
alter role "$FROM" rename to "$TO";
alter role "$TO" password '$TO';
alter database "$FROM" rename to "$TO";
SQL
psql_as "$TO" postgres -c "drop role \"$TMP\""

echo "Done. Point DATABASE_URL at postgresql://$TO:$TO@<host>:<port>/$TO"
