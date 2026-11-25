#!/bin/sh
set -eu

: "${POSTGRES_DB:?}" "${POSTGRES_USER:?}" "${POSTGRES_PASSWORD:?}" "${ANALYTICS_READER_PASSWORD:?}"
case "$POSTGRES_USER" in
    patroni_admin|replicator|analytics_reader)
        echo "POSTGRES_USER conflicts with a PostgreSQL HA role" >&2
        exit 1
        ;;
esac

# Patroni supplies the connection string and PGPASSFILE.
exec psql -X --set ON_ERROR_STOP=1 "$1" <<'SQL'
\getenv db POSTGRES_DB
\getenv app_user POSTGRES_USER
\getenv app_password POSTGRES_PASSWORD
\getenv reader_password ANALYTICS_READER_PASSWORD

CREATE ROLE :"app_user" WITH LOGIN SUPERUSER PASSWORD :'app_password';
SELECT format('CREATE DATABASE %I OWNER %I', :'db', :'app_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'db') \gexec
ALTER DATABASE :"db" OWNER TO :"app_user";

CREATE ROLE analytics_reader WITH LOGIN PASSWORD :'reader_password';
ALTER ROLE analytics_reader SET default_transaction_read_only = on;
GRANT CONNECT ON DATABASE :"db" TO analytics_reader;
SQL
