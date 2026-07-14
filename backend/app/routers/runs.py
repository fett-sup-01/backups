from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..security import current_client

router = APIRouter(tags=["cliente"])


@router.post("/runs")
def post_run(
    payload: dict = Body(...),
    cli: models.Cliente = Depends(current_client),
    db: Session = Depends(get_db),
):
    """Relatorio da rodada (doc 7). Aceita o payload que o bkp.py v1.0 ja envia.

    `versao_config` (versao da config aplicada) e opcional: o bkp.py v1.0 ainda
    nao a envia. E a unica mudanca minima mapeada no motor (ecoar _config_versao
    do .conf) para o dashboard distinguir pendente vs aplicada (doc 8, pendencia #3).
    """
    run = models.Run(
        cliente_id=cli.id,
        run_id=str(payload.get("run_id", "")),
        status=payload.get("status"),
        jobs_ok=payload.get("jobs_ok"),
        total_jobs=payload.get("total_jobs"),
        versao_config=payload.get("versao_config"),
        payload=payload,
    )
    db.add(run)
    if payload.get("versao_script"):
        cli.versao_script = payload["versao_script"]
    db.commit()
    return {"ok": True, "id": run.id}
