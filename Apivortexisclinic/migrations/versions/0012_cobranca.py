"""Cobrança: plano pendente e registro de eventos do gateway.

Duas coisas:

* `subscriptions.pending_plan_id` — o plano que a conta escolheu e ainda
  não pagou. O plano só muda quando o webhook confirma o pagamento; sem
  isto, iniciar o checkout já daria o plano de graça.
* `billing_events` — um registro por evento recebido do gateway. O
  `event_id` é único: o Asaas reenvia webhook, e processar duas vezes o
  mesmo evento não pode mudar nada.

Revision ID: 0012_cobranca
Revises: 0011_planos
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0012_cobranca"
down_revision: Union[str, None] = "0011_planos"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ARGS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}


def upgrade() -> None:
    op.add_column("subscriptions",
                  sa.Column("pending_plan_id", mysql.BIGINT(unsigned=True), nullable=True))
    op.create_foreign_key("fk_subscriptions_pending_plan_id", "subscriptions", "plans",
                          ["pending_plan_id"], ["id"], ondelete="SET NULL")

    op.create_table(
        "billing_events",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("event_id", sa.String(120), nullable=False),
        sa.Column("event", sa.String(60), nullable=False),
        sa.Column("subscription_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_billing_events"),
        sa.UniqueConstraint("provider", "event_id", name="uq_billing_events_provider_event_id"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"],
                                name="fk_billing_events_subscription_id", ondelete="SET NULL"),
        **ARGS,
    )


def downgrade() -> None:
    op.drop_table("billing_events")
    op.drop_constraint("fk_subscriptions_pending_plan_id", "subscriptions", type_="foreignkey")
    op.drop_column("subscriptions", "pending_plan_id")
