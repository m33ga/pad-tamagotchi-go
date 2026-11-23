#!/bin/sh
set -eu
umask 077
install -d -o postgres -g postgres -m 700 "$PGDATA" /run/patroni
exec gosu postgres python /usr/local/bin/configure.py
