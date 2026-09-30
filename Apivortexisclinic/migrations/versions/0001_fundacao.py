"""Fundação: identidade, workspaces, RBAC e sessões.

Primeira migration do projeto. Cria só o que a Etapa 3 precisa —
pacientes, agenda, atendimentos, financeiro e prontuário NÃO entram aqui.

Convenções adotadas (valem para todas as migrations seguintes):
  - InnoDB, utf8mb4 / utf8mb4_unicode_ci (funciona em MySQL 8 e MariaDB);
  - PK interna BIGINT UNSIGNED + public_id CHAR(26) ULID para as URLs;
  - datas em UTC, DATETIME(3);
  - toda tabela de tenant ganha UNIQUE (tenant_id, id), que é o que
    permitirá FK composta nas tabelas de negócio das próximas etapas.

Revision ID: 0001_fundacao
Revises:
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0001_fundacao"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ARGS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}


def _pk():
    return [
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(26), nullable=False),
    ]


def _timestamps():
    return [
        sa.Column("created_at", mysql.DATETIME(fsp=3), server_default=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), server_default=sa.text("CURRENT_TIMESTAMP(3)"),
                  server_onupdate=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
    ]


def upgrade() -> None:
    # ---------------- catálogo de profissões ----------------
    # Entra agora porque o cadastro já pergunta a profissão, e é ela que
    # decide se a tela pede conselho/registro. Sem catálogo, isso viraria
    # `if profissao == "psicologo"` no código.
    op.create_table(
        "professions",
        *_pk(),
        sa.Column("slug", sa.String(60), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("requires_council", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("council_label", sa.String(40), nullable=True),
        sa.Column("registration_label", sa.String(60), nullable=True),
        sa.Column("default_terminology", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_professions"),
        sa.UniqueConstraint("public_id", name="uq_professions_public_id"),
        sa.UniqueConstraint("slug", name="uq_professions_slug"),
        **ARGS,
    )

    # ---------------- RBAC ----------------
    op.create_table(
        "roles",
        *_pk(),
        sa.Column("key", sa.String(40), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.String(200), nullable=False, server_default=""),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
        sa.UniqueConstraint("public_id", name="uq_roles_public_id"),
        sa.UniqueConstraint("key", name="uq_roles_key"),
        **ARGS,
    )

    op.create_table(
        "permissions",
        *_pk(),
        sa.Column("key", sa.String(60), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        # A classe do dado mora na própria permissão: é o que impede, na
        # consulta, uma permissão administrativa alcançar conteúdo clínico.
        sa.Column("data_class",
                  sa.Enum("administrative", "clinical", "account", "audit", name="permission_data_class"),
                  nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_permissions"),
        sa.UniqueConstraint("public_id", name="uq_permissions_public_id"),
        sa.UniqueConstraint("key", name="uq_permissions_key"),
        **ARGS,
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("permission_id", mysql.BIGINT(unsigned=True), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name="pk_role_permissions"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], name="fk_role_permissions_role_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"],
                                name="fk_role_permissions_permission_id", ondelete="CASCADE"),
        **ARGS,
    )

    # ---------------- usuários (globais) ----------------
    op.create_table(
        "users",
        *_pk(),
        sa.Column("name", sa.String(120), nullable=False),
        # Unicidade de e-mail: coluna UNIQUE + valor sempre normalizado em
        # minúsculo pela aplicação. A collation _ci também compara sem
        # diferenciar caixa, então não há duas contas "Ana@" e "ana@".
        sa.Column("email", sa.String(190), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("status", sa.Enum("pending", "active", "blocked", name="user_status"),
                  nullable=False, server_default="active"),
        sa.Column("email_verified_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("last_login_at", mysql.DATETIME(fsp=3), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("public_id", name="uq_users_public_id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        **ARGS,
    )

    # ---------------- tenants ----------------
    op.create_table(
        "tenants",
        *_pk(),
        sa.Column("name", sa.String(140), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("type", sa.Enum("solo", "office", "clinic", name="tenant_type"),
                  nullable=False, server_default="solo"),
        sa.Column("status", sa.Enum("trial", "active", "past_due", "suspended", "cancelled", name="tenant_status"),
                  nullable=False, server_default="trial"),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="America/Sao_Paulo"),
        sa.Column("profession_id", mysql.BIGINT(unsigned=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_tenants"),
        sa.UniqueConstraint("public_id", name="uq_tenants_public_id"),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
        sa.ForeignKeyConstraint(["profession_id"], ["professions.id"],
                                name="fk_tenants_profession_id", ondelete="RESTRICT"),
        **ARGS,
    )

    op.create_table(
        "tenant_settings",
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("terminology", sa.Text(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="BRL"),
        *_timestamps(),
        sa.PrimaryKeyConstraint("tenant_id", name="pk_tenant_settings"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name="fk_tenant_settings_tenant_id", ondelete="CASCADE"),
        **ARGS,
    )

    # ---------------- memberships ----------------
    op.create_table(
        "memberships",
        *_pk(),
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("user_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("role_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("data_scope", sa.Enum("all", "own", name="membership_scope"),
                  nullable=False, server_default="own"),
        sa.Column("status", sa.Enum("invited", "active", "suspended", name="membership_status"),
                  nullable=False, server_default="active"),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_memberships"),
        sa.UniqueConstraint("public_id", name="uq_memberships_public_id"),
        # Uma pessoa tem no máximo um vínculo por conta...
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_memberships_tenant_id_user_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_memberships_tenant_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_memberships_user_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], name="fk_memberships_role_id", ondelete="RESTRICT"),
        **ARGS,
    )
    # ...e a lista de contas do usuário é consulta de todo login.
    op.create_index("ix_memberships_user_id_status", "memberships", ["user_id", "status"])
    op.create_index("ix_memberships_tenant_id", "memberships", ["tenant_id"])

    op.create_table(
        "membership_permissions",
        *_pk(),
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("membership_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("permission_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("effect", sa.Enum("grant", "deny", name="permission_effect"), nullable=False),
        # Exceção sem motivo não existe.
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("granted_by_user_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("starts_at", mysql.DATETIME(fsp=3), nullable=True),
        # Concessão clínica nasce temporária: cobertura de férias vence sozinha.
        sa.Column("expires_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("revoked_at", mysql.DATETIME(fsp=3), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_membership_permissions"),
        sa.UniqueConstraint("public_id", name="uq_membership_permissions_public_id"),
        sa.UniqueConstraint("membership_id", "permission_id", "effect",
                            name="uq_membership_permissions_membership_id_permission_id_effect"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name="fk_membership_permissions_tenant_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["membership_id"], ["memberships.id"],
                                name="fk_membership_permissions_membership_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"],
                                name="fk_membership_permissions_permission_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["users.id"],
                                name="fk_membership_permissions_granted_by_user_id", ondelete="SET NULL"),
        **ARGS,
    )
    op.create_index("ix_membership_permissions_tenant_id", "membership_permissions", ["tenant_id"])

    # ---------------- perfil profissional ----------------
    op.create_table(
        "professionals",
        *_pk(),
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("membership_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("profession_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("display_name", sa.String(140), nullable=False),
        # Conselho e registro são opcionais de propósito: nem toda
        # categoria profissional tem conselho.
        sa.Column("council", sa.String(20), nullable=True),
        sa.Column("registration_number", sa.String(40), nullable=True),
        sa.Column("specialty", sa.String(120), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_professionals"),
        sa.UniqueConstraint("public_id", name="uq_professionals_public_id"),
        # Chave que sustenta a FK composta das próximas etapas.
        sa.UniqueConstraint("tenant_id", "id", name="uq_professionals_tenant_id_id"),
        sa.UniqueConstraint("membership_id", name="uq_professionals_membership_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name="fk_professionals_tenant_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["membership_id"], ["memberships.id"],
                                name="fk_professionals_membership_id", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["profession_id"], ["professions.id"],
                                name="fk_professionals_profession_id", ondelete="RESTRICT"),
        **ARGS,
    )
    op.create_index("ix_professionals_tenant_id", "professionals", ["tenant_id"])

    # ---------------- sessões ----------------
    # Sessão opaca: o banco guarda o HASH do token, nunca o token.
    op.create_table(
        "auth_sessions",
        *_pk(),
        sa.Column("user_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("active_tenant_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("idle_expires_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("absolute_expires_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("last_seen_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("revoked_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("revoked_reason", sa.String(40), nullable=True),
        sa.Column("ip", mysql.VARBINARY(16), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_auth_sessions"),
        sa.UniqueConstraint("public_id", name="uq_auth_sessions_public_id"),
        sa.UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_auth_sessions_user_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["active_tenant_id"], ["tenants.id"],
                                name="fk_auth_sessions_active_tenant_id", ondelete="SET NULL"),
        **ARGS,
    )
    op.create_index("ix_auth_sessions_user_id_revoked_at", "auth_sessions", ["user_id", "revoked_at"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["absolute_expires_at"])

    op.create_table(
        "password_reset_tokens",
        *_pk(),
        sa.Column("user_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("used_at", mysql.DATETIME(fsp=3), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_password_reset_tokens"),
        sa.UniqueConstraint("public_id", name="uq_password_reset_tokens_public_id"),
        sa.UniqueConstraint("token_hash", name="uq_password_reset_tokens_token_hash"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name="fk_password_reset_tokens_user_id", ondelete="CASCADE"),
        **ARGS,
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])

    # ---------------- trilha de segurança ----------------
    # Nunca guarda senha, token, cookie ou segredo.
    op.create_table(
        "security_events",
        *_pk(),
        sa.Column("created_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.Column("user_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("outcome", sa.Enum("allowed", "denied", "failed", name="security_outcome"), nullable=False),
        sa.Column("ip", mysql.VARBINARY(16), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("meta", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_security_events"),
        sa.UniqueConstraint("public_id", name="uq_security_events_public_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_security_events_user_id", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name="fk_security_events_tenant_id", ondelete="SET NULL"),
        **ARGS,
    )
    op.create_index("ix_security_events_user_id_created_at", "security_events", ["user_id", "created_at"])
    op.create_index("ix_security_events_action_created_at", "security_events", ["action", "created_at"])


def downgrade() -> None:
    # Ordem inversa por causa das FKs.
    op.drop_table("security_events")
    op.drop_table("password_reset_tokens")
    op.drop_table("auth_sessions")
    op.drop_table("professionals")
    op.drop_table("membership_permissions")
    op.drop_table("memberships")
    op.drop_table("tenant_settings")
    op.drop_table("tenants")
    op.drop_table("users")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("professions")
