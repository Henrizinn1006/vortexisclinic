"""Agenda recorrente e bloqueios de horário.

Duas tabelas novas e duas colunas em `appointments`. **Nada é apagado**:
as colunas nascem nulas, e atendimento avulso continua sendo atendimento
avulso.

Revision ID: 0007_agenda
Revises: 0006_equipe_config
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0007_agenda"
down_revision: Union[str, None] = "0006_equipe_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ARGS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}


def upgrade() -> None:
    # ---------------- o molde da recorrência ----------------
    op.create_table(
        "appointment_series",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(26), nullable=False),
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("client_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("professional_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("frequency",
                  sa.Enum("weekly", "biweekly", "monthly", name="series_frequency"),
                  nullable=False, server_default="weekly"),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("duration_min", mysql.SMALLINT(unsigned=True), nullable=False,
                  server_default="50"),
        sa.Column("modality",
                  sa.Enum("in_person", "online", name="appointment_modality"),
                  nullable=False, server_default="in_person"),
        sa.Column("price", mysql.DECIMAL(10, 2), nullable=True),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("occurrences", mysql.SMALLINT(unsigned=True), nullable=False,
                  server_default="8"),
        sa.Column("status", sa.Enum("active", "ended", name="series_status"),
                  nullable=False, server_default="active"),
        sa.Column("ended_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("created_by_user_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"),
                  server_onupdate=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_appointment_series"),
        sa.UniqueConstraint("public_id", name="uq_appointment_series_public_id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_appointment_series_tenant_id_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name="fk_appointment_series_tenant_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"],
                                name="fk_appointment_series_tenant_id_client_id",
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "professional_id"],
                                ["professionals.tenant_id", "professionals.id"],
                                name="fk_appointment_series_tenant_id_professional_id",
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"],
                                name="fk_appointment_series_created_by_user_id",
                                ondelete="SET NULL"),
        **ARGS,
    )
    op.create_index("ix_appointment_series_tenant_id", "appointment_series", ["tenant_id"])
    op.create_index("ix_appointment_series_tenant_id_client_id",
                    "appointment_series", ["tenant_id", "client_id"])

    # ---------------- horário indisponível ----------------
    # Tabela própria, e não "atendimento de um cliente falso": bloqueio não
    # pode entrar em contagem, presença nem financeiro.
    op.create_table(
        "schedule_blocks",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(26), nullable=False),
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=False),
        # Nulo = vale para a conta inteira (feriado não é de uma pessoa só).
        sa.Column("professional_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("start_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("end_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("kind",
                  sa.Enum("vacation", "holiday", "break", "other", name="block_kind"),
                  nullable=False, server_default="other"),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("created_by_user_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"),
                  server_onupdate=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_schedule_blocks"),
        sa.UniqueConstraint("public_id", name="uq_schedule_blocks_public_id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_schedule_blocks_tenant_id_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name="fk_schedule_blocks_tenant_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id", "professional_id"],
                                ["professionals.tenant_id", "professionals.id"],
                                name="fk_schedule_blocks_tenant_id_professional_id",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"],
                                name="fk_schedule_blocks_created_by_user_id",
                                ondelete="SET NULL"),
        **ARGS,
    )
    op.create_index("ix_schedule_blocks_tenant_id", "schedule_blocks", ["tenant_id"])
    op.create_index("ix_schedule_blocks_tenant_id_start_at",
                    "schedule_blocks", ["tenant_id", "start_at"])

    # ---------------- o vínculo do atendimento com a série ----------------
    op.add_column("appointments",
                  sa.Column("series_id", mysql.BIGINT(unsigned=True), nullable=True))
    op.add_column("appointments",
                  sa.Column("series_index", sa.SmallInteger(), nullable=True))
    op.create_index("ix_appointments_tenant_id_series_id",
                    "appointments", ["tenant_id", "series_id"])
    op.create_foreign_key("fk_appointments_tenant_id_series_id", "appointments",
                          "appointment_series",
                          ["tenant_id", "series_id"], ["tenant_id", "id"], ondelete="RESTRICT")


def downgrade() -> None:
    op.drop_constraint("fk_appointments_tenant_id_series_id", "appointments", type_="foreignkey")
    op.drop_index("ix_appointments_tenant_id_series_id", table_name="appointments")
    op.drop_column("appointments", "series_index")
    op.drop_column("appointments", "series_id")
    op.drop_table("schedule_blocks")
    op.drop_table("appointment_series")
