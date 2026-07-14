from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .settings import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    # v1: create_all para subir a espinha. Migracoes com Alembic entram como
    # proximo passo (o schema ainda vai crescer com dashboard/updates).
    from . import models  # noqa: F401  -- registra os modelos no metadata
    Base.metadata.create_all(bind=engine)
