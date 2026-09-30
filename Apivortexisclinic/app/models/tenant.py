"""
tenants — o workspace: autônomo, consultório ou clínica.

Tenant NÃO herda TenantScoped: ele é o próprio escopo. O acesso a um tenant
é decidido pela membership do usuário autenticado, nunca por id recebido do
navegador.
"""
from datetime import time
from decimal import Decimal
from typing import Optional

from sqlalchemy import Enum, ForeignKey, String, Text, Time
from sqlalchemy.dialects.mysql import BIGINT, DECIMAL, SMALLINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TABLE_ARGS, Base, PKMixin, TimestampMixin

TIPOS_TENANT = ("solo", "office", "clinic")
STATUS_TENANT = ("trial", "active", "past_due", "suspended", "cancelled")


class Tenant(Base, PKMixin, TimestampMixin):
    __tablename__ = "tenants"
    __table_args__ = (TABLE_ARGS,)

    name: Mapped[str] = mapped_column(String(140), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(
        Enum(*TIPOS_TENANT, name="tenant_type"), nullable=False, default="solo"
    )
    status: Mapped[str] = mapped_column(
        Enum(*STATUS_TENANT, name="tenant_status"), nullable=False, default="trial"
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="America/Sao_Paulo")

    profession_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("professions.id", ondelete="RESTRICT"), nullable=True
    )

    memberships = relationship("Membership", back_populates="tenant")
    settings = relationship("TenantSettings", back_populates="tenant", uselist=False)

    def __repr__(self) -> str:
        return f"<Tenant {self.public_id} {self.slug}>"


class TenantSettings(Base, TimestampMixin):
    """Preferências da conta — jornada, duração padrão, meta e terminologia.

    Duas escolhas que valem explicar:

    **A meta do mês nasce NULA.** Meta inventada vira cobrança em cima de
    um número que ninguém escolheu. Sem meta, a tela mostra estado vazio,
    não uma barra em 0%.

    **A jornada não bloqueia o agendamento.** Ela desenha a grade e sugere
    horários; marcar fora dela é decisão de quem atende, não erro. Quem
    atende sábado às 7h por exceção não precisa mudar a configuração da
    conta para conseguir.
    """

    __tablename__ = "tenant_settings"
    __table_args__ = (TABLE_ARGS,)

    tenant_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # JSON guardado como texto para manter compatibilidade MySQL/MariaDB.
    # Conteúdo validado no servidor: rótulo é texto puro, sem marcação.
    terminology: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")

    # ---------------- jornada ----------------
    workday_start: Mapped[time] = mapped_column(Time, nullable=False,
                                                default=time(8, 0))
    workday_end: Mapped[time] = mapped_column(Time, nullable=False,
                                              default=time(20, 0))
    # Dias da semana em ISO (1=segunda … 7=domingo), separados por vírgula.
    workdays: Mapped[str] = mapped_column(String(20), nullable=False, default="1,2,3,4,5")

    default_duration_min: Mapped[int] = mapped_column(SMALLINT(unsigned=True),
                                                      nullable=False, default=50)
    slot_interval_min: Mapped[int] = mapped_column(SMALLINT(unsigned=True),
                                                   nullable=False, default=10)
    no_show_tolerance_hours: Mapped[int] = mapped_column(SMALLINT(unsigned=True),
                                                         nullable=False, default=24)

    # Nula de propósito: ver docstring.
    monthly_goal: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 2), nullable=True)

    tenant = relationship("Tenant", back_populates="settings")

    @property
    def dias_da_semana(self) -> list:
        return [int(d) for d in self.workdays.split(",") if d.strip().isdigit()]
