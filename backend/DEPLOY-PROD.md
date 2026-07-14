# Deploy de produção (simples, http://IP:8080)

Sobe banco + API + painel num comando. Testado end-to-end (login, criar e excluir cliente).

## No servidor (VPS zerado)

1. Copie o projeto para o VPS (git clone ou scp). Precisa das pastas
   `backend/`, `frontend/`, `deploy/` e os arquivos `agente.py` / `backup.py`.

2. Crie o arquivo de segredos `backend/.env.prod`. **Ele NÃO vai no git** (está no
   `.gitignore`), então crie direto no servidor. Use o conteúdo que já foi gerado
   (mesmos segredos do `.env.prod` local) ou gere novos:

   ```bash
   cd backend
   cp .env.prod.example .env.prod
   # edite e troque os segredos:
   #   JWT_SECRET         -> openssl rand -hex 32
   #   ADMIN_PASSWORD     -> openssl rand -base64 15   (min 12 chars)
   #   POSTGRES_PASSWORD  -> openssl rand -base64 24   (e replique no DATABASE_URL)
   #   RECOVERY_AGE_PUBKEY-> age-keygen -o recovery.key ; guarde a PRIVADA fora do servidor
   ```

3. Suba:

   ```bash
   cd backend
   docker compose -f docker-compose.prod.yml up -d --build
   ```

4. Acesse `http://IP-DO-SERVIDOR:8080` e entre com `admin` / (ADMIN_PASSWORD do .env.prod).
   O schema é migrado sozinho na subida (alembic upgrade head).

## Comandos úteis

```bash
# logs
docker compose -f docker-compose.prod.yml logs -f api

# recriar só o painel (após mudar o frontend)
docker compose -f docker-compose.prod.yml up -d --build --force-recreate web

# parar tudo (mantém os dados)
docker compose -f docker-compose.prod.yml down

# ZERAR tudo, inclusive o banco (apaga os dados!)
docker compose -f docker-compose.prod.yml down -v

# ver clientes no banco
docker compose -f docker-compose.prod.yml exec -T db \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select nome,status from clientes order by id;"'
```

## Notas

- Só a porta 8080 (painel) fica exposta; Postgres e API ficam na rede interna do compose.
- Sem TLS aqui. Para HTTPS/domínio (Let's Encrypt) use `docker-compose.prod.tls.yml`.
- A tabela é `clientes` (não `clients`): esta é a versão do código deste repositório.
- Excluir um cliente no painel apaga a linha e todo o histórico (cascade). Se a
  máquina ainda tiver o agente rodando, ela apenas recebe 401 nos heartbeats — não
  volta a aparecer sozinha (para removê-la de vez, desinstale o agente na máquina).
```
