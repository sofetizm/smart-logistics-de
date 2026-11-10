#!/bin/sh
set -eu
if [ ! -s /run/credentials/postgres_password ]; then
    umask 077
    head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' > /run/credentials/postgres_password
fi
export POSTGRES_PASSWORD_FILE=/run/credentials/postgres_password
exec /usr/local/bin/docker-entrypoint.sh "$@"
