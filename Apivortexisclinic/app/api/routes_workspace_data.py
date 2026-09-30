"""
Rotas tenant-scoped mínimas — a prova de que o isolamento funciona.

Nenhum módulo de negócio entra nesta etapa (pacientes, agenda, financeiro e
prontuário continuam mockados no painel). O que existe aqui é o menor
conjunto necessário para exercitar, de ponta a ponta:

  - leitura escopada pelo tenant da sessão;
  - 404 (não 403) para recurso de outro tenant;
  - permissão negada por papel;
  - permissão da classe clínica que o OWNER não tem.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from app import errors
from app.api.deps import Contexto, com_tenant, exigir
from app.models.membership import Membership
from app.models.professional import Professional
from app.models.user import User

router = APIRouter(prefix="/workspace", tags=["workspace"])


class ProfissionalOut(BaseModel):
    id: str
    nome_exibicao: str
    profissao: Optional[str] = None
    conselho: Optional[str] = None
    registro: Optional[str] = None
    ativo: bool


class MembroOut(BaseModel):
    id: str
    nome: str
    email: str
    papel: str
    escopo: str
    status: str


@router.get("/professionals", response_model=List[ProfissionalOut])
def listar_profissionais(ctx: Contexto = Depends(com_tenant)):
    """Sem WHERE de tenant nesta consulta — e ainda assim ela é escopada.

    Quem aplica o filtro é a sessão do ORM (db/session.py). Se o contexto
    estiver vazio, a consulta levanta em vez de devolver tudo.
    """
    linhas = ctx.db.execute(select(Professional).order_by(Professional.id)).scalars().all()
    return [
        ProfissionalOut(
            id=p.public_id,
            nome_exibicao=p.display_name,
            profissao=p.profession.slug if p.profession else None,
            conselho=p.council,
            registro=p.registration_number,
            ativo=p.active,
        )
        for p in linhas
    ]


@router.get("/professionals/{public_id}", response_model=ProfissionalOut)
def obter_profissional(public_id: str, ctx: Contexto = Depends(com_tenant)):
    p = ctx.db.execute(
        select(Professional).where(Professional.public_id == public_id)
    ).scalar_one_or_none()
    if p is None:
        # Existe no tenant B? Para o tenant A, não existe. 404, nunca 403.
        raise errors.nao_encontrado("profissional")
    return ProfissionalOut(
        id=p.public_id,
        nome_exibicao=p.display_name,
        profissao=p.profession.slug if p.profession else None,
        conselho=p.council,
        registro=p.registration_number,
        ativo=p.active,
    )


@router.get("/members", response_model=List[MembroOut])
def listar_membros(ctx: Contexto = Depends(exigir("members.manage"))):
    linhas = ctx.db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.tenant_id == ctx.tenant_id)
        .order_by(Membership.id)
    ).all()
    return [
        MembroOut(
            id=m.public_id,
            nome=u.name,
            email=u.email,
            papel=m.role.key,
            escopo=m.data_scope,
            status=m.status,
        )
        for m, u in linhas
    ]


@router.get("/clinical-check")
def checagem_clinica(ctx: Contexto = Depends(exigir("clinical_records.read"))):
    """Rota de prova: só quem tem permissão CLÍNICA entra.

    O OWNER, por decisão de arquitetura, não tem — administrar a conta não
    abre prontuário. Existe teste automatizado garantindo isso.
    """
    return {"ok": True, "workspace": ctx.membership.tenant.public_id}
