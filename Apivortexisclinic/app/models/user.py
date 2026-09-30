"""
users — usuário GLOBAL da plataforma.

Não tem tenant_id: o acesso é o vínculo (membership). O mesmo e-mail atende
no consultório próprio e numa clínica, com papéis diferentes, sem precisar
de duas contas.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TABLE_ARGS, Base, PKMixin, TimestampMixin

STATUS_USUARIO = ("pending", "active", "blocked")


class User(Base, PKMixin, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (TABLE_ARGS,)

    name: Mapped[str] = mapped_column(String(120), nullable=False)

    # Unicidade real de e-mail: a coluna guarda o e-mail normalizado
    # (minúsculo, sem espaço). A collation é utf8mb4_unicode_ci, então a
    # comparação já é case-insensitive — a normalização garante que o
    # armazenado também seja previsível.
    email: Mapped[str] = mapped_column(String(190), nullable=False, unique=True)

    # Argon2id. Nunca senha em texto puro, nunca reversível.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    status: Mapped[str] = mapped_column(
        Enum(*STATUS_USUARIO, name="user_status"), nullable=False, default="active"
    )
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)

    memberships = relationship("Membership", back_populates="user", lazy="selectin")

    def __repr__(self) -> str:  # nunca logar e-mail inteiro nem hash
        return f"<User {self.public_id}>"
