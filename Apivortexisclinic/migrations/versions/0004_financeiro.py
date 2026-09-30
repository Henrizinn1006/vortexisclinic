"""Financeiro: livro-caixa.

Uma tabela só, `payments`, e nenhuma alteração destrutiva: as colunas de
pagamento que já existiam em `appointments` continuam lá, agora no papel
de **bandeira de liquidação** (este atendimento está quitado?), mantidas
em sincronia com o livro-caixa dentro da mesma transação.

Nada é apagado por esta migration.

Revision ID: 0004_financeiro
Revises: 0003_negocio
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0004_financeiro"
down_revision: Union[str, None] = "0003_negocio"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ARGS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(26), nullable=False),
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("client_id", mysql.BIGINT(unsigned=True), nullable=False),
        # Nulo quando o pagamento não nasce de um atendimento (avulso, pacote).
        sa.Column("appointment_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("amount", mysql.DECIMAL(10, 2), nullable=False),
        sa.Column("method",
                  sa.Enum("pix", "card", "cash", "transfer", "other", name="payment_method"),
                  nullable=False),
        sa.Column("status", sa.Enum("paid", "refunded", name="payment_status"),
                  nullable=False, server_default="paid"),
        # Data em que o dinheiro entrou — é por ela que o caixa é somado.
        sa.Column("paid_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("note", sa.String(200), nullable=True),
        # Estorno não apaga a linha: marca.
        sa.Column("refunded_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("refund_reason", sa.String(200), nullable=True),
        sa.Column("created_by_user_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"),
                  server_onupdate=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_payments"),
        sa.UniqueConstraint("public_id", name="uq_payments_public_id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_payments_tenant_id_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name="fk_payments_tenant_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"],
                                name="fk_payments_tenant_id_client_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "appointment_id"],
                                ["appointments.tenant_id", "appointments.id"],
                                name="fk_payments_tenant_id_appointment_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"],
                                name="fk_payments_created_by_user_id", ondelete="SET NULL"),
        **ARGS,
    )
    op.create_index("ix_payments_tenant_id", "payments", ["tenant_id"])
    op.create_index("ix_payments_tenant_id_paid_at", "payments", ["tenant_id", "paid_at"])
    op.create_index("ix_payments_tenant_id_client_id_paid_at",
                    "payments", ["tenant_id", "client_id", "paid_at"])
    op.create_index("ix_payments_tenant_id_appointment_id", "payments", ["tenant_id", "appointment_id"])


def downgrade() -> None:
    op.drop_table("payments")
