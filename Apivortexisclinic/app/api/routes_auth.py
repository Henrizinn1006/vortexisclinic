"""
Rotas de autenticação.

    POST /auth/register          cadastro completo (transacional)
    POST /auth/login             abre sessão
    POST /auth/logout            revoga a sessão
    GET  /auth/me                usuário, workspaces, permissões
    POST /auth/password/forgot   prepara recuperação (resposta sempre igual)
    POST /auth/password/reset    redefine e derruba todas as sessões
"""
import logging

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app import errors, rbac, schemas
from app.api.deps import Contexto, contexto, ip_binario
from app.config import settings
from app.db.context import sem_escopo_de_tenant
from app.db.session import get_db
from app.ids import novo_ulid
from app.models.professional import Professional
from app.models.security import SecurityEvent
from app.security import cookies
from app.security.ratelimit import limitador
from app.services import auth as servico_auth
from app.services import mailer
from app.services import permissions as servico_permissoes
from app.services import sessions as servico_sessoes
from app.services import tenants as servico_tenants

log = logging.getLogger("vc.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------- apoio ----------------
def registrar_evento(db: Session, *, request: Request, action: str, outcome: str,
                     user_id=None, tenant_id=None, meta: str = "") -> None:
    """Trilha de segurança. Nunca recebe senha, token ou cookie."""
    db.add(
        SecurityEvent(
            public_id=novo_ulid(),
            user_id=user_id,
            tenant_id=tenant_id,
            action=action[:40],
            outcome=outcome,
            ip=ip_binario(request),
            user_agent=(request.headers.get("user-agent") or "")[:255] or None,
            meta=meta[:500] or None,
        )
    )


def workspace_out(membership, ativo: bool) -> schemas.WorkspaceOut:
    tenant = membership.tenant
    return schemas.WorkspaceOut(
        id=tenant.public_id,
        nome=tenant.name,
        slug=tenant.slug,
        tipo=tenant.type,
        papel=membership.role.key,
        papel_nome=rbac.PAPEIS.get(membership.role.key, {}).get("name", membership.role.name),
        escopo=membership.data_scope,
        ativo=ativo,
    )


def montar_me(db: Session, usuario, membership_ativa, csrf: str = None) -> schemas.MeOut:
    memberships = servico_tenants.workspaces_do_usuario(db, usuario.id)
    ativo_id = membership_ativa.tenant_id if membership_ativa else None

    perfil = None
    if membership_ativa is not None:
        with sem_escopo_de_tenant():
            from sqlalchemy import select

            p = db.execute(
                select(Professional).where(
                    Professional.tenant_id == membership_ativa.tenant_id,
                    Professional.membership_id == membership_ativa.id,
                )
            ).scalar_one_or_none()
        if p is not None:
            perfil = schemas.PerfilOut(
                id=p.public_id,
                nome_exibicao=p.display_name,
                profissao=p.profession.slug if p.profession else None,
                conselho=p.council,
                registro=p.registration_number,
            )

    return schemas.MeOut(
        usuario=schemas.UsuarioOut(
            id=usuario.public_id,
            nome=usuario.name,
            email=usuario.email,
            email_verificado=usuario.email_verified_at is not None,
        ),
        workspace_ativo=workspace_out(membership_ativa, True) if membership_ativa else None,
        workspaces=[workspace_out(m, m.tenant_id == ativo_id) for m in memberships],
        permissoes=sorted(servico_permissoes.efetivas(db, membership_ativa)) if membership_ativa else [],
        perfil=perfil,
        csrf_token=csrf,
    )


def abrir_sessao(db: Session, response: Response, request: Request, usuario, membership) -> str:
    sessao, token, csrf = servico_sessoes.criar(
        db,
        user_id=usuario.id,
        ip=ip_binario(request),
        user_agent=request.headers.get("user-agent"),
        tenant_id=membership.tenant_id if membership else None,
    )
    max_age = servico_sessoes.max_age_segundos()
    cookies.gravar_sessao(response, token, max_age)
    cookies.gravar_csrf(response, csrf, max_age)
    return csrf


# ---------------- cadastro ----------------
@router.post("/register", response_model=schemas.MeOut, status_code=201)
def register(dados: schemas.CadastroIn, request: Request, response: Response,
             db: Session = Depends(get_db)):
    chave = f"register:{request.client.host if request.client else 'desconhecido'}"
    permitido, espera = limitador.registrar_e_checar(
        chave, settings.VC_RATE_LIMIT_REGISTER, settings.VC_RATE_LIMIT_REGISTER_WINDOW
    )
    if not permitido:
        raise errors.excesso_de_tentativas(espera)

    try:
        usuario, membership = servico_auth.cadastrar(
            db,
            nome=dados.nome,
            email=dados.email,
            senha=dados.senha,
            nome_workspace=dados.workspace,
            tipo_workspace=dados.tipo_workspace,
            profissao_slug=dados.profissao,
            conselho=dados.conselho,
            registro=dados.registro,
        )
        csrf = abrir_sessao(db, response, request, usuario, membership)
        registrar_evento(db, request=request, action="register", outcome="allowed",
                         user_id=usuario.id, tenant_id=membership.tenant_id)
        corpo = montar_me(db, usuario, membership, csrf)
        db.commit()          # tudo ou nada: usuário + tenant + membership + perfil
        return corpo
    except errors.ApiError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        # Detalhe fica no log do servidor, não na resposta.
        log.exception("falha no cadastro")
        raise errors.conflito("falha_no_cadastro", "Não foi possível criar a conta agora.")


# ---------------- login ----------------
@router.post("/login", response_model=schemas.MeOut)
def login(dados: schemas.LoginIn, request: Request, response: Response,
          db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "desconhecido"
    email_normalizado = servico_auth.normalizar_email(dados.email)

    for chave in (f"login:ip:{ip}", f"login:email:{email_normalizado}"):
        permitido, espera = limitador.registrar_e_checar(
            chave, settings.VC_RATE_LIMIT_LOGIN, settings.VC_RATE_LIMIT_LOGIN_WINDOW
        )
        if not permitido:
            registrar_evento(db, request=request, action="login", outcome="denied", meta="rate_limit")
            db.commit()
            raise errors.excesso_de_tentativas(espera)

    usuario = servico_auth.autenticar(db, dados.email, dados.senha)
    if usuario is None:
        registrar_evento(db, request=request, action="login", outcome="failed")
        db.commit()
        raise errors.credenciais_invalidas()          # mesma resposta para e-mail e senha

    limitador.limpar(f"login:email:{email_normalizado}")

    # Entra direto quando só existe um workspace; com vários, a sessão
    # nasce SEM workspace e o painel pede a escolha.
    memberships = servico_tenants.workspaces_do_usuario(db, usuario.id)
    membership = memberships[0] if len(memberships) == 1 else None

    csrf = abrir_sessao(db, response, request, usuario, membership)
    registrar_evento(db, request=request, action="login", outcome="allowed",
                     user_id=usuario.id, tenant_id=membership.tenant_id if membership else None)
    corpo = montar_me(db, usuario, membership, csrf)
    db.commit()
    return corpo


# ---------------- logout ----------------
@router.post("/logout", response_model=schemas.MensagemOut)
def logout(request: Request, response: Response, ctx: Contexto = Depends(contexto)):
    servico_sessoes.revogar(ctx.db, ctx.sessao, "logout")
    registrar_evento(ctx.db, request=request, action="logout", outcome="allowed",
                     user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
    ctx.db.commit()
    cookies.apagar(response)
    return schemas.MensagemOut(mensagem="Sessão encerrada.")


# ---------------- quem sou eu ----------------
@router.get("/me", response_model=schemas.MeOut)
def me(ctx: Contexto = Depends(contexto)):
    return montar_me(ctx.db, ctx.usuario, ctx.membership)


# ---------------- recuperação de senha ----------------
@router.post("/password/forgot", response_model=schemas.MensagemOut)
def esqueci(dados: schemas.EsqueciSenhaIn, request: Request, db: Session = Depends(get_db)):
    """Resposta idêntica exista ou não o e-mail — senão a rota vira lista de clientes.

    A mensagem vai para a **fila** de e-mail (`app/services/mailer.py`) e
    é entregue pelo job, fora da requisição. Fora de produção o token
    também aparece no log, para dar para testar sem SMTP.
    """
    usuario = servico_auth.buscar_por_email(db, dados.email)
    if usuario is not None:
        token = servico_auth.criar_token_de_reset(db, usuario)
        mailer.redefinicao(db, usuario, token)
        registrar_evento(db, request=request, action="password_forgot", outcome="allowed",
                         user_id=usuario.id)
        if not settings.is_production:
            log.info("token de recuperação gerado (apenas desenvolvimento): %s", token)
    db.commit()
    return schemas.MensagemOut(
        mensagem="Se existir uma conta com este e-mail, enviaremos as instruções."
    )


@router.post("/password/reset", response_model=schemas.MensagemOut)
def redefinir(dados: schemas.RedefinirSenhaIn, request: Request, response: Response,
              db: Session = Depends(get_db)):
    from app.security import passwords

    servico_auth.validar_senha(dados.senha)
    usuario = servico_auth.consumir_token_de_reset(db, dados.token)
    if usuario is None:
        db.commit()
        raise errors.dados_invalidos("Link inválido ou expirado.")

    usuario.password_hash = passwords.gerar_hash(dados.senha)
    quantas = servico_sessoes.revogar_todas_do_usuario(db, usuario.id, "password_reset")
    registrar_evento(db, request=request, action="password_reset", outcome="allowed",
                     user_id=usuario.id, meta=f"sessoes_revogadas={quantas}")
    db.commit()
    cookies.apagar(response)
    return schemas.MensagemOut(mensagem="Senha alterada. Entre novamente.")

# ---------------- verificação de e-mail ----------------
@router.post("/email/verify/request", response_model=schemas.MensagemOut)
def pedir_verificacao(request: Request, ctx: Contexto = Depends(contexto)):
    """Enfileira o e-mail de confirmação do endereço atual.

    Sempre responde a mesma coisa, inclusive quando já está verificado:
    a rota não é lugar de dizer o estado da conta de ninguém.
    """
    chave = f"verify:{ctx.usuario.id}"
    permitido, espera = limitador.registrar_e_checar(chave, 5, 3600)
    if not permitido:
        raise errors.excesso_de_tentativas(espera)

    if ctx.usuario.email_verified_at is None:
        token = servico_auth.criar_token_de_verificacao(ctx.db, ctx.usuario)
        mailer.verificacao(ctx.db, ctx.usuario, token)
        registrar_evento(ctx.db, request=request, action="email_verify_request",
                         outcome="allowed", user_id=ctx.usuario.id)
        if not settings.is_production:
            log.info("token de verificação gerado (apenas desenvolvimento): %s", token)
    ctx.db.commit()
    return schemas.MensagemOut(mensagem="Se for necessário, enviaremos o link de confirmação.")


@router.post("/email/verify", response_model=schemas.MensagemOut)
def verificar(dados: schemas.VerificarEmailIn, request: Request,
              db: Session = Depends(get_db)):
    """Confirma o endereço. Token errado, vencido ou usado: mesma resposta."""
    usuario = servico_auth.confirmar_email(db, dados.token)
    if usuario is None:
        registrar_evento(db, request=request, action="email_verify", outcome="failed")
        db.commit()
        raise errors.dados_invalidos("Link inválido ou expirado.")
    registrar_evento(db, request=request, action="email_verify", outcome="allowed",
                     user_id=usuario.id)
    db.commit()
    return schemas.MensagemOut(mensagem="E-mail confirmado.")
