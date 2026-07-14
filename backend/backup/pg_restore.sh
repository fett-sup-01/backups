#!/usr/bin/env bash
# Restore do backend (doc 13/16). Decifra (age) e restaura no Postgres alvo.
# Plano de desastre = "subir tudo de novo": Postgres novo + este restore.
#
# Uso: pg_restore.sh <arquivo(.dump.age|.dump)> --force
#
# Env: PGHOST PGUSER PGDATABASE PGPASSWORD
#      BACKUP_AGE_KEY (identidade age de backup, vinda do 1Password) · AGE_BIN
set -euo pipefail

FILE="${1:?uso: pg_restore.sh <arquivo> --force}"
FORCE="${2:-}"
: "${PGHOST:=db}" "${PGUSER:=backup}" "${PGDATABASE:=backup}"
AGE_BIN="${AGE_BIN:-age}"
KEY="${BACKUP_AGE_KEY:-}"

echo "[restore] alvo: ${PGDATABASE}@${PGHOST}  <-  $(basename "$FILE")"
if [ "$FORCE" != "--force" ]; then
  echo "[restore] isto SOBRESCREVE objetos do banco alvo. Repita com --force para confirmar."
  exit 1
fi

decode() {
  case "$FILE" in
    *.age)
      if [ -z "$KEY" ]; then echo "[restore] ERRO: BACKUP_AGE_KEY (identidade) necessaria para decifrar"; exit 1; fi
      "$AGE_BIN" -d -i "$KEY" "$FILE"
      ;;
    *) cat "$FILE" ;;
  esac
}

# --clean --if-exists: derruba objetos antigos antes de recriar (idempotente).
decode | pg_restore --clean --if-exists --no-owner -h "$PGHOST" -U "$PGUSER" -d "$PGDATABASE"
echo "[restore] concluido. Confira: SELECT count(*) FROM clientes;"
