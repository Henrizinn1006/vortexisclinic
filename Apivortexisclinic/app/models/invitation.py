"""
invitations — como alguém entra numa conta que não é a sua.

Até aqui, o único jeito de ter duas pessoas na mesma clínica era escrever
a linha de `memberships` direto no banco. Isto resolve isso, e resolve com
os mesmos cuidados do resto do sistema.

**O token não fica guardado**

Só o sha256 dele. Quem tiver o dump do banco não consegue aceitar convite
nenhum — é o mesmo desenho das sessões e do reset de senha. O link vai
para o e-mail da pessoa convidada e mais ninguém.

**O convite carrega o acesso, não quem convida**

Papel e escopo de dados são decididos no momento do convite e viajam com
ele. Aceitar não escolhe nada: a pessoa entra exatamente no lugar que foi
definido por quem tinha `members.manage`. Não existe caminho em que
aceitar um convite renda mais acesso do que o convite dizia.

**E-mail é parte do convite**

O convite é para um endereço específico. Aceitar logado com outra conta é
recusado — senão um link vazado viraria porta de entrada para qualquer um.

Esta tabela NÃO herda TenantScoped: ela é lida por token, antes de existir
sessão (e antes de existir conta, no caso de quem ainda não é usuário). O
isolamento dela é feito à mão, sempre pelo tenant do convite.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Enum, ForeignKey, Index, String
from sqlalchemy.dialects.mysql import BIGINT, DATETIME
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TABLE_ARGS, Base, PKMixin, TimestampMixin

STATUS_CONVITE = ("pending", "accepted", "revoked")


class Invitation(Base, PKMixin, TimestampMixin):
    __tablename__ = "invitations"
    __table_args__ = (
        Index("ix_invitations_tenant_id_status", "tenant_id", "status"),
        Index("ix_invitations_email", "email"),
        TABLE_ARGS,
    )

    tenant_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(190), nullable=False)

    # O acesso já vem decidido. Aceitar não escolhe papel nem escopo.
    role_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    data_scope: Mapped[str] = mapped_column(
        Enum("all", "own", name="membership_scope"), nullable=False, default="own"
    )
    # Quando preenchido, a pessoa nasce com perfil profissional — e, com
    # ele, acesso clínico ao que for seu.
    profession_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("professions.id", ondelete="RESTRICT"), nullable=True
    )

    # sha256 do token. O token em si existe uma vez, no link, e some daqui.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    status: Mapped[str] = mapped_column(
        Enum(*STATUS_CONVITE, name="invitation_status"), nullable=False, default="pending"
    )
    expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)
    accepted_user_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)
    invited_by_user_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Mensagem curta de quem convidou. Texto puro, mostrado com escape.
    message: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    tenant = relationship("Tenant", lazy="joined")
    role = relationship("Role", lazy="joined")

    def vigente(self, agora: datetime) -> bool:
        return self.status == "pending" and self.expires_at > agora

    def __repr__(self) -> str:      # nunca o e-mail inteiro, nunca o token
        return f"<Invitation {self.public_id} {self.status}>"
