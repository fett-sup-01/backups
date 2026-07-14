#!/usr/bin/env bash
# Instalador do agente de backup em frota (doc 11) — modelo curl | bash.
# Nao precisa copiar nada: baixa o agente do proprio backend.
#
#   curl -fsSL https://SEU_HOST/install.sh | sudo bash -s -- \
#        --backend https://SEU_HOST --token TOKEN_EFEMERO [--dir /opt/backup]
#
# O unico segredo por cliente e o token efemero (uso unico, expira apos o enrollment).
set -euo pipefail

BACKEND=""; TOKEN=""; INSTALL_DIR="/opt/backup"
while [ $# -gt 0 ]; do
  case "$1" in
    --backend) BACKEND="$2"; shift 2;;
    --token)   TOKEN="$2";   shift 2;;
    --dir)     INSTALL_DIR="$2"; shift 2;;
    *) echo "arg desconhecido: $1"; exit 2;;
  esac
done
[ -n "$BACKEND" ] && [ -n "$TOKEN" ] || {
  echo "uso: curl -fsSL <HOST>/install.sh | sudo bash -s -- --backend <HOST> --token <TOKEN> [--dir DIR]"; exit 2; }
[ "$(id -u)" = "0" ] || { echo "rode como root (sudo)"; exit 1; }

BACKEND="${BACKEND%/}"
API="$BACKEND/api"        # o nginx do backend faz proxy de /api -> FastAPI
DIST="$BACKEND/agent"     # arquivos do agente servidos pelo backend

echo "==> dependencias"
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -qq || true
  apt-get install -y -qq curl age minisign rsync cifs-utils ntfs-3g sshpass rclone python3 >/dev/null 2>&1 || \
    echo "   (aviso: apt nao instalou tudo; garanta age/minisign/rsync/python3 manualmente)"
fi
for bin in curl python3 age rsync; do
  command -v "$bin" >/dev/null 2>&1 || echo "   FALTA: $bin (o agente precisa dele)"
done

echo "==> baixando o agente para $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
curl -fsSL "$DIST/agente.py" -o "$INSTALL_DIR/agente.py"
curl -fsSL "$DIST/backup.py" -o "$INSTALL_DIR/backup.py"
chmod 0755 "$INSTALL_DIR/agente.py" "$INSTALL_DIR/backup.py"
# chave publica de assinatura (verifica updates). Best-effort: sem ela, o agente
# apenas nao aplica updates (fail-safe).
curl -fsSL "$DIST/minisign.pub" -o "$INSTALL_DIR/minisign.pub" 2>/dev/null && chmod 0644 "$INSTALL_DIR/minisign.pub" || \
  echo "   (sem minisign.pub servido; updates ficam desabilitados ate coloca-lo em $INSTALL_DIR)"

echo "==> enrollment (gera par de chaves age; troca o token efemero pelo permanente)"
python3 "$INSTALL_DIR/agente.py" enroll --backend "$API" --token "$TOKEN"

echo "==> units do systemd"
for u in backup-agente.service backup-run.service backup-run.timer; do
  curl -fsSL "$DIST/systemd/$u" | sed "s#__INSTALL_DIR__#$INSTALL_DIR#g" > "/etc/systemd/system/$u"
done
systemctl daemon-reload
systemctl enable --now backup-agente.service
systemctl enable --now backup-run.timer

echo "==> primeiro pull da config"
python3 "$INSTALL_DIR/agente.py" pull || echo "   (sem config ainda? preencha no dashboard; o proximo heartbeat puxa)"

echo "==> pronto."
systemctl --no-pager --lines=3 status backup-agente.service || true
