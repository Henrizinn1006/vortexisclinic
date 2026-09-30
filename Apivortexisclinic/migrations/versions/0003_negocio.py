"""Módulos de negócio: pessoas atendidas e atendimentos.

Entram aqui as duas primeiras tabelas de produto. Financeiro ainda **não**
ganha tabela própria: valor e situação de pagamento vivem no atendimento,
que é onde nascem. `payments`, baixa e métodos entram na etapa do financeiro.

O que esta migration prova na prática:

  - `UNIQUE (tenant_id, id)` em `clients` existe para sustentar FK composta;
  - `appointments` referencia **(tenant_id, client_id)** e
    **(tenant_id, professional_id)** — o banco recusa, sozinho, cruzar
    contas, mesmo que a aplicação erre;
  - `client_professionals` tem PK `(tenant_id, client_id, professional_id)`:
    é a tabela que responde "quais são os meus" para o escopo `own`.

Revision ID: 0003_negocio
Revises: 0002_seed
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0003_negocio"
down_revision: Union[str, None] = "0002_seed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ARGS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}


def _timestamps():
    return [
        sa.Column("created_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"),
                  server_onupdate=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
    ]


def upgrade() -> None:
    # ---------------- pessoas atendidas ----------------
    op.create_table(
        "clients",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(26), nullable=False),
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("name", sa.String(140), nullable=False),
        sa.Column("email", sa.String(190), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("guardian", sa.Text(), nullable=True),
        sa.Column("status", sa.Enum("active", "inactive", "archived", name="client_status"),
                  nullable=False, server_default="active"),
        sa.Column("frequency",
                  sa.Enum("weekly", "biweekly", "monthly", "irregular", name="client_frequency"),
                  nullable=False, server_default="weekly"),
        sa.Column("default_modality",
                  sa.Enum("in_person", "online", name="appointment_modality"),
                  nullable=False, server_default="in_person"),
        sa.Column("default_price", mysql.DECIMAL(10, 2), nullable=True),
        sa.Column("started_at", sa.Date(), nullable=True),
        # Observação administrativa. Conteúdo clínico NÃO entra aqui.
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("archived_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("anonymized_at", mysql.DATETIME(fsp=3), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_clients"),
        sa.UniqueConstraint("public_id", name="uq_clients_public_id"),
        # Sustenta as FKs compostas das tabelas que apontam para cliente.
        sa.UniqueConstraint("tenant_id", "id", name="uq_clients_tenant_id_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name="fk_clients_tenant_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"],
                                name="fk_clients_created_by_user_id", ondelete="SET NULL"),
        **ARGS,
    )
    op.create_index("ix_clients_tenant_id", "clients", ["tenant_id"])
    op.create_index("ix_clients_tenant_id_status_name", "clients", ["tenant_id", "status", "name"])
    op.create_index("ix_clients_tenant_id_created_at", "clients", ["tenant_id", "created_at"])

    # ---------------- quem atende quem ----------------
    op.create_table(
        "client_professionals",
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("client_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("professional_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("started_at", sa.Date(), nullable=True),
        sa.Column("ended_at", sa.Date(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("tenant_id", "client_id", "professional_id",
                                name="pk_client_professionals"),
        sa.ForeignKeyConstraint(["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"],
                                name="fk_client_professionals_tenant_id_client_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id", "professional_id"],
                                ["professionals.tenant_id", "professionals.id"],
                                name="fk_client_professionals_tenant_id_professional_id",
                                ondelete="CASCADE"),
        **ARGS,
    )
    op.create_index("ix_client_professionals_tenant_id_professional_id",
                    "client_professionals", ["tenant_id", "professional_id"])

    # ---------------- atendimentos ----------------
    op.create_table(
        "appointments",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(26), nullable=False),
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("client_id", mysql.BIGINT(unsigned=True), nullable=False),
        # Obrigatório: todo atendimento tem dono. É o que sustenta o escopo "own".
        sa.Column("professional_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("start_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("duration_min", sa.SmallInteger(), nullable=False, server_default="50"),
        sa.Column("modality", sa.Enum("in_person", "online", name="appointment_modality"),
                  nullable=False, server_default="in_person"),
        sa.Column("status",
                  sa.Enum("scheduled", "confirmed", "done", "no_show", "cancelled",
                          name="appointment_status"),
                  nullable=False, server_default="scheduled"),
        sa.Column("price", mysql.DECIMAL(10, 2), nullable=True),
        sa.Column("payment_status",
                  sa.Enum("pending", "paid", "waived", name="appointment_payment_status"),
                  nullable=False, server_default="pending"),
        sa.Column("payment_method",
                  sa.Enum("pix", "card", "cash", "transfer", "other",
                          name="appointment_payment_method"), nullable=True),
        sa.Column("paid_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("cancelled_reason", sa.String(200), nullable=True),
        # Observação operacional (remarcou, chegou atrasado).
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", mysql.BIGINT(unsigned=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_appointments"),
        sa.UniqueConstraint("public_id", name="uq_appointments_public_id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_appointments_tenant_id_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name="fk_appointments_tenant_id", ondelete="RESTRICT"),
        # As duas FKs compostas: cruzar contas é impossível no banco.
        sa.ForeignKeyConstraint(["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"],
                                name="fk_appointments_tenant_id_client_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "professional_id"],
                                ["professionals.tenant_id", "professionals.id"],
                                name="fk_appointments_tenant_id_professional_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"],
                                name="fk_appointments_created_by_user_id", ondelete="SET NULL"),
        **ARGS,
    )
    op.create_index("ix_appointments_tenant_id_start_at", "appointments", ["tenant_id", "start_at"])
    # Agenda do profissional e checagem de conflito de horário.
    op.create_index("ix_appointments_tenant_id_professional_id_start_at",
                    "appointments", ["tenant_id", "professional_id", "start_at"])
    op.create_index("ix_appointments_tenant_id_client_id_start_at",
                    "appointments", ["tenant_id", "client_id", "start_at"])
    # Pendências financeiras.
    op.create_index("ix_appointments_tenant_id_payment_status_start_at",
                    "appointments", ["tenant_id", "payment_status", "start_at"])


def downgrade() -> None:
    op.drop_table("appointments")
    op.drop_table("client_professionals")
    op.drop_table("clients")
