"""
Camada de domínio: a definição dos números.

**Esta é a única fonte.** Tela, relatório e exportação leem daqui. Foi o
problema número 14 da análise: cada lugar calculando do seu jeito, e o
mesmo mês mostrando dois valores.

As regras, escritas uma vez:

- **Cancelado não conta** em volume nem em receita. Foi desmarcado a tempo;
  tratar como falta distorceria presença e faturamento.
- **Presença** = realizados ÷ (realizados + faltas). Agendado ainda não
  aconteceu e cancelado saiu da conta, então nenhum dos dois entra.
- **Recebido é regime de caixa.** Mudou na etapa do financeiro: antes
  vinha da bandeira do atendimento, agora vem do livro-caixa, somando os
  pagamentos pela data em que o dinheiro **entrou** (`paid_at`). É o que
  a pessoa quer dizer com "quanto recebi em setembro" — um atendimento
  de agosto pago em setembro entra em setembro, e é assim que ela vai
  conferir com o extrato do banco.
- **Pendente** é o que já foi realizado (ou o cliente faltou e a política
  cobra) e continua `pending`. **Previsto** é o que ainda vai acontecer.
  Esses dois continuam vindo do atendimento, porque falam de compromisso,
  não de caixa.
- **Isento** (`waived`) não é receita nem pendência: é uma decisão do
  profissional, e some das duas contas.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterable, List, Optional, Sequence

from app.models.appointment import Appointment

CANCELADO = "cancelled"
REALIZADO = "done"
FALTA = "no_show"
PAGO = "paid"
PENDENTE = "pending"
ISENTO = "waived"

ZERO = Decimal("0.00")


def _valor(a: Appointment) -> Decimal:
    return a.price if a.price is not None else ZERO


def ativos(lista: Iterable[Appointment]) -> List[Appointment]:
    """Tudo que não foi cancelado."""
    return [a for a in lista if a.status != CANCELADO]


def soma(lista: Iterable[Appointment]) -> Decimal:
    return sum((_valor(a) for a in lista), ZERO)


def contagens(lista: Iterable[Appointment]) -> dict:
    lista = list(lista)
    return {
        "total": len(ativos(lista)),
        "agendados": len([a for a in lista if a.status in ("scheduled", "confirmed")]),
        "realizados": len([a for a in lista if a.status == REALIZADO]),
        "faltas": len([a for a in lista if a.status == FALTA]),
        "cancelados": len([a for a in lista if a.status == CANCELADO]),
    }


def presenca(realizados: int, faltas: int) -> Optional[float]:
    """None quando não houve nenhum dos dois — 0% seria mentira."""
    base = realizados + faltas
    if base == 0:
        return None
    return round(realizados * 100 / base, 1)


def presenca_de(lista: Iterable[Appointment]) -> Optional[float]:
    c = contagens(lista)
    return presenca(c["realizados"], c["faltas"])


def caixa(pagamentos: Iterable) -> dict:
    """O que efetivamente entrou. Estorno não conta."""
    validos = [p for p in pagamentos if p.status == "paid"]
    return {
        "recebido": sum((p.amount for p in validos), ZERO),
        "quantidade_recebida": len(validos),
    }


def receita(
    lista: Iterable[Appointment],
    agora: Optional[datetime] = None,
    pagamentos: Optional[Iterable] = None,
) -> dict:
    """Números do mês.

    `lista` são os atendimentos do período (compromisso) e `pagamentos`
    são as entradas do período (caixa). Os dois recortes são pelo mesmo
    mês, mas por datas diferentes de propósito — ver o cabeçalho.

    Sem `pagamentos`, o recebido cai de volta na bandeira do atendimento.
    Isso serve ao teste de definição e a quem ainda não tem livro-caixa;
    a API sempre passa os pagamentos.
    """
    agora = agora or datetime.utcnow()
    lista = [a for a in lista if a.status != CANCELADO]

    # Pendente de verdade: já aconteceu e não foi pago nem isentado.
    pendentes = [
        a for a in lista
        if a.payment_status == PENDENTE and a.status in (REALIZADO, FALTA)
    ]
    previstos = [
        a for a in lista
        if a.payment_status == PENDENTE and a.status in ("scheduled", "confirmed")
    ]

    if pagamentos is None:
        pagos = [a for a in lista if a.payment_status == PAGO]
        entrada = {"recebido": soma(pagos), "quantidade_recebida": len(pagos)}
    else:
        entrada = caixa(pagamentos)

    return {
        "recebido": entrada["recebido"],
        "pendente": soma(pendentes),
        "previsto": soma(previstos),
        "total": entrada["recebido"] + soma(pendentes),
        "quantidade_recebida": entrada["quantidade_recebida"],
        "quantidade_pendente": len(pendentes),
    }


def percentual_meta(recebido: Decimal, meta: Optional[Decimal]) -> Optional[float]:
    if not meta:
        return None
    return round(float(recebido) * 100 / float(meta), 1)


def variacao(atual: Decimal, anterior: Decimal) -> Optional[float]:
    """Variação percentual. None quando não há base de comparação."""
    if not anterior:
        return None
    return round((float(atual) - float(anterior)) * 100 / float(anterior), 1)


def resumo_do_dia(lista: Sequence[Appointment], agora: Optional[datetime] = None) -> dict:
    agora = agora or datetime.utcnow()
    c = contagens(lista)
    restantes = [
        a for a in ativos(lista)
        if a.start_at > agora and a.status in ("scheduled", "confirmed")
    ]
    return {
        "total": c["total"],
        "realizados": c["realizados"],
        "faltas": c["faltas"],
        "cancelados": c["cancelados"],
        "restantes": len(restantes),
        "previsto": soma(ativos(lista)),
        "presenca": presenca(c["realizados"], c["faltas"]),
    }


def resumo_da_semana(lista: Sequence[Appointment], inicio_semana: date, fuso=None) -> dict:
    """Agrupa por dia. Com `fuso`, o dia é o da conta — não o de Greenwich.

    Sem ele o atendimento das 22h de terça no Brasil cairia na quarta,
    porque em UTC já é quarta. O fuso é opcional só para não quebrar
    chamada antiga; quem vem das rotas sempre passa.
    """
    from app.domain import calendario

    def data_local(a):
        return calendario.para_local(a.start_at, fuso).date() if fuso else a.start_at.date()

    dias = []
    hoje = calendario.hoje_local(fuso) if fuso else datetime.utcnow().date()
    for i in range(7):
        d = inicio_semana + timedelta(days=i)
        do_dia = [a for a in lista if data_local(a) == d]
        c = contagens(do_dia)
        dias.append({"data": d, "total": c["total"], "realizados": c["realizados"],
                     "faltas": c["faltas"], "hoje": d == hoje})

    c = contagens(lista)
    return {
        "inicio": inicio_semana,
        "fim": inicio_semana + timedelta(days=6),
        "dias": dias,
        "agendados": c["agendados"],
        "realizados": c["realizados"],
        "faltas": c["faltas"],
        "presenca": presenca(c["realizados"], c["faltas"]),
    }


def em_aberto(lista: Iterable[Appointment], agora: Optional[datetime] = None) -> List[Appointment]:
    """Já aconteceu e continua sem pagamento."""
    agora = agora or datetime.utcnow()
    return [
        a for a in lista
        if a.payment_status == PENDENTE and a.status in (REALIZADO, FALTA) and a.start_at <= agora
    ]


def dias_em_aberto(a: Appointment, agora: Optional[datetime] = None) -> int:
    agora = agora or datetime.utcnow()
    return max((agora - a.start_at).days, 0)


def total_em_aberto(lista: Iterable[Appointment]) -> Decimal:
    return soma(lista)


def resumo_do_cliente(lista: Sequence[Appointment], agora: Optional[datetime] = None) -> dict:
    """O que a lista e a ficha da pessoa atendida mostram."""
    agora = agora or datetime.utcnow()
    validos = ativos(lista)
    passados = sorted([a for a in validos if a.start_at <= agora], key=lambda a: a.start_at)
    futuros = sorted(
        [a for a in validos if a.start_at > agora and a.status in ("scheduled", "confirmed")],
        key=lambda a: a.start_at,
    )
    abertos = em_aberto(lista, agora)
    c = contagens(lista)

    return {
        "total": c["total"],
        "realizados": c["realizados"],
        "faltas": c["faltas"],
        "presenca": presenca(c["realizados"], c["faltas"]),
        "ultimo": passados[-1].start_at if passados else None,
        "proximo": futuros[0].start_at if futuros else None,
        "valor_em_aberto": soma(abertos),
        "quantidade_em_aberto": len(abertos),
    }
