"""
Rotas de equipe: convidar, aceitar, e mexer no acesso de quem já está.

Duas metades com regras diferentes de propósito.

**Dentro da conta** (`/workspace/...`) exige sessão, workspace ativo e
`members.manage`. É a parte administrativa.

**O aceite do convite** (`/invitations/...`) é público, porque quem vai
aceitar pode ainda não ter conta nenhuma. A autenticação ali é o próprio
token: 32 bytes aleatórios cujo sha256 está no banco. Link errado, vencido,
revogado ou já usado recebem todos a **mesma** resposta — 404 —, porque
distinguir os casos só serviria para quem está testando links.

O link do convite é devolvido UMA vez, na criação, para quem convidou
copiar. Quando o envio de e-mail existir, ele passa a ir direto para a
pessoa e some da resposta.
"""
import logging

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import errors, rbac, schemas
from app.api.deps import Contexto, contexto, exigir
from app.api.routes_auth import abrir_sessao, montar_me, registrar_evento
from app.config import settings
from app.db.context import sem_escopo_de_tenant
from app.db.session import get_db
from app.models.profession import Profession
from app.models.user import User
from app.security.ratelimit import limitador
from app.services import auth as servico_auth
from app.services import mailer
from app.services import members as servico

log = logging.getLogger("vc.equipe")

router = APIRouter(tags=["equipe"])


def convite_out(convite, db: Session, *, link: str = None) -> schemas.ConviteOut:
    profissao = None
    if convite.profession_id:
        profissao = db.execute(
            select(Profession.slug).where(Profession.id == convite.profession_id)
        ).scalar_one_or_none()
    quem = None
    if convite.invited_by_user_id:
        quem = db.execute(
            select(User.name).where(User.id == convite.invited_by_user_id)
        ).scalar_one_or_none()
    return schemas.ConviteOut(
        id=convite.public_id,
        email=convite.email,
        papel=convite.role.key,
        escopo=convite.data_scope,
        profissao=profissao,
        mensagem=convite.message,
        expira_em=convite.expires_at,
        convidado_por=quem,
        link=link,
    )


# ---------------- dentro da conta ----------------
@router.get("/workspace/team", response_model=schemas.EquipeOut)
def equipe(ctx: Contexto = Depends(exigir("members.manage"))):
    membros = []
    for membership, usuario, perfil in servico.listar(ctx.db, ctx):
        membros.append(schemas.MembroDetalheOut(
            id=membership.public_id,
            nome=usuario.name,
            email=usuario.email,
            papel=membership.role.key,
            papel_nome=rbac.PAPEIS.get(membership.role.key, {}).get("name", membership.role.key),
            escopo=membership.data_scope,
            status=membership.status,
            sou_eu=membership.id == ctx.membership.id,
            atende=perfil is not None,
            profissional_id=perfil.public_id if perfil else None,
        ))
    convites = [convite_out(c, ctx.db) for c in servico.convites_abertos(ctx.db, ctx)]
    return schemas.EquipeOut(membros=membros, convites=convites)


@router.post("/workspace/invitations", response_model=schemas.ConviteOut, status_code=201)
def convidar(dados: schemas.ConviteIn, request: Request,
             ctx: Contexto = Depends(exigir("members.manage"))):
    """Cria o convite e devolve o link uma única vez."""
    try:
        convite, token = servico.convidar(ctx.db, ctx, dados)
        # O e-mail vai para a fila e é entregue pelo job, fora da
        # requisição. O link continua voltando na resposta enquanto não
        # houver SMTP configurado — sem ele, um convite enviado por um
        # sistema sem e-mail seria um convite perdido.
        mailer.convite(ctx.db, convite, token, ctx.usuario.name)
        registrar_evento(ctx.db, request=request, action="invitation_create",
                         outcome="allowed", user_id=ctx.usuario.id, tenant_id=ctx.tenant_id,
                         meta=f"papel={dados.papel}")
        corpo = convite_out(convite, ctx.db, link=f"{settings.painel_url}/#/convite/{token}")
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise


@router.post("/workspace/invitations/{public_id}/revoke", response_model=schemas.ConviteOut)
def revogar(public_id: str, request: Request,
            ctx: Contexto = Depends(exigir("members.manage"))):
    try:
        convite = servico.revogar(ctx.db, ctx, public_id)
        registrar_evento(ctx.db, request=request, action="invitation_revoke",
                         outcome="allowed", user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
        corpo = convite_out(convite, ctx.db)
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise


@router.patch("/workspace/members/{public_id}", response_model=schemas.MembroDetalheOut)
def alterar_membro(public_id: str, dados: schemas.MembroIn, request: Request,
                   ctx: Contexto = Depends(exigir("members.manage"))):
    """Papel, escopo e situação. Não dá para editar o próprio acesso."""
    try:
        membership = servico.alterar(ctx.db, ctx, public_id, dados)
        usuario = ctx.db.get(User, membership.user_id)
        registrar_evento(ctx.db, request=request, action="member_update", outcome="allowed",
                         user_id=ctx.usuario.id, tenant_id=ctx.tenant_id,
                         meta=f"alvo={membership.public_id}")
        corpo = schemas.MembroDetalheOut(
            id=membership.public_id, nome=usuario.name, email=usuario.email,
            papel=membership.role.key,
            papel_nome=rbac.PAPEIS.get(membership.role.key, {}).get("name", membership.role.key),
            escopo=membership.data_scope, status=membership.status, sou_eu=False,
        )
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise


# ---------------- aceite (público) ----------------
@router.get("/invitations/{token}", response_model=schemas.ConvitePublicoOut)
def ver_convite(token: str, db: Session = Depends(get_db)):
    """O que a tela de aceite mostra. Não exige sessão."""
    convite = servico.por_token(db, token)
    with sem_escopo_de_tenant():
        ja_tem_conta = db.execute(
            select(User.id).where(User.email == convite.email)
        ).first() is not None
    return schemas.ConvitePublicoOut(
        workspace=convite.tenant.name,
        papel=convite.role.key,
        papel_nome=rbac.PAPEIS.get(convite.role.key, {}).get("name", convite.role.key),
        email=convite.email,
        mensagem=convite.message,
        expira_em=convite.expires_at,
        ja_tem_conta=ja_tem_conta,
    )


@router.post("/invitations/{token}/accept", response_model=schemas.MeOut)
def aceitar_convite(token: str, dados: schemas.AceitarConviteIn, request: Request,
                    response: Response, db: Session = Depends(get_db)):
    """Aceita o convite e já deixa a pessoa dentro, com sessão aberta.

    Dois caminhos: quem já tem conta entra com a sessão que tiver (ou faz
    login antes); quem não tem, cria a conta aqui mesmo — e ela nasce
    **sem workspace próprio**, porque o workspace dela é a conta que
    convidou.
    """
    chave = f"invite:{request.client.host if request.client else 'desconhecido'}"
    permitido, espera = limitador.registrar_e_checar(
        chave, settings.VC_RATE_LIMIT_REGISTER, settings.VC_RATE_LIMIT_REGISTER_WINDOW
    )
    if not permitido:
        raise errors.excesso_de_tentativas(espera)

    convite = servico.por_token(db, token)

    # Já logado? usa essa pessoa. Senão, cria ou exige senha.
    usuario = None
    cookie = request.cookies.get(settings.VC_SESSION_COOKIE_NAME, "")
    if cookie:
        from app.services import sessions as servico_sessoes

        sessao = servico_sessoes.buscar_vigente(db, cookie)
        if sessao is not None and sessao.user is not None:
            usuario = sessao.user

    try:
        if usuario is None:
            with sem_escopo_de_tenant():
                usuario = servico_auth.buscar_por_email(db, convite.email)
            if usuario is None:
                if not dados.nome or not dados.senha:
                    raise errors.dados_invalidos(
                        "Para aceitar o convite, informe seu nome e crie uma senha.")
                usuario = servico_auth.criar_usuario(
                    db, nome=dados.nome, email=convite.email, senha=dados.senha)
            elif dados.senha:
                if not servico_auth.autenticar(db, convite.email, dados.senha):
                    raise errors.credenciais_invalidas()
            else:
                # Tem conta e não mandou senha: entra pelo login normal.
                raise errors.nao_autenticado("entre_para_aceitar")

        membership = servico.aceitar(db, convite, usuario)
        csrf = abrir_sessao(db, response, request, usuario, membership)
        registrar_evento(db, request=request, action="invitation_accept", outcome="allowed",
                         user_id=usuario.id, tenant_id=membership.tenant_id)
        corpo = montar_me(db, usuario, membership, csrf)
        db.commit()
        return corpo
    except errors.ApiError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        log.exception("falha ao aceitar convite")
        raise errors.conflito("falha_no_convite", "Não foi possível aceitar o convite agora.")
