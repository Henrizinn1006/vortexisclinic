"""
documents — recibo, declaração, laudo e arquivo anexado.

**A classe do documento decide quem abre**

Recibo é administrativo: a recepção emite e o dono confere, porque é
dinheiro. Declaração, laudo e relatório são clínicos: quem assina é quem
atende, e ler é a mesma porta do prontuário. Misturar os dois numa
permissão só acabaria de um jeito previsível — a recepção enxergando laudo
para conseguir imprimir recibo.

Por isso a coluna `data_class`: ela não é decoração, é o que a rota
consulta para saber qual permissão exigir.

**O arquivo não fica legível no disco**

O conteúdo é cifrado com a mesma chave mestra do prontuário e derivação
por documento (AAD com prefixo próprio, para que ciphertext de nota nunca
abra como documento). No disco fica um `.bin` sem nome falante; o nome
original, o tipo e o tamanho ficam na linha.

**O que está guardado aqui não é o que foi impresso**

`content_hash` é o sha256 do arquivo em claro. Serve para provar que o
PDF que alguém apresenta é o mesmo que o sistema emitiu — e é o começo
do caminho para assinatura digital, quando ela entrar.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (Enum, ForeignKey, ForeignKeyConstraint, Index, String,
                        UniqueConstraint)
from sqlalchemy.dialects.mysql import BIGINT, DATETIME, INTEGER, SMALLINT, VARBINARY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TABLE_ARGS, Base, PKMixin, TenantScoped, TimestampMixin

# receipt         recibo de pagamento              → administrativo
# attendance      declaração de comparecimento     → clínico
# report          relatório / laudo                → clínico
# record_copy     cópia do prontuário              → clínico
# upload          arquivo anexado                  → clínico (por precaução)
TIPOS = ("receipt", "attendance", "report", "record_copy", "upload")
CLASSES = ("administrative", "clinical")

CLASSE_DE_TIPO = {
    "receipt": "administrative",
    "attendance": "clinical",
    "report": "clinical",
    "record_copy": "clinical",
    # Anexo sobe como clínico por precaução: ninguém sabe o que tem
    # dentro de um arquivo que alguém mandou, e o erro seguro é para o
    # lado de menos acesso.
    "upload": "clinical",
}


class Document(Base, PKMixin, TenantScoped, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_documents_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"],
            name="fk_documents_tenant_id_client_id", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "professional_id"], ["professionals.tenant_id", "professionals.id"],
            name="fk_documents_tenant_id_professional_id", ondelete="RESTRICT",
        ),
        Index("ix_documents_tenant_id_client_id_created_at",
              "tenant_id", "client_id", "created_at"),
        TABLE_ARGS,
    )

    client_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    # Quem assina. Nulo para recibo emitido pela recepção — recibo não é
    # ato profissional, é comprovante de dinheiro.
    professional_id: Mapped[Optional[int]] = mapped_column(BIGINT(unsigned=True), nullable=True)

    kind: Mapped[str] = mapped_column(Enum(*TIPOS, name="document_kind"), nullable=False)
    data_class: Mapped[str] = mapped_column(
        Enum(*CLASSES, name="document_class"), nullable=False, default="clinical"
    )

    title: Mapped[str] = mapped_column(String(160), nullable=False)
    file_name: Mapped[str] = mapped_column(String(160), nullable=False)
    mime: Mapped[str] = mapped_column(String(100), nullable=False, default="application/pdf")
    size_bytes: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False, default=0)

    # Caminho relativo dentro de VC_FILES_DIR. Não tem nome falante.
    storage_key: Mapped[str] = mapped_column(String(200), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Cifra: mesmo desenho do prontuário. Sal nulo = conteúdo destruído a
    # pedido do titular, sem apagar a linha.
    key_salt: Mapped[Optional[bytes]] = mapped_column(VARBINARY(16), nullable=True)
    nonce: Mapped[bytes] = mapped_column(VARBINARY(12), nullable=False)
    key_version: Mapped[int] = mapped_column(SMALLINT, nullable=False, default=0)

    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    content_erased_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)

    client = relationship(
        "Client",
        primaryjoin="and_(Document.tenant_id == Client.tenant_id, "
                    "Document.client_id == Client.id)",
        foreign_keys="[Document.tenant_id, Document.client_id]",
        lazy="joined", viewonly=True,
    )

    @property
    def eh_clinico(self) -> bool:
        return self.data_class == "clinical"

    def __repr__(self) -> str:      # nunca o nome do arquivo original
        return f"<Document {self.public_id} {self.kind}>"
