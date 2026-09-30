"""
Prontuário: a nota, as versões e a trilha de quem olhou.

Três tabelas, e cada uma existe por um motivo que não é organização de
código.

**clinical_notes — a ficha, sem o texto**

Guarda metadado: de quem é, quem escreveu, quando aconteceu, que tipo é,
se está assinada. O texto NÃO está aqui. Separar permite listar o
histórico de uma pessoa (quantas evoluções, quando, de quem) sem decifrar
uma linha sequer — e listar é a operação mais frequente.

Repare no que não existe: **não há título**. Título de evolução é
conteúdo clínico disfarçado de metadado ("crise", "alta") e ficaria em
texto puro no índice. A nota se identifica por tipo e data.

**clinical_note_versions — o texto, cifrado, append-only**

Uma linha por versão. Editar não altera linha: insere a próxima. Isso é
exigência de registro em saúde — o que foi escrito e depois corrigido
precisa continuar demonstrável — e é também a razão de não existir
UPDATE no serviço.

O conteúdo é `VARBINARY` porque é ciphertext, não texto: não há collation,
não há LIKE, não há índice de busca. Buscar dentro do prontuário exigiria
decifrar o acervo inteiro a cada consulta; essa é uma troca consciente,
descrita no README.

**clinical_access_log — quem abriu o quê**

Prontuário sem trilha de acesso é prontuário aberto: ninguém descobre que
foi lido indevidamente. A trilha grava leitura, escrita **e negativa** —
a tentativa recusada é justamente o sinal que interessa. Também é
append-only, e nem o dono da conta apaga linha dela.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (Enum, ForeignKey, ForeignKeyConstraint, Index, SmallInteger,
                        String, UniqueConstraint, func)
from sqlalchemy.dialects.mysql import (BIGINT, DATETIME, INTEGER, MEDIUMBLOB,
                                       VARBINARY)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TABLE_ARGS, Base, PKMixin, TenantScoped, TimestampMixin

TIPOS_NOTA = ("session", "assessment", "plan", "note")
STATUS_NOTA = ("draft", "signed")

ACOES = ("list", "read", "create", "update", "sign", "export")
RESULTADOS = ("allowed", "denied")


class ClinicalNote(Base, PKMixin, TenantScoped, TimestampMixin):
    __tablename__ = "clinical_notes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_clinical_notes_tenant_id_id"),
        # FKs compostas: a nota não cruza contas nem que a aplicação erre.
        ForeignKeyConstraint(
            ["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"],
            name="fk_clinical_notes_tenant_id_client_id", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "professional_id"], ["professionals.tenant_id", "professionals.id"],
            name="fk_clinical_notes_tenant_id_professional_id", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "appointment_id"], ["appointments.tenant_id", "appointments.id"],
            name="fk_clinical_notes_tenant_id_appointment_id", ondelete="RESTRICT",
        ),
        Index("ix_clinical_notes_tenant_id_client_id_occurred_at",
              "tenant_id", "client_id", "occurred_at"),
        Index("ix_clinical_notes_tenant_id_professional_id", "tenant_id", "professional_id"),
        TABLE_ARGS,
    )

    client_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)

    # Autor. Não é nulo de propósito: escrever prontuário exige perfil
    # profissional nesta conta. Quem administra a conta e não atende não
    # tem como ser autor — nem por concessão.
    professional_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)

    appointment_id: Mapped[Optional[int]] = mapped_column(BIGINT(unsigned=True), nullable=True)

    kind: Mapped[str] = mapped_column(
        Enum(*TIPOS_NOTA, name="clinical_note_kind"), nullable=False, default="session"
    )
    status: Mapped[str] = mapped_column(
        Enum(*STATUS_NOTA, name="clinical_note_status"), nullable=False, default="draft"
    )

    occurred_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)

    # Sal da derivação de chave desta nota. NULO = conteúdo destruído a
    # pedido do titular: as versões continuam na tabela e nenhuma delas
    # abre mais. Metadado e trilha sobrevivem; o texto, não.
    content_key_salt: Mapped[Optional[bytes]] = mapped_column(VARBINARY(16), nullable=True)

    current_version: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False, default=0)

    signed_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)
    signed_by_membership_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), nullable=True
    )
    content_erased_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)

    versions = relationship(
        "ClinicalNoteVersion", back_populates="note", lazy="selectin",
        order_by="ClinicalNoteVersion.version",
        primaryjoin="and_(ClinicalNote.tenant_id == ClinicalNoteVersion.tenant_id, "
                    "ClinicalNote.id == ClinicalNoteVersion.note_id)",
        foreign_keys="[ClinicalNoteVersion.tenant_id, ClinicalNoteVersion.note_id]",
        viewonly=True,
    )
    client = relationship(
        "Client",
        primaryjoin="and_(ClinicalNote.tenant_id == Client.tenant_id, "
                    "ClinicalNote.client_id == Client.id)",
        foreign_keys="[ClinicalNote.tenant_id, ClinicalNote.client_id]",
        lazy="joined", viewonly=True,
    )
    appointment = relationship(
        "Appointment",
        primaryjoin="and_(ClinicalNote.tenant_id == Appointment.tenant_id, "
                    "ClinicalNote.appointment_id == Appointment.id)",
        foreign_keys="[ClinicalNote.tenant_id, ClinicalNote.appointment_id]",
        lazy="joined", viewonly=True,
    )

    @property
    def assinada(self) -> bool:
        return self.status == "signed"

    def __repr__(self) -> str:      # jamais conteúdo, jamais nome de pessoa
        return f"<ClinicalNote {self.public_id} v{self.current_version}>"


class ClinicalNoteVersion(Base, PKMixin, TenantScoped):
    """Uma versão do texto. Nasce e não muda mais.

    Sem `updated_at` de propósito: a coluna sugeriria que a linha pode ser
    alterada, e a regra aqui é a oposta. Correção vira versão nova.
    """

    __tablename__ = "clinical_note_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "note_id", "version",
                         name="uq_clinical_note_versions_tenant_id_note_id_version"),
        ForeignKeyConstraint(
            ["tenant_id", "note_id"], ["clinical_notes.tenant_id", "clinical_notes.id"],
            name="fk_clinical_note_versions_tenant_id_note_id", ondelete="RESTRICT",
        ),
        TABLE_ARGS,
    )

    note_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    version: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False)

    # Ciphertext AES-256-GCM (a tag vem junto). Binário: sem collation,
    # sem LIKE, sem índice de texto — e é assim que tem que ser.
    ciphertext: Mapped[bytes] = mapped_column(MEDIUMBLOB, nullable=False)
    nonce: Mapped[bytes] = mapped_column(VARBINARY(12), nullable=False)
    key_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    # sha256 do texto em claro: detecta salvamento sem mudança e permite
    # conferir integridade depois de decifrar.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    created_by_membership_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), nullable=True
    )
    # Motivo obrigatório quando a nota já estava assinada (adendo).
    reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), server_default=func.now(3), nullable=False
    )

    note = relationship(
        "ClinicalNote", back_populates="versions",
        primaryjoin="and_(ClinicalNote.tenant_id == ClinicalNoteVersion.tenant_id, "
                    "ClinicalNote.id == ClinicalNoteVersion.note_id)",
        foreign_keys="[ClinicalNoteVersion.tenant_id, ClinicalNoteVersion.note_id]",
        viewonly=True,
    )

    def __repr__(self) -> str:
        return f"<ClinicalNoteVersion nota={self.note_id} v{self.version}>"


class ClinicalAccessLog(Base, PKMixin, TenantScoped):
    """Trilha de acesso ao prontuário. Append-only, inclusive as negativas."""

    __tablename__ = "clinical_access_log"
    __table_args__ = (
        Index("ix_clinical_access_log_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_clinical_access_log_tenant_id_client_id_created_at",
              "tenant_id", "client_id", "created_at"),
        Index("ix_clinical_access_log_tenant_id_user_id_created_at",
              "tenant_id", "user_id", "created_at"),
        TABLE_ARGS,
    )

    user_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    membership_id: Mapped[Optional[int]] = mapped_column(BIGINT(unsigned=True), nullable=True)

    # Sem FK composta aqui de propósito: a trilha precisa sobreviver a
    # qualquer coisa que aconteça com a nota, inclusive ao conteúdo ser
    # destruído. Ela registra o que foi tentado, não o que ainda existe.
    client_id: Mapped[Optional[int]] = mapped_column(BIGINT(unsigned=True), nullable=True)
    note_id: Mapped[Optional[int]] = mapped_column(BIGINT(unsigned=True), nullable=True)

    action: Mapped[str] = mapped_column(Enum(*ACOES, name="clinical_access_action"), nullable=False)
    outcome: Mapped[str] = mapped_column(
        Enum(*RESULTADOS, name="clinical_access_outcome"), nullable=False, default="allowed"
    )
    # Código curto ("sem_permissao", "nao_e_autor"). Nunca conteúdo.
    reason: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    auth_session_id: Mapped[Optional[int]] = mapped_column(BIGINT(unsigned=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), server_default=func.now(3), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ClinicalAccessLog {self.action}/{self.outcome}>"
