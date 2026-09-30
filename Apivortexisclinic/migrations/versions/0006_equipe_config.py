"""Equipe e configurações da conta.

Cria `invitations` e acrescenta colunas a `tenant_settings`. **Nada é
apagado**: as colunas novas nascem com valor padrão, então contas que já
existem continuam funcionando sem migração de dados.

As duas coisas juntas numa migration só porque são a mesma etapa e
compartilham o destino: sem convite, uma clínica não tem equipe; sem
configuração gravável, a equipe não tem jornada em comum.

Revision ID: 0006_equipe_config
Revises: 0005_prontuario
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0006_equipe_config"
down_revision: Union[str, None] = "0005_prontuario"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ARGS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}


def upgrade() -> None:
    op.create_table(
        "invitations",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(26), nullable=False),
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("email", sa.String(190), nullable=False),
        # O acesso vem decidido no convite; aceitar não escolhe nada.
        sa.Column("role_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("data_scope", sa.Enum("all", "own", name="membership_scope"),
                  nullable=False, server_default="own"),
        sa.Column("profession_id", mysql.BIGINT(unsigned=True), nullable=True),
        # Só o hash. O token existe uma vez, no link.
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.Enum("pending", "accepted", "revoked", name="invitation_status"),
                  nullable=False, server_default="pending"),
        sa.Column("expires_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("accepted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("accepted_user_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("revoked_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("invited_by_user_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("message", sa.String(300), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"),
                  server_onupdate=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_invitations"),
        sa.UniqueConstraint("public_id", name="uq_invitations_public_id"),
        sa.UniqueConstraint("token_hash", name="uq_invitations_token_hash"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name="fk_invitations_tenant_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"],
                                name="fk_invitations_role_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["profession_id"], ["professions.id"],
                                name="fk_invitations_profession_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["accepted_user_id"], ["users.id"],
                                name="fk_invitations_accepted_user_id", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"],
                                name="fk_invitations_invited_by_user_id", ondelete="SET NULL"),
        **ARGS,
    )
    op.create_index("ix_invitations_tenant_id_status", "invitations", ["tenant_id", "status"])
    op.create_index("ix_invitations_email", "invitations", ["email"])

    # ---------------- configurações da conta ----------------
    # Todas com padrão: conta existente continua válida sem tocar em dados.
    op.add_column("tenant_settings",
                  sa.Column("workday_start", sa.Time(), nullable=False,
                            server_default=sa.text("'08:00:00'")))
    op.add_column("tenant_settings",
                  sa.Column("workday_end", sa.Time(), nullable=False,
                            server_default=sa.text("'20:00:00'")))
    op.add_column("tenant_settings",
                  sa.Column("workdays", sa.String(20), nullable=False,
                            server_default="1,2,3,4,5"))
    op.add_column("tenant_settings",
                  sa.Column("default_duration_min", mysql.SMALLINT(unsigned=True),
                            nullable=False, server_default="50"))
    op.add_column("tenant_settings",
                  sa.Column("slot_interval_min", mysql.SMALLINT(unsigned=True),
                            nullable=False, server_default="10"))
    op.add_column("tenant_settings",
                  sa.Column("no_show_tolerance_hours", mysql.SMALLINT(unsigned=True),
                            nullable=False, server_default="24"))
    # Nula de propósito: meta inventada vira cobrança sobre número que
    # ninguém escolheu.
    op.add_column("tenant_settings",
                  sa.Column("monthly_goal", mysql.DECIMAL(10, 2), nullable=True))


def downgrade() -> None:
    """Recusa se houver convite aceito: desfazer apagaria vínculo de gente."""
    conexao = op.get_bind()
    aceitos = conexao.exec_driver_sql(
        "SELECT COUNT(*) FROM invitations WHERE status = 'accepted'").scalar()
    if aceitos:
        raise RuntimeError(
            f"downgrade recusado: {aceitos} convite(s) já aceito(s). "
            "Remover a tabela apagaria o histórico de como cada pessoa entrou na conta."
        )
    for coluna in ("monthly_goal", "no_show_tolerance_hours", "slot_interval_min",
                   "default_duration_min", "workdays", "workday_end", "workday_start"):
        op.drop_column("tenant_settings", coluna)
    op.drop_table("invitations")
