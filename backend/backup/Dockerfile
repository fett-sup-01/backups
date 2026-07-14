# Sidecar de backup: pg_dump/pg_restore (postgres-client) + age (cifra) + rclone (offsite).
FROM postgres:16

RUN apt-get update \
 && apt-get install -y --no-install-recommends age rclone ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY pg_backup.sh pg_restore.sh entrypoint-cron.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/pg_backup.sh /usr/local/bin/pg_restore.sh /usr/local/bin/entrypoint-cron.sh

ENTRYPOINT ["/usr/local/bin/entrypoint-cron.sh"]
