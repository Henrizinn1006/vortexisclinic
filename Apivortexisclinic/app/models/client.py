"""
clients — a pessoa atendida.

Rótulo na tela vem da terminologia da conta ("paciente", "cliente"); aqui o
nome é `clients` porque a borda da API fala inglês (decisão 5 da Etapa 2).

Duas coisas de arquitetura moram aqui:

1. **Tenant-scoped de verdade** — herda `TenantScoped`, então toda consulta
   recebe o filtro automático e falha sem tenant no contexto.
2. **`UNIQUE (tenant_id, id)`** — é a chave que `appointments` referencia com
   FK composta. Assim, um atendimento do tenant A **não consegue** apontar
   para um cliente do tenant B nem que a aplicação erre.

Ser atendido por um terapeuta já é dado de saúde (sensível por associação),
por isso esta tabela tem o mesmo cuidado do prontuário na hora de exportar,
logar ou cachear — mesmo sendo, para efeito de permissão, administrativa.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (Boolean, Date, Enum, ForeignKey, ForeignKeyConstraint, Index,
                        String, Text, UniqueConstraint)
from sqlalchemy.dialects.mysql import BIGINT, DATETIME, DECIMAL
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TABLE_ARGS, Base, PKMixin, TenantScoped, TimestampMixin

STATUS_CLIENTE = ("active", "inactive", "archived")
FREQUENCIAS = ("weekly", "biweekly", "monthly", "irregular")
MODALIDADES = ("in_person", "online")


class Client(Base, PKMixin, TenantScoped, TimestampMixin):
    __tablename__ = "clients"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_clients_tenant_id_id"),
        Index("ix_clients_tenant_id_status_name", "tenant_id", "status", "name"),
        Index("ix_clients_tenant_id_created_at", "tenant_id", "created_at"),
        TABLE_ARGS,
    )

    name: Mapped[str] = mapped_column(String(140), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(190), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Responsável, quando a pessoa atendida é menor de idade ou está sob
    # curatela. JSON em texto para não depender do tipo JSON do MySQL.
    guardian: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        Enum(*STATUS_CLIENTE, name="client_status"), nullable=False, default="active"
    )
    frequency: Mapped[str] = mapped_column(
        Enum(*FREQUENCIAS, name="client_frequency"), nullable=False, default="weekly"
    )
    default_modality: Mapped[str] = mapped_column(
        Enum(*MODALIDADES, name="appointment_modality"), nullable=False, default="in_person"
    )
    default_price: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 2), nullable=True)

    started_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Observação ADMINISTRATIVA (chegou atrasado, prefere manhã).
    # Conteúdo clínico não entra aqui — tem tabela, cifra e permissão próprias.
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)
    # Preenchido pelo fluxo de LGPD: o cadastro é anonimizado, a série
    # clínica sobrevive sem titular identificável.
    anonymized_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=3), nullable=True)

    profissionais = relationship(
        "ClientProfessional", back_populates="client", lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:      # nunca o nome: isso é dado de pessoa atendida
        return f"<Client {self.public_id}>"


class ClientProfessional(Base, TenantScoped, TimestampMixin):
    """Quem atende quem — a base do escopo "só os meus".

    Sem esta tabela, `data_scope = "own"` não teria como ser respondido:
    seria preciso deduzir pelo histórico de atendimentos, o que falharia
    justamente no caso novo (cliente cadastrado e ainda sem sessão).
    """

    __tablename__ = "client_professionals"
    __table_args__ = (
        # FK COMPOSTA: o vínculo aponta para (tenant, cliente) e para
        # (tenant, profissional) ao mesmo tempo. O banco impede, sozinho,
        # ligar um cliente de uma conta a um profissional de outra.
        ForeignKeyConstraint(
            ["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"],
            name="fk_client_professionals_tenant_id_client_id", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "professional_id"], ["professionals.tenant_id", "professionals.id"],
            name="fk_client_professionals_tenant_id_professional_id", ondelete="CASCADE",
        ),
        Index("ix_client_professionals_tenant_id_professional_id", "tenant_id", "professional_id"),
        TABLE_ARGS,
    )

    # tenant_id entra na chave primária: o vínculo é (conta, cliente, profissional).
    tenant_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True)
    client_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True)
    professional_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True)

    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    started_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    ended_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    client = relationship(
        "Client", back_populates="profissionais",
        primaryjoin="and_(ClientProfessional.tenant_id == Client.tenant_id, "
                    "ClientProfessional.client_id == Client.id)",
        foreign_keys="[ClientProfessional.tenant_id, ClientProfessional.client_id]",
    )
