"""
appointments — o encontro: atendimento, sessão ou consulta.

O rótulo muda por profissão (terminologia da conta); a entidade é uma só.

Decisões que estão na tabela, não no código:

- **FK composta** para cliente e profissional: `(tenant_id, client_id)` e
  `(tenant_id, professional_id)`. Atendimento de uma conta não consegue
  apontar para cliente ou profissional de outra.
- **`professional_id` é obrigatório**: todo atendimento tem dono, e é isso
  que sustenta o escopo "só os meus".
- **Dinheiro em `DECIMAL(10,2)`**, nunca float.
- **Conteúdo clínico não mora aqui.** `note` é observação operacional
  ("remarcou", "chegou atrasado"). Registro de sessão tem tabela própria,
  cifra e permissão própria — administrar a agenda não abre prontuário.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (Enum, ForeignKey, ForeignKeyConstraint, Index, SmallInteger,
                        String, Text, UniqueConstraint)
from sqlalchemy.dialects.mysql import BIGINT, DATETIME, DECIMAL
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TABLE_ARGS, Base, PKMixin, TenantScoped, TimestampMixin

MODALIDADES = ("in_person", "online")
# agendado → confirmado → realizado | falta ; qualquer um → cancelado
STATUS = ("scheduled", "confirmed", "done", "no_show", "cancelled")
PAGAMENTO = ("pending", "paid", "waived")
METODOS = ("pix", "card", "cash", "transfer", "other")

# Para onde cada status pode ir. Transição fora daqui é recusada.
TRANSICOES = {
    "scheduled": {"confirmed", "done", "no_show", "cancelled"},
    "confirmed": {"done", "no_show", "cancelled", "scheduled"},
    "done": {"no_show", "cancelled"},          # correção de lançamento
    "no_show": {"done", "cancelled"},
    "cancelled": set(),                         # cancelado não volta: crie outro
}

# Status que ocupam o horário do profissional (cancelado libera a vaga).
OCUPAM_HORARIO = ("scheduled", "confirmed", "done", "no_show")


class Appointment(Base, PKMixin, TenantScoped, TimestampMixin):
    __tablename__ = "appointments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_appointments_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "series_id"],
            ["appointment_series.tenant_id", "appointment_series.id"],
            # RESTRICT e não SET NULL: tenant_id é NOT NULL, e o MySQL
            # recusa SET NULL em FK composta com coluna obrigatória.
            # Série não se apaga — se encerra (status = ended).
            name="fk_appointments_tenant_id_series_id", ondelete="RESTRICT",
        ),
        Index("ix_appointments_tenant_id_series_id", "tenant_id", "series_id"),
        ForeignKeyConstraint(
            ["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"],
            name="fk_appointments_tenant_id_client_id", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "professional_id"], ["professionals.tenant_id", "professionals.id"],
            name="fk_appointments_tenant_id_professional_id", ondelete="RESTRICT",
        ),
        Index("ix_appointments_tenant_id_start_at", "tenant_id", "start_at"),
        # A consulta da agenda e a checagem de conflito usam este:
        Index("ix_appointments_tenant_id_professional_id_start_at",
              "tenant_id", "professional_id", "start_at"),
        Index("ix_appointments_tenant_id_client_id_start_at", "tenant_id", "client_id", "start_at"),
        Index("ix_appointments_tenant_id_payment_status_start_at",
              "tenant_id", "payment_status", "start_at"),
        TABLE_ARGS,
    )

    client_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    professional_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)

    # Sempre UTC. O fuso de exibição é do tenant.
    start_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    duration_min: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=50)

    modality: Mapped[str] = mapped_column(
        Enum(*MODALIDADES, name="appointment_modality"), nullable=False, default="in_person"
    )
    status: Mapped[str] = mapped_column(
        Enum(*STATUS, name="appointment_status"), nullable=False, default="scheduled"
    )

    price: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 2), nullable=True)
    payment_status: Mapped[str] = mapped_column(
        Enum(*PAGAMENTO, name="appointment_payment_status"), nullable=False, default="pending"
    )
    payment_method: Mapped[Optional[str]] = mapped_column(
        Enum(*METODOS, name="appointment_payment_method"), nullable=True
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)

    # Série recorrente de origem. Nulo para atendimento avulso.
    # A série é um MOLDE: depois de nascer, cada ocorrência tem vida
    # própria — remarcar uma não mexe nas irmãs, e mexer na série não
    # reescreve quem já existe.
    series_id: Mapped[Optional[int]] = mapped_column(BIGINT(unsigned=True), nullable=True)
    series_index: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)

    cancelled_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    client = relationship(
        "Client",
        primaryjoin="and_(Appointment.tenant_id == Client.tenant_id, "
                    "Appointment.client_id == Client.id)",
        foreign_keys="[Appointment.tenant_id, Appointment.client_id]",
        lazy="joined",
        viewonly=True,
    )

    @property
    def end_at(self) -> datetime:
        from datetime import timedelta

        return self.start_at + timedelta(minutes=self.duration_min or 0)

    def pode_ir_para(self, novo: str) -> bool:
        return novo in TRANSICOES.get(self.status, set())

    def __repr__(self) -> str:
        return f"<Appointment {self.public_id} {self.status}>"
