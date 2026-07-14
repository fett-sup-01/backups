#!/bin/sh
# Migra o schema antes de servir (fonte unica de schema = Alembic).
set -e
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
