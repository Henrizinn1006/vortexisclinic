"""
Base do ORM.

Duas coisas importantes moram aqui:

1. `Base` com convenção de nomes — índice, FK e UNIQUE nascem com nome
   previsível, o que faz o Alembic gerar migration limpa.
2. `TenantScoped` — o marcador que diz "esta tabela pertence a um tenant".
   Quem herda isso é filtrado automaticamente pela sessão do ORM
   (ver db/session.py). Não é opcional e não depende de lembrar do WHERE.
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, MetaData, String, func
from sqlalchemy.dialects.mysql import BIGINT, DATETIME
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

CONVENCAO = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s",
    "pk": "pk_%(table_name)s",
}

# utf8mb4_unicode_ci funciona em MySQL 8 e MariaDB 10.6.
# (utf8mb4_0900_ai_ci é exclusivo do MySQL 8 — evitado de propósito.)
TABLE_ARGS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCAO)


class PKMixin:
    """PK interna BIGINT + identificador público ULID.

    O id sequencial nunca sai da API: expor "cliente 1832" entrega volume
    de negócio e facilita enumeração. Para fora vai só o public_id.
    """

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(26), unique=True, index=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), server_default=func.now(3), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), server_default=func.now(3), onupdate=func.now(), nullable=False
    )


class TenantScoped:
    """Marcador de tabela pertencente a um tenant.

    Herdar disto tem duas consequências automáticas:
      - a coluna tenant_id existe;
      - toda consulta passa pelo filtro de tenant, que falha quando não há
        tenant no contexto (fail-closed).
    """

    @declared_attr
    def tenant_id(cls) -> Mapped[int]:
        from sqlalchemy import ForeignKey

        return mapped_column(
            BIGINT(unsigned=True),
            ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        )


__all__ = ["Base", "PKMixin", "TimestampMixin", "TenantScoped", "TABLE_ARGS", "BigInteger", "DateTime"]
