"""Atendimentos: agendar, conflito de horário, transições e números."""
from datetime import datetime, timedelta

import pytest

from app.services.sessions import agora
from tests.conftest import cadastrar, csrf

AMANHA = (agora() + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)


@pytest.fixture
def conta(cliente):
    r = cadastrar(cliente, nome="Camila Ferraz", email="camila@exemplo.com",
                  workspace="Consultório Camila", profissao="terapia_integrativa")
    assert r.status_code == 201
    return r.json()


@pytest.fixture
def pessoa(cliente, conta):
    return cliente.post("/workspace/clients",
                        json={"nome": "Ana Beatriz", "valor_sessao": "180.00"},
                        headers=csrf(cliente)).json()


def agendar(cliente, pessoa, inicio=AMANHA, duracao=50, **extra):
    corpo = {"cliente_id": pessoa["id"], "inicio": inicio.isoformat(), "duracao_min": duracao}
    corpo.update(extra)
    return cliente.post("/workspace/appointments", json=corpo, headers=csrf(cliente))


# ---------------- agendar ----------------
def test_agendar_usa_o_valor_padrao_da_pessoa(cliente, pessoa):
    r = agendar(cliente, pessoa)
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["status"] == "scheduled"
    assert corpo["pagamento"] == "pending"
    assert float(corpo["valor"]) == 180.0
    assert corpo["cliente"]["nome"] == "Ana Beatriz"


def test_valor_do_atendimento_sobrepoe_o_padrao(cliente, pessoa):
    r = agendar(cliente, pessoa, valor="250.00")
    assert float(r.json()["valor"]) == 250.0


def test_agendar_para_pessoa_de_outra_conta_responde_404(cliente, pessoa):
    cliente.cookies.clear()
    cadastrar(cliente, nome="Bia", email="bia@exemplo.com", workspace="Clínica da Bia")
    r = agendar(cliente, pessoa)
    assert r.status_code == 404


def test_duracao_absurda_e_recusada(cliente, pessoa):
    assert agendar(cliente, pessoa, duracao=5000).status_code == 422


# ---------------- conflito de horário ----------------
def test_mesmo_horario_no_mesmo_profissional_da_conflito(cliente, pessoa):
    assert agendar(cliente, pessoa).status_code == 201
    r = agendar(cliente, pessoa)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "conflito_de_horario"


def test_sobreposicao_parcial_tambem_da_conflito(cliente, pessoa):
    agendar(cliente, pessoa, inicio=AMANHA, duracao=50)
    r = agendar(cliente, pessoa, inicio=AMANHA + timedelta(minutes=30), duracao=50)
    assert r.status_code == 409


def test_horario_encostado_nao_da_conflito(cliente, pessoa):
    """14:00–14:50 e 14:50–15:40 convivem: o fim de um é o começo do outro."""
    agendar(cliente, pessoa, inicio=AMANHA, duracao=50)
    r = agendar(cliente, pessoa, inicio=AMANHA + timedelta(minutes=50), duracao=50)
    assert r.status_code == 201


def test_horario_de_atendimento_cancelado_fica_livre(cliente, pessoa):
    primeiro = agendar(cliente, pessoa).json()
    cliente.post(f"/workspace/appointments/{primeiro['id']}/status",
                 json={"status": "cancelled", "motivo": "cliente remarcou"}, headers=csrf(cliente))
    assert agendar(cliente, pessoa).status_code == 201


def test_reagendar_para_horario_ocupado_da_conflito(cliente, pessoa):
    agendar(cliente, pessoa, inicio=AMANHA)
    segundo = agendar(cliente, pessoa, inicio=AMANHA + timedelta(hours=2)).json()

    r = cliente.post(f"/workspace/appointments/{segundo['id']}/reschedule",
                     json={"inicio": AMANHA.isoformat()}, headers=csrf(cliente))
    assert r.status_code == 409


def test_reagendar_para_horario_livre_funciona(cliente, pessoa):
    a = agendar(cliente, pessoa).json()
    novo_inicio = AMANHA + timedelta(hours=3)
    r = cliente.post(f"/workspace/appointments/{a['id']}/reschedule",
                     json={"inicio": novo_inicio.isoformat()}, headers=csrf(cliente))
    assert r.status_code == 200
    assert r.json()["inicio"].startswith(novo_inicio.strftime("%Y-%m-%dT%H:%M"))


# ---------------- transições ----------------
def test_fluxo_normal_do_atendimento(cliente, pessoa):
    a = agendar(cliente, pessoa).json()
    for destino in ["confirmed", "done"]:
        r = cliente.post(f"/workspace/appointments/{a['id']}/status",
                         json={"status": destino}, headers=csrf(cliente))
        assert r.status_code == 200, r.text
        assert r.json()["status"] == destino


def test_cancelado_nao_volta(cliente, pessoa):
    a = agendar(cliente, pessoa).json()
    cliente.post(f"/workspace/appointments/{a['id']}/status",
                 json={"status": "cancelled"}, headers=csrf(cliente))
    r = cliente.post(f"/workspace/appointments/{a['id']}/status",
                     json={"status": "confirmed"}, headers=csrf(cliente))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "transicao_invalida"


def test_cancelar_tira_da_cobranca(cliente, pessoa):
    a = agendar(cliente, pessoa).json()
    r = cliente.post(f"/workspace/appointments/{a['id']}/status",
                     json={"status": "cancelled"}, headers=csrf(cliente))
    assert r.json()["pagamento"] == "waived"


def test_reagendar_cancelado_e_recusado(cliente, pessoa):
    a = agendar(cliente, pessoa).json()
    cliente.post(f"/workspace/appointments/{a['id']}/status",
                 json={"status": "cancelled"}, headers=csrf(cliente))
    r = cliente.post(f"/workspace/appointments/{a['id']}/reschedule",
                     json={"inicio": (AMANHA + timedelta(days=1)).isoformat()},
                     headers=csrf(cliente))
    assert r.status_code == 409


# ---------------- listagem e filtros ----------------
def test_filtros_de_listagem(cliente, pessoa):
    a1 = agendar(cliente, pessoa, inicio=AMANHA).json()
    agendar(cliente, pessoa, inicio=AMANHA + timedelta(hours=2), modalidade="online")

    cliente.post(f"/workspace/appointments/{a1['id']}/status",
                 json={"status": "cancelled"}, headers=csrf(cliente))

    assert len(cliente.get("/workspace/appointments").json()) == 2
    assert len(cliente.get("/workspace/appointments?status=cancelled").json()) == 1
    assert len(cliente.get("/workspace/appointments?modalidade=online").json()) == 1


def test_periodo_filtra_por_data(cliente, pessoa):
    agendar(cliente, pessoa, inicio=AMANHA)
    depois = AMANHA + timedelta(days=10)
    agendar(cliente, pessoa, inicio=depois)

    de = (AMANHA + timedelta(days=5)).isoformat()
    lista = cliente.get(f"/workspace/appointments?de={de}").json()
    assert len(lista) == 1


def test_atendimento_de_outra_conta_nao_existe(cliente, pessoa):
    a = agendar(cliente, pessoa).json()
    cliente.cookies.clear()
    cadastrar(cliente, nome="Bia", email="bia3@exemplo.com", workspace="Clínica da Bia 3")

    assert cliente.get("/workspace/appointments").json() == []
    assert cliente.get(f"/workspace/appointments/{a['id']}").status_code == 404


# ---------------- números ----------------
def test_dashboard_conta_o_dia_e_a_semana(cliente, pessoa):
    hoje = agora().replace(hour=23, minute=0, second=0, microsecond=0)
    a = agendar(cliente, pessoa, inicio=hoje).json()
    cliente.post(f"/workspace/appointments/{a['id']}/status",
                 json={"status": "done"}, headers=csrf(cliente))

    d = cliente.get("/workspace/dashboard").json()
    assert d["resumo_dia"]["total"] == 1
    assert d["resumo_dia"]["realizados"] == 1
    assert d["resumo_dia"]["presenca"] == 100.0
    assert d["clientes"]["ativos"] == 1
    assert len(d["semana"]["dias"]) == 7


def test_cancelado_sai_do_volume_e_da_receita(cliente, pessoa):
    hoje = agora().replace(hour=22, minute=0, second=0, microsecond=0)
    a = agendar(cliente, pessoa, inicio=hoje).json()
    cliente.post(f"/workspace/appointments/{a['id']}/status",
                 json={"status": "cancelled"}, headers=csrf(cliente))

    d = cliente.get("/workspace/dashboard").json()
    assert d["resumo_dia"]["total"] == 0
    assert float(d["financeiro"]["previsto"]) == 0.0
    assert d["resumo_dia"]["presenca"] is None


def test_realizado_e_nao_pago_vira_pendencia(cliente, pessoa):
    # 30 horas atrás, e não "ontem às 10h": "ontem às 10h" depende da hora
    # em que a suíte roda — de madrugada ainda não completou um dia, e o
    # teste falhava sozinho sem nada ter quebrado.
    a = agendar(cliente, pessoa, inicio=agora() - timedelta(hours=30)).json()
    cliente.post(f"/workspace/appointments/{a['id']}/status",
                 json={"status": "done"}, headers=csrf(cliente))

    pend = cliente.get("/workspace/finance/pending").json()
    assert len(pend) == 1
    assert pend[0]["dias_em_aberto"] >= 1
    assert float(cliente.get("/workspace/finance/summary").json()["pendente"]) == 180.0


def test_agendado_no_futuro_e_previsto_nao_pendencia(cliente, pessoa):
    agendar(cliente, pessoa)
    resumo = cliente.get("/workspace/finance/summary").json()
    assert float(resumo["pendente"]) == 0.0
    assert cliente.get("/workspace/finance/pending").json() == []


def test_serie_mensal_tem_o_tamanho_pedido(cliente, pessoa):
    serie = cliente.get("/workspace/finance/series?meses=3").json()
    assert len(serie) == 3
