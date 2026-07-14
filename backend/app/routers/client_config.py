import copy

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..config_merge import set_path
from ..database import get_db
from ..security import current_client

router = APIRouter(tags=["cliente"])


@router.get("/config/{cliente}")
def get_config(cliente: str, cli: models.Cliente = Depends(current_client), db: Session = Depends(get_db)):
    """Config mesclado, com os campos de senha cifrados (age) inline (doc 7/8).

    O agente decifra com a chave privada local e grava o <cliente>.conf. O motor
    (bkp.py) nunca ve ciphertext.
    """
    if cli.nome != cliente:
        raise HTTPException(status_code=403, detail="escopo do token nao confere com o cliente pedido")

    cfg = (
        db.query(models.Config)
        .filter_by(cliente_id=cli.id)
        .order_by(models.Config.versao.desc())
        .first()
    )
    if cfg is None:
        raise HTTPException(status_code=404, detail="sem config para este cliente")

    conteudo = copy.deepcopy(cfg.conteudo)
    for s in db.query(models.ClientSecret).filter_by(cliente_id=cli.id).all():
        try:
            set_path(conteudo, s.campo, s.ciphertext)
        except (KeyError, IndexError, ValueError):
            # o campo pode ter sumido da config numa versao nova; ignora o orfao
            continue

    # o agente ecoa isto no /runs (versao aplicada); pendencia mapeada no bkp.py
    conteudo["_config_versao"] = cfg.versao
    return conteudo
