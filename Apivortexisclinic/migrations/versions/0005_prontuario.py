"""Prontuário: nota, versões cifradas e trilha de acesso.

Três tabelas novas. **Nada é apagado nem alterado** — nenhuma tabela
existente é tocada por esta migration.

Duas escolhas de esquema que merecem nota:

* `clinical_note_versions.ciphertext` é MEDIUMBLOB, não TEXT. Conteúdo
  cifrado não tem collation nem índice de texto — e é justamente por isso
  que não existe busca dentro do prontuário (troca consciente, descrita no
  README).
* `clinical_access_log` não tem FK para `clinical_notes`. A trilha precisa
  sobreviver ao que acontecer com a nota: ela registra o que foi tentado,
  não o que ainda existe.

Revision ID: 0005_prontuario
Revises: 0004_financeiro
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0005_prontuario"
down_revision: Union[str, None] = "0004_financeiro"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ARGS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}


def upgrade() -> None:
    # ---------------- a ficha (sem o texto) ----------------
    op.create_table(
        "clinical_notes",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(26), nullable=False),
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("client_id", mysql.BIGINT(unsigned=True), nullable=False),
        # Autor: exige perfil profissional. Quem só administra a conta não
        # tem como ser autor de registro clínico.
        sa.Column("professional_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("appointment_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("kind",
                  sa.Enum("session", "assessment", "plan", "note", name="clinical_note_kind"),
                  nullable=False, server_default="session"),
        sa.Column("status", sa.Enum("draft", "signed", name="clinical_note_status"),
                  nullable=False, server_default="draft"),
        sa.Column("occurred_at", mysql.DATETIME(fsp=3), nullable=False),
        # Sal da derivação de chave. NULO = conteúdo destruído a pedido do
        # titular: as versões continuam, nenhuma delas abre mais.
        sa.Column("content_key_salt", mysql.VARBINARY(16), nullable=True),
        sa.Column("current_version", mysql.INTEGER(unsigned=True),
                  nullable=False, server_default="0"),
        sa.Column("signed_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("signed_by_membership_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("content_erased_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"),
                  server_onupdate=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_clinical_notes"),
        sa.UniqueConstraint("public_id", name="uq_clinical_notes_public_id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_clinical_notes_tenant_id_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name="fk_clinical_notes_tenant_id", ondelete="RESTRICT"),
        # FKs compostas: a nota não cruza contas nem que a aplicação erre.
        sa.ForeignKeyConstraint(["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"],
                                name="fk_clinical_notes_tenant_id_client_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "professional_id"],
                                ["professionals.tenant_id", "professionals.id"],
                                name="fk_clinical_notes_tenant_id_professional_id",
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "appointment_id"],
                                ["appointments.tenant_id", "appointments.id"],
                                name="fk_clinical_notes_tenant_id_appointment_id",
                                ondelete="RESTRICT"),
        **ARGS,
    )
    op.create_index("ix_clinical_notes_tenant_id", "clinical_notes", ["tenant_id"])
    op.create_index("ix_clinical_notes_tenant_id_client_id_occurred_at",
                    "clinical_notes", ["tenant_id", "client_id", "occurred_at"])
    op.create_index("ix_clinical_notes_tenant_id_professional_id",
                    "clinical_notes", ["tenant_id", "professional_id"])

    # ---------------- o texto, cifrado, append-only ----------------
    op.create_table(
        "clinical_note_versions",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(26), nullable=False),
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("note_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("version", mysql.INTEGER(unsigned=True), nullable=False),
        # AES-256-GCM (tag inclusa). Binário: sem collation, sem LIKE.
        sa.Column("ciphertext", mysql.MEDIUMBLOB, nullable=False),
        sa.Column("nonce", mysql.VARBINARY(12), nullable=False),
        sa.Column("key_version", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_by_membership_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        # Sem updated_at de propósito: a linha nasce e não muda.
        sa.PrimaryKeyConstraint("id", name="pk_clinical_note_versions"),
        sa.UniqueConstraint("public_id", name="uq_clinical_note_versions_public_id"),
        sa.UniqueConstraint("tenant_id", "note_id", "version",
                            name="uq_clinical_note_versions_tenant_id_note_id_version"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name="fk_clinical_note_versions_tenant_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "note_id"],
                                ["clinical_notes.tenant_id", "clinical_notes.id"],
                                name="fk_clinical_note_versions_tenant_id_note_id",
                                ondelete="RESTRICT"),
        **ARGS,
    )
    op.create_index("ix_clinical_note_versions_tenant_id",
                    "clinical_note_versions", ["tenant_id"])

    # ---------------- quem abriu o quê ----------------
    op.create_table(
        "clinical_access_log",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(26), nullable=False),
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("user_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("membership_id", mysql.BIGINT(unsigned=True), nullable=True),
        # Sem FK para notes/clients: a trilha registra o que foi TENTADO.
        sa.Column("client_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("note_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("action",
                  sa.Enum("list", "read", "create", "update", "sign", "export",
                          name="clinical_access_action"),
                  nullable=False),
        sa.Column("outcome", sa.Enum("allowed", "denied", name="clinical_access_outcome"),
                  nullable=False, server_default="allowed"),
        sa.Column("reason", sa.String(60), nullable=True),
        sa.Column("auth_session_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_clinical_access_log"),
        sa.UniqueConstraint("public_id", name="uq_clinical_access_log_public_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name="fk_clinical_access_log_tenant_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name="fk_clinical_access_log_user_id", ondelete="RESTRICT"),
        **ARGS,
    )
    op.create_index("ix_clinical_access_log_tenant_id", "clinical_access_log", ["tenant_id"])
    op.create_index("ix_clinical_access_log_tenant_id_created_at",
                    "clinical_access_log", ["tenant_id", "created_at"])
    op.create_index("ix_clinical_access_log_tenant_id_client_id_created_at",
                    "clinical_access_log", ["tenant_id", "client_id", "created_at"])
    op.create_index("ix_clinical_access_log_tenant_id_user_id_created_at",
                    "clinical_access_log", ["tenant_id", "user_id", "created_at"])


def downgrade() -> None:
    """Descer daqui APAGA prontuário. Recusa se houver alguma nota.

    Não existe "desfazer" para registro clínico: o texto é cifrado com
    chave derivada por nota, e o esquema vai junto. Se a intenção for
    mesmo descartar, apague as notas explicitamente antes — para que a
    decisão seja de alguém, e não de um comando de rotina.
    """
    conexao = op.get_bind()
    existentes = conexao.exec_driver_sql("SELECT COUNT(*) FROM clinical_notes").scalar()
    if existentes:
        raise RuntimeError(
            f"downgrade recusado: {existentes} registro(s) clínico(s) na base. "
            "Apagar prontuário é decisão explícita, não efeito colateral de migration."
        )
    op.drop_table("clinical_access_log")
    op.drop_table("clinical_note_versions")
    op.drop_table("clinical_notes")
