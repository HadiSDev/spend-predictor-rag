#!/usr/bin/env bash
# Rename a development PostgreSQL database and its owning role in place.
#
# The dev stack was initialised as `spend_predictor` (database, role and
# password). The product is now Steelyard, and a fresh stack initialises as
# `steelyard` — but POSTGRES_* only applies to an empty data directory, so an
# existing ./pgdata keeps the old names until this script renames them. Nothing
# is dumped or re-created: every table, row and alembic revision stays put.
#
# The role is RENAMED, not re-created. POSTGRES_USER is the cluster's bootstrap
# superuser: it owns `postgres` and the template databases and cannot be
# dropped, so "create the new role, reassign, drop the old one" fails at the
# drop. A session also cannot rename its own role, so a temporary superuser does
# the renaming and is removed afterwards.
#
# Usage:
#   scripts/rename-dev-db.sh                       # spend_predictor -> steelyard
#   scripts/rename-dev-db.sh --from steelyard --to spend_predictor   # roll back
#   scripts/rename-dev-db.sh --container NAME      # a container outside compose
#
# Stop the web API, the runners and anything else connected first: a database
# cannot be renamed while sessions are open on it, and the script refuses
# rather than terminating them for you. Idempotent: run it twice and the second
# run reports there is nothing to do.
set -euo pipefail

FROM=spend_predictor
TO=steelyard
CONTAINER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from) FROM="$2"; shift 2 ;;
    --to) TO="$2"; shift 2 ;;
    --container) CONTAINER="$2"; shift 2 ;;
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

TMP="${TO}_rename_tmp"

# psql inside the Postgres container, over its local socket (trust auth in the
# official image). -v ON_ERROR_STOP makes any failed statement fail the script.
psql_as() {
  local user="$1" db="$2"; shift 2
  if [[ -n "$CONTAINER" ]]; then
    docker exec -i "$CONTAINER" psql -X -q -v ON_ERROR_STOP=1 -U "$user" -d "$db" "$@"
  else
    docker compose exec -T postgres psql -X -q -v ON_ERROR_STOP=1 -U "$user" -d "$db" "$@"
  fi
}

# Whichever superuser exists answers catalog questions.
probe_user() {
  for u in "$FROM" "$TO" "$TMP"; do
    if psql_as "$u" postgres -tAc "select 1" >/dev/null 2>&1; then echo "$u"; return; fi
  done
  echo "no superuser named $FROM, $TO or $TMP can connect — is the right container running?" >&2
  exit 1
}

ADMIN="$(probe_user)"
exists() { # exists <catalog> <name-column> <name>
  [[ "$(psql_as "$ADMIN" postgres -tAc "select count(*) from $1 where $2 = '$3'")" == "1" ]]
}

if ! exists pg_roles rolname "$FROM" && exists pg_roles rolname "$TO" \
   && ! exists pg_database datname "$FROM" && exists pg_database datname "$TO"; then
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
-- Renaming a role clears an MD5 password; set it explicitly either way.
alter role "$TO" password '$TO';
alter database "$FROM" rename to "$TO";
SQL
psql_as "$TO" postgres -c "drop role \"$TMP\""

echo "Done. Point DATABASE_URL at postgresql://$TO:$TO@<host>:<port>/$TO"
