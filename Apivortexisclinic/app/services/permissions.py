"""
Permissão efetiva de uma membership.

    efetivas = permissões do papel
             + concessões vigentes (grant)
             − revogações vigentes (deny)

Concessão/revogação vencida ou revogada não conta. Deny sempre vence grant:
tirar acesso não pode depender da ordem de avaliação.

Não existe atalho por papel. Em lugar nenhum deste arquivo há
`if papel == OWNER: return True`.
"""
from datetime import datetime
from typing import Set

from sqlalchemy.orm import Session

from app import rbac
from app.models.membership import Membership
from app.services.sessions import agora


def _vigente(excecao, momento: datetime) -> bool:
    if excecao.revoked_at is not None:
        return False
    if excecao.starts_at is not None and excecao.starts_at > momento:
        return False
    if excecao.expires_at is not None and excecao.expires_at <= momento:
        return False
    return True


def efetivas(db: Session, membership: Membership) -> Set[str]:
    if membership is None or not membership.ativa:
        return set()

    resultado = set(rbac.permissoes_do_papel(membership.role.key))

    momento = agora()
    concedidas, revogadas = set(), set()
    for excecao in membership.excecoes:
        if not _vigente(excecao, momento):
            continue
        chave = excecao.permission.key
        (concedidas if excecao.effect == "grant" else revogadas).add(chave)

    return (resultado | concedidas) - revogadas


def pode(db: Session, membership: Membership, permissao: str) -> bool:
    return permissao in efetivas(db, membership)


# ---------------- o dono que também atende ----------------
# Permissões clínicas que o titular recebe por ATENDER, não por ser dono.
# `clinical_records.read_others` fica de fora de propósito: dono que atende
# enxerga o próprio prontuário, não o do colega.
CLINICAS_DO_TITULAR = (
    "clinical_records.read",
    "clinical_records.write",
    "documents.read",
    "documents.write",
)

MOTIVO_TITULAR = "Titular com perfil profissional nesta conta"


def conceder_clinicas_ao_titular(db: Session, membership: Membership) -> int:
    """Dá acesso clínico a quem se cadastrou declarando que atende.

    Por que não colocar isso na matriz do papel: porque a regra do produto
    é que **administrar a conta não abre prontuário**, e afrouxar a matriz
    para o caso do consultório de uma pessoa só apagaria a regra para
    todas as clínicas. O acesso aqui vem de uma linha explícita em
    `membership_permissions`, com motivo, autoria e data — visível na
    auditoria e removível com um UPDATE, sem tocar no papel.

    Sem validade: não é cobertura temporária, é o próprio profissional. A
    concessão morre quando o perfil profissional for desativado ou a linha
    for revogada.
    """
    from sqlalchemy import select

    from app.ids import novo_ulid
    from app.models.membership import MembershipPermission
    from app.models.rbac import Permission

    alvo = dict(db.execute(
        select(Permission.key, Permission.id).where(Permission.key.in_(CLINICAS_DO_TITULAR))
    ).all())

    ja_tem = {
        chave for (chave,) in db.execute(
            select(Permission.key)
            .join(MembershipPermission, MembershipPermission.permission_id == Permission.id)
            .where(MembershipPermission.membership_id == membership.id,
                   MembershipPermission.effect == "grant")
        ).all()
    }

    criadas = 0
    for chave, permission_id in alvo.items():
        if chave in ja_tem:
            continue
        db.add(MembershipPermission(
            public_id=novo_ulid(),
            tenant_id=membership.tenant_id,
            membership_id=membership.id,
            permission_id=permission_id,
            effect="grant",
            reason=MOTIVO_TITULAR,
            granted_by_user_id=membership.user_id,
            expires_at=None,
        ))
        criadas += 1
    return criadas
