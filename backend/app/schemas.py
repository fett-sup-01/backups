import datetime as dt

from pydantic import BaseModel


# ---- Enrollment (doc 11) ------------------------------------------------------
class EnrollRequest(BaseModel):
    enrollment_token: str
    age_pubkey: str


class EnrollResponse(BaseModel):
    cliente: str
    token: str  # Bearer permanente (mostrado uma unica vez)


# ---- Heartbeat (doc 4/7) ------------------------------------------------------
class HeartbeatRequest(BaseModel):
    versao_script: str | None = None


class HeartbeatResponse(BaseModel):
    config_disponivel: bool
    config_versao: int | None
    comandos: list[dict]
    update: dict | None = None


# ---- Admin / dashboard (auth interna entra no proximo passo) ------------------
class ClienteCreate(BaseModel):
    nome: str
    plataforma: str = "linux"  # linux | windows


class ClienteCreateResponse(BaseModel):
    cliente: str
    plataforma: str = "linux"
    enrollment_token: str  # efemero, uso unico (mostrado uma unica vez)
    expira_em: dt.datetime


class ConfigSave(BaseModel):
    conteudo: dict  # estrutura em claro (sem senhas)
    secrets: dict[str, str] = {}  # {caminho_do_campo: senha_em_claro}
    autor: str | None = None


class ConfigSaveResponse(BaseModel):
    versao: int
