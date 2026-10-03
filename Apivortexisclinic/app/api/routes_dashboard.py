"""
Painel inicial e números do financeiro.

Por que existe um endpoint só para o dashboard: a tela precisa de seis
recortes ao mesmo tempo. Seis chamadas seriam seis idas ao banco e seis
chances de cada uma calcular do seu jeito. Aqui a conta é feita uma vez,
pela camada de domínio, e a tela só desenha.

**Financeiro nesta etapa é só leitura.** Valor e situação de pagamento
nascem no atendimento, então o resumo já é real. A tabela `payments`, a
baixa e os métodos entram na etapa do financeiro.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app import schemas_negocio as sn
from app.api import apresentacao
from app.api.deps import Contexto, com_tenant, exigir
from app.domain import calendario, metrics
from app.models.appointment import Appointment
from app.models.payment import Payment
from app.services import appointments as servico_atendimentos
from app.services import clients as servico_clientes
from app.services import scope
from app.services.sessions import agora

router = APIRouter(prefix="/workspace", tags=["dashboard"])


# ---------------- apoio ----------------
# Os recortes ("hoje", "este mês", "esta semana") são calculados no FUSO
# DA CONTA e convertidos para UTC na hora de consultar. Antes disso tudo
# rodava em UTC, e quem atende no Brasil via o atendimento das 22h cair no
# dia seguinte. Ver app/domain/calendario.py.
inicio_do_mes = calendario.inicio_do_mes
fim_do_mes = calendario.fim_do_mes
inicio_da_semana = calendario.inicio_da_semana


def _do_periodo(db, ctx, de: datetime, ate: datetime) -> List[Appointment]:
    consulta = scope.atendimentos(
        select(Appointment).where(Appointment.start_at >= de, Appointment.start_at <= ate), ctx
    )
    return list(db.execute(consulta).scalars())


def _pagamentos_do_periodo(db, ctx, de: datetime, ate: datetime) -> List[Payment]:
    """Entradas do período, pela data em que o dinheiro entrou."""
    from app.services import payments as servico_pagamentos

    return servico_pagamentos.listar(db, ctx, de=de, ate=ate,
                                     incluir_estornados=False, limite=500)


def _meta_do_tenant(ctx) -> Optional[Decimal]:
    """Meta do mês, como a conta configurou. Nula quando ninguém definiu.

    Nula de propósito: meta inventada vira cobrança em cima de um número
    que a pessoa não escolheu. A tela mostra estado vazio.
    """
    from app.services import settings as servico_config

    return servico_config.obter(ctx.db, ctx.tenant_id).monthly_goal


def resumo_financeiro(db, ctx, referencia: date) -> sn.ResumoFinanceiroOut:
    fuso = ctx.fuso
    primeiro = inicio_do_mes(referencia)
    anterior_ref = primeiro - timedelta(days=1)

    # O mês da conta, não o mês de Greenwich: o fechamento do dia 31 não
    # pode pegar as primeiras horas do dia 1º.
    de_mes, ate_mes = calendario.mes(referencia, fuso)
    de_ant, ate_ant = calendario.mes(anterior_ref, fuso)

    do_mes = _do_periodo(db, ctx, de_mes, ate_mes)
    do_anterior = _do_periodo(db, ctx, de_ant, ate_ant)

    # Recebido vem do livro-caixa (regime de caixa); pendente e previsto,
    # do atendimento. Ver app/domain/metrics.py.
    pagos_no_mes = _pagamentos_do_periodo(db, ctx, de_mes, ate_mes)
    pagos_no_anterior = _pagamentos_do_periodo(db, ctx, de_ant, ate_ant)

    r = metrics.receita(do_mes, agora(), pagos_no_mes)
    anterior = metrics.receita(do_anterior, agora(), pagos_no_anterior)
    meta = _meta_do_tenant(ctx)

    return sn.ResumoFinanceiroOut(
        referencia=primeiro,
        recebido=r["recebido"], pendente=r["pendente"], previsto=r["previsto"], total=r["total"],
        quantidade_recebida=r["quantidade_recebida"],
        quantidade_pendente=r["quantidade_pendente"],
        meta=meta,
        percentual_meta=metrics.percentual_meta(r["recebido"], meta),
        variacao_mes_anterior=metrics.variacao(r["recebido"], anterior["recebido"]),
    )


def pendencias(db, ctx) -> List[sn.PendenciaOut]:
    momento = agora()
    abertos = metrics.em_aberto(
        _do_periodo(db, ctx, datetime(2000, 1, 1), momento), momento
    )
    abertos.sort(key=lambda a: a.start_at)
    mapa = apresentacao.MapaDeProfissionais(db, [a.professional_id for a in abertos])
    return [
        apresentacao.pendencia(a, metrics.dias_em_aberto(a, momento), mapa.publico(a.professional_id))
        for a in abertos
    ]


# ---------------- rotas ----------------
@router.get("/dashboard", response_model=sn.DashboardOut)
def dashboard(ctx: Contexto = Depends(exigir("appointments.read"))):
    db = ctx.db
    momento = agora()
    fuso = ctx.fuso
    hoje_local = calendario.hoje_local(fuso)

    hoje = servico_atendimentos.do_dia(db, ctx, hoje_local, fuso=fuso)
    proximos = [a for a in servico_atendimentos.proximos(db, ctx, 8)
                if calendario.para_local(a.start_at, fuso).date() != hoje_local][:5]

    comeco = inicio_da_semana(hoje_local)
    de_semana, ate_semana = calendario.semana(hoje_local, fuso)
    da_semana = _do_periodo(db, ctx, de_semana, ate_semana)

    # Financeiro só para quem pode ver financeiro. O dashboard não é
    # atalho para contornar permissão.
    financeiro = resumo_financeiro(db, ctx, hoje_local) if ctx.pode("finance.read") else None
    abertos = pendencias(db, ctx) if ctx.pode("finance.read") else []

    mapa = apresentacao.MapaDeProfissionais(
        db, [a.professional_id for a in hoje] + [a.professional_id for a in proximos]
    )

    return sn.DashboardOut(
        hoje=[apresentacao.atendimento(a, mapa.publico(a.professional_id)) for a in hoje],
        resumo_dia=sn.ResumoDiaOut(**metrics.resumo_do_dia(hoje, momento)),
        proximos=[apresentacao.atendimento(a, mapa.publico(a.professional_id)) for a in proximos],
        clientes=sn.ContagemClientesOut(**servico_clientes.contar(db, ctx)),
        financeiro=financeiro,
        pendencias=abertos,
        semana=sn.ResumoSemanaOut(**metrics.resumo_da_semana(da_semana, comeco, fuso)),
    )


@router.get("/finance/summary", response_model=sn.ResumoFinanceiroOut)
def financeiro_resumo(mes: Optional[date] = Query(None),
                      ctx: Contexto = Depends(exigir("finance.read"))):
    return resumo_financeiro(ctx.db, ctx, mes or calendario.hoje_local(ctx.fuso))


@router.get("/finance/pending", response_model=List[sn.PendenciaOut])
def financeiro_pendencias(ctx: Contexto = Depends(exigir("finance.read"))):
    lista = pendencias(ctx.db, ctx)
    lista.sort(key=lambda p: p.dias_em_aberto, reverse=True)
    return lista


@router.get("/finance/series", response_model=List[sn.PontoDaSerieOut])
def financeiro_serie(meses: int = Query(6, ge=1, le=24),
                     ctx: Contexto = Depends(exigir("finance.read"))):
    fuso = ctx.fuso
    hoje = calendario.hoje_local(fuso)
    saida = []
    for i in range(meses - 1, -1, -1):
        ref = inicio_do_mes(hoje)
        for _ in range(i):
            ref = inicio_do_mes(ref - timedelta(days=1))
        de, ate = calendario.mes(ref, fuso)
        pagos = _pagamentos_do_periodo(ctx.db, ctx, de, ate)
        caixa = metrics.caixa(pagos)
        saida.append(sn.PontoDaSerieOut(mes=ref, valor=caixa["recebido"],
                                        quantidade=caixa["quantidade_recebida"]))
    return saida


@router.get("/agenda", response_model=List[sn.AtendimentoOut])
def agenda(de: sn.Instante = Query(...), ate: sn.Instante = Query(...),
           ctx: Contexto = Depends(exigir("agenda.read"))):
    linhas = servico_atendimentos.listar(ctx.db, ctx, de=de, ate=ate, limite=1000)
    mapa = apresentacao.MapaDeProfissionais(ctx.db, [a.professional_id for a in linhas])
    return [apresentacao.atendimento(a, mapa.publico(a.professional_id)) for a in linhas]
