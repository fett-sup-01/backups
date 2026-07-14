"""Agregacoes de leitura para o dashboard (frota, runs, config aplicada)."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models


def parse_uso_pct(v):
    """'68%' / '68' / '-' -> 68 | None."""
    if v is None:
        return None
    s = str(v).strip().rstrip("%")
    try:
        return int(round(float(s)))
    except ValueError:
        return None


def ultimo_run(db: Session, cliente_id: int):
    return (
        db.query(models.Run)
        .filter_by(cliente_id=cliente_id)
        .order_by(models.Run.id.desc())
        .first()
    )


def _duracao_seg(payload: dict):
    """Soma as duracoes dos jobs (best-effort); None se nao der para somar."""
    total = 0.0
    achou = False
    for j in (payload or {}).get("jobs", []) or []:
        d = j.get("duracao")
        try:
            total += float(d)
            achou = True
        except (TypeError, ValueError):
            continue
    return int(total) if achou else None


def serializa_run(db: Session, run: models.Run, incluir_cliente=False):
    payload = run.payload or {}
    destino = payload.get("destino") or {}
    out = {
        "id": run.id,
        "run_id": run.run_id,
        "status": run.status,
        "jobs_ok": run.jobs_ok,
        "total_jobs": run.total_jobs,
        "versao_config": run.versao_config,
        "versao_script": payload.get("versao_script"),
        "data": payload.get("data") or run.created_at.isoformat(),
        "uso_pct": parse_uso_pct(destino.get("uso_pct")),
        "duracao_seg": _duracao_seg(payload),
    }
    if incluir_cliente:
        cli = db.get(models.Cliente, run.cliente_id)
        out["cliente"] = cli.nome if cli else None
    return out


def enriquece_cliente(db: Session, cli: models.Cliente):
    """Cliente + versao de config (pendente vs aplicada) + ultimo run + uso do HD."""
    latest_cfg = db.query(func.max(models.Config.versao)).filter_by(cliente_id=cli.id).scalar()
    ur = ultimo_run(db, cli.id)
    aplicada = ur.versao_config if ur else None
    pendente = latest_cfg is not None and ((aplicada or 0) < latest_cfg)

    uso = None
    run_info = None
    if ur:
        destino = (ur.payload or {}).get("destino") or {}
        uso = parse_uso_pct(destino.get("uso_pct"))
        run_info = {
            "data": (ur.payload or {}).get("data") or ur.created_at.isoformat(),
            "status": ur.status,
            "jobs_ok": ur.jobs_ok,
            "total_jobs": ur.total_jobs,
        }

    return {
        "nome": cli.nome,
        "status": cli.status,
        "canary": cli.canary,
        "plataforma": cli.plataforma,
        "versao_script": cli.versao_script,
        "ultimo_heartbeat": cli.ultimo_heartbeat,
        "enrolled": bool(cli.token_hash),
        "config_versao": latest_cfg,
        "config_pendente": pendente,
        "hd_uso_pct": uso,
        "ultimo_run": run_info,
    }
