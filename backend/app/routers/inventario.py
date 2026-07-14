from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..security import current_client

router = APIRouter(tags=["cliente"])


@router.post("/inventario")
def post_inventario(
    payload: dict = Body(...),
    cli: models.Cliente = Depends(current_client),
    db: Session = Depends(get_db),
):
    """Resumo de metadados da estrutura de origem (doc 7). v1: recebe e guarda;
    analise inteligente fica para a fase 2 (doc 14)."""
    inv = models.Inventario(
        cliente_id=cli.id,
        run_id=str(payload.get("run_id", "")) or None,
        payload=payload,
    )
    db.add(inv)
    db.commit()
    return {"ok": True, "id": inv.id}
