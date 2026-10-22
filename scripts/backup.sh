#!/bin/sh
# Backup: Postgres (custom-format dump) + object storage (tar.gz with sha256 manifest).
#   scripts/backup.sh                         # dev stack
#   COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod" scripts/backup.sh
# Output: backups/<UTC timestamp>/{db.dump,objects.tar.gz,SHA256SUMS}. Copy the folder off-site.
set -eu
COMPOSE=${COMPOSE:-docker compose}
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT=backups/$TS
mkdir -p "$OUT"
$COMPOSE exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$OUT/db.dump"
$COMPOSE exec -T api sh -c 'python -m app.backup_storage export /tmp/objects.tar.gz >/tmp/objects.json && cat /tmp/objects.tar.gz && rm /tmp/objects.tar.gz' > "$OUT/objects.tar.gz"
( cd "$OUT" && sha256sum db.dump objects.tar.gz > SHA256SUMS )
echo "backup written to $OUT ($(du -sh "$OUT" | cut -f1))"
