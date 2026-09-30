"""Fila de e-mail e verificação de endereço.

Duas tabelas. Nada é apagado.

`email_messages` não herda o escopo de tenant de propósito: verificação de
e-mail e redefinição de senha acontecem antes de haver workspace ativo e
cairiam no fail-closed. `tenant_id` existe como referência.

Revision ID: 0010_email
Revises: 0009_lgpd
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0010_email"
down_revision: Union[str, None] = "0009_lgpd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ARGS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}


def upgrade() -> None:
    op.create_table(
        "email_messages",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(26), nullable=False),
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("to_email", sa.String(190), nullable=False),
        sa.Column("to_name", sa.String(120), nullable=True),
        sa.Column("kind",
                  sa.Enum("verify_email", "password_reset", "invitation",
                          "appointment_reminder", "other", name="email_kind"),
                  nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        # Texto puro. Sem HTML de propósito: nada aqui precisa de layout, e
        # marcação é uma superfície a mais.
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.Enum("queued", "sent", "failed", "cancelled", name="email_status"),
                  nullable=False, server_default="queued"),
        sa.Column("scheduled_for", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("sent_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(300), nullable=True),
        # Idempotência: o job de lembretes pode rodar dez vezes no dia.
        sa.Column("dedupe_key", sa.String(120), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"),
                  server_onupdate=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_email_messages"),
        sa.UniqueConstraint("public_id", name="uq_email_messages_public_id"),
        sa.UniqueConstraint("dedupe_key", name="uq_email_messages_dedupe_key"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name="fk_email_messages_tenant_id", ondelete="SET NULL"),
        **ARGS,
    )
    op.create_index("ix_email_messages_status_scheduled_for",
                    "email_messages", ["status", "scheduled_for"])
    op.create_index("ix_email_messages_tenant_id_created_at",
                    "email_messages", ["tenant_id", "created_at"])

    op.create_table(
        "email_verifications",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(26), nullable=False),
        sa.Column("user_id", mysql.BIGINT(unsigned=True), nullable=False),
        # Guardado porque a pessoa pode trocar de e-mail antes de clicar:
        # aí o token não vale mais.
        sa.Column("email", sa.String(190), nullable=False),
        # Só o hash. O token existe uma vez, no link.
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("used_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"),
                  server_onupdate=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_email_verifications"),
        sa.UniqueConstraint("public_id", name="uq_email_verifications_public_id"),
        sa.UniqueConstraint("token_hash", name="uq_email_verifications_token_hash"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name="fk_email_verifications_user_id", ondelete="CASCADE"),
        **ARGS,
    )
    op.create_index("ix_email_verifications_user_id", "email_verifications", ["user_id"])


def downgrade() -> None:
    op.drop_table("email_verifications")
    op.drop_table("email_messages")
