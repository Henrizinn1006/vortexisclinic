"""
Configuração da API — tudo vem de variáveis de ambiente.

Nenhum host, usuário, senha, segredo ou string de conexão aparece neste
arquivo. O que existe aqui são NOMES de variáveis e padrões inofensivos
(localhost, porta 3306, nomes de cookie). Os valores reais moram no .env,
que está no .gitignore.
"""
from functools import lru_cache
from typing import List, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---------------- Ambiente ----------------
    VC_ENV: Literal["development", "test", "production"] = "development"
    VC_DEBUG: bool = False
    VC_LOG_LEVEL: str = "INFO"

    # ---------------- Banco ----------------
    VC_DB_HOST: str = "127.0.0.1"
    VC_DB_PORT: int = 3306
    VC_DB_NAME: str = "vortexis_clinic"
    VC_DB_USER: str = "root"
    VC_DB_PASSWORD: str = ""
    VC_DB_SSL_CA: str = ""          # caminho do CA quando o MySQL exigir TLS
    VC_DB_ECHO: bool = False
    VC_DB_POOL_SIZE: int = 5
    VC_DB_POOL_RECYCLE: int = 1800

    # ---------------- Sessão ----------------
    VC_SESSION_COOKIE_NAME: str = "vc_session"
    VC_CSRF_COOKIE_NAME: str = "vc_csrf"
    VC_SESSION_IDLE_MINUTES: int = 720        # 12h sem uso encerra
    VC_SESSION_ABSOLUTE_HOURS: int = 168      # 7 dias no máximo, usando ou não
    VC_COOKIE_SECURE: bool = False            # OBRIGATÓRIO true em produção
    VC_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    VC_COOKIE_DOMAIN: str = ""
    VC_COOKIE_PATH: str = "/"

    # ---------------- CORS ----------------
    # Origens do painel, separadas por vírgula. Vazio = mesma origem apenas.
    # É string (e não lista) de propósito: variável de ambiente é texto, e
    # exigir JSON aqui só rende erro de configuração.
    VC_CORS_ORIGINS: str = ""

    # Endereço do painel — usado para montar links que a pessoa clica
    # (convite, verificação de e-mail, redefinição de senha). Sem barra
    # no fim; a primeira origem do CORS serve de padrão.
    VC_PANEL_URL: str = ""

    # ---------------- Rate limit ----------------
    VC_RATE_LIMIT_LOGIN: int = 8              # tentativas
    VC_RATE_LIMIT_LOGIN_WINDOW: int = 300     # por janela, em segundos
    VC_RATE_LIMIT_REGISTER: int = 5
    VC_RATE_LIMIT_REGISTER_WINDOW: int = 3600
    # Teto de escrita por pessoa. Não é para conter ataque — é para uma
    # automação com defeito não encher o banco antes de alguém perceber.
    # Generoso de propósito: quem está trabalhando não pode esbarrar nele.
    VC_RATE_LIMIT_WRITE: int = 240
    VC_RATE_LIMIT_WRITE_WINDOW: int = 60

    # ---------------- Cifra do conteúdo clínico ----------------
    # Versões de chave separadas por vírgula: "1:base64,2:base64".
    # 32 bytes por chave, em base64. O valor real mora no .env — aqui só o
    # nome da variável. Vazio fora de produção usa chave de desenvolvimento
    # (com aviso no log); em produção, subir sem isto é erro.
    VC_CLINICAL_KEYS: str = ""
    # Onde os arquivos de documento ficam. Eles vão cifrados para o disco,
    # com a mesma chave mestra do prontuário. Caminho relativo é resolvido
    # a partir de onde a API roda.
    VC_FILES_DIR: str = "arquivos"
    VC_MAX_UPLOAD_MB: int = 8
    VC_CLINICAL_KEY_VERSION: int = 0          # a versão usada para ESCREVER

    # ---------------- Planos ----------------
    # Dias de teste de uma conta nova. É uma decisão de PRODUTO, não uma
    # regra legal: ajuste quando decidir. 0 = sem prazo de teste.
    VC_TRIAL_DAYS: int = 14

    # ---------------- E-mail ----------------
    # Desligado por padrão: sem SMTP configurado, a mensagem é enfileirada
    # e fica visível na fila em vez de sumir. Em desenvolvimento, o backend
    # "console" imprime no log — assim dá para testar o fluxo inteiro sem
    # mandar e-mail de verdade para ninguém.
    VC_MAIL_BACKEND: Literal["queue", "console", "smtp"] = "queue"
    VC_MAIL_FROM: str = "Vortexis Clinic <nao-responda@exemplo.com>"
    VC_MAIL_REPLY_TO: str = ""
    VC_SMTP_HOST: str = ""
    VC_SMTP_PORT: int = 587
    VC_SMTP_USER: str = ""
    VC_SMTP_PASSWORD: str = ""
    VC_SMTP_TLS: bool = True
    VC_MAIL_MAX_ATTEMPTS: int = 5
    # Quantas horas antes da sessão o lembrete sai.
    VC_REMINDER_HOURS: int = 24
    VC_EMAIL_VERIFY_TTL_HOURS: int = 48

    # ---------------- Senha ----------------
    VC_ARGON2_TIME_COST: int = 3
    VC_ARGON2_MEMORY_KB: int = 65536
    VC_ARGON2_PARALLELISM: int = 2
    VC_PASSWORD_MIN_LENGTH: int = 10
    VC_PASSWORD_RESET_TTL_MINUTES: int = 30

    # ---------------- Derivados ----------------
    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.VC_CORS_ORIGINS.split(",") if o.strip()]

    @property
    def painel_url(self) -> str:
        if self.VC_PANEL_URL:
            return self.VC_PANEL_URL.rstrip("/")
        origens = self.cors_origins
        return origens[0].rstrip("/") if origens else ""

    @property
    def database_url(self) -> str:
        from urllib.parse import quote_plus

        senha = quote_plus(self.VC_DB_PASSWORD)
        usuario = quote_plus(self.VC_DB_USER)
        return (
            f"mysql+pymysql://{usuario}:{senha}"
            f"@{self.VC_DB_HOST}:{self.VC_DB_PORT}/{self.VC_DB_NAME}?charset=utf8mb4"
        )

    @property
    def is_production(self) -> bool:
        return self.VC_ENV == "production"

    def validar_producao(self) -> None:
        """Em produção, algumas frouxidões de desenvolvimento não passam."""
        if not self.is_production:
            return
        problemas = []
        if not self.VC_COOKIE_SECURE:
            problemas.append("VC_COOKIE_SECURE precisa ser true em produção")
        if not self.VC_DB_PASSWORD:
            problemas.append("VC_DB_PASSWORD não pode ser vazio em produção")
        if self.VC_DEBUG:
            problemas.append("VC_DEBUG precisa ser false em produção")
        if self.VC_COOKIE_SAMESITE == "none" and not self.VC_COOKIE_SECURE:
            problemas.append("SameSite=None exige cookie Secure")
        if not self.VC_CLINICAL_KEYS:
            # Sem chave, o prontuário seria gravado com a chave de
            # desenvolvimento — que está no código. Não sobe assim.
            problemas.append("VC_CLINICAL_KEYS é obrigatório em produção")
        if problemas:
            raise RuntimeError("Configuração inválida para produção: " + "; ".join(problemas))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
