#!/bin/sh
# Restaure une sauvegarde.
#   ./deploy/backup/restore.sh <fichier.sql.gz>               -> restaure DANS users_db (remplace les données)
#   ./deploy/backup/restore.sh <fichier.sql.gz> <base_test>   -> test de restauration dans une base jetable
set -eu

FILE="${1:?Usage: restore.sh <fichier.sql.gz> [base_cible]}"

read_env() {
  value=""
  if [ -f .env.docker ]; then
    value=$(grep -E "^$1=" .env.docker | tail -n 1 | cut -d= -f2- || true)
  fi
  echo "${value:-$2}"
}

DB_NAME=$(read_env DB_NAME users_db)
DB_USER=$(read_env DB_USER postgres)
CONTAINER="${DB_CONTAINER:-s2-users-db}"
TARGET="${2:-$DB_NAME}"

[ -f "$FILE" ] || { echo "Fichier introuvable : $FILE" >&2; exit 1; }

if [ "$TARGET" != "$DB_NAME" ]; then
  docker exec "$CONTAINER" psql -U "$DB_USER" -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='$TARGET'" | grep -q 1 \
    || docker exec "$CONTAINER" createdb -U "$DB_USER" "$TARGET"
fi

gunzip -c "$FILE" | docker exec -i "$CONTAINER" psql -U "$DB_USER" -d "$TARGET" -v ON_ERROR_STOP=1 -q

echo "Restauration terminée dans la base '$TARGET'."
echo "Utilisateurs restaurés :"
docker exec "$CONTAINER" psql -U "$DB_USER" -d "$TARGET" -tc "SELECT count(*) FROM users_user;"
