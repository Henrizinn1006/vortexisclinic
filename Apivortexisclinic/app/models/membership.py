"""
memberships — o vínculo usuário ↔ tenant. É ele que dá acesso.

Ponto de atenção: membership NÃO herda TenantScoped de propósito.
Ela é consultada ANTES de existir tenant no contexto (no login, para saber
em quais contas o usuário entra, e na troca de workspace, para validar).
Se herdasse, cairia no fail-closed e nada funcionaria. O isolamento dela é
feito à mão e sempre pelo user_id da sessão autenticada.
"""
from typing import Optional

from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.mysql import BIGINT, DATETIME
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TABLE_ARGS, Base, PKMixin, TimestampMixin

STATUS_MEMBERSHIP = ("invited", "active", "suspended")
ESCOPOS = ("all", "own")


class Membership(Base, PKMixin, TimestampMixin):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_memberships_tenant_id_user_id"),
        Index("ix_memberships_user_id_status", "user_id", "status"),
        TABLE_ARGS,
    )

    tenant_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    data_scope: Mapped[str] = mapped_column(
        Enum(*ESCOPOS, name="membership_scope"), nullable=False, default="own"
    )
    status: Mapped[str] = mapped_column(
        Enum(*STATUS_MEMBERSHIP, name="membership_status"), nullable=False, default="active"
    )

    user = relationship("User", back_populates="memberships")
    tenant = relationship("Tenant", back_populates="memberships")
    role = relationship("Role", lazy="joined")
    excecoes = relationship("MembershipPermission", back_populates="membership", lazy="selectin")

    @property
    def ativa(self) -> bool:
        return self.status == "active"


class MembershipPermission(Base, PKMixin, TimestampMixin):
    """Exceção por pessoa: concede ou revoga uma permissão específica.

    Exceção sem motivo não existe (reason é NOT NULL), e concessão clínica
    nasce temporária: expires_at faz a cobertura de férias vencer sozinha.
    """

    __tablename__ = "membership_permissions"
    __table_args__ = (
        UniqueConstraint(
            "membership_id", "permission_id", "effect",
            name="uq_membership_permissions_membership_id_permission_id_effect",
        ),
        TABLE_ARGS,
    )

    tenant_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    membership_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("memberships.id", ondelete="CASCADE"), nullable=False
    )
    permission_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False
    )
    effect: Mapped[str] = mapped_column(
        Enum("grant", "deny", name="permission_effect"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    granted_by_user_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    starts_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)

    membership = relationship("Membership", back_populates="excecoes")
    permission = relationship("Permission", lazy="joined")
