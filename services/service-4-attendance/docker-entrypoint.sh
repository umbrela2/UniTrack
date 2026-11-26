#!/bin/sh
set -e
# Seul le conteneur "api" applique les migrations (RUN_MIGRATIONS=1) ; on attend que PostgreSQL réponde.
if [ "$RUN_MIGRATIONS" = "1" ]; then
  until python manage.py migrate --noinput; do
    echo "PostgreSQL pas prêt, nouvelle tentative dans 3 s..."; sleep 3
  done
fi
exec "$@"
