#!/usr/bin/env bash
# Backup do backend (doc 13): pg_dump -Fc -> cifra (age) -> envia para FORA da VPS
# (rclone) -> retencao. O backup nao pode morrer junto com o servidor.
#
# Cifra para um par age DEDICADO de backup (BACKUP_AGE_RECIPIENT). A privada
# correspondente mora no 1Password e so e usada no restore (nunca aqui).
#
# Env: PGHOST PGUSER PGDATABASE PGPASSWORD
#      BACKUP_DIR (/backups) · BACKUP_AGE_RECIPIENT (age1... ; vazio = sem cifra)
#      RCLONE_REMOTE (ex: b2:bucket/pasta ; vazio = nao envia p/ fora)
#      RETENTION_KEEP (14) · AGE_BIN (age)
set -euo pipefail

: "${PGHOST:=db}" "${PGUSER:=backup}" "${PGDATABASE:=backup}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_KEEP="${RETENTION_KEEP:-14}"
RECIP="${BACKUP_AGE_RECIPIENT:-}"
AGE_BIN="${AGE_BIN:-age}"

mkdir -p "$BACKUP_DIR"
TS=$(date +%Y%m%d-%H%M%S)
BASE="$BACKUP_DIR/pgbackup-${PGDATABASE}-${TS}"

echo "[backup] pg_dump ${PGDATABASE}@${PGHOST}"
if [ -n "$RECIP" ]; then
  FILE="${BASE}.dump.age"
  pg_dump -Fc -h "$PGHOST" -U "$PGUSER" "$PGDATABASE" | "$AGE_BIN" -r "$RECIP" > "$FILE"
else
  echo "[backup] AVISO: BACKUP_AGE_RECIPIENT vazio -> dump SEM cifra (nao recomendado)"
  FILE="${BASE}.dump"
  pg_dump -Fc -h "$PGHOST" -U "$PGUSER" "$PGDATABASE" > "$FILE"
fi

SIZE=$(stat -c%s "$FILE")
if [ "$SIZE" -le 0 ]; then echo "[backup] ERRO: dump vazio"; rm -f "$FILE"; exit 1; fi
echo "[backup] gravado $(basename "$FILE") (${SIZE} bytes)"

# envio OFFSITE (o ponto central: o backup vive fora da VPS)
if [ -n "${RCLONE_REMOTE:-}" ]; then
  echo "[backup] upload -> ${RCLONE_REMOTE}"
  rclone copy "$FILE" "$RCLONE_REMOTE"
  rclone delete --min-age "${RETENTION_KEEP}d" "$RCLONE_REMOTE" 2>/dev/null || true
else
  echo "[backup] AVISO: RCLONE_REMOTE vazio -> dump ficou SO na VPS (configure o offsite!)"
fi

# retencao local
ls -1t "$BACKUP_DIR"/pgbackup-"${PGDATABASE}"-* 2>/dev/null | tail -n +$((RETENTION_KEEP + 1)) | xargs -r rm -f
echo "[backup] ok"
