"""
professions — catálogo de categorias profissionais.

Entra nesta etapa porque o cadastro já precisa dela: o onboarding pergunta
a profissão, e é ela que decide se a tela pede conselho e registro. Sem o
catálogo, esse "se" viraria `if profissao == "psicologo"` no código — que é
exatamente o que a arquitetura proibiu.

`profession_fields` (campos extras por profissão) NÃO entra agora: nenhum
formulário desta etapa consome campo dinâmico. Fica modelado no documento
de arquitetura e entra quando o perfil profissional ganhar edição.
"""
from typing import Optional

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TABLE_ARGS, Base, PKMixin, TimestampMixin


class Profession(Base, PKMixin, TimestampMixin):
    __tablename__ = "professions"
    __table_args__ = (TABLE_ARGS,)

    slug: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    # Nem toda profissão tem conselho. Quem decide é o catálogo, não o código.
    requires_council: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    council_label: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    registration_label: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)

    # Sugestão de terminologia da categoria (JSON em texto, compatível
    # com MySQL e MariaDB). O painel já sabe consumir este formato.
    default_terminology: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
