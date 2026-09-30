"""
professionals — perfil profissional dentro de um tenant.

É tenant-scoped de verdade (herda TenantScoped): consulta sem tenant no
contexto falha. Um usuário pode ter perfil em mais de uma conta, com
registro diferente em cada uma.

Conselho e registro são opcionais por decisão de produto: terapeuta
integrativo, coach e várias categorias não têm conselho. Quem diz se o
campo é exigido é `professions.requires_council`.
"""
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TABLE_ARGS, Base, PKMixin, TenantScoped, TimestampMixin


class Professional(Base, PKMixin, TenantScoped, TimestampMixin):
    __tablename__ = "professionals"
    __table_args__ = (
        # Permite FK composta (tenant_id, id) nas tabelas de negócio das
        # próximas etapas: atendimento do tenant A não consegue apontar
        # para profissional do tenant B nem por erro de aplicação.
        UniqueConstraint("tenant_id", "id", name="uq_professionals_tenant_id_id"),
        UniqueConstraint("membership_id", name="uq_professionals_membership_id"),
        TABLE_ARGS,
    )

    membership_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True
    )
    profession_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("professions.id", ondelete="RESTRICT"), nullable=False
    )

    display_name: Mapped[str] = mapped_column(String(140), nullable=False)
    council: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    registration_number: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    specialty: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    profession = relationship("Profession", lazy="joined")
