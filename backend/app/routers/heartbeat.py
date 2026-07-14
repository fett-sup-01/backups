from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..models import now
from ..schemas import HeartbeatRequest, HeartbeatResponse
from ..security import current_client
from .updates import update_para

router = APIRouter(tags=["cliente"])


def _comandos_pendentes(db: Session, cliente_id: int, marcar_enviado: bool) -> list[dict]:
    pend = db.query(models.Comando).filter_by(cliente_id=cliente_id, estado="pendente").all()
    out = [{"id": c.id, "tipo": c.tipo, "args": c.args} for c in pend]
    if marcar_enviado:
        for c in pend:
            c.estado = "enviado"
            c.updated_at = now()
    return out


@router.post("/heartbeat", response_model=HeartbeatResponse)
def heartbeat(
    req: HeartbeatRequest,
    cli: models.Cliente = Depends(current_client),
    db: Session = Depends(get_db),
):
    """'Estou vivo' leve: resposta diz se ha config nova, comando ou update (doc 4/7)."""
    cli.ultimo_heartbeat = now()
    cli.status = "online"
    if req.versao_script:
        cli.versao_script = req.versao_script

    latest = db.query(func.max(models.Config.versao)).filter_by(cliente_id=cli.id).scalar()
    ultimo_run = (
        db.query(models.Run).filter_by(cliente_id=cli.id).order_by(models.Run.id.desc()).first()
    )
    aplicada = ultimo_run.versao_config if ultimo_run else None
    config_disponivel = latest is not None and (aplicada is None or aplicada < latest)

    comandos = _comandos_pendentes(db, cli.id, marcar_enviado=True)
    update = update_para(db, cli)  # rollout canary/geral (doc 10)
    db.commit()

    return HeartbeatResponse(
        config_disponivel=config_disponivel,
        config_versao=latest,
        comandos=comandos,
        update=update,
    )


@router.get("/comando/{cliente}")
def comandos_pendentes(
    cliente: str,
    cli: models.Cliente = Depends(current_client),
    db: Session = Depends(get_db),
):
    """Alternativa ao embutido no heartbeat (doc 7). Nao marca como enviado."""
    from fastapi import HTTPException

    if cli.nome != cliente:
        raise HTTPException(status_code=403, detail="escopo do token nao confere")
    return {"comandos": _comandos_pendentes(db, cli.id, marcar_enviado=False)}
