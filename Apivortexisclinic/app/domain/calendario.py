"""
Fuso horário: onde "hoje" começa.

O banco guarda tudo em UTC, e isso está certo — instante é instante. O que
estava errado era o resto: "hoje", "esta semana" e "este mês" eram
calculados em UTC também. Para quem atende no Brasil, um atendimento das
22h de terça aparecia na quarta, e o fechamento do dia 31 pegava três
horas do dia 1º.

Este módulo é a fronteira entre os dois mundos:

    UTC   — o que está gravado, o que é comparado, o que é ordenado
    local — o que a pessoa chama de dia, semana e mês

A regra prática: **recorte é calculado em local, consulta é feita em UTC**.
Converte-se na borda, uma vez, e nunca no meio.

Horário de verão: a conversão usa `zoneinfo`, então a mudança de offset é
respeitada sem tabela própria. Um dia que "tem 23 horas" continua sendo um
dia — é por isso que o fim da janela é calculado como *começo do dia
seguinte menos um milissegundo em local*, e não como "início + 24h".
"""
from datetime import date, datetime, timedelta, timezone
from typing import Tuple

from zoneinfo import ZoneInfo

UTC = timezone.utc
PADRAO = ZoneInfo("America/Sao_Paulo")


def agora_utc() -> datetime:
    """Instante atual em UTC, sem tzinfo — como o banco guarda."""
    return datetime.now(UTC).replace(tzinfo=None)


def normalizar_utc(quando: datetime) -> datetime:
    """Data-hora que chega pela API → UTC ingênuo, como o banco guarda.

    Com fuso (`2026-11-12T14:00:00-03:00`, `...Z`): converte para UTC e tira
    o tzinfo. Sem fuso: já é UTC por contrato — é o que o painel manda.

    Sem isto, `14:00-03:00` era gravado como 14h UTC (três horas fora, em
    silêncio) e o prontuário quebrava com 500 ao comparar data com fuso
    contra data sem fuso.
    """
    if quando.tzinfo is None or quando.utcoffset() is None:
        return quando.replace(tzinfo=None)
    return quando.astimezone(UTC).replace(tzinfo=None)


def para_local(quando: datetime, fuso: ZoneInfo) -> datetime:
    """UTC ingênuo → local ingênuo."""
    return quando.replace(tzinfo=UTC).astimezone(fuso).replace(tzinfo=None)


def para_utc(quando_local: datetime, fuso: ZoneInfo) -> datetime:
    """Local ingênuo → UTC ingênuo.

    Em horário de verão existe hora que não acontece e hora que acontece
    duas vezes; `fold=0` escolhe a primeira, que é o comportamento que as
    pessoas esperam de um agendamento.
    """
    return quando_local.replace(tzinfo=fuso).astimezone(UTC).replace(tzinfo=None)


def hoje_local(fuso: ZoneInfo) -> date:
    return para_local(agora_utc(), fuso).date()


def dia(d: date, fuso: ZoneInfo) -> Tuple[datetime, datetime]:
    """A janela UTC que corresponde a um dia inteiro naquele fuso."""
    comeco = para_utc(datetime.combine(d, datetime.min.time()), fuso)
    fim = para_utc(datetime.combine(d + timedelta(days=1), datetime.min.time()), fuso)
    return comeco, fim - timedelta(milliseconds=1)


def periodo(de: date, ate: date, fuso: ZoneInfo) -> Tuple[datetime, datetime]:
    """Janela UTC de um intervalo de dias locais, inclusivo nas duas pontas."""
    comeco, _ = dia(de, fuso)
    _, fim = dia(ate, fuso)
    return comeco, fim


def inicio_da_semana(d: date) -> date:
    return d - timedelta(days=d.weekday())          # segunda


def inicio_do_mes(d: date) -> date:
    return d.replace(day=1)


def fim_do_mes(d: date) -> date:
    return (inicio_do_mes(d) + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def mes(d: date, fuso: ZoneInfo) -> Tuple[datetime, datetime]:
    return periodo(inicio_do_mes(d), fim_do_mes(d), fuso)


def semana(d: date, fuso: ZoneInfo) -> Tuple[datetime, datetime]:
    comeco = inicio_da_semana(d)
    return periodo(comeco, comeco + timedelta(days=6), fuso)
