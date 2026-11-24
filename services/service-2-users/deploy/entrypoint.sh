#!/bin/sh
set -e

if [ "$RUN_MIGRATIONS" = "True" ]; then
  echo ">> migrate"
  python manage.py migrate --noinput
fi

if [ "$CONSUL_REGISTER" = "True" ]; then
  echo ">> enregistrement dans Consul"
  python manage.py consul_register || echo "!! Consul indisponible : enregistrement ignoré"
fi

exec "$@"
