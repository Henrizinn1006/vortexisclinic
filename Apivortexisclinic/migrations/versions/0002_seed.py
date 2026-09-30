"""Seed de papéis, permissões e profissões.

Seed vive em migration, não em script solto, por um motivo prático: papel e
permissão fazem parte do CONTRATO de segurança. Se eles entrassem por
script manual, dois ambientes poderiam ter matrizes diferentes — e aí
"testado em desenvolvimento" não significa nada.

O seed é idempotente: rodar de novo não duplica nem sobrescreve o que já
existe. Nada aqui apaga dado.

Revision ID: 0002_seed
Revises: 0001_fundacao
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app import rbac
from app.ids import novo_ulid

revision: str = "0002_seed"
down_revision: Union[str, None] = "0001_fundacao"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Catálogo inicial. A plataforma não é "para psicólogos": é para
# profissionais de atendimento, e a categoria é dado, não código.
PROFISSOES = [
    # slug, nome, exige conselho, rótulo conselho, rótulo registro
    ("psicologia", "Psicologia", True, "CRP", "Número do CRP"),
    ("psicanalise", "Psicanálise", False, None, None),
    ("psiquiatria", "Psiquiatria", True, "CRM", "Número do CRM"),
    ("nutricao", "Nutrição", True, "CRN", "Número do CRN"),
    ("fonoaudiologia", "Fonoaudiologia", True, "CRFa", "Número do CRFa"),
    ("terapia_ocupacional", "Terapia ocupacional", True, "CREFITO", "Número do CREFITO"),
    ("fisioterapia", "Fisioterapia", True, "CREFITO", "Número do CREFITO"),
    ("terapia_integrativa", "Terapia integrativa", False, None, None),
    ("coaching", "Coaching", False, None, None),
    ("outra", "Outra", False, None, None),
]


def upgrade() -> None:
    conexao = op.get_bind()

    # ---------------- profissões ----------------
    for slug, nome, exige, conselho, registro in PROFISSOES:
        existe = conexao.execute(
            sa.text("SELECT id FROM professions WHERE slug = :slug"), {"slug": slug}
        ).first()
        if existe:
            continue
        conexao.execute(
            sa.text(
                "INSERT INTO professions (public_id, slug, name, requires_council, "
                "council_label, registration_label, active) "
                "VALUES (:pid, :slug, :nome, :exige, :conselho, :registro, 1)"
            ),
            {"pid": novo_ulid(), "slug": slug, "nome": nome,
             "exige": 1 if exige else 0, "conselho": conselho, "registro": registro},
        )

    # ---------------- permissões ----------------
    for chave, nome, classe in rbac.PERMISSOES:
        existe = conexao.execute(
            sa.text("SELECT id FROM permissions WHERE `key` = :k"), {"k": chave}
        ).first()
        if existe:
            continue
        conexao.execute(
            sa.text(
                "INSERT INTO permissions (public_id, `key`, name, data_class) "
                "VALUES (:pid, :k, :nome, :classe)"
            ),
            {"pid": novo_ulid(), "k": chave, "nome": nome, "classe": classe},
        )

    # ---------------- papéis ----------------
    for chave, dados in rbac.PAPEIS.items():
        existe = conexao.execute(
            sa.text("SELECT id FROM roles WHERE `key` = :k"), {"k": chave}
        ).first()
        if existe:
            continue
        conexao.execute(
            sa.text(
                "INSERT INTO roles (public_id, `key`, name, description, is_system) "
                "VALUES (:pid, :k, :nome, :desc, 1)"
            ),
            {"pid": novo_ulid(), "k": chave, "nome": dados["name"], "desc": dados["description"]},
        )

    # ---------------- matriz papel × permissão ----------------
    # É AQUI que "OWNER não é bypass" vira dado. Existe teste garantindo
    # que esta matriz e o rbac.py não divergem.
    papeis = {linha[1]: linha[0] for linha in conexao.execute(sa.text("SELECT id, `key` FROM roles")).all()}
    permissoes = {linha[1]: linha[0] for linha in conexao.execute(sa.text("SELECT id, `key` FROM permissions")).all()}

    for papel, chaves in rbac.PAPEL_PERMISSOES.items():
        role_id = papeis[papel]
        for chave in chaves:
            permission_id = permissoes[chave]
            existe = conexao.execute(
                sa.text(
                    "SELECT role_id FROM role_permissions "
                    "WHERE role_id = :r AND permission_id = :p"
                ),
                {"r": role_id, "p": permission_id},
            ).first()
            if existe:
                continue
            conexao.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id) VALUES (:r, :p)"
                ),
                {"r": role_id, "p": permission_id},
            )


def downgrade() -> None:
    """Remove apenas as linhas de catálogo, e só se nada estiver usando.

    Não apaga tenant, usuário nem membership — downgrade de seed não é
    desculpa para destruir dado de cliente.
    """
    conexao = op.get_bind()
    em_uso = conexao.execute(sa.text("SELECT COUNT(*) FROM memberships")).scalar()
    if em_uso:
        raise RuntimeError(
            "Existem memberships usando estes papéis. "
            "Downgrade do seed cancelado para não corromper acesso."
        )
    conexao.execute(sa.text("DELETE FROM role_permissions"))
    conexao.execute(sa.text("DELETE FROM permissions"))
    conexao.execute(sa.text("DELETE FROM roles"))
    conexao.execute(sa.text("DELETE FROM professions WHERE id NOT IN (SELECT profession_id FROM professionals)"))
