"""Auth do dashboard -> backend: usuario interno com papeis (doc 7).

Camada separada do token Bearer do cliente (security.py) e da cripto age. Aqui e
sessao de operador humano: senha bcrypt + JWT HS256.
"""

import datetime as dt

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .settings import settings

_bearer = HTTPBearer(auto_error=True)


def hash_password(senha: str) -> str:
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(senha: str, senha_hash: str) -> bool:
    try:
        return bcrypt.checkpw(senha.encode("utf-8"), senha_hash.encode("ascii"))
    except ValueError:
        return False


def create_access_token(login: str, papel: str) -> str:
    agora = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": login,
        "papel": papel,
        "iat": agora,
        "exp": agora + dt.timedelta(minutes=settings.jwt_expire_min),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def current_user(
    cred: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> models.Usuario:
    try:
        payload = jwt.decode(cred.credentials, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="sessao invalida ou expirada")
    user = db.query(models.Usuario).filter_by(login=payload.get("sub")).first()
    if user is None:
        raise HTTPException(status_code=401, detail="usuario nao existe mais")
    return user


def require_papel(*papeis: str):
    """Dependencia que exige um dos papeis dados (vazio = qualquer usuario logado)."""

    def _dep(user: models.Usuario = Depends(current_user)) -> models.Usuario:
        if papeis and user.papel not in papeis:
            raise HTTPException(status_code=403, detail="papel sem permissao para esta acao")
        return user

    return _dep


def seed_admin(db: Session) -> None:
    """Cria o admin inicial se nao houver nenhum usuario (idempotente)."""
    if db.query(models.Usuario).first() is not None:
        return
    db.add(
        models.Usuario(
            login=settings.admin_login,
            senha_hash=hash_password(settings.admin_password),
            papel="admin",
        )
    )
    db.commit()
