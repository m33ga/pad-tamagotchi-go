#!/opt/patroni/bin/python
"""Patroni post-bootstrap callback. Identifiers/passwords are never shell-expanded."""
import os
import sys

import psycopg2
from psycopg2 import sql


def bootstrap(connection, env: dict[str, str]) -> None:
    connection.autocommit = True
    with connection.cursor() as cursor:
        for role, password in (
            (env['POSTGRES_USER'], env['POSTGRES_PASSWORD']),
            ('analytics_reader', env['ANALYTICS_READER_PASSWORD']),
            ('monitoring', env['POSTGRES_EXPORTER_PASSWORD']),
        ):
            cursor.execute('SELECT 1 FROM pg_roles WHERE rolname = %s', (role,))
            if cursor.fetchone() is None:
                cursor.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %s').format(sql.Identifier(role)), (password,))
        cursor.execute(sql.SQL('ALTER ROLE analytics_reader SET default_transaction_read_only = on'))
        cursor.execute('GRANT pg_monitor TO monitoring')
        cursor.execute('SELECT 1 FROM pg_database WHERE datname = %s', (env['POSTGRES_DB'],))
        if cursor.fetchone() is None:
            cursor.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(sql.Identifier(env['POSTGRES_DB']), sql.Identifier(env['POSTGRES_USER'])))
        # Reader receives SELECT only on the analytics views granted by service migrations.
        cursor.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO analytics_reader, monitoring').format(sql.Identifier(env['POSTGRES_DB'])))


if __name__ == '__main__':
    # Patroni supplies the URL and a PGPASSFILE for the superuser connection.
    connection = psycopg2.connect(sys.argv[1])
    try:
        bootstrap(connection, dict(os.environ))
    finally:
        connection.close()
