"""Retencao/limpeza de runs e inventarios (doc 16).

Apaga registros mais velhos que N dias, mas SEMPRE preserva as `min_por_cliente`
rodadas mais recentes de cada cliente (para o dashboard nao ficar sem historico
de um cliente que passou dias sem rodar).
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import models
from .models import now

DEFAULTS = dict(
    runs_reter_dias=90, inventarios_reter_dias=90,
    min_por_cliente=20, auto_limpeza=False, intervalo_horas=24,
)

# tbl vem de constantes internas (nunca de entrada do usuario) -> seguro no format.
_ALVOS = ("runs", "created_at"), ("inventarios", "created_at")

_SEL = """
SELECT id FROM (
  SELECT id, created_at,
         row_number() OVER (PARTITION BY cliente_id ORDER BY id DESC) AS rn
  FROM {tbl}
) t
WHERE created_at < now() - make_interval(days => :dias) AND rn > :minpc
"""


def get_config(db: Session) -> models.RetencaoConfig:
    cfg = db.get(models.RetencaoConfig, 1)
    if cfg is None:
        cfg = models.RetencaoConfig(id=1, **DEFAULTS)
        db.add(cfg)
        db.commit()
    return cfg


def _count(db: Session, tbl: str, dias: int, minpc: int) -> int:
    q = "SELECT count(*) FROM (%s) x" % _SEL.format(tbl=tbl)
    return db.execute(text(q), {"dias": dias, "minpc": minpc}).scalar() or 0


def _delete(db: Session, tbl: str, dias: int, minpc: int) -> int:
    q = "DELETE FROM {tbl} WHERE id IN ({sel})".format(tbl=tbl, sel=_SEL.format(tbl=tbl))
    return db.execute(text(q), {"dias": dias, "minpc": minpc}).rowcount


def preview(db: Session, cfg: models.RetencaoConfig) -> dict:
    """Quantos registros seriam apagados agora (sem apagar)."""
    return {
        "runs": _count(db, "runs", cfg.runs_reter_dias, cfg.min_por_cliente),
        "inventarios": _count(db, "inventarios", cfg.inventarios_reter_dias, cfg.min_por_cliente),
    }


def limpar(db: Session, cfg: models.RetencaoConfig) -> dict:
    rr = _delete(db, "runs", cfg.runs_reter_dias, cfg.min_por_cliente)
    ii = _delete(db, "inventarios", cfg.inventarios_reter_dias, cfg.min_por_cliente)
    cfg.ultima_limpeza = now()
    db.commit()
    return {"runs_removidos": rr, "inventarios_removidos": ii}
