from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..models import now
from ..schemas import EnrollRequest, EnrollResponse
from ..security import hash_token, new_token

router = APIRouter(tags=["cliente"])


@router.post("/enroll", response_model=EnrollResponse)
def enroll(req: EnrollRequest, db: Session = Depends(get_db)):
    """O instalador troca o token efemero + chave publica age pelo token permanente (doc 11)."""
    et = (
        db.query(models.EnrollmentToken)
        .filter_by(token_hash=hash_token(req.enrollment_token), usado=False)
        .first()
    )
    if et is None:
        raise HTTPException(status_code=400, detail="token de enrollment invalido ou ja usado")
    if et.expira_em < now():
        raise HTTPException(status_code=400, detail="token de enrollment expirado")

    cli = db.get(models.Cliente, et.cliente_id)
    if cli is None:
        raise HTTPException(status_code=400, detail="cliente do token nao existe mais")

    cli.age_pubkey = req.age_pubkey
    permanente = new_token()
    cli.token_hash = hash_token(permanente)  # guardamos so o hash
    cli.status = "enrolled"
    et.usado = True  # uso unico
    db.commit()

    return EnrollResponse(cliente=cli.nome, token=permanente)
