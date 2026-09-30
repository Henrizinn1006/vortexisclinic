"""
payments — o livro-caixa.

Uma linha por dinheiro que entrou. Não é "um campo a mais no
atendimento": é registro contábil, e por isso tem regras próprias.

**Por que uma tabela e não só a bandeira no atendimento**

`appointments.payment_status` responde "este atendimento está quitado?".
Útil para pendências, inútil para o resto: não diz quando o dinheiro
entrou, por qual meio, nem permite estorno sem apagar história. Um
consultório precisa das duas respostas, e elas são diferentes.

**Como as duas convivem sem divergir**

A baixa grava o pagamento **e** atualiza a bandeira do atendimento na
mesma transação. Nunca uma sem a outra. Existe teste para isso.

**Estorno não apaga**

Dinheiro devolvido vira `status = refunded`, com motivo e data. A linha
original continua lá. Apagar lançamento é como rasurar livro-caixa —
some a explicação junto com o erro.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (Enum, ForeignKey, ForeignKeyConstraint, Index, String,
                        Text, UniqueConstraint)
from sqlalchemy.dialects.mysql import BIGINT, DATETIME, DECIMAL
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TABLE_ARGS, Base, PKMixin, TenantScoped, TimestampMixin

METODOS = ("pix", "card", "cash", "transfer", "other")
STATUS = ("paid", "refunded")


class Payment(Base, PKMixin, TenantScoped, TimestampMixin):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_payments_tenant_id_id"),
        # FK compostas: o lançamento não cruza contas nem por erro da aplicação.
        ForeignKeyConstraint(
            ["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"],
            name="fk_payments_tenant_id_client_id", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "appointment_id"], ["appointments.tenant_id", "appointments.id"],
            name="fk_payments_tenant_id_appointment_id", ondelete="RESTRICT",
        ),
        # O caixa é consultado por DATA DO PAGAMENTO, não do atendimento.
        Index("ix_payments_tenant_id_paid_at", "tenant_id", "paid_at"),
        Index("ix_payments_tenant_id_client_id_paid_at", "tenant_id", "client_id", "paid_at"),
        Index("ix_payments_tenant_id_appointment_id", "tenant_id", "appointment_id"),
        TABLE_ARGS,
    )

    client_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    # Opcional: pagamento avulso ou pacote não nasce de um atendimento.
    appointment_id: Mapped[Optional[int]] = mapped_column(BIGINT(unsigned=True), nullable=True)

    amount: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    method: Mapped[str] = mapped_column(Enum(*METODOS, name="payment_method"), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(*STATUS, name="payment_status"), nullable=False, default="paid"
    )

    # Quando o dinheiro entrou. É por este campo que "recebido no mês"
    # é calculado — regime de caixa, que é o que a pessoa quer saber.
    paid_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)

    note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    refunded_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)
    refund_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    client = relationship(
        "Client",
        primaryjoin="and_(Payment.tenant_id == Client.tenant_id, "
                    "Payment.client_id == Client.id)",
        foreign_keys="[Payment.tenant_id, Payment.client_id]",
        lazy="joined", viewonly=True,
    )
    appointment = relationship(
        "Appointment",
        primaryjoin="and_(Payment.tenant_id == Appointment.tenant_id, "
                    "Payment.appointment_id == Appointment.id)",
        foreign_keys="[Payment.tenant_id, Payment.appointment_id]",
        lazy="joined", viewonly=True,
    )

    @property
    def vale(self) -> bool:
        """Lançamento que ainda conta no caixa."""
        return self.status == "paid"

    def __repr__(self) -> str:
        return f"<Payment {self.public_id} {self.status}>"
