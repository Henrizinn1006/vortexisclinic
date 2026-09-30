"""
Escopo de dados — a segunda pergunta depois do tenant.

O tenant já foi resolvido pela sessão e é aplicado automaticamente pelo ORM.
Dentro do tenant ainda existe uma divisão: `memberships.data_scope`.

    "all"  — enxerga toda a conta (dono, recepção)
    "own"  — só as pessoas e os atendimentos que são seus (padrão do
             profissional)

Regra que não pode ser afrouxada: quem está em `own` **sem perfil
profissional** não enxerga nada. É o caso do usuário que perdeu o perfil ou
de um vínculo mal configurado — e a resposta certa é lista vazia, nunca a
conta inteira. Fail-closed também aqui.
"""
from typing import Optional

from sqlalchemy import Select, and_, exists, select

from app.models.appointment import Appointment
from app.models.client import Client, ClientProfessional

# Condição impossível: usada quando o escopo não pode ser resolvido.
FALSO = Client.id == None  # noqa: E711


def clientes(consulta: Select, ctx) -> Select:
    """Aplica o escopo de dados a uma consulta de clientes."""
    if ctx.ve_tudo:
        return consulta
    if ctx.professional_id is None:
        return consulta.where(FALSO)

    vinculo = exists().where(
        and_(
            ClientProfessional.tenant_id == Client.tenant_id,
            ClientProfessional.client_id == Client.id,
            ClientProfessional.professional_id == ctx.professional_id,
            ClientProfessional.ended_at.is_(None),
        )
    )
    return consulta.where(vinculo)


def atendimentos(consulta: Select, ctx) -> Select:
    """Aplica o escopo de dados a uma consulta de atendimentos."""
    if ctx.ve_tudo:
        return consulta
    if ctx.professional_id is None:
        return consulta.where(Appointment.id == None)  # noqa: E711
    return consulta.where(Appointment.professional_id == ctx.professional_id)


def alcanca_cliente(db, ctx, client_id: int) -> bool:
    """O usuário alcança este cliente? Usado antes de escrever."""
    if ctx.ve_tudo:
        return True
    if ctx.professional_id is None:
        return False
    return db.execute(
        select(ClientProfessional.client_id).where(
            ClientProfessional.client_id == client_id,
            ClientProfessional.professional_id == ctx.professional_id,
            ClientProfessional.ended_at.is_(None),
        )
    ).first() is not None


def profissional_alvo(ctx, pedido: Optional[int]) -> Optional[int]:
    """Qual profissional a operação pode usar.

    Em `own`, o único profissional possível é o próprio — pedir outro não
    é "sem permissão", é simplesmente não disponível. Em `all`, o pedido
    vale (já validado como pertencente ao tenant por quem chama).
    """
    if ctx.ve_tudo:
        return pedido or ctx.professional_id
    return ctx.professional_id
