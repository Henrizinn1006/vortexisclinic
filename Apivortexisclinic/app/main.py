"""
Aplicação FastAPI.

Responsabilidades deste arquivo: montar as rotas, configurar CORS restrito,
checar a origem em métodos que escrevem, limpar o contexto de tenant ao fim
de cada requisição e transformar exceções em respostas que não descrevem o
interior do sistema.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (routes_agenda, routes_appointments, routes_auth, routes_billing,
                     routes_clients,
                     routes_clinical, routes_documents, routes_lgpd,
                     routes_dashboard, routes_members, routes_meta, routes_payments,
                     routes_settings, routes_workspace_data, routes_workspaces)
from app.config import settings
from app.db import context
from app.db.context import TenantContextError

logging.basicConfig(
    level=getattr(logging, settings.VC_LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("vc")

settings.validar_producao()

app = FastAPI(
    title="Vortexis Clinic API",
    version="1.0.0-rc",
    description="Identidade, isolamento multi-tenant, pessoas atendidas, agenda, financeiro, prontuário e equipe.",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/openapi.json",
)

# CORS restrito: só as origens declaradas, e com credenciais (o cookie
# precisa viajar). Lista vazia = apenas mesma origem.
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
        max_age=600,
    )

METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def contexto_por_requisicao(request: Request, call_next):
    """Origem conferida, contexto limpo no fim. Sempre."""
    # Segunda barreira de CSRF, antes até do cookie ser lido: se a
    # requisição que escreve vem de uma origem que não está na lista,
    # não passa. Requisição sem Origin (curl, app nativo) segue para a
    # verificação de token na dependência.
    if request.method not in METODOS_SEGUROS and settings.cors_origins:
        origem = request.headers.get("origin")
        if origem and origem not in settings.cors_origins:
            return JSONResponse(
                status_code=403,
                content={"code": "origem_nao_permitida", "message": "Origem não permitida."},
            )
    try:
        resposta = await call_next(request)

        # Resposta de dados NUNCA entra em cache.
        #
        # São dois motivos, e os dois importam:
        # 1) correção — sem isto, o navegador serve a lista antiga
        #    depois de um cadastro, e a tela mostra dado velho;
        # 2) privacidade — lista de pessoas atendidas é dado de
        #    saúde por associação. Não pode ficar no disco do
        #    navegador nem em proxy no caminho.
        resposta.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        resposta.headers["Pragma"] = "no-cache"

        # Cabeçalhos de segurança básicos: a API não é feita para ser
        # aberta no navegador nem embutida em outra página.
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        resposta.headers["X-Frame-Options"] = "DENY"
        resposta.headers["Referrer-Policy"] = "no-referrer"
        return resposta
    finally:
        context.limpar()


@app.exception_handler(TenantContextError)
async def _sem_tenant(request: Request, exc: TenantContextError):
    """Fail-closed chegou até aqui: a operação exigia tenant e não havia.

    Isso é erro de programação (rota tenant-scoped sem a dependência certa)
    e precisa aparecer no log — mas o cliente recebe só um código curto.
    """
    log.error("operação tenant-scoped sem contexto: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=409,
        content={"code": "sem_workspace_ativo", "message": "Nenhum workspace ativo nesta sessão."},
    )


@app.exception_handler(Exception)
async def _erro_inesperado(request: Request, exc: Exception):
    log.exception("erro não tratado em %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"code": "erro_interno", "message": "Não foi possível concluir a operação."},
    )


app.include_router(routes_meta.router)
app.include_router(routes_auth.router)
app.include_router(routes_workspaces.router)
app.include_router(routes_workspace_data.router)
app.include_router(routes_clients.router)
app.include_router(routes_appointments.router)
app.include_router(routes_agenda.router)
app.include_router(routes_payments.router)
app.include_router(routes_clinical.router)
app.include_router(routes_documents.router)
app.include_router(routes_billing.router)
app.include_router(routes_lgpd.router)
app.include_router(routes_members.router)
app.include_router(routes_settings.router)
app.include_router(routes_dashboard.router)
