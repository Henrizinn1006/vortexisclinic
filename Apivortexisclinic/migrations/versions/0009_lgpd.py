"""Direitos do titular: consentimento, pedido e retenção.

Quatro tabelas. Nada é apagado.

A mais importante delas é `retention_policies`, e a coisa mais importante
sobre ela é que **ela nasce vazia**. O prazo de guarda depende do conselho
profissional de cada categoria, e inventar um número daria aparência de
conformidade a um chute. Sem política com base legal preenchida, nada é
apagado automaticamente — e a ausência fica visível, em vez de virar um
padrão silencioso.

Revision ID: 0009_lgpd
Revises: 0008_documentos
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0009_lgpd"
down_revision: Union[str, None] = "0008_documentos"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ARGS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}

ALVOS = ("registration", "appointments", "payments", "clinical", "documents", "other")


def upgrade() -> None:
    # ---------------- consentimento ----------------
    op.create_table(
        "consents",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(26), nullable=False),
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("client_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("kind",
                  sa.Enum("terms", "privacy", "clinical_treatment", "image", "communication",
                          name="consent_kind"),
                  nullable=False),
        # Versão do texto aceito: sem ela, "a pessoa aceitou" não diz nada
        # depois que o texto mudar.
        sa.Column("version", sa.String(40), nullable=False, server_default="1"),
        sa.Column("text_hash", sa.String(64), nullable=True),
        sa.Column("granted_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("revoked_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("source", sa.Enum("in_person", "online", "imported", name="consent_source"),
                  nullable=False, server_default="in_person"),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("registered_by_user_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"),
                  server_onupdate=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_consents"),
        sa.UniqueConstraint("public_id", name="uq_consents_public_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name="fk_consents_tenant_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"],
                                name="fk_consents_tenant_id_client_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["registered_by_user_id"], ["users.id"],
                                name="fk_consents_registered_by_user_id", ondelete="SET NULL"),
        **ARGS,
    )
    op.create_index("ix_consents_tenant_id", "consents", ["tenant_id"])
    op.create_index("ix_consents_tenant_id_client_id_kind",
                    "consents", ["tenant_id", "client_id", "kind"])

    # ---------------- pedido do titular ----------------
    op.create_table(
        "data_requests",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(26), nullable=False),
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("client_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("kind",
                  sa.Enum("access", "portability", "rectification", "erasure",
                          "restriction", "revoke_consent", "information",
                          name="data_request_kind"),
                  nullable=False),
        sa.Column("status",
                  sa.Enum("open", "in_progress", "done", "refused", name="data_request_status"),
                  nullable=False, server_default="open"),
        sa.Column("requested_at", mysql.DATETIME(fsp=3), nullable=False),
        # Nulo por padrão: quem registra informa, se a conta tiver prazo.
        # Nenhum número é chutado aqui.
        sa.Column("due_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("closed_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("requester", sa.String(120), nullable=False, server_default="titular"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("outcome_note", sa.Text(), nullable=True),
        sa.Column("registered_by_user_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"),
                  server_onupdate=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_data_requests"),
        sa.UniqueConstraint("public_id", name="uq_data_requests_public_id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_data_requests_tenant_id_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name="fk_data_requests_tenant_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"],
                                name="fk_data_requests_tenant_id_client_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["registered_by_user_id"], ["users.id"],
                                name="fk_data_requests_registered_by_user_id",
                                ondelete="SET NULL"),
        **ARGS,
    )
    op.create_index("ix_data_requests_tenant_id", "data_requests", ["tenant_id"])
    op.create_index("ix_data_requests_tenant_id_status", "data_requests", ["tenant_id", "status"])

    # ---------------- decisão item a item ----------------
    op.create_table(
        "data_request_items",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(26), nullable=False),
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("request_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("target", sa.Enum(*ALVOS, name="data_item_target"), nullable=False),
        sa.Column("decision",
                  sa.Enum("export", "anonymize", "erase", "keep", "restrict",
                          name="data_item_decision"),
                  nullable=False),
        # Obrigatório inclusive para "manter": manter prontuário contra um
        # pedido de exclusão é legítimo, e precisa estar escrito.
        sa.Column("reason", sa.String(300), nullable=False),
        sa.Column("legal_basis", sa.String(200), nullable=True),
        sa.Column("applied_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("applied_by_user_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("result", sa.String(300), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"),
                  server_onupdate=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_data_request_items"),
        sa.UniqueConstraint("public_id", name="uq_data_request_items_public_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name="fk_data_request_items_tenant_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "request_id"],
                                ["data_requests.tenant_id", "data_requests.id"],
                                name="fk_data_request_items_tenant_id_request_id",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["applied_by_user_id"], ["users.id"],
                                name="fk_data_request_items_applied_by_user_id",
                                ondelete="SET NULL"),
        **ARGS,
    )
    op.create_index("ix_data_request_items_tenant_id", "data_request_items", ["tenant_id"])
    op.create_index("ix_data_request_items_tenant_id_request_id",
                    "data_request_items", ["tenant_id", "request_id"])

    # ---------------- retenção ----------------
    op.create_table(
        "retention_policies",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(26), nullable=False),
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("record_kind", sa.Enum(*ALVOS, name="data_item_target"), nullable=False),
        sa.Column("profession_id", mysql.BIGINT(unsigned=True), nullable=True),
        # NULO = sem prazo definido. É o padrão, e é proposital.
        sa.Column("months", sa.SmallInteger(), nullable=True),
        sa.Column("legal_basis", sa.String(300), nullable=True),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"),
                  server_onupdate=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_retention_policies"),
        sa.UniqueConstraint("public_id", name="uq_retention_policies_public_id"),
        sa.UniqueConstraint("tenant_id", "record_kind", "profession_id",
                            name="uq_retention_policies_tenant_id_record_kind_profession_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name="fk_retention_policies_tenant_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profession_id"], ["professions.id"],
                                name="fk_retention_policies_profession_id", ondelete="CASCADE"),
        **ARGS,
    )
    op.create_index("ix_retention_policies_tenant_id", "retention_policies", ["tenant_id"])
    # Nenhuma linha é inserida aqui de propósito. Ver a docstring.


def downgrade() -> None:
    """Recusa se houver pedido registrado: a resposta dada ao titular é
    justamente o que precisa sobreviver."""
    conexao = op.get_bind()
    existentes = conexao.exec_driver_sql("SELECT COUNT(*) FROM data_requests").scalar()
    if existentes:
        raise RuntimeError(
            f"downgrade recusado: {existentes} pedido(s) do titular registrado(s). "
            "O histórico de como cada pedido foi respondido não pode sumir.")
    op.drop_table("retention_policies")
    op.drop_table("data_request_items")
    op.drop_table("data_requests")
    op.drop_table("consents")
