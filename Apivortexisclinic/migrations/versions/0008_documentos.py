"""Documentos: recibo, declaração, cópia de prontuário e anexo.

Uma tabela. O arquivo em si **não fica no banco**: vai cifrado para o
disco, e aqui ficam os metadados e o material da cifra. Nada é apagado
por esta migration.

Revision ID: 0008_documentos
Revises: 0007_agenda
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0008_documentos"
down_revision: Union[str, None] = "0007_agenda"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ARGS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(26), nullable=False),
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("client_id", mysql.BIGINT(unsigned=True), nullable=False),
        # Nulo para recibo: recibo não é ato profissional, é comprovante.
        sa.Column("professional_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("kind",
                  sa.Enum("receipt", "attendance", "report", "record_copy", "upload",
                          name="document_kind"),
                  nullable=False),
        # É esta coluna que a rota consulta para saber qual permissão exigir.
        sa.Column("data_class",
                  sa.Enum("administrative", "clinical", name="document_class"),
                  nullable=False, server_default="clinical"),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("file_name", sa.String(160), nullable=False),
        sa.Column("mime", sa.String(100), nullable=False, server_default="application/pdf"),
        sa.Column("size_bytes", mysql.INTEGER(unsigned=True), nullable=False,
                  server_default="0"),
        # Caminho relativo dentro de VC_FILES_DIR, sem nome falante.
        sa.Column("storage_key", sa.String(200), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        # Cifra: mesmo desenho do prontuário. Sal nulo = conteúdo destruído.
        sa.Column("key_salt", mysql.VARBINARY(16), nullable=True),
        sa.Column("nonce", mysql.VARBINARY(12), nullable=False),
        sa.Column("key_version", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("created_by_user_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("content_erased_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"),
                  server_onupdate=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.UniqueConstraint("public_id", name="uq_documents_public_id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_documents_tenant_id_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name="fk_documents_tenant_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"],
                                name="fk_documents_tenant_id_client_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "professional_id"],
                                ["professionals.tenant_id", "professionals.id"],
                                name="fk_documents_tenant_id_professional_id",
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"],
                                name="fk_documents_created_by_user_id", ondelete="SET NULL"),
        **ARGS,
    )
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])
    op.create_index("ix_documents_tenant_id_client_id_created_at",
                    "documents", ["tenant_id", "client_id", "created_at"])


def downgrade() -> None:
    """Recusa se houver documento: a linha some, o arquivo cifrado fica
    órfão no disco, e ninguém mais sabe a que ele pertencia."""
    conexao = op.get_bind()
    existentes = conexao.exec_driver_sql("SELECT COUNT(*) FROM documents").scalar()
    if existentes:
        raise RuntimeError(
            f"downgrade recusado: {existentes} documento(s) emitido(s). "
            "Apagar a tabela deixaria os arquivos cifrados órfãos no disco.")
    op.drop_table("documents")
