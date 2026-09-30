"""
Agenda recorrente e bloqueio de horário.

Duas regras travadas aqui: um horário ocupado não derruba a série inteira,
e bloqueio ocupa horário sem virar atendimento — não entra em contagem,
presença nem financeiro.
"""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.context import sem_escopo_de_tenant
from app.models.agenda import AppointmentSeries, ScheduleBlock
from app.models.appointment import Appointment
from app.services.sessions import agora
from tests.conftest import cadastrar, csrf

PROXIMA_SEGUNDA = (agora() + timedelta(days=(7 - agora().weekday()) or 7)).replace(
    hour=9, minute=0, second=0, microsecond=0)


@pytest.fixture
def conta(cliente):
    r = cadastrar(cliente, nome="Clara Mendes", email="clara@exemplo.com",
                  workspace="Clínica Bem Viver", profissao="terapia_integrativa")
    assert r.status_code == 201
    return r.json()


@pytest.fixture
def pessoa(cliente, conta):
    return cliente.post("/workspace/clients",
                        json={"nome": "Ana Beatriz", "valor_sessao": "180.00"},
                        headers=csrf(cliente)).json()


def criar_serie(cliente, pessoa, **extra):
    corpo = {"cliente_id": pessoa["id"], "inicio": PROXIMA_SEGUNDA.isoformat(),
             "frequencia": "weekly", "ocorrencias": 8}
    corpo.update(extra)
    return cliente.post("/workspace/series", json=corpo, headers=csrf(cliente))


def bloquear(cliente, inicio, fim, **extra):
    corpo = {"inicio": inicio.isoformat(), "fim": fim.isoformat(), "titulo": "Férias"}
    corpo.update(extra)
    return cliente.post("/workspace/blocks", json=corpo, headers=csrf(cliente))


# ---------------- recorrência ----------------
def test_serie_semanal_cria_as_ocorrencias(cliente, pessoa):
    r = criar_serie(cliente, pessoa)
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert len(corpo["criados"]) == 8
    assert corpo["conflitos"] == []

    # De 7 em 7 dias, no mesmo horário.
    inicios = [a["inicio"] for a in corpo["criados"]]
    assert len(set(inicios)) == 8
    assert all(i[11:16] == PROXIMA_SEGUNDA.strftime("%H:%M") for i in inicios)


def test_quinzenal_pula_uma_semana(cliente, pessoa):
    corpo = criar_serie(cliente, pessoa, frequencia="biweekly", ocorrencias=3).json()
    from datetime import datetime

    datas = [datetime.fromisoformat(a["inicio"]) for a in corpo["criados"]]
    assert (datas[1] - datas[0]).days == 14
    assert (datas[2] - datas[1]).days == 14


def test_mensal_repete_o_dia_do_mes(cliente, pessoa):
    corpo = criar_serie(cliente, pessoa, frequencia="monthly", ocorrencias=3).json()
    from datetime import datetime

    dias = [datetime.fromisoformat(a["inicio"]).day for a in corpo["criados"]]
    assert len(set(dias)) == 1, "mensal repete o dia do mês, não a semana"


def test_ocorrencias_herdam_o_valor_da_pessoa(cliente, pessoa):
    corpo = criar_serie(cliente, pessoa, ocorrencias=2).json()
    assert all(float(a["valor"]) == 180.0 for a in corpo["criados"])


def test_horario_ocupado_nao_derruba_a_serie(cliente, pessoa):
    """A ocorrência que bateu é pulada e volta listada. As outras nascem."""
    ocupa = PROXIMA_SEGUNDA + timedelta(days=14)
    assert cliente.post("/workspace/appointments",
                        json={"cliente_id": pessoa["id"], "inicio": ocupa.isoformat()},
                        headers=csrf(cliente)).status_code == 201

    corpo = criar_serie(cliente, pessoa, ocorrencias=4).json()
    assert len(corpo["criados"]) == 3
    assert len(corpo["conflitos"]) == 1
    assert corpo["conflitos"][0]["motivo"] == "conflito_de_horario"


def test_serie_toda_ocupada_e_recusada(cliente, pessoa):
    criar_serie(cliente, pessoa, ocorrencias=2)
    r = criar_serie(cliente, pessoa, ocorrencias=2)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "nenhuma_ocorrencia_livre"


def test_horizonte_e_finito(cliente, pessoa):
    r = criar_serie(cliente, pessoa, ocorrencias=999)
    assert r.status_code == 422


def test_data_final_corta_a_serie(cliente, pessoa):
    ate = (PROXIMA_SEGUNDA + timedelta(days=15)).date().isoformat()
    corpo = criar_serie(cliente, pessoa, ocorrencias=10, ate=ate).json()
    assert len(corpo["criados"]) == 3      # semana 0, 7 e 14 dias


def test_remarcar_uma_nao_mexe_nas_irmas(cliente, pessoa):
    """A série é molde: depois de nascer, cada sessão tem vida própria."""
    corpo = criar_serie(cliente, pessoa, ocorrencias=3).json()
    alvo = corpo["criados"][1]
    novo = (PROXIMA_SEGUNDA + timedelta(days=8, hours=3)).isoformat()

    r = cliente.post(f"/workspace/appointments/{alvo['id']}/reschedule",
                     json={"inicio": novo}, headers=csrf(cliente))
    assert r.status_code == 200

    agenda = cliente.get("/workspace/appointments").json()
    inicios = sorted(a["inicio"] for a in agenda)
    assert corpo["criados"][0]["inicio"] in inicios
    assert corpo["criados"][2]["inicio"] in inicios


def test_encerrar_cancela_so_o_futuro(cliente, db, pessoa):
    corpo = criar_serie(cliente, pessoa, ocorrencias=3).json()
    serie_id = corpo["serie"]["id"]

    # Uma das ocorrências "já aconteceu": marcada como realizada.
    primeira = corpo["criados"][0]["id"]
    with sem_escopo_de_tenant():
        a = db.execute(select(Appointment)
                       .where(Appointment.public_id == primeira)).scalar_one()
        a.start_at = agora() - timedelta(days=1)
        a.status = "done"
        db.commit()

    r = cliente.post(f"/workspace/series/{serie_id}/end",
                     json={"motivo": "pessoa recebeu alta"}, headers=csrf(cliente))
    assert r.status_code == 200
    assert r.json()["status"] == "ended"

    agenda = cliente.get("/workspace/appointments").json()
    por_id = {a["id"]: a for a in agenda}
    assert por_id[primeira]["status"] == "realizado" or por_id[primeira]["status"] == "done"
    futuros = [a for a in agenda if a["id"] != primeira]
    assert all(a["status"] in ("cancelled", "cancelado") for a in futuros)


def test_serie_de_outra_conta_nao_existe(cliente, pessoa):
    serie_id = criar_serie(cliente, pessoa, ocorrencias=2).json()["serie"]["id"]
    cliente.cookies.clear()
    cadastrar(cliente, nome="Bia Outra", email="bia@exemplo.com", workspace="Clínica da Bia",
              profissao="terapia_integrativa")
    r = cliente.post(f"/workspace/series/{serie_id}/end", json={}, headers=csrf(cliente))
    assert r.status_code == 404


def test_serie_nao_vaza_na_listagem_do_cliente(cliente, pessoa):
    criar_serie(cliente, pessoa, ocorrencias=2)
    assert len(cliente.get(f"/workspace/clients/{pessoa['id']}/series").json()) == 1

    cliente.cookies.clear()
    cadastrar(cliente, nome="Bia Outra", email="bia2@exemplo.com", workspace="Clínica da Bia 2")
    assert cliente.get(f"/workspace/clients/{pessoa['id']}/series").status_code == 404


# ---------------- bloqueios ----------------
def test_bloqueio_impede_agendar_em_cima(cliente, pessoa):
    inicio = PROXIMA_SEGUNDA
    assert bloquear(cliente, inicio, inicio + timedelta(days=7)).status_code == 201

    r = cliente.post("/workspace/appointments",
                     json={"cliente_id": pessoa["id"],
                           "inicio": (inicio + timedelta(days=2)).isoformat()},
                     headers=csrf(cliente))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "horario_bloqueado"


def test_bloqueio_nao_e_atendimento(cliente, pessoa):
    """Não entra em contagem, presença nem financeiro."""
    bloquear(cliente, PROXIMA_SEGUNDA, PROXIMA_SEGUNDA + timedelta(days=3))
    painel = cliente.get("/workspace/dashboard").json()
    assert painel["resumo_dia"]["total"] == 0
    assert cliente.get("/workspace/appointments").json() == []
    assert float(painel["financeiro"]["previsto"]) == 0.0


def test_bloqueio_recusa_por_cima_de_atendimento_marcado(cliente, pessoa):
    cliente.post("/workspace/appointments",
                 json={"cliente_id": pessoa["id"], "inicio": PROXIMA_SEGUNDA.isoformat()},
                 headers=csrf(cliente))
    r = bloquear(cliente, PROXIMA_SEGUNDA - timedelta(hours=1),
                 PROXIMA_SEGUNDA + timedelta(hours=3))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "atendimentos_no_periodo"


def test_forcar_bloqueia_mas_nao_cancela_ninguem(cliente, pessoa):
    """Cancelar sessão é decisão de gente, não efeito colateral de férias."""
    atendimento = cliente.post("/workspace/appointments",
                               json={"cliente_id": pessoa["id"],
                                     "inicio": PROXIMA_SEGUNDA.isoformat()},
                               headers=csrf(cliente)).json()
    r = bloquear(cliente, PROXIMA_SEGUNDA - timedelta(hours=1),
                 PROXIMA_SEGUNDA + timedelta(hours=3), forcar=True)
    assert r.status_code == 201
    assert len(r.json()["atendimentos_no_periodo"]) == 1

    ainda = cliente.get(f"/workspace/appointments/{atendimento['id']}").json()
    assert ainda["status"] in ("scheduled", "agendado")


def test_remarcar_para_dentro_do_bloqueio_e_recusado(cliente, pessoa):
    atendimento = cliente.post("/workspace/appointments",
                               json={"cliente_id": pessoa["id"],
                                     "inicio": PROXIMA_SEGUNDA.isoformat()},
                               headers=csrf(cliente)).json()
    inicio_bloqueio = PROXIMA_SEGUNDA + timedelta(days=10)
    bloquear(cliente, inicio_bloqueio, inicio_bloqueio + timedelta(days=2))

    r = cliente.post(f"/workspace/appointments/{atendimento['id']}/reschedule",
                     json={"inicio": (inicio_bloqueio + timedelta(hours=2)).isoformat()},
                     headers=csrf(cliente))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "horario_bloqueado"


def test_serie_pula_o_que_esta_bloqueado(cliente, pessoa):
    fora = PROXIMA_SEGUNDA + timedelta(days=7)
    bloquear(cliente, fora - timedelta(hours=1), fora + timedelta(hours=3))

    corpo = criar_serie(cliente, pessoa, ocorrencias=3).json()
    assert len(corpo["criados"]) == 2
    assert corpo["conflitos"][0]["motivo"] == "horario_bloqueado"
    assert corpo["conflitos"][0]["detalhe"] == "Férias"


def test_bloqueio_invertido_e_recusado(cliente, pessoa):
    r = bloquear(cliente, PROXIMA_SEGUNDA + timedelta(days=1), PROXIMA_SEGUNDA)
    assert r.status_code == 422


def test_remover_bloqueio_libera_o_horario(cliente, pessoa):
    bloqueio = bloquear(cliente, PROXIMA_SEGUNDA,
                        PROXIMA_SEGUNDA + timedelta(days=2)).json()["bloqueio"]
    assert cliente.delete(f"/workspace/blocks/{bloqueio['id']}",
                          headers=csrf(cliente)).status_code == 200
    r = cliente.post("/workspace/appointments",
                     json={"cliente_id": pessoa["id"], "inicio": PROXIMA_SEGUNDA.isoformat()},
                     headers=csrf(cliente))
    assert r.status_code == 201


def test_bloqueio_de_outra_conta_nao_existe(cliente, pessoa):
    bloqueio = bloquear(cliente, PROXIMA_SEGUNDA,
                        PROXIMA_SEGUNDA + timedelta(days=2)).json()["bloqueio"]
    cliente.cookies.clear()
    cadastrar(cliente, nome="Bia Outra", email="bia3@exemplo.com", workspace="Clínica da Bia 3")
    assert cliente.get("/workspace/blocks").json() == []
    assert cliente.delete(f"/workspace/blocks/{bloqueio['id']}",
                          headers=csrf(cliente)).status_code == 404


def test_bloqueio_padrao_e_da_propria_agenda(cliente, pessoa):
    """Marcar férias não fecha a clínica inteira por descuido."""
    r = bloquear(cliente, PROXIMA_SEGUNDA, PROXIMA_SEGUNDA + timedelta(days=1))
    assert r.status_code == 201
    assert r.json()["bloqueio"]["da_conta_inteira"] is False


def test_feriado_da_conta_vale_para_todo_mundo(cliente, pessoa):
    r = bloquear(cliente, PROXIMA_SEGUNDA, PROXIMA_SEGUNDA + timedelta(days=1),
                 titulo="Feriado", conta_inteira=True)
    assert r.status_code == 201
    assert r.json()["bloqueio"]["da_conta_inteira"] is True

    r = cliente.post("/workspace/appointments",
                     json={"cliente_id": pessoa["id"], "inicio": PROXIMA_SEGUNDA.isoformat()},
                     headers=csrf(cliente))
    assert r.status_code == 409


def test_escrita_sem_csrf_e_bloqueada(cliente, pessoa):
    assert cliente.post("/workspace/blocks",
                        json={"inicio": PROXIMA_SEGUNDA.isoformat(),
                              "fim": (PROXIMA_SEGUNDA + timedelta(hours=2)).isoformat(),
                              "titulo": "x"}).status_code == 403
