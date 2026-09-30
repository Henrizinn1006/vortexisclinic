"""
Sessões, recuperação de senha e trilha de segurança.

Decisão mantida da Etapa 2: **sessão opaca no servidor**. O navegador
carrega um cookie com um token aleatório que não significa nada sozinho;
quem sabe quem é o usuário é esta tabela. Isso permite revogar na hora —
essencial quando o produto guarda dado de saúde. JWT em localStorage seria
XSS na veia e não teria revogação.

O que vai para o banco é o **hash** do token, não o token. Vazamento de
dump de banco não vira sessão válida.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.mysql import BIGINT, DATETIME, VARBINARY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TABLE_ARGS, Base, PKMixin, TimestampMixin


class AuthSession(Base, PKMixin, TimestampMixin):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index("ix_auth_sessions_user_id_revoked_at", "user_id", "revoked_at"),
        Index("ix_auth_sessions_expires_at", "absolute_expires_at"),
        TABLE_ARGS,
    )

    user_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # sha256 do token do cookie. O token em si nunca é gravado.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # sha256 do token CSRF desta sessão (double submit cookie).
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Tenant ativo da sessão. Vem daqui, NUNCA do corpo da requisição.
    active_tenant_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )

    idle_expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)
    revoked_reason: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    ip: Mapped[Optional[bytes]] = mapped_column(VARBINARY(16), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    user = relationship("User", lazy="joined")

    def vigente(self, agora: datetime) -> bool:
        return (
            self.revoked_at is None
            and self.idle_expires_at > agora
            and self.absolute_expires_at > agora
        )


class PasswordResetToken(Base, PKMixin, TimestampMixin):
    """Recuperação de senha — estrutura pronta, envio de e-mail fica para depois.

    Guarda hash, uso único, validade curta. A resposta da API é sempre a
    mesma exista ou não o e-mail: descobrir quem tem conta já é vazamento.
    """

    __tablename__ = "password_reset_tokens"
    __table_args__ = (Index("ix_password_reset_tokens_user_id", "user_id"), TABLE_ARGS)

    user_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)


class SecurityEvent(Base, PKMixin):
    """Trilha de segurança: login, falha, logout, troca de workspace, negativa.

    Nunca guarda senha, token, cookie ou segredo — só o que aconteceu, com
    quem e de onde. `meta` é texto curto e controlado pela aplicação.
    """

    __tablename__ = "security_events"
    __table_args__ = (
        Index("ix_security_events_user_id_created_at", "user_id", "created_at"),
        Index("ix_security_events_action_created_at", "action", "created_at"),
        TABLE_ARGS,
    )

    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=func.now(3)
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    tenant_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    outcome: Mapped[str] = mapped_column(
        Enum("allowed", "denied", "failed", name="security_outcome"), nullable=False
    )
    ip: Mapped[Optional[bytes]] = mapped_column(VARBINARY(16), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    meta: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
