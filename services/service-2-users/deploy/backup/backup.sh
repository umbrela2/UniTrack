#!/bin/sh
# Sauvegarde de users_db (FC6) - à lancer depuis la racine du service.
# Cron quotidien : 0 2 * * * cd /opt/unitrack/service-2-users && ./deploy/backup/backup.sh >> backups/backup.log 2>&1
set -eu

read_env() {  # $1 = nom de la variable dans .env.docker, $2 = valeur par défaut
  value=""
  if [ -f .env.docker ]; then
    value=$(grep -E "^$1=" .env.docker | tail -n 1 | cut -d= -f2- || true)
  fi
  echo "${value:-$2}"
}

DB_NAME=$(read_env DB_NAME users_db)
DB_USER=$(read_env DB_USER postgres)
CONTAINER="${DB_CONTAINER:-s2-users-db}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP_DAYS="${KEEP_DAYS:-7}"

mkdir -p "$BACKUP_DIR"
FILE="$BACKUP_DIR/${DB_NAME}_$(date +%Y%m%d_%H%M%S).sql.gz"

docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" --clean --if-exists --no-owner | gzip > "$FILE"

# vérification : archive valide et non vide
if ! gzip -t "$FILE" 2>/dev/null || [ "$(wc -c < "$FILE")" -lt 1024 ]; then
  echo "ERREUR : sauvegarde invalide, fichier supprimé." >&2
  rm -f "$FILE"
  exit 1
fi

# rétention
find "$BACKUP_DIR" -name "${DB_NAME}_*.sql.gz" -mtime +"$KEEP_DAYS" -delete

echo "$(date '+%F %T') OK : $FILE ($(wc -c < "$FILE") octets)"
