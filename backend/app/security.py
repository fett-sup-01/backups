"""Autenticacao cliente -> backend: Bearer por cliente, com escopo (doc 7).

Isto e 'quem esta pedindo', camada separada da cripto age ('quem consegue ler').
O token e um segredo de alta entropia; guardamos so o sha256 dele.
"""

import hashlib
import secrets as _secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import models
from .database import get_db

_bearer = HTTPBearer(auto_error=True)


def new_token() -> str:
    return _secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def current_client(
    cred: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> models.Cliente:
    cli = db.query(models.Cliente).filter_by(token_hash=hash_token(cred.credentials)).first()
    if cli is None:
        raise HTTPException(status_code=401, detail="token invalido")
    return cli
