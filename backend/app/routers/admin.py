"""Superficie dashboard -> backend (doc 7).

Exige usuario interno logado (require_papel() no router). Papeis finos por rota
podem ser adicionados depois (ex.: so admin controla rollout de update).
"""

import copy
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..aggregate import enriquece_cliente
from ..auth import require_papel
from ..crypto import encrypt_secret
from ..database import get_db
from ..models import now
from ..schemas import (
    ClienteCreate,
    ClienteCreateResponse,
    ConfigSave,
    ConfigSaveResponse,
)
from ..security import hash_token, new_token
from ..settings import settings

# Toda a superficie /admin exige usuario interno logado (doc 7).
router = APIRouter(prefix="/admin", tags=["dashboard"], dependencies=[Depends(require_papel())])


@router.post("/clientes", response_model=ClienteCreateResponse)
def criar_cliente(req: ClienteCreate, db: Session = Depends(get_db)):
    """Cria o cliente e gera um token de enrollment efemero/uso unico (doc 11)."""
    nome = (req.nome or "").strip()
    if not nome:
        raise HTTPException(status_code=400, detail="o nome do cliente e obrigatorio")
    plataforma = (req.plataforma or "linux").strip().lower()
    if plataforma not in ("linux", "windows"):
        raise HTTPException(status_code=400, detail="plataforma deve ser linux ou windows")
    if db.query(models.Cliente).filter_by(nome=nome).first():
        raise HTTPException(status_code=409, detail="ja existe um cliente com esse nome")

    cli = models.Cliente(nome=nome, plataforma=plataforma, status="novo")
    db.add(cli)
    db.flush()  # garante cli.id

    efemero = new_token()
    et = models.EnrollmentToken(
        cliente_id=cli.id,
        token_hash=hash_token(efemero),
        expira_em=now() + dt.timedelta(minutes=settings.enrollment_ttl_min),
    )
    db.add(et)
    db.commit()
    return ClienteCreateResponse(cliente=cli.nome, plataforma=cli.plataforma, enrollment_token=efemero, expira_em=et.expira_em)


@router.post("/clientes/{nome}/config", response_model=ConfigSaveResponse)
def salvar_config(nome: str, req: ConfigSave, db: Session = Depends(get_db)):
    """Salva uma nova VERSAO da config (doc 8). A estrutura vai em claro; cada
    senha e cifrada (age, 2 destinatarios) e guardada em client_secrets."""
    cli = db.query(models.Cliente).filter_by(nome=nome).first()
    if cli is None:
        raise HTTPException(status_code=404, detail="cliente nao existe")
    if req.secrets and not cli.age_pubkey:
        raise HTTPException(
            status_code=400, detail="cliente ainda nao fez enrollment (sem chave age publica)"
        )

    # valida a estrutura: campos vazios geram config quebrada no cliente
    # (ex.: montagem com "ponto" vazio -> os.makedirs('') estoura no backup.py)
    ct = req.conteudo or {}
    erros = []
    for i, m in enumerate(ct.get("montagens") or []):
        if not str(m.get("origem") or "").strip():
            erros.append(f"montagens[{i}].origem vazia")
        if not str(m.get("ponto") or "").strip():
            erros.append(f"montagens[{i}].ponto vazio")
    for i, m in enumerate(ct.get("mapeamentos") or []):
        if not str(m.get("unc") or "").strip():
            erros.append(f"mapeamentos[{i}].unc vazio")
    for i, c in enumerate(ct.get("copias") or []):
        if not str(c.get("nome") or "").strip():
            erros.append(f"copias[{i}].nome vazio")
        if not str(c.get("origem") or "").strip():
            erros.append(f"copias[{i}].origem vazia")
    if erros:
        raise HTTPException(status_code=400, detail="config invalida: " + "; ".join(erros))

    ultima = db.query(func.max(models.Config.versao)).filter_by(cliente_id=cli.id).scalar() or 0
    nova = ultima + 1

    db.add(
        models.Config(
            cliente_id=cli.id,
            versao=nova,
            conteudo=copy.deepcopy(req.conteudo),  # sem senhas
            autor=req.autor,
        )
    )

    for campo, plano in (req.secrets or {}).items():
        ct = encrypt_secret(plano, cli.age_pubkey)  # cifra na memoria, some em seguida
        existente = (
            db.query(models.ClientSecret).filter_by(cliente_id=cli.id, campo=campo).first()
        )
        if existente:
            existente.ciphertext = ct
            existente.updated_at = now()
        else:
            db.add(models.ClientSecret(cliente_id=cli.id, campo=campo, ciphertext=ct))

    db.commit()
    return ConfigSaveResponse(versao=nova)


@router.post("/clientes/{nome}/enrollment-token", response_model=ClienteCreateResponse)
def novo_enrollment_token(nome: str, db: Session = Depends(get_db)):
    """Gera um novo token efemero para um cliente JA existente (recuperacao/reinstalacao,
    doc 12). A maquina nova troca por um token permanente e registra sua nova chave age."""
    cli = db.query(models.Cliente).filter_by(nome=nome).first()
    if cli is None:
        raise HTTPException(status_code=404, detail="cliente nao existe")
    efemero = new_token()
    et = models.EnrollmentToken(
        cliente_id=cli.id,
        token_hash=hash_token(efemero),
        expira_em=now() + dt.timedelta(minutes=settings.enrollment_ttl_min),
    )
    db.add(et)
    db.commit()
    return ClienteCreateResponse(cliente=cli.nome, plataforma=cli.plataforma, enrollment_token=efemero, expira_em=et.expira_em)


@router.delete("/clientes/{nome}")
def remover_cliente(nome: str, db: Session = Depends(get_db)):
    """Apaga o cliente e todo o historico (cascade: configs, segredos, runs,
    inventarios, comandos, tokens)."""
    cli = db.query(models.Cliente).filter_by(nome=nome).first()
    if cli is None:
        raise HTTPException(status_code=404, detail="cliente nao existe")
    db.delete(cli)  # FKs ON DELETE CASCADE cuidam das tabelas filhas
    db.commit()
    return {"ok": True, "nome": nome}


@router.get("/clientes/{nome}")
def detalhe_cliente(nome: str, db: Session = Depends(get_db)):
    cli = db.query(models.Cliente).filter_by(nome=nome).first()
    if cli is None:
        raise HTTPException(status_code=404, detail="cliente nao existe")
    ultima = db.query(func.max(models.Config.versao)).filter_by(cliente_id=cli.id).scalar()
    return {
        "nome": cli.nome, "status": cli.status, "canary": cli.canary, "plataforma": cli.plataforma,
        "age_pubkey": cli.age_pubkey, "versao_script": cli.versao_script,
        "ultimo_heartbeat": cli.ultimo_heartbeat, "enrolled": bool(cli.token_hash),
        "config_versao": ultima,
    }


@router.get("/clientes/{nome}/secrets")
def listar_secrets(nome: str, db: Session = Depends(get_db)):
    """Lista os ciphertexts (age) dos segredos. Usado pela ferramenta de recuperacao
    offline (doc 12). Devolver ciphertext e seguro: so a chave do cliente ou a de
    recuperacao (1Password) decifram."""
    cli = db.query(models.Cliente).filter_by(nome=nome).first()
    if cli is None:
        raise HTTPException(status_code=404, detail="cliente nao existe")
    return [
        {"campo": s.campo, "ciphertext": s.ciphertext, "updated_at": s.updated_at}
        for s in db.query(models.ClientSecret).filter_by(cliente_id=cli.id).order_by(models.ClientSecret.campo).all()
    ]


@router.put("/clientes/{nome}/secrets")
def gravar_secrets(nome: str, secrets: dict[str, str], db: Session = Depends(get_db)):
    """Grava ciphertexts ja cifrados (recifrados pela ferramenta offline para a chave
    da maquina NOVA). O backend nao decifra nada; so armazena (doc 12)."""
    cli = db.query(models.Cliente).filter_by(nome=nome).first()
    if cli is None:
        raise HTTPException(status_code=404, detail="cliente nao existe")
    for campo, ct in secrets.items():
        existente = db.query(models.ClientSecret).filter_by(cliente_id=cli.id, campo=campo).first()
        if existente:
            existente.ciphertext = ct
            existente.updated_at = now()
        else:
            db.add(models.ClientSecret(cliente_id=cli.id, campo=campo, ciphertext=ct))
    db.commit()
    return {"ok": True, "atualizados": list(secrets.keys())}


@router.get("/clientes")
def listar_clientes(db: Session = Depends(get_db)):
    """Frota enriquecida: status, heartbeat, versao, config pendente/aplicada,
    ultimo run e uso do HD (para a visao geral do dashboard)."""
    return [
        enriquece_cliente(db, c)
        for c in db.query(models.Cliente).order_by(models.Cliente.nome).all()
    ]


@router.post("/clientes/{nome}/comandos")
def enfileirar_comando(nome: str, tipo: str, db: Session = Depends(get_db)):
    """Enfileira um comando on-demand ('rodar_agora', 'check') (doc 7)."""
    cli = db.query(models.Cliente).filter_by(nome=nome).first()
    if cli is None:
        raise HTTPException(status_code=404, detail="cliente nao existe")
    cmd = models.Comando(cliente_id=cli.id, tipo=tipo, estado="pendente")
    db.add(cmd)
    db.commit()
    return {"ok": True, "id": cmd.id}
