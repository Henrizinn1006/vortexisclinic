"""Planos e assinatura.

Duas tabelas e o catálogo inicial. Nada é apagado.

**Não há cobrança aqui.** Nenhum gateway, nenhuma chave, nenhum webhook —
isso depende de uma conta de pagamento que o produto ainda não tem.
`subscriptions.provider` e `external_ref` são o encaixe, vazios, para
quando essa decisão for tomada.

Os números e os nomes dos planos são um **ponto de partida**, não uma
decisão de produto: eles moram no banco justamente para mudar com um
UPDATE, sem deploy. Os preços nascem NULOS — inventar valor de mensalidade
seria o mesmo erro de inventar prazo de retenção.

Revision ID: 0011_planos
Revises: 0010_email
"""
import time
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0011_planos"
down_revision: Union[str, None] = "0010_email"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ARGS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}

# NULO = sem limite. "Ilimitado" precisa ser dizível, e 9999 é um limite.
PLANOS = [
    # chave, nome, descrição, preço, ordem, prof, membros, pessoas, MB,
    # clínico, documentos, exportação, lembretes
    ("essencial", "Essencial", "Consultório pequeno.", None, 1,
     5, 10, 500, 500, True, True, True, True),
    ("profissional", "Profissional", "Consultório com equipe de apoio.", None, 2,
     15, 30, 2000, 2000, True, True, True, True),
    ("clinica", "Clínica", "Equipe grande, sem teto de cadastro.", None, 3,
     None, None, None, 10000, True, True, True, True),
]


def upgrade() -> None:
    planos = op.create_table(
        "plans",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(26), nullable=False),
        sa.Column("key", sa.String(40), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.String(300), nullable=True),
        sa.Column("monthly_price", mysql.DECIMAL(10, 2), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        # NULO = sem limite.
        sa.Column("max_professionals", sa.Integer(), nullable=True),
        sa.Column("max_members", sa.Integer(), nullable=True),
        sa.Column("max_clients", sa.Integer(), nullable=True),
        sa.Column("max_storage_mb", sa.Integer(), nullable=True),
        sa.Column("allows_clinical", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("allows_documents", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("allows_export", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("allows_reminders", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"),
                  server_onupdate=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_plans"),
        sa.UniqueConstraint("public_id", name="uq_plans_public_id"),
        sa.UniqueConstraint("key", name="uq_plans_key"),
        **ARGS,
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(26), nullable=False),
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("plan_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("status",
                  sa.Enum("trialing", "active", "past_due", "canceled",
                          name="subscription_status"),
                  nullable=False, server_default="trialing"),
        sa.Column("trial_ends_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("current_period_end", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("canceled_at", mysql.DATETIME(fsp=3), nullable=True),
        # O encaixe do gateway, vazio até a decisão ser tomada.
        sa.Column("provider", sa.String(40), nullable=True),
        sa.Column("external_ref", sa.String(120), nullable=True),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=3),
                  server_default=sa.text("CURRENT_TIMESTAMP(3)"),
                  server_onupdate=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_subscriptions"),
        sa.UniqueConstraint("public_id", name="uq_subscriptions_public_id"),
        sa.UniqueConstraint("tenant_id", name="uq_subscriptions_tenant_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name="fk_subscriptions_tenant_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"],
                                name="fk_subscriptions_plan_id", ondelete="RESTRICT"),
        **ARGS,
    )

    # ---------------- catálogo inicial ----------------
    # Idempotente: rodar de novo não duplica nem sobrescreve preço ajustado.
    conexao = op.get_bind()
    existentes = {
        linha[0] for linha in conexao.exec_driver_sql("SELECT `key` FROM plans").all()
    }
    novos = []
    for i, dados in enumerate(PLANOS):
        (chave, nome, descricao, preco, ordem, prof, membros, pessoas, mb,
         clinico, documentos, exportacao, lembretes) = dados
        if chave in existentes:
            continue
        novos.append({
            "public_id": f"PLAN{int(time.time()):010d}{i:012d}"[:26],
            "key": chave, "name": nome, "description": descricao,
            "monthly_price": preco, "active": True, "sort_order": ordem,
            "max_professionals": prof, "max_members": membros,
            "max_clients": pessoas, "max_storage_mb": mb,
            "allows_clinical": clinico, "allows_documents": documentos,
            "allows_export": exportacao, "allows_reminders": lembretes,
        })
    if novos:
        op.bulk_insert(planos, novos)


def downgrade() -> None:
    op.drop_table("subscriptions")
    op.drop_table("plans")
