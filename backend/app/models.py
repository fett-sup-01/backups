import datetime as dt

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Cliente(Base):
    """Uma maquina de cliente na frota (doc secao 6)."""

    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    plataforma: Mapped[str] = mapped_column(String(16), nullable=False, server_default="linux", default="linux")  # linux | windows
    age_pubkey: Mapped[str | None] = mapped_column(String(120))  # so a publica; a privada fica no cliente
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)  # sha256 do Bearer permanente
    versao_script: Mapped[str | None] = mapped_column(String(32))
    ultimo_heartbeat: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="novo")
    # cliente de teste do rollout de update (recebe versoes canary antes do geral, doc 10)
    canary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false", default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Config(Base):
    """Config versionada por cliente: SO a parte nao-secreta (doc 5.2 / 6)."""

    __tablename__ = "configs"
    __table_args__ = (UniqueConstraint("cliente_id", "versao", name="uq_config_cliente_versao"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), index=True)
    versao: Mapped[int] = mapped_column(Integer)
    conteudo: Mapped[dict] = mapped_column(JSONB)  # estrutura em claro, sem senhas
    autor: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class ClientSecret(Base):
    """Valor de senha cifrado (age, 2 destinatarios), referenciando qual campo de
    qual montagem/copia ele preenche (doc 6). ciphertext = 'age:' + base64(bin)."""

    __tablename__ = "client_secrets"
    __table_args__ = (UniqueConstraint("cliente_id", "campo", name="uq_secret_cliente_campo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), index=True)
    campo: Mapped[str] = mapped_column(String(200))  # caminho, ex: "montagens[0].senha"
    ciphertext: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Run(Base):
    """Payload do POST /runs (doc 6/7). versao_config = versao da config aplicada."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str] = mapped_column(String(80))
    status: Mapped[str | None] = mapped_column(String(32))
    jobs_ok: Mapped[int | None] = mapped_column(Integer)
    total_jobs: Mapped[int | None] = mapped_column(Integer)
    versao_config: Mapped[int | None] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Inventario(Base):
    """Payload do POST /inventario: recebe e guarda no v1; analise na fase 2 (doc 14)."""

    __tablename__ = "inventarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Comando(Base):
    """Fila on-demand por cliente ('rodar agora', '--check') (doc 6/7)."""

    __tablename__ = "comandos"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(40))
    args: Mapped[dict | None] = mapped_column(JSONB)
    estado: Mapped[str] = mapped_column(String(20), default="pendente")  # pendente|enviado|concluido
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Update(Base):
    """Versoes do bkp.py com assinatura minisign e grupo de rollout (doc 6/10)."""

    __tablename__ = "updates"

    id: Mapped[int] = mapped_column(primary_key=True)
    versao: Mapped[str] = mapped_column(String(32), unique=True)
    arquivo: Mapped[str] = mapped_column(String(300))  # nome do arquivo (ex: backup.py)
    conteudo: Mapped[str] = mapped_column(Text)  # fonte do bkp.py novo (servido no download)
    assinatura: Mapped[str] = mapped_column(Text)  # assinatura minisign (.minisig)
    grupo_rollout: Mapped[str] = mapped_column(String(20), default="canary")  # canary|geral
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Usuario(Base):
    """Login do dashboard, com papeis (doc 6/7). Auth interna entra no proximo passo."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(120), unique=True)
    senha_hash: Mapped[str] = mapped_column(String(200))  # bcrypt (usuario interno, nao token)
    papel: Mapped[str] = mapped_column(String(32), default="operador")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class RetencaoConfig(Base):
    """Politica de retencao/limpeza de runs e inventarios (doc 16). Linha unica (id=1),
    editavel pelo dashboard. Purga apaga registros mais velhos que N dias, mas SEMPRE
    preserva as `min_por_cliente` rodadas mais recentes de cada cliente."""

    __tablename__ = "retencao_config"

    id: Mapped[int] = mapped_column(primary_key=True)  # sempre 1
    runs_reter_dias: Mapped[int] = mapped_column(Integer, nullable=False, server_default="90", default=90)
    inventarios_reter_dias: Mapped[int] = mapped_column(Integer, nullable=False, server_default="90", default=90)
    min_por_cliente: Mapped[int] = mapped_column(Integer, nullable=False, server_default="20", default=20)
    auto_limpeza: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false", default=False)
    intervalo_horas: Mapped[int] = mapped_column(Integer, nullable=False, server_default="24", default=24)
    ultima_limpeza: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class EnrollmentToken(Base):
    """Token efemero/uso unico gerado pelo front, com expiracao (doc 6/11)."""

    __tablename__ = "enrollment_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64))  # sha256 do token efemero
    expira_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    usado: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
