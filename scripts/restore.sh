#!/bin/sh
# Restore drill / disaster recovery.
#   scripts/restore.sh backups/<ts>                 # restore test: DB into a scratch database "restore_check",
#                                                   # archive verified, row counts compared — production data untouched
#   scripts/restore.sh backups/<ts> --apply         # disaster recovery: replace the live DB and re-upload objects
set -eu
COMPOSE=${COMPOSE:-docker compose}
DIR=${1:?backup folder}
MODE=${2:-check}
( cd "$DIR" && sha256sum -c SHA256SUMS )
TARGET=restore_check
[ "$MODE" = "--apply" ] && TARGET='"$POSTGRES_DB"'
if [ "$MODE" = "--apply" ]; then
  $COMPOSE stop api worker
  $COMPOSE exec -T db sh -c 'dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
else
  $COMPOSE exec -T db sh -c 'dropdb -U "$POSTGRES_USER" --if-exists restore_check && createdb -U "$POSTGRES_USER" restore_check'
fi
$COMPOSE exec -T db sh -c "pg_restore -U \"\$POSTGRES_USER\" -d $TARGET --no-owner" < "$DIR/db.dump"
$COMPOSE exec -T api sh -c 'cat > /tmp/objects.tar.gz' < "$DIR/objects.tar.gz"
if [ "$MODE" = "--apply" ]; then
  $COMPOSE start api worker
  $COMPOSE exec -T api python -m app.backup_storage import /tmp/objects.tar.gz
  echo "restored into the live stack"
else
  $COMPOSE exec -T api python -m app.backup_storage verify /tmp/objects.tar.gz
  for t in users projects design_versions documents source_assets external_product_records audit_events; do
    a=$($COMPOSE exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -tAc 'select count(*) from $t'")
    b=$($COMPOSE exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -d restore_check -tAc 'select count(*) from $t'")
    printf '%-26s live=%-6s restored=%-6s %s\n' "$t" "$a" "$b" "$([ "$a" -ge "$b" ] && echo ok || echo MISMATCH)"
  done
  $COMPOSE exec -T db sh -c 'dropdb -U "$POSTGRES_USER" restore_check'
fi
