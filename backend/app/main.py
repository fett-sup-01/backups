import datetime as dt
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import retencao
from .auth import seed_admin
from .database import SessionLocal
from .routers import (
    admin,
    auth,
    client_config,
    enrollment,
    heartbeat,
    inventario,
    painel,
    runs,
    updates,
)
from .settings import settings

# Fail-closed: em prod, recusa subir com segredos padrao/fracos (ver settings).
_problemas = settings.problemas_prod()
if _problemas:
    raise RuntimeError(
        "Config de producao insegura (APP_ENV=prod):\n - " + "\n - ".join(_problemas)
    )


def _purge_loop():
    """Job da retencao automatica (doc 16): a cada 10 min checa a politica e roda a
    limpeza se `auto_limpeza` estiver ligada e ja passou `intervalo_horas` da ultima."""
    while True:
        time.sleep(600)
        try:
            with SessionLocal() as db:
                cfg = retencao.get_config(db)
                if not cfg.auto_limpeza:
                    continue
                agora = dt.datetime.now(dt.timezone.utc)
                venceu = cfg.ultima_limpeza is None or \
                    (agora - cfg.ultima_limpeza) >= dt.timedelta(hours=cfg.intervalo_horas)
                if venceu:
                    retencao.limpar(db, cfg)
        except Exception:
            pass  # nunca derruba o processo por um erro no job de limpeza


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema via Alembic no entrypoint (alembic upgrade head); aqui so semeia o admin.
    with SessionLocal() as db:
        seed_admin(db)
    threading.Thread(target=_purge_loop, daemon=True).start()
    yield


app = FastAPI(
    title="Backups Backend",
    version="0.1.0",
    lifespan=lifespan,
    # /docs, /redoc e /openapi.json ficam OFF em prod (nao expor o schema).
    docs_url="/docs" if settings.expose_docs else None,
    redoc_url="/redoc" if settings.expose_docs else None,
    openapi_url="/openapi.json" if settings.expose_docs else None,
)

# CORS so quando ha origens configuradas (em prod, mesma origem via nginx = sem CORS).
if settings.cors_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/health")
def health():
    return {"status": "ok"}


for _mod in (auth, enrollment, client_config, heartbeat, runs, inventario, admin, painel):
    app.include_router(_mod.router)

# updates expoe dois routers (admin e cliente)
app.include_router(updates.admin_router)
app.include_router(updates.client_router)
