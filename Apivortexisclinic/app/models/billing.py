"""
Planos e assinatura.

**O que existe aqui e o que não existe**

Existe: o catálogo de planos, o que cada um permite, e a assinatura de
cada conta. Existe também a checagem — criar o profissional de número 6
num plano de 5 é recusado, com mensagem que diz o que fazer.

Cobrança: o gateway é o Asaas (`app/services/asaas.py`). `provider` guarda
"asaas" e `external_ref` o id da assinatura lá. `status` usa os estados que
todo gateway usa (`trialing`, `active`, `past_due`, `canceled`) e só muda
por webhook confirmado. O plano escolhido fica em `pending_plan_id` até o
pagamento chegar. Suporte ainda troca plano à mão por `app/jobs/assinatura.py`.

**Por que limite e não só "plano"**

Guardar o nome do plano e espalhar `if plano == "pro"` pelo código é como
essas coisas apodrecem. Aqui o plano **carrega os números**, e quem
pergunta pergunta pelo limite, não pelo nome. Mudar o que o plano Pro
permite é um UPDATE, não um deploy.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.mysql import BIGINT, DATETIME, DECIMAL
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TABLE_ARGS, Base, PKMixin, TimestampMixin

STATUS_ASSINATURA = ("trialing", "active", "past_due", "canceled")

# Ilimitado é NULO, não um número grande. "9999 pessoas atendidas" é um
# limite; a ausência de limite precisa ser dizível.
SEM_LIMITE = None


class Plan(Base, PKMixin, TimestampMixin):
    """Catálogo de planos. Global — não pertence a nenhuma conta."""

    __tablename__ = "plans"
    __table_args__ = (TABLE_ARGS,)

    key: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    monthly_price: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 2), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ---------------- limites ----------------
    # NULO = sem limite. Ver a nota sobre SEM_LIMITE acima.
    max_professionals: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_members: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_clients: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_storage_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ---------------- o que o plano abre ----------------
    allows_clinical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allows_documents: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allows_export: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allows_reminders: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<Plan {self.key}>"


class Subscription(Base, PKMixin, TimestampMixin):
    """A assinatura de uma conta. Uma por tenant.

    NÃO herda `TenantScoped`: é lida no meio da checagem de limite, que
    acontece dentro de operações já escopadas, e um filtro a mais só
    complicaria sem proteger nada — o `tenant_id` aqui é a chave.
    """

    __tablename__ = "subscriptions"
    __table_args__ = (TABLE_ARGS,)

    tenant_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    plan_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Enum(*STATUS_ASSINATURA, name="subscription_status"),
        nullable=False, default="trialing",
    )

    trial_ends_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)
    canceled_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)

    # O encaixe do gateway, para quando ele existir. Nome genérico de
    # propósito: amarrar a coluna a um fornecedor específico seria
    # decidir agora uma coisa que ainda não foi decidida.
    provider: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    external_ref: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    # Plano escolhido e ainda não pago. Só vira `plan_id` quando o webhook
    # confirma o pagamento.
    pending_plan_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("plans.id", ondelete="SET NULL"), nullable=True
    )

    plan = relationship("Plan", lazy="joined", foreign_keys=[plan_id])
    pending_plan = relationship("Plan", lazy="joined", foreign_keys=[pending_plan_id])

    @property
    def vigente(self) -> bool:
        """Conta em dia. `past_due` continua vigente de propósito.

        Cortar o acesso no primeiro atraso é como se perde cliente por
        um cartão que venceu. Bloquear é decisão de produto, e quando for
        tomada mora aqui — não espalhada pelo código.
        """
        return self.status in ("trialing", "active", "past_due")

    def __repr__(self) -> str:
        return f"<Subscription tenant={self.tenant_id} {self.status}>"


class BillingEvent(Base):
    """Evento já recebido do gateway. `event_id` único = idempotência."""

    __tablename__ = "billing_events"
    __table_args__ = (UniqueConstraint("provider", "event_id"), TABLE_ARGS)

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    event_id: Mapped[str] = mapped_column(String(120), nullable=False)
    event: Mapped[str] = mapped_column(String(60), nullable=False)
    subscription_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), server_default=func.now(3), nullable=False
    )
