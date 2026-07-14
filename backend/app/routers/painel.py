"""Endpoints de leitura do dashboard (frota/runs/config/comandos). Auth de operador."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, retencao
from ..aggregate import serializa_run
from ..auth import require_papel
from ..database import get_db

router = APIRouter(prefix="/admin", tags=["dashboard"], dependencies=[Depends(require_papel())])


@router.get("/clientes/{nome}/config")
def config_do_cliente(nome: str, db: Session = Depends(get_db)):
    """Ultima versao da config (estrutura em claro, sem senhas) para o detalhe do cliente."""
    cli = db.query(models.Cliente).filter_by(nome=nome).first()
    if cli is None:
        raise HTTPException(status_code=404, detail="cliente nao existe")
    cfg = (
        db.query(models.Config)
        .filter_by(cliente_id=cli.id)
        .order_by(models.Config.versao.desc())
        .first()
    )
    if cfg is None:
        return {"versao": None, "conteudo": None}
    return {"versao": cfg.versao, "conteudo": cfg.conteudo, "autor": cfg.autor}


@router.get("/clientes/{nome}/runs")
def runs_do_cliente(nome: str, limit: int = Query(20, le=200), db: Session = Depends(get_db)):
    cli = db.query(models.Cliente).filter_by(nome=nome).first()
    if cli is None:
        raise HTTPException(status_code=404, detail="cliente nao existe")
    rows = (
        db.query(models.Run)
        .filter_by(cliente_id=cli.id)
        .order_by(models.Run.id.desc())
        .limit(limit)
        .all()
    )
    return [serializa_run(db, r) for r in rows]


@router.get("/runs")
def runs_consolidados(
    status: str | None = None,
    cliente: str | None = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(models.Run)
    if cliente:
        c = db.query(models.Cliente).filter_by(nome=cliente).first()
        q = q.filter_by(cliente_id=c.id if c else -1)
    if status:
        q = q.filter(models.Run.status == status)
    rows = q.order_by(models.Run.id.desc()).limit(limit).all()
    return [serializa_run(db, r, incluir_cliente=True) for r in rows]


@router.get("/comandos")
def comandos_todos(limit: int = Query(100, le=500), db: Session = Depends(get_db)):
    rows = db.query(models.Comando).order_by(models.Comando.id.desc()).limit(limit).all()
    out = []
    for c in rows:
        cli = db.get(models.Cliente, c.cliente_id)
        out.append({
            "id": c.id, "cliente": cli.nome if cli else None,
            "tipo": c.tipo, "estado": c.estado,
            "criado_em": c.created_at.isoformat() if c.created_at else None,
        })
    return out


@router.delete("/comandos/{cmd_id}")
def cancelar_comando(cmd_id: int, db: Session = Depends(get_db)):
    cmd = db.get(models.Comando, cmd_id)
    if cmd is None:
        raise HTTPException(status_code=404, detail="comando nao existe")
    if cmd.estado != "pendente":
        raise HTTPException(status_code=400, detail="so da para cancelar comando pendente")
    db.delete(cmd)
    db.commit()
    return {"ok": True, "id": cmd_id}


# ---- retencao / limpeza (doc 16) ----------------------------------------------
class RetencaoUpdate(BaseModel):
    runs_reter_dias: int = Field(ge=1, le=3650)
    inventarios_reter_dias: int = Field(ge=1, le=3650)
    min_por_cliente: int = Field(ge=0, le=1000)
    auto_limpeza: bool
    intervalo_horas: int = Field(ge=1, le=720)


def _cfg_dict(cfg: models.RetencaoConfig) -> dict:
    return {
        "runs_reter_dias": cfg.runs_reter_dias,
        "inventarios_reter_dias": cfg.inventarios_reter_dias,
        "min_por_cliente": cfg.min_por_cliente,
        "auto_limpeza": cfg.auto_limpeza,
        "intervalo_horas": cfg.intervalo_horas,
        "ultima_limpeza": cfg.ultima_limpeza,
    }


@router.get("/retencao")
def get_retencao(db: Session = Depends(get_db)):
    cfg = retencao.get_config(db)
    return {"config": _cfg_dict(cfg), "preview": retencao.preview(db, cfg)}


@router.put("/retencao")
def put_retencao(req: RetencaoUpdate, db: Session = Depends(get_db)):
    cfg = retencao.get_config(db)
    cfg.runs_reter_dias = req.runs_reter_dias
    cfg.inventarios_reter_dias = req.inventarios_reter_dias
    cfg.min_por_cliente = req.min_por_cliente
    cfg.auto_limpeza = req.auto_limpeza
    cfg.intervalo_horas = req.intervalo_horas
    cfg.updated_at = models.now()
    db.commit()
    return {"config": _cfg_dict(cfg), "preview": retencao.preview(db, cfg)}


@router.post("/retencao/limpar")
def limpar_agora(db: Session = Depends(get_db)):
    cfg = retencao.get_config(db)
    return retencao.limpar(db, cfg)
