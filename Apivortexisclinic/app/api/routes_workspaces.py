"""
Workspaces: listar, criar e trocar.

A troca de workspace é o ponto mais sensível desta etapa. Ela recebe um id
do navegador — e é exatamente por isso que ela não confia nele: o id é
usado apenas para PROCURAR uma membership ativa do usuário autenticado. Se
não achar, responde 404. Não existe caminho em que "mandar outro id" mude o
tenant da sessão.

Trocar de workspace também ROTACIONA o token da sessão: mudança de
privilégio não reaproveita credencial anterior.
"""
from typing import List

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app import errors, schemas
from app.api.deps import Contexto, contexto
from app.api.routes_auth import montar_me, registrar_evento, workspace_out
from app.db.session import get_db
from app.security import cookies
from app.services import auth as servico_auth
from app.services import sessions as servico_sessoes
from app.services import tenants as servico_tenants

router = APIRouter(tags=["workspaces"])


@router.get("/workspaces", response_model=List[schemas.WorkspaceOut])
def listar(ctx: Contexto = Depends(contexto)):
    ativo = ctx.membership.tenant_id if ctx.membership else None
    return [
        workspace_out(m, m.tenant_id == ativo)
        for m in servico_tenants.workspaces_do_usuario(ctx.db, ctx.usuario.id)
    ]


@router.post("/workspaces", response_model=schemas.MeOut, status_code=201)
def criar(dados: schemas.NovoWorkspaceIn, request: Request, ctx: Contexto = Depends(contexto)):
    """Cria mais um workspace para o usuário logado, já como OWNER."""
    try:
        profissao = servico_auth.profissao_por_slug(ctx.db, dados.profissao)
        membership = servico_tenants.criar_workspace(
            ctx.db,
            user_id=ctx.usuario.id,
            nome=dados.nome,
            tipo=dados.tipo,
            profession_id=profissao.id if profissao else None,
        )
        # Declarou profissão ao abrir o workspace: ganha perfil
        # profissional e a concessão clínica explícita, igual ao cadastro.
        servico_auth.preparar_titular(ctx.db, ctx.usuario, membership, profissao)
        registrar_evento(ctx.db, request=request, action="workspace_create", outcome="allowed",
                         user_id=ctx.usuario.id, tenant_id=membership.tenant_id)
        corpo = montar_me(ctx.db, ctx.usuario, ctx.membership)
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise
    except Exception:
        ctx.db.rollback()
        raise errors.conflito("falha_ao_criar_workspace", "Não foi possível criar o workspace agora.")


@router.post("/session/workspace", response_model=schemas.MeOut)
def trocar(dados: schemas.TrocarWorkspaceIn, request: Request, response: Response,
           ctx: Contexto = Depends(contexto)):
    membership = servico_tenants.membership_validada(ctx.db, ctx.usuario.id, dados.workspace_id)
    if membership is None:
        # 404 mesmo quando o workspace existe e é de outra pessoa:
        # 403 aqui responderia "existe, mas não é seu".
        registrar_evento(ctx.db, request=request, action="workspace_switch", outcome="denied",
                         user_id=ctx.usuario.id, meta="sem_membership_ativa")
        ctx.db.commit()
        raise errors.nao_encontrado("workspace")

    ctx.sessao.active_tenant_id = membership.tenant_id
    # Troca de privilégio: token novo (anti session fixation).
    token, csrf = servico_sessoes.rotacionar(ctx.db, ctx.sessao)
    max_age = servico_sessoes.max_age_segundos()
    cookies.gravar_sessao(response, token, max_age)
    cookies.gravar_csrf(response, csrf, max_age)

    registrar_evento(ctx.db, request=request, action="workspace_switch", outcome="allowed",
                     user_id=ctx.usuario.id, tenant_id=membership.tenant_id)
    corpo = montar_me(ctx.db, ctx.usuario, membership, csrf)
    ctx.db.commit()
    return corpo
