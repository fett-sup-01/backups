from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..auth import (
    create_access_token,
    current_user,
    hash_password,
    require_papel,
    verify_password,
)
from ..database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    login: str
    senha: str


class TokenResponse(BaseModel):
    access_token: str
    papel: str


class UsuarioCreate(BaseModel):
    login: str
    senha: str
    papel: str = "operador"


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.Usuario).filter_by(login=req.login).first()
    if user is None or not verify_password(req.senha, user.senha_hash):
        raise HTTPException(status_code=401, detail="credenciais invalidas")
    return TokenResponse(access_token=create_access_token(user.login, user.papel), papel=user.papel)


@router.get("/me")
def me(user: models.Usuario = Depends(current_user)):
    return {"login": user.login, "papel": user.papel}


@router.post("/usuarios")
def criar_usuario(
    req: UsuarioCreate,
    _: models.Usuario = Depends(require_papel("admin")),
    db: Session = Depends(get_db),
):
    """So admin cria usuarios."""
    if db.query(models.Usuario).filter_by(login=req.login).first():
        raise HTTPException(status_code=409, detail="login ja existe")
    db.add(
        models.Usuario(login=req.login, senha_hash=hash_password(req.senha), papel=req.papel)
    )
    db.commit()
    return {"ok": True, "login": req.login, "papel": req.papel}
