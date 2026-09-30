"""
Agenda recorrente e bloqueios de horário.

**Por que a recorrência materializa as ocorrências**

Havia dois caminhos: guardar a regra e expandir na hora de mostrar, ou
gerar as linhas de uma vez. O segundo ganhou, e por um motivo prático: no
consultório, cada sessão vira um fato próprio — uma é remarcada, outra
vira falta, outra tem valor diferente porque foi mais longa. Regra
expandida ao vivo não tem onde pendurar isso; teria que ganhar uma tabela
de exceções, e aí seriam duas fontes de verdade para a mesma pergunta.

Então a série é um **molde**: ela cria atendimentos de verdade, cada um
com vida própria, e continua existindo só para responder "quais são
irmãos deste" quando alguém quiser mexer em todos de uma vez.

O horizonte é finito de propósito (`MAX_OCORRENCIAS`). Recorrência
infinita vira agenda infinita, e agenda infinita é agenda que ninguém
consegue limpar.

**Por que o bloqueio não é um atendimento fantasma**

Férias, feriado e almoço poderiam ser gravados como atendimentos de um
cliente falso. Seria mais curto e estragaria todo o resto: eles entrariam
nas contagens, no financeiro, na presença, e um dia alguém tentaria
cobrar por eles. Bloqueio é outra coisa, então é outra tabela — e o que
ele faz é só uma: ocupar horário.
"""
from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from sqlalchemy import (Date, Enum, ForeignKey, ForeignKeyConstraint, Index, String,
                        Time, UniqueConstraint)
from sqlalchemy.dialects.mysql import BIGINT, DATETIME, DECIMAL, SMALLINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TABLE_ARGS, Base, PKMixin, TenantScoped, TimestampMixin

FREQUENCIAS = ("weekly", "biweekly", "monthly")
STATUS_SERIE = ("active", "ended")
MAX_OCORRENCIAS = 52

TIPOS_BLOQUEIO = ("vacation", "holiday", "break", "other")


class AppointmentSeries(Base, PKMixin, TenantScoped, TimestampMixin):
    """O molde de uma recorrência. Não aparece na agenda — os filhos aparecem."""

    __tablename__ = "appointment_series"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_appointment_series_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"],
            name="fk_appointment_series_tenant_id_client_id", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "professional_id"], ["professionals.tenant_id", "professionals.id"],
            name="fk_appointment_series_tenant_id_professional_id", ondelete="RESTRICT",
        ),
        Index("ix_appointment_series_tenant_id_client_id", "tenant_id", "client_id"),
        TABLE_ARGS,
    )

    client_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    professional_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)

    frequency: Mapped[str] = mapped_column(
        Enum(*FREQUENCIAS, name="series_frequency"), nullable=False, default="weekly"
    )
    # Horário e duração do molde. Cada ocorrência nasce com isto e pode
    # divergir depois — a série não volta a mandar em quem já nasceu.
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration_min: Mapped[int] = mapped_column(SMALLINT(unsigned=True), nullable=False, default=50)
    modality: Mapped[str] = mapped_column(
        Enum("in_person", "online", name="appointment_modality"),
        nullable=False, default="in_person",
    )
    price: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 2), nullable=True)

    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    occurrences: Mapped[int] = mapped_column(SMALLINT(unsigned=True), nullable=False, default=8)

    status: Mapped[str] = mapped_column(
        Enum(*STATUS_SERIE, name="series_status"), nullable=False, default="active"
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    client = relationship(
        "Client",
        primaryjoin="and_(AppointmentSeries.tenant_id == Client.tenant_id, "
                    "AppointmentSeries.client_id == Client.id)",
        foreign_keys="[AppointmentSeries.tenant_id, AppointmentSeries.client_id]",
        lazy="joined", viewonly=True,
    )

    def __repr__(self) -> str:
        return f"<AppointmentSeries {self.public_id} {self.frequency}>"


class ScheduleBlock(Base, PKMixin, TenantScoped, TimestampMixin):
    """Horário indisponível: férias, feriado, almoço, compromisso.

    `professional_id` nulo significa a conta inteira — feriado não é de
    uma pessoa só. Bloqueio **ocupa horário e nada mais**: não entra em
    contagem, em presença nem no financeiro.
    """

    __tablename__ = "schedule_blocks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_schedule_blocks_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "professional_id"], ["professionals.tenant_id", "professionals.id"],
            name="fk_schedule_blocks_tenant_id_professional_id", ondelete="CASCADE",
        ),
        Index("ix_schedule_blocks_tenant_id_start_at", "tenant_id", "start_at"),
        TABLE_ARGS,
    )

    # Nulo = vale para toda a conta.
    professional_id: Mapped[Optional[int]] = mapped_column(BIGINT(unsigned=True), nullable=True)

    start_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)

    kind: Mapped[str] = mapped_column(
        Enum(*TIPOS_BLOQUEIO, name="block_kind"), nullable=False, default="other"
    )
    # Texto puro, mostrado com escape. Não é registro clínico: "férias",
    # "almoço", "congresso" — nada sobre quem é atendido.
    title: Mapped[str] = mapped_column(String(120), nullable=False)

    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    def cobre(self, inicio: datetime, fim: datetime) -> bool:
        return inicio < self.end_at and fim > self.start_at

    def __repr__(self) -> str:
        return f"<ScheduleBlock {self.public_id} {self.kind}>"
