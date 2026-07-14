# Backend — Gerenciamento de Backup em Frota

Espinha do backend central (doc `arquitetura.md`, seções 6/7/13): FastAPI + Postgres
em Docker Compose. Modelo **pull**, só HTTPS de saída no cliente.

## Subir (dev)

```bash
cp .env.example .env   # ajuste RECOVERY_AGE_PUBKEY (a privada mora no 1Password)
docker compose up --build -d
curl localhost:8010/health          # {"status":"ok"}
open http://localhost:8010/docs     # Swagger
```

- API em `localhost:8010` (8000/8001/8080/8081 ocupados no host).
- Postgres em `localhost:55432` (útil p/ `psql`/`pg_dump`).

## O que já existe nesta fase (fundação)

- **Modelo de dados** (doc 6): `clientes`, `configs` (versionada), `client_secrets`,
  `runs`, `inventarios`, `comandos`, `updates`, `usuarios`, `enrollment_tokens`.
- **Cripto de segredos** (`app/crypto.py`, doc 5): `age` via `pyrage`, cifra **só**
  para 2 destinatários (cliente + recuperação), fail-closed sem a chave de recuperação.
  Formato do campo cifrado: `age:<base64(ciphertext)>` inline (pendência #2 decidida).
- **Endpoints do cliente** (Bearer por cliente, com escopo):
  `POST /enroll`, `GET /config/{cliente}`, `POST /heartbeat`, `GET /comando/{cliente}`,
  `POST /runs`, `POST /inventario`.
- **Superfície admin/seed** sob `/admin` (**sem auth ainda** — próximo passo):
  criar cliente + token de enrollment, salvar config+segredos, listar frota, enfileirar comando.

## Ainda NÃO nesta fase (próximos passos)

- Auth de usuário interno do dashboard (sessão/JWT + papéis) — hoje `/admin` é aberto.
- Migrações Alembic (hoje `create_all` na subida).
- Rollout/canary de update e verificação `minisign` no agente (doc 10, pendência #4).
- Retenção/limpeza de `runs`/`inventarios` (pendência #5) e `pg_dump` p/ fora (doc 13).
- **Mudança mínima mapeada no `bkp.py`**: ecoar `_config_versao` (vindo do `.conf`) no
  payload de `/runs`, para o dashboard distinguir config *pendente* vs *aplicada* (doc 8).
  O backend já aceita esse campo (opcional). O resto do `bkp.py` não muda.

## Produção (doc 13)

Hardening já embutido: `APP_ENV=prod` **recusa subir** com segredos padrão/fracos
(`problemas_prod` em `settings.py`), `/docs`+`/openapi` ficam **off**, CORS só se
`CORS_ORIGINS` for setado, container da API roda **não-root** (uid 10001), Postgres e
API **não** ficam expostos no host, e o nginx tem TLS + HSTS + `server_tokens off`.

```bash
# na VPS, no diretorio backend/
cp .env.prod.example .env          # preencha com segredos FORTES (ver comentarios do arquivo)
#   JWT_SECRET: openssl rand -hex 32   ·   ADMIN_PASSWORD/POSTGRES_PASSWORD: openssl rand -base64
#   RECOVERY_AGE_PUBKEY e MINISIGN_PUBLIC_KEY: as PUBLICAS (privadas ficam no 1Password)
#   DOMAIN: dominio do dashboard (aponte o DNS para a VPS antes)

# 1) sobe sem TLS ainda, para o certbot resolver o desafio ACME
docker compose -f docker-compose.prod.yml up -d --build db api web

# 2) emite o certificado (uma vez); depois o servico certbot renova sozinho
docker compose -f docker-compose.prod.yml run --rm certbot certonly \
  --webroot -w /var/www/certbot -d "$DOMAIN" --agree-tos -m voce@empresa.com -n

# 3) recarrega o nginx com o cert e sobe o certbot de renovacao
docker compose -f docker-compose.prod.yml up -d
```

## Backup e restore do backend (doc 13/16)

O backend é o ponto único de falha; o plano de desastre é "subir tudo de novo". O
serviço `backup` (sidecar em `backup/`) roda `pg_dump -Fc`, **cifra com `age`** (par
dedicado de backup) e **envia para fora da VPS via `rclone`**, com retenção. Validado
com roundtrip real (dump → cifra → decifra → restore → contagens conferem).

**Setup (uma vez):**
```bash
age-keygen -o backup.key                 # PRIVADA -> 1Password (usada só no restore)
grep 'public key' backup.key             # PUBLICA -> BACKUP_AGE_RECIPIENT no .env
cp backup/rclone.conf.example backup/rclone.conf   # configure o remote offsite (rclone config)
# no .env: BACKUP_AGE_RECIPIENT, RCLONE_REMOTE, RETENTION_KEEP, BACKUP_INTERVAL_SEC
docker compose -f docker-compose.prod.yml up -d --build backup
```

**Backup manual (sob demanda):**
```bash
docker compose -f docker-compose.prod.yml exec backup pg_backup.sh
```

**Restore (desastre — máquina nova):**
```bash
# 1) suba o stack novo (db/api/web) com o .env
# 2) traga a PRIVADA de backup do 1Password para a máquina (temporário) e o dump do offsite:
rclone copy "$RCLONE_REMOTE/pgbackup-...dump.age" ./
# 3) restaure para dentro do container db:
docker compose -f docker-compose.prod.yml run --rm \
  -e PGDATABASE=$POSTGRES_DB -e BACKUP_AGE_KEY=/keys/backup.key \
  -v $PWD/backup.key:/keys/backup.key:ro -v $PWD:/backups \
  --entrypoint pg_restore.sh backup /backups/pgbackup-...dump.age --force
# 4) confira: docker compose ... exec db psql -U $POSTGRES_USER -d $POSTGRES_DB -c 'select count(*) from clientes;'
# 5) apague a backup.key da máquina.
```

## Retenção / limpeza (doc 16)

Política editável em **Configurações** no dashboard (ou via `GET/PUT /admin/retencao`):
dias a reter para `runs` e `inventarios`, **mínimo por cliente** (nunca apaga as N
rodadas mais recentes de cada cliente) e limpeza automática (intervalo em horas,
rodada por um job em background na API). Botão “Limpar agora” executa na hora
(`POST /admin/retencao/limpar`). Validado: filtro por idade + proteção do mínimo por
cliente. Retenção dos **dumps** de backup é separada (`RETENTION_KEEP`, ver acima).
