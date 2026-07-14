from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT = "dev-troque-este-segredo"
DEV_ADMIN_PW = "admin"


class Settings(BaseSettings):
    # dev | prod. Em prod, a validacao abaixo recusa segredos padrao (fail-closed).
    app_env: str = "dev"

    database_url: str = "postgresql+psycopg2://backup:backup@db:5432/backup"

    # Chave PUBLICA age de recuperacao (doc 5.3). A privada mora no 1Password e
    # NUNCA toca o servidor. Obrigatoria: encrypt_secret() falha se estiver vazia.
    recovery_age_pubkey: str = ""

    # Chave PUBLICA minisign, so para entregar/exibir ao agente.
    minisign_public_key: str = ""

    enrollment_ttl_min: int = 60

    # Auth do dashboard (usuario interno).
    jwt_secret: str = DEV_JWT
    jwt_expire_min: int = 480
    admin_login: str = "admin"
    admin_password: str = DEV_ADMIN_PW

    # CORS: vazio = sem cabecalhos CORS (o normal em prod, mesma origem via nginx).
    # Em dev com `npm run dev` o Vite ja proxia /api, entao tambem nao precisa.
    cors_origins: str = ""

    # /docs e /openapi: sempre desligados em prod (nao expor o schema).
    docs_enabled: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def is_prod(self) -> bool:
        return self.app_env.strip().lower() == "prod"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def expose_docs(self) -> bool:
        return self.docs_enabled and not self.is_prod

    def problemas_prod(self) -> list[str]:
        """Config insegura para producao (fail-closed na subida)."""
        if not self.is_prod:
            return []
        p = []
        if self.jwt_secret in ("", DEV_JWT) or len(self.jwt_secret) < 32:
            p.append("JWT_SECRET ausente/padrao/fraco (use >= 32 chars aleatorios)")
        if self.admin_password in ("", DEV_ADMIN_PW) or len(self.admin_password) < 12:
            p.append("ADMIN_PASSWORD ausente/padrao/fraco (use >= 12 chars)")
        if not self.recovery_age_pubkey:
            p.append("RECOVERY_AGE_PUBKEY ausente (doc 5.3)")
        if "backup:backup@" in self.database_url:
            p.append("credenciais padrao (backup:backup) no DATABASE_URL")
        return p


settings = Settings()
