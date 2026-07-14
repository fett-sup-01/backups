"""Auto-update do bkp.py (doc 10): assinatura minisign + canary + rollback.

Backend so *serve* a versao e a assinatura; a verificacao minisign e o gate de
--check acontecem no AGENTE, antes de aplicar. A chave privada de assinatura mora
no 1Password e nunca toca o servidor (doc 5.5).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..auth import require_papel
from ..database import get_db
from ..security import current_client
from ..versioning import maior, parse_versao


# ---- helper compartilhado com o heartbeat -------------------------------------
def update_para(db: Session, cli: models.Cliente) -> dict | None:
    """Update aplicavel a este cliente (grupo geral, ou canary se for cliente canary),
    mais novo que a versao de script que ele reporta. None se nao ha."""
    ups = db.query(models.Update).all()
    aplicaveis = [
        u for u in ups
        if u.grupo_rollout == "geral" or (u.grupo_rollout == "canary" and cli.canary)
    ]
    candidatas = [u for u in aplicaveis if maior(u.versao, cli.versao_script or "0")]
    if not candidatas:
        return None
    alvo = max(candidatas, key=lambda u: parse_versao(u.versao))
    return {"versao": alvo.versao, "arquivo": alvo.arquivo}


# ---- admin (dashboard) --------------------------------------------------------
admin_router = APIRouter(prefix="/admin", tags=["dashboard"], dependencies=[Depends(require_papel())])


class UpdateCreate(BaseModel):
    versao: str
    conteudo: str  # fonte do backup.py novo
    assinatura: str  # .minisig gerado offline (chave no 1Password)
    grupo_rollout: str = "canary"  # canary | geral
    arquivo: str = "backup.py"


@admin_router.get("/updates")
def listar_updates(db: Session = Depends(get_db)):
    """Versoes registradas + quantos clientes ja rodam cada versao (dashboard)."""
    ups = db.query(models.Update).order_by(models.Update.id.desc()).all()
    out = []
    for u in ups:
        n = db.query(models.Cliente).filter_by(versao_script=u.versao).count()
        out.append({
            "versao": u.versao, "grupo_rollout": u.grupo_rollout,
            "clientes_count": n, "criado_em": u.created_at.isoformat() if u.created_at else None,
        })
    return out


@admin_router.post("/updates")
def registrar_update(req: UpdateCreate, db: Session = Depends(get_db)):
    if req.grupo_rollout not in ("canary", "geral"):
        raise HTTPException(status_code=400, detail="grupo_rollout deve ser canary ou geral")
    if db.query(models.Update).filter_by(versao=req.versao).first():
        raise HTTPException(status_code=409, detail="versao ja registrada")
    db.add(models.Update(
        versao=req.versao, conteudo=req.conteudo, assinatura=req.assinatura,
        grupo_rollout=req.grupo_rollout, arquivo=req.arquivo,
    ))
    db.commit()
    return {"ok": True, "versao": req.versao, "grupo_rollout": req.grupo_rollout}


@admin_router.post("/updates/{versao}/promover")
def promover_update(versao: str, db: Session = Depends(get_db)):
    """Canary -> geral: libera a versao para toda a frota (doc 10)."""
    up = db.query(models.Update).filter_by(versao=versao).first()
    if up is None:
        raise HTTPException(status_code=404, detail="versao nao existe")
    up.grupo_rollout = "geral"
    db.commit()
    return {"ok": True, "versao": versao, "grupo_rollout": "geral"}


@admin_router.post("/clientes/{nome}/canary")
def set_canary(nome: str, ativo: bool = True, db: Session = Depends(get_db)):
    cli = db.query(models.Cliente).filter_by(nome=nome).first()
    if cli is None:
        raise HTTPException(status_code=404, detail="cliente nao existe")
    cli.canary = ativo
    db.commit()
    return {"ok": True, "nome": nome, "canary": ativo}


# ---- cliente (download) -------------------------------------------------------
client_router = APIRouter(tags=["cliente"])


@client_router.get("/update/{versao}")
def baixar_update(versao: str, cli: models.Cliente = Depends(current_client), db: Session = Depends(get_db)):
    """Devolve o bkp.py novo + a assinatura minisign. So serve se o rollout se
    aplica a este cliente (geral, ou canary se ele for canary)."""
    up = db.query(models.Update).filter_by(versao=versao).first()
    if up is None:
        raise HTTPException(status_code=404, detail="versao nao existe")
    if not (up.grupo_rollout == "geral" or (up.grupo_rollout == "canary" and cli.canary)):
        raise HTTPException(status_code=403, detail="update nao liberado para este cliente")
    return {"versao": up.versao, "arquivo": up.arquivo, "conteudo": up.conteudo, "assinatura": up.assinatura}
