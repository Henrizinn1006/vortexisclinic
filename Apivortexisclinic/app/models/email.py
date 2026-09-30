"""
Fila de e-mail e verificação de endereço.

**Por que uma fila, e não `smtplib` direto na rota**

Três motivos, e nenhum é elegância:

1. **O servidor de e-mail cai.** Se a rota mandasse direto, um SMTP fora
   do ar derrubaria o cadastro junto. Com fila, a mensagem espera.
2. **Dá para ver o que foi mandado.** "A pessoa não recebeu o convite" é
   uma frase que se responde olhando a fila — ela diz se saiu, quando, e
   com que erro se não saiu.
3. **Enviar é lento.** Uma conexão SMTP no meio de uma requisição é meio
   segundo que a pessoa espera olhando a tela.

**O corpo do e-mail nunca carrega conteúdo clínico**

Esta tabela guarda o texto do que foi enviado, então ela é, na prática,
uma cópia de tudo que saiu. Um lembrete diz "você tem atendimento amanhã
às 10h" — data, hora e onde. Nunca o que foi ou será tratado. Há teste
para isso, porque é o tipo de coisa que alguém "melhora" um dia sem
perceber o que está fazendo.

**Endereço de destino é dado pessoal**

Por isso a fila tem limpeza: mensagem enviada há muito tempo não precisa
guardar o corpo para sempre. `limpar_antigas()` existe para isso e é
chamada pelo job.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Enum, ForeignKey, Index, SmallInteger, String, Text
from sqlalchemy.dialects.mysql import BIGINT, DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TABLE_ARGS, Base, PKMixin, TimestampMixin

TIPOS = ("verify_email", "password_reset", "invitation", "appointment_reminder", "other")
STATUS = ("queued", "sent", "failed", "cancelled")


class EmailMessage(Base, PKMixin, TimestampMixin):
    """Uma mensagem na fila.

    NÃO herda `TenantScoped`: verificação de e-mail e redefinição de senha
    acontecem antes de haver workspace ativo, e cairiam no fail-closed.
    `tenant_id` existe como referência, e o filtro por conta é feito à mão
    onde faz sentido.
    """

    __tablename__ = "email_messages"
    __table_args__ = (
        Index("ix_email_messages_status_scheduled_for", "status", "scheduled_for"),
        Index("ix_email_messages_tenant_id_created_at", "tenant_id", "created_at"),
        TABLE_ARGS,
    )

    tenant_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )
    to_email: Mapped[str] = mapped_column(String(190), nullable=False)
    to_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    kind: Mapped[str] = mapped_column(Enum(*TIPOS, name="email_kind"), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    # Texto puro. Não há HTML de propósito: e-mail com marcação é uma
    # superfície a mais, e nada aqui precisa de layout.
    body: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(
        Enum(*STATUS, name="email_status"), nullable=False, default="queued"
    )
    scheduled_for: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    # Mensagem de erro do servidor de e-mail. Nunca a senha do SMTP.
    last_error: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    # Chave de idempotência: impede o job de enfileirar o mesmo lembrete
    # duas vezes se rodar duas vezes no mesmo dia.
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, unique=True)

    def __repr__(self) -> str:      # nunca o endereço inteiro, nunca o corpo
        return f"<EmailMessage {self.public_id} {self.kind}/{self.status}>"


class EmailVerification(Base, PKMixin, TimestampMixin):
    """Token de confirmação de endereço.

    Mesmo desenho das sessões e do reset de senha: o token existe uma vez,
    no link, e o que fica guardado é o sha256 dele.
    """

    __tablename__ = "email_verifications"
    __table_args__ = (
        Index("ix_email_verifications_user_id", "user_id"),
        TABLE_ARGS,
    )

    user_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # O endereço que está sendo confirmado. Guardado porque a pessoa pode
    # trocar de e-mail antes de clicar no link — e aí o token não vale mais.
    email: Mapped[str] = mapped_column(String(190), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)

    def vigente(self, agora: datetime) -> bool:
        return self.used_at is None and self.expires_at > agora

    def __repr__(self) -> str:
        return f"<EmailVerification {self.public_id}>"
