"""Rotas públicas: saúde do serviço e catálogo de profissões (usado no cadastro)."""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.config import settings
from app.db.session import get_db
from app.models.profession import Profession

router = APIRouter(tags=["meta"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    """Responde se a API está de pé E se o banco responde.

    Não devolve host, usuário, versão do driver nem nome do banco: health
    check é público e não precisa descrever a infraestrutura.
    """
    try:
        db.execute(select(1))
        banco = "ok"
    except Exception:
        banco = "indisponivel"
    return {"status": "ok" if banco == "ok" else "degradado", "banco": banco, "ambiente": settings.VC_ENV}


@router.get("/professions", response_model=List[schemas.ProfissaoOut])
def profissoes(db: Session = Depends(get_db)):
    """Catálogo para a tela de cadastro. É o que evita `if profissao == 'psicologo'`."""
    linhas = db.execute(
        select(Profession).where(Profession.active.is_(True)).order_by(Profession.name)
    ).scalars().all()
    return [
        schemas.ProfissaoOut(
            slug=p.slug,
            nome=p.name,
            exige_conselho=p.requires_council,
            rotulo_conselho=p.council_label,
            rotulo_registro=p.registration_label,
        )
        for p in linhas
    ]
