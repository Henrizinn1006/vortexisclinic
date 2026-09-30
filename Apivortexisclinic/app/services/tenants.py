"""
Workspaces: criação, listagem e troca — sempre a partir do usuário autenticado.

A função mais importante deste arquivo é `membership_validada`. É ela que
responde "este usuário pode entrar neste tenant?", e ela é a ÚNICA porta.
Nenhum endpoint aceita tenant vindo do corpo, da query ou de cabeçalho sem
passar por aqui.
"""
import re
import unicodedata
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import rbac
from app.ids import novo_ulid
from app.models.membership import Membership
from app.models.rbac import Role
from app.models.tenant import Tenant, TenantSettings


# ---------------- slug ----------------
def slugify(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower()
    return base[:60] or "workspace"


def slug_disponivel(db: Session, desejado: str) -> str:
    base = slugify(desejado)
    candidato = base
    sufixo = 1
    while db.execute(select(Tenant.id).where(Tenant.slug == candidato)).first() is not None:
        sufixo += 1
        candidato = f"{base}-{sufixo}"[:80]
    return candidato


# ---------------- consultas ----------------
def membership_validada(db: Session, user_id: int, tenant_public_id: str) -> Optional[Membership]:
    """A porta única de acesso a um tenant.

    Devolve a membership ATIVA do usuário autenticado naquele tenant, ou
    None. Quem chama transforma None em 404 — nunca em 403, que confirmaria
    a existência do workspace.
    """
    if not tenant_public_id:
        return None
    return db.execute(
        select(Membership)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .where(
            Membership.user_id == user_id,
            Tenant.public_id == tenant_public_id,
            Membership.status == "active",
        )
    ).scalar_one_or_none()


def membership_por_tenant_id(db: Session, user_id: int, tenant_id: int) -> Optional[Membership]:
    return db.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.tenant_id == tenant_id,
            Membership.status == "active",
        )
    ).scalar_one_or_none()


def workspaces_do_usuario(db: Session, user_id: int) -> List[Membership]:
    return list(
        db.execute(
            select(Membership)
            .join(Tenant, Tenant.id == Membership.tenant_id)
            .where(Membership.user_id == user_id, Membership.status == "active")
            .order_by(Membership.created_at.asc())
        ).scalars()
    )


# ---------------- criação ----------------
def papel(db: Session, chave: str) -> Role:
    role = db.execute(select(Role).where(Role.key == chave)).scalar_one_or_none()
    if role is None:
        raise RuntimeError(f"papel {chave} ausente — rode as migrations (seed de papéis)")
    return role


def criar_workspace(
    db: Session,
    *,
    user_id: int,
    nome: str,
    tipo: str = "solo",
    profession_id: Optional[int] = None,
) -> Membership:
    """Cria tenant + settings + membership OWNER.

    Não faz commit: quem chama decide a fronteira da transação. É isso que
    permite o cadastro inteiro (usuário + workspace + perfil) ser tudo ou
    nada.
    """
    tenant = Tenant(
        public_id=novo_ulid(),
        name=nome.strip(),
        slug=slug_disponivel(db, nome),
        type=tipo,
        status="trial",
        profession_id=profession_id,
    )
    db.add(tenant)
    db.flush()

    db.add(TenantSettings(tenant_id=tenant.id))

    membership = Membership(
        public_id=novo_ulid(),
        tenant_id=tenant.id,
        user_id=user_id,
        role_id=papel(db, rbac.OWNER).id,
        data_scope="all",
        status="active",
    )
    db.add(membership)
    db.flush()
    return membership


def contar_workspaces(db: Session, user_id: int) -> int:
    return int(
        db.execute(
            select(func.count(Membership.id)).where(
                Membership.user_id == user_id, Membership.status == "active"
            )
        ).scalar_one()
    )
