"""
Definição dos números — o par do teste que roda no painel.

O painel tem auxiliares de apresentação que repetem estas mesmas regras
(`assets/js/domain/metrics.js`). Repetição é risco: as duas
implementações podem se soltar sem ninguém notar, e aí a mesma tela mostra
um valor e o relatório mostra outro.

A trava é este arquivo: **o exemplo aqui é idêntico ao do painel**, com os
mesmos quatro atendimentos e os mesmos resultados esperados. Se um lado
mudar de ideia sobre o que é "pendente", um dos dois testes quebra.

Não precisa de banco: são funções puras sobre objetos.
"""
from datetime import datetime, timedelta
from decimal import Decimal

from app.domain import metrics


class FalsoAtendimento:
    """O suficiente para as funções de domínio — sem tocar no banco."""

    def __init__(self, hora, status, pagamento, valor):
        base = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        self.start_at = base.replace(hour=hora)
        self.status = status
        self.payment_status = pagamento
        self.price = Decimal(str(valor))
        self.duration_min = 50


def lista_exemplo():
    """Os mesmos quatro atendimentos do teste do painel."""
    return [
        FalsoAtendimento(8, "done", "paid", 200),
        FalsoAtendimento(9, "done", "pending", 200),
        FalsoAtendimento(10, "no_show", "pending", 200),
        FalsoAtendimento(11, "cancelled", "waived", 200),
    ]


def test_cancelado_nao_entra_no_total():
    c = metrics.contagens(lista_exemplo())
    assert [c["total"], c["realizados"], c["faltas"], c["cancelados"]] == [3, 2, 1, 1]


def test_presenca_e_realizados_sobre_realizados_mais_faltas():
    assert metrics.presenca(2, 1) == 66.7      # o painel arredonda para 67 ao exibir


def test_sem_historico_presenca_e_nula_nao_zero():
    assert metrics.presenca(0, 0) is None


def test_recebido_soma_so_o_que_esta_pago():
    r = metrics.receita(lista_exemplo(), datetime.utcnow().replace(hour=23))
    assert r["recebido"] == Decimal("200.00")


def test_a_receber_inclui_falta_cobrada():
    r = metrics.receita(lista_exemplo(), datetime.utcnow().replace(hour=23))
    assert r["pendente"] == Decimal("400.00")


def test_cancelado_fica_fora_do_total():
    r = metrics.receita(lista_exemplo(), datetime.utcnow().replace(hour=23))
    assert r["total"] == Decimal("600.00")


def test_isento_nao_e_receita_nem_pendencia():
    lista = [FalsoAtendimento(8, "done", "waived", 300)]
    r = metrics.receita(lista, datetime.utcnow().replace(hour=23))
    assert r["recebido"] == Decimal("0.00")
    assert r["pendente"] == Decimal("0.00")


def test_resumo_do_dia_bate_com_as_contagens():
    d = metrics.resumo_do_dia(lista_exemplo(), datetime.utcnow().replace(hour=23))
    assert [d["total"], d["realizados"], d["faltas"]] == [3, 2, 1]


def test_agendado_no_futuro_e_previsto_nao_pendente():
    futuro = FalsoAtendimento(8, "scheduled", "pending", 150)
    futuro.start_at = datetime.utcnow() + timedelta(days=2)
    r = metrics.receita([futuro], datetime.utcnow())
    assert r["previsto"] == Decimal("150.00")
    assert r["pendente"] == Decimal("0.00")


def test_em_aberto_so_conta_o_que_ja_aconteceu():
    passado = FalsoAtendimento(8, "done", "pending", 100)
    passado.start_at = datetime.utcnow() - timedelta(days=3)
    futuro = FalsoAtendimento(9, "scheduled", "pending", 100)
    futuro.start_at = datetime.utcnow() + timedelta(days=3)

    abertos = metrics.em_aberto([passado, futuro], datetime.utcnow())
    assert len(abertos) == 1
    assert metrics.dias_em_aberto(abertos[0], datetime.utcnow()) == 3
