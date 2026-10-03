"""
Rotas de atendimentos e agenda.

Cancelar tem permissão própria (`appointments.cancel`): desmarcar afeta a
agenda de outra pessoa e o faturamento, então não vem de brinde com
"editar".
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request, Response

from app import errors, schemas_negocio as sn
from app.api import apresentacao
from app.api.deps import Contexto, exigir
from app.api.routes_auth import registrar_evento
from app.services import appointments as servico

router = APIRouter(prefix="/workspace/appointments", tags=["appointments"])


def _saida(ctx: Contexto, linhas):
    mapa = apresentacao.MapaDeProfissionais(ctx.db, [a.professional_id for a in linhas])
    return [apresentacao.atendimento(a, mapa.publico(a.professional_id)) for a in linhas]


@router.get("", response_model=List[sn.AtendimentoOut])
def listar(
    resposta: Response,
    de: Optional[sn.Instante] = Query(None),
    ate: Optional[sn.Instante] = Query(None),
    status: Optional[str] = Query(None, max_length=20),
    modalidade: Optional[str] = Query(None, max_length=20),
    pagamento: Optional[str] = Query(None, max_length=20),
    limite: int = Query(500, ge=1, le=1000),
    pagina: int = Query(0, ge=0),
    ctx: Contexto = Depends(exigir("appointments.read")),
):
    """`pagina=0` devolve a janela inteira — é o que a agenda usa, porque
    ali o recorte já são as datas. Com página, o total vai em
    `X-Total-Count`."""
    from app.services import paginacao

    filtros = dict(de=de, ate=ate, status=status, modalidade=modalidade, pagamento=pagamento)
    linhas = servico.listar(ctx.db, ctx, limite=limite, pagina=pagina, **filtros)
    if pagina:
        paginacao.cabecalhos(resposta, total_de_linhas=servico.contar(ctx.db, ctx, **filtros),
                             pagina=pagina, tamanho=limite)
    return _saida(ctx, linhas)


@router.get("/proximos", response_model=List[sn.AtendimentoOut])
def proximos(quantidade: int = Query(5, ge=1, le=50),
             ctx: Contexto = Depends(exigir("appointments.read"))):
    return _saida(ctx, servico.proximos(ctx.db, ctx, quantidade))


@router.get("/{public_id}", response_model=sn.AtendimentoOut)
def obter(public_id: str, ctx: Contexto = Depends(exigir("appointments.read"))):
    a = servico.obter(ctx.db, ctx, public_id)
    mapa = apresentacao.MapaDeProfissionais(ctx.db, [a.professional_id])
    return apresentacao.atendimento(a, mapa.publico(a.professional_id))


@router.post("", response_model=sn.AtendimentoOut, status_code=201)
def criar(dados: sn.AtendimentoIn, request: Request,
          ctx: Contexto = Depends(exigir("appointments.write"))):
    try:
        a = servico.criar(ctx.db, ctx, dados)
        registrar_evento(ctx.db, request=request, action="appointment_create", outcome="allowed",
                         user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
        mapa = apresentacao.MapaDeProfissionais(ctx.db, [a.professional_id])
        saida = apresentacao.atendimento(a, mapa.publico(a.professional_id))
        ctx.db.commit()
        return saida
    except errors.ApiError:
        ctx.db.rollback()
        raise
    except Exception:
        ctx.db.rollback()
        raise errors.conflito("falha_ao_agendar", "Não foi possível agendar agora.")


@router.patch("/{public_id}", response_model=sn.AtendimentoOut)
def atualizar(public_id: str, dados: sn.AtendimentoUpdateIn,
              ctx: Contexto = Depends(exigir("appointments.write"))):
    a = servico.obter(ctx.db, ctx, public_id)
    servico.atualizar(ctx.db, ctx, a, dados)
    mapa = apresentacao.MapaDeProfissionais(ctx.db, [a.professional_id])
    saida = apresentacao.atendimento(a, mapa.publico(a.professional_id))
    ctx.db.commit()
    return saida


@router.post("/{public_id}/reschedule", response_model=sn.AtendimentoOut)
def reagendar(public_id: str, dados: sn.ReagendarIn, request: Request,
              ctx: Contexto = Depends(exigir("appointments.write"))):
    a = servico.obter(ctx.db, ctx, public_id)
    try:
        servico.reagendar(ctx.db, ctx, a, dados.inicio, dados.duracao_min)
        registrar_evento(ctx.db, request=request, action="appointment_reschedule",
                         outcome="allowed", user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
        mapa = apresentacao.MapaDeProfissionais(ctx.db, [a.professional_id])
        saida = apresentacao.atendimento(a, mapa.publico(a.professional_id))
        ctx.db.commit()
        return saida
    except errors.ApiError:
        ctx.db.rollback()
        raise


@router.post("/{public_id}/status", response_model=sn.AtendimentoOut)
def mudar_status(public_id: str, dados: sn.StatusIn, request: Request,
                 ctx: Contexto = Depends(exigir("appointments.write"))):
    a = servico.obter(ctx.db, ctx, public_id)

    # Cancelar é uma ação à parte: mexe na agenda e no faturamento.
    if dados.status == "cancelled" and not ctx.pode("appointments.cancel"):
        raise errors.sem_permissao("appointments.cancel")

    try:
        servico.mudar_status(ctx.db, ctx, a, dados.status, dados.motivo)
        registrar_evento(ctx.db, request=request, action="appointment_status", outcome="allowed",
                         user_id=ctx.usuario.id, tenant_id=ctx.tenant_id,
                         meta=f"status={dados.status}")
        mapa = apresentacao.MapaDeProfissionais(ctx.db, [a.professional_id])
        saida = apresentacao.atendimento(a, mapa.publico(a.professional_id))
        ctx.db.commit()
        return saida
    except errors.ApiError:
        ctx.db.rollback()
        raise
