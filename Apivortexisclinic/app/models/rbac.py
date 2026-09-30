"""
RBAC: papéis, permissões e a ligação entre eles.

Regra que vem da Etapa 2 e não muda: **OWNER não é bypass**. Papel é um
conjunto de permissões, e nenhum papel tem "todas". Administrar a conta não
dá acesso ao conteúdo clínico.

`Permission.data_class` liga cada permissão à classificação do dado
(administrative / clinical / account / audit). Isso permite responder, numa
consulta só, "esta permissão alcança conteúdo clínico?" — sem depender de
lista escrita em código de tela.
"""
from sqlalchemy import Boolean, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TABLE_ARGS, Base, PKMixin, TimestampMixin

CLASSES_DE_DADO = ("administrative", "clinical", "account", "audit")


class Role(Base, PKMixin, TimestampMixin):
    __tablename__ = "roles"
    __table_args__ = (TABLE_ARGS,)

    key: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    permissoes = relationship("RolePermission", back_populates="role", lazy="selectin")


class Permission(Base, PKMixin, TimestampMixin):
    __tablename__ = "permissions"
    __table_args__ = (TABLE_ARGS,)

    key: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    data_class: Mapped[str] = mapped_column(
        Enum(*CLASSES_DE_DADO, name="permission_data_class"), nullable=False
    )


class RolePermission(Base, TimestampMixin):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_id_permission_id"),
        TABLE_ARGS,
    )

    role_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )

    role = relationship("Role", back_populates="permissoes")
    permission = relationship("Permission", lazy="joined")
