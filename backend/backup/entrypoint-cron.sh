#!/usr/bin/env bash
# Loop agendador do backup (sidecar). Roda o pg_backup.sh a cada BACKUP_INTERVAL_SEC.
set -u
INTERVAL="${BACKUP_INTERVAL_SEC:-86400}"   # 1x/dia
echo "[backup-cron] intervalo=${INTERVAL}s · remote=${RCLONE_REMOTE:-<vazio>}"
# nao roda um dump imediato na subida por padrao (evita duplicar em restart);
# ligue BACKUP_ON_START=1 se quiser um dump ao iniciar.
if [ "${BACKUP_ON_START:-0}" = "1" ]; then /usr/local/bin/pg_backup.sh || echo "[backup-cron] primeiro dump falhou"; fi
while :; do
  sleep "$INTERVAL"
  /usr/local/bin/pg_backup.sh || echo "[backup-cron] dump falhou (segue no proximo ciclo)"
done
