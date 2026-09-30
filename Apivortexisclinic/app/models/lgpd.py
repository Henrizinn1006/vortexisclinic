"""
Consentimento, pedido do titular e política de retenção.

Este arquivo é o que separa "ter uma página escrita LGPD" de ter privacidade
na arquitetura. As três tabelas existem porque três perguntas precisam de
resposta demonstrável:

**"Com base em quê vocês guardam isto?"** → `consents`. Consentimento tem
versão e data, e é revogável. Sem versão, "a pessoa aceitou" não quer dizer
nada seis meses depois, quando o texto mudou.

**"Eu pedi exclusão, o que vocês fizeram?"** → `data_requests` e
`data_request_items`. Um pedido do titular **não é um DELETE**: é uma
decisão item a item, cada uma com motivo e base legal. Prontuário tem
guarda obrigatória; cadastro comercial não tem. Tratar os dois igual é
errado nos dois sentidos — ou some o que a lei manda guardar, ou fica o
que a pessoa pediu para apagar.

**"Por quanto tempo isto fica?"** → `retention_policies`. E aqui está a
decisão mais importante do arquivo: **ela nasce vazia**. O prazo de guarda
depende do conselho profissional de cada categoria, e inventar um número
seria pior do que não ter nenhum — daria aparência de conformidade a um
chute. Enquanto não houver política com `legal_basis` preenchida, **nada é
apagado automaticamente**.
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (Enum, ForeignKey, ForeignKeyConstraint, Index, SmallInteger,
                        String, Text, UniqueConstraint)
from sqlalchemy.dialects.mysql import BIGINT, DATETIME
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TABLE_ARGS, Base, PKMixin, TenantScoped, TimestampMixin

TIPOS_CONSENTIMENTO = ("terms", "privacy", "clinical_treatment", "image", "communication")

# Os direitos do titular, na ordem do art. 18 da LGPD.
TIPOS_PEDIDO = ("access", "portability", "rectification", "erasure",
                "restriction", "revoke_consent", "information")
STATUS_PEDIDO = ("open", "in_progress", "done", "refused")

# Sobre o que cada item do pedido decide.
ALVOS = ("registration", "appointments", "payments", "clinical", "documents", "other")
DECISOES = ("export", "anonymize", "erase", "keep", "restrict")


class Consent(Base, PKMixin, TenantScoped, TimestampMixin):
    """Um aceite, com versão e data. Revogável."""

    __tablename__ = "consents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"],
            name="fk_consents_tenant_id_client_id", ondelete="RESTRICT",
        ),
        Index("ix_consents_tenant_id_client_id_kind", "tenant_id", "client_id", "kind"),
        TABLE_ARGS,
    )

    client_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    kind: Mapped[str] = mapped_column(
        Enum(*TIPOS_CONSENTIMENTO, name="consent_kind"), nullable=False
    )
    # Versão do texto aceito. Sem isto, "a pessoa aceitou" não diz nada
    # depois que o texto mudar.
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="1")
    # sha256 do texto apresentado — prova de QUAL texto foi aceito.
    text_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    granted_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)
    source: Mapped[str] = mapped_column(
        Enum("in_person", "online", "imported", name="consent_source"),
        nullable=False, default="in_person",
    )
    note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    registered_by_user_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    client = relationship(
        "Client",
        primaryjoin="and_(Consent.tenant_id == Client.tenant_id, "
                    "Consent.client_id == Client.id)",
        foreign_keys="[Consent.tenant_id, Consent.client_id]",
        lazy="joined", viewonly=True,
    )

    @property
    def vigente(self) -> bool:
        return self.revoked_at is None

    def __repr__(self) -> str:
        return f"<Consent {self.public_id} {self.kind}>"


class DataRequest(Base, PKMixin, TenantScoped, TimestampMixin):
    """Pedido do titular. Não é um DELETE — é uma decisão item a item."""

    __tablename__ = "data_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"],
            name="fk_data_requests_tenant_id_client_id", ondelete="RESTRICT",
        ),
        Index("ix_data_requests_tenant_id_status", "tenant_id", "status"),
        TABLE_ARGS,
    )

    client_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    kind: Mapped[str] = mapped_column(Enum(*TIPOS_PEDIDO, name="data_request_kind"),
                                      nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(*STATUS_PEDIDO, name="data_request_status"), nullable=False, default="open"
    )

    requested_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    # Prazo de resposta. Fica NULO por padrão: quem registra o pedido
    # informa, se a conta tiver um. Não há número chutado aqui.
    due_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)

    # Quem pediu: o próprio titular, um representante legal, etc.
    requester: Mapped[str] = mapped_column(String(120), nullable=False, default="titular")
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Quando o pedido é recusado, o motivo é obrigatório na aplicação.
    outcome_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    registered_by_user_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    client = relationship(
        "Client",
        primaryjoin="and_(DataRequest.tenant_id == Client.tenant_id, "
                    "DataRequest.client_id == Client.id)",
        foreign_keys="[DataRequest.tenant_id, DataRequest.client_id]",
        lazy="joined", viewonly=True,
    )
    itens = relationship(
        "DataRequestItem", lazy="selectin",
        primaryjoin="and_(DataRequest.tenant_id == DataRequestItem.tenant_id, "
                    "DataRequest.id == DataRequestItem.request_id)",
        foreign_keys="[DataRequestItem.tenant_id, DataRequestItem.request_id]",
        viewonly=True, order_by="DataRequestItem.id",
    )

    def __repr__(self) -> str:
        return f"<DataRequest {self.public_id} {self.kind}/{self.status}>"


class DataRequestItem(Base, PKMixin, TenantScoped, TimestampMixin):
    """Uma decisão do pedido: sobre o quê, o que foi feito, e por quê.

    `legal_basis` existe porque "apagamos" e "mantivemos" precisam ser
    igualmente justificáveis. Manter prontuário contra um pedido de
    exclusão é legítimo — e é exatamente o tipo de coisa que precisa estar
    escrito antes de alguém perguntar.
    """

    __tablename__ = "data_request_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "request_id"], ["data_requests.tenant_id", "data_requests.id"],
            name="fk_data_request_items_tenant_id_request_id", ondelete="CASCADE",
        ),
        Index("ix_data_request_items_tenant_id_request_id", "tenant_id", "request_id"),
        TABLE_ARGS,
    )

    request_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    target: Mapped[str] = mapped_column(Enum(*ALVOS, name="data_item_target"), nullable=False)
    decision: Mapped[str] = mapped_column(Enum(*DECISOES, name="data_item_decision"),
                                          nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    legal_basis: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)
    applied_by_user_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Resultado em texto curto ("3 notas apagadas"). Nunca conteúdo.
    result: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    def __repr__(self) -> str:
        return f"<DataRequestItem {self.target}/{self.decision}>"


class RetentionPolicy(Base, PKMixin, TenantScoped, TimestampMixin):
    """Por quanto tempo cada coisa fica — quando alguém definir.

    **Nasce vazia, e continua vazia até que uma pessoa preencha.** O prazo
    de guarda depende do conselho profissional de cada categoria; inventar
    um número daria aparência de conformidade a um chute. Sem política com
    base legal, nada é apagado automaticamente — e a ausência fica
    visível, em vez de virar um padrão silencioso.
    """

    __tablename__ = "retention_policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "record_kind", "profession_id",
                         name="uq_retention_policies_tenant_id_record_kind_profession_id"),
        TABLE_ARGS,
    )

    record_kind: Mapped[str] = mapped_column(Enum(*ALVOS, name="data_item_target"),
                                             nullable=False)
    profession_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("professions.id", ondelete="CASCADE"), nullable=True
    )
    # NULO = sem prazo definido. É o padrão, e é proposital.
    months: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    # Sem base legal escrita, a política não vale para apagar nada.
    legal_basis: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    @property
    def aplicavel(self) -> bool:
        """Só vale se tiver prazo E base legal. Uma sem a outra não decide nada."""
        return self.months is not None and bool((self.legal_basis or "").strip())

    def __repr__(self) -> str:
        return f"<RetentionPolicy {self.record_kind} {self.months}m>"
