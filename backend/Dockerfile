FROM python:3.11-slim

WORKDIR /app

# pyrage e psycopg2-binary vem como wheels -> sem toolchain de compilacao.
# O backend NAO precisa dos binarios age/minisign: cifra via pyrage (em memoria)
# e nunca decifra nem assina (isso e do agente e da ferramenta offline).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY app ./app
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

# roda como usuario nao-root (hardening)
RUN useradd -r -u 10001 appuser
USER appuser

EXPOSE 8000
CMD ["./entrypoint.sh"]
