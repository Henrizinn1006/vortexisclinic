"""
Conversão modelo → resposta.

Um lugar só para isso, por dois motivos: a resposta nunca é "o modelo do
banco serializado" (id interno e coluna nova não escapam por descuido), e
o formato fica igual em toda rota que devolve a mesma entidade.
"""
from typing import Optional

from app.models.appointment import Appointment
from app.models.client import Client
from app.models.professional import Professional
from app.schemas_negocio import (AtendimentoOut, ClienteOut, ClienteResumidoOut,
                                 PendenciaOut, ResumoClienteOut)


def cliente_resumido(c: Client) -> ClienteResumidoOut:
    return ClienteResumidoOut(id=c.public_id, nome=c.name, status=c.status)


def cliente(c: Client, resumo: Optional[dict] = None) -> ClienteOut:
    return ClienteOut(
        id=c.public_id,
        nome=c.name,
        email=c.email,
        telefone=c.phone,
        nascimento=c.birth_date,
        status=c.status,
        frequencia=c.frequency,
        modalidade=c.default_modality,
        valor_sessao=c.default_price,
        desde=c.started_at,
        observacao=c.notes,
        anonimizado_em=c.anonymized_at,
        resumo=ResumoClienteOut(**resumo) if resumo else None,
    )


def atendimento(a: Appointment, publico_do_profissional: str = "") -> AtendimentoOut:
    return AtendimentoOut(
        id=a.public_id,
        inicio=a.start_at,
        duracao_min=a.duration_min,
        modalidade=a.modality,
        status=a.status,
        valor=a.price,
        pagamento=a.payment_status,
        metodo_pagamento=a.payment_method,
        pago_em=a.paid_at,
        observacao=a.note,
        cliente=cliente_resumido(a.client),
        profissional_id=publico_do_profissional,
    )


def pendencia(a: Appointment, dias: int, publico_do_profissional: str = "") -> PendenciaOut:
    base = atendimento(a, publico_do_profissional)
    return PendenciaOut(**base.model_dump(), dias_em_aberto=dias)


class MapaDeProfissionais:
    """Traduz id interno → id público sem uma consulta por linha."""

    def __init__(self, db, ids):
        from sqlalchemy import select

        ids = {i for i in ids if i}
        self._mapa = {}
        if ids:
            linhas = db.execute(
                select(Professional.id, Professional.public_id).where(Professional.id.in_(ids))
            ).all()
            self._mapa = {interno: publico for interno, publico in linhas}

    def publico(self, interno) -> str:
        return self._mapa.get(interno, "")
