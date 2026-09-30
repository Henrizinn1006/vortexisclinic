"""
Rotas de recorrência e bloqueio de horário.

Duas decisões aparecem no formato das respostas.

**Criar recorrência devolve três coisas**: a série, o que foi criado e o
que **não** deu — com o motivo de cada um. Recusar as doze ocorrências
porque a terceira bateu com outra sessão seria obedecer à máquina em vez
da pessoa, que quer as onze livres marcadas e quer saber da que faltou.

**Criar bloqueio por cima de atendimento marcado é recusado**, com a
contagem do que está lá dentro. Quem confirma (`forcar`) bloqueia mesmo
assim — e os atendimentos **continuam de pé**. Cancelar sessão de alguém é
decisão de gente, não efeito colateral de um bloqueio de férias.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request

from app import errors, schemas_negocio as sn
from app.api import apresentacao
from app.api.deps import Contexto, exigir
from app.api.routes_auth import registrar_evento
from app.services import agenda as servico

router = APIRouter(prefix="/workspace", tags=["agenda"])


def serie_out(s, publico_do_profissional: str = "") -> sn.SerieOut:
    from datetime import datetime as dt

    return sn.SerieOut(
        id=s.public_id,
        frequencia=s.frequency,
        inicio=dt.combine(s.starts_on, s.start_time),
        duracao_min=s.duration_min,
        modalidade=s.modality,
        valor=s.price,
        ocorrencias=s.occurrences,
        ate=s.ends_on,
        status=s.status,
        cliente=apresentacao.cliente_resumido(s.client) if s.client else None,
        observacao=s.note,
    )


def bloqueio_out(b, publico_do_profissional: Optional[str] = None) -> sn.BloqueioOut:
    return sn.BloqueioOut(
        id=b.public_id,
        inicio=b.start_at,
        fim=b.end_at,
        titulo=b.title,
        tipo=b.kind,
        profissional_id=publico_do_profissional,
        da_conta_inteira=b.professional_id is None,
    )


# ---------------- recorrência ----------------
@router.post("/series", response_model=sn.SerieCriadaOut, status_code=201)
def criar_serie(dados: sn.SerieIn, request: Request,
                ctx: Contexto = Depends(exigir("appointments.write"))):
    try:
        serie, criados, conflitos = servico.criar_serie(ctx.db, ctx, dados)
        registrar_evento(ctx.db, request=request, action="series_create", outcome="allowed",
                         user_id=ctx.usuario.id, tenant_id=ctx.tenant_id,
                         meta=f"freq={serie.frequency} n={len(criados)}")
        mapa = apresentacao.MapaDeProfissionais(ctx.db, [serie.professional_id])
        corpo = sn.SerieCriadaOut(
            serie=serie_out(serie),
            criados=[apresentacao.atendimento(a, mapa.publico(a.professional_id))
                     for a in criados],
            conflitos=[sn.ConflitoOut(**c) for c in conflitos],
        )
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise


@router.get("/clients/{public_id}/series", response_model=List[sn.SerieOut])
def series_do_cliente(public_id: str, ctx: Contexto = Depends(exigir("appointments.read"))):
    from sqlalchemy import select

    from app.models.agenda import AppointmentSeries
    from app.services import clients as servico_clientes

    cliente = servico_clientes.obter(ctx.db, ctx, public_id)
    consulta = select(AppointmentSeries).where(AppointmentSeries.client_id == cliente.id)
    if not ctx.ve_tudo:
        if ctx.professional_id is None:
            return []
        consulta = consulta.where(AppointmentSeries.professional_id == ctx.professional_id)
    linhas = ctx.db.execute(consulta.order_by(AppointmentSeries.id.desc())).scalars()
    return [serie_out(s) for s in linhas]


@router.post("/series/{public_id}/end", response_model=sn.SerieOut)
def encerrar_serie(public_id: str, dados: sn.EncerrarSerieIn, request: Request,
                   ctx: Contexto = Depends(exigir("appointments.cancel"))):
    """Encerra o molde e, por padrão, cancela as ocorrências futuras.

    O passado nunca é tocado: sessão que já aconteceu é fato, não plano.
    """
    serie = servico.obter_serie(ctx.db, ctx, public_id)
    try:
        serie, cancelados = servico.encerrar_serie(
            ctx.db, ctx, serie, dados.motivo, dados.cancelar_futuros)
        registrar_evento(ctx.db, request=request, action="series_end", outcome="allowed",
                         user_id=ctx.usuario.id, tenant_id=ctx.tenant_id,
                         meta=f"cancelados={cancelados}")
        corpo = serie_out(serie)
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise


# ---------------- bloqueios ----------------
@router.get("/blocks", response_model=List[sn.BloqueioOut])
def listar_bloqueios(de: Optional[datetime] = Query(None), ate: Optional[datetime] = Query(None),
                     ctx: Contexto = Depends(exigir("agenda.read"))):
    linhas = servico.listar_bloqueios(ctx.db, ctx, de=de, ate=ate)
    mapa = apresentacao.MapaDeProfissionais(ctx.db, [b.professional_id for b in linhas])
    return [bloqueio_out(b, mapa.publico(b.professional_id) or None) for b in linhas]


@router.post("/blocks", response_model=sn.BloqueioCriadoOut, status_code=201)
def criar_bloqueio(dados: sn.BloqueioIn, request: Request,
                   ctx: Contexto = Depends(exigir("agenda.write"))):
    try:
        bloqueio, dentro = servico.criar_bloqueio(ctx.db, ctx, dados)
        registrar_evento(ctx.db, request=request, action="block_create", outcome="allowed",
                         user_id=ctx.usuario.id, tenant_id=ctx.tenant_id,
                         meta=f"tipo={bloqueio.kind}")
        mapa = apresentacao.MapaDeProfissionais(
            ctx.db, [bloqueio.professional_id] + [a.professional_id for a in dentro])
        corpo = sn.BloqueioCriadoOut(
            bloqueio=bloqueio_out(bloqueio, mapa.publico(bloqueio.professional_id) or None),
            atendimentos_no_periodo=[
                apresentacao.atendimento(a, mapa.publico(a.professional_id)) for a in dentro],
        )
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise


@router.delete("/blocks/{public_id}", response_model=sn.BloqueioOut)
def remover_bloqueio(public_id: str, request: Request,
                     ctx: Contexto = Depends(exigir("agenda.write"))):
    bloqueio = servico.obter_bloqueio(ctx.db, ctx, public_id)
    corpo = bloqueio_out(bloqueio)
    try:
        servico.remover_bloqueio(ctx.db, ctx, bloqueio)
        registrar_evento(ctx.db, request=request, action="block_delete", outcome="allowed",
                         user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise
