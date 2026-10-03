"""
Data com fuso na entrada da API.

O banco guarda DATETIME sem fuso, sempre UTC. Antes do tipo `Instante`,
`2026-11-12T14:00:00-03:00` era aceito e gravado como 14h UTC — três horas
fora, sem erro nenhum — e a mesma data no prontuário quebrava com 500, por
comparar data com fuso contra data sem fuso.

Passou despercebido porque o painel manda data sem sufixo, já em UTC. Só
aparece quando algo de fora do painel chama a API — e é exatamente isso que
estes testes fazem.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.context import sem_escopo_de_tenant
from app.domain.calendario import normalizar_utc
from app.models.agenda import ScheduleBlock
from app.models.appointment import Appointment
from app.models.clinical import ClinicalNote
from app.models.payment import Payment
from app.services.sessions import agora
from tests.conftest import cadastrar, csrf

AMANHA = (agora() + timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0)
ONTEM = (agora() - timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0)


def com_fuso(utc_ingenuo: datetime, horas: int) -> str:
    """O mesmo instante, escrito no fuso pedido: 17:00 UTC → '14:00-03:00'."""
    fuso = timezone(timedelta(hours=horas))
    return utc_ingenuo.replace(tzinfo=timezone.utc).astimezone(fuso).isoformat()


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


def agendar(cliente, pessoa, inicio: str):
    return cliente.post("/workspace/appointments",
                        json={"cliente_id": pessoa["id"], "inicio": inicio},
                        headers=csrf(cliente))


def gravado(db, modelo, coluna, public_id):
    db.expire_all()
    with sem_escopo_de_tenant():
        return db.execute(select(coluna).where(modelo.public_id == public_id)).scalar_one()


# ---------------- a conversão em si ----------------
@pytest.mark.parametrize("entrada", [
    datetime(2026, 11, 12, 14, 0, tzinfo=timezone(timedelta(hours=-3))),
    datetime(2026, 11, 12, 17, 0, tzinfo=timezone.utc),
    datetime(2026, 11, 12, 19, 0, tzinfo=timezone(timedelta(hours=2))),
    datetime(2026, 11, 12, 17, 0),
])
def test_todo_formato_vira_o_mesmo_utc_ingenuo(entrada):
    saida = normalizar_utc(entrada)
    assert saida == datetime(2026, 11, 12, 17, 0)
    assert saida.tzinfo is None


# ---------------- atendimento ----------------
def test_atendimento_com_fuso_e_gravado_no_instante_certo(cliente, db, pessoa):
    r = agendar(cliente, pessoa, com_fuso(AMANHA, -3))
    assert r.status_code == 201, r.text
    assert r.json()["inicio"].startswith(AMANHA.strftime("%Y-%m-%dT%H:%M"))
    assert gravado(db, Appointment, Appointment.start_at, r.json()["id"]) == AMANHA


@pytest.mark.parametrize("forma", ["Z", "sem_sufixo", "+02:00"])
def test_o_mesmo_instante_em_outra_forma_da_conflito(cliente, pessoa, forma):
    """Se a conversão falhar, 14:00-03:00 e 17:00Z viram horários diferentes
    e o conflito passa — dois atendimentos no mesmo horário."""
    assert agendar(cliente, pessoa, com_fuso(AMANHA, -3)).status_code == 201
    outra = {
        "Z": AMANHA.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sem_sufixo": AMANHA.isoformat(),
        "+02:00": com_fuso(AMANHA, 2),
    }[forma]
    r = agendar(cliente, pessoa, outra)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "conflito_de_horario"


def test_remarcar_com_fuso(cliente, db, pessoa):
    a = agendar(cliente, pessoa, AMANHA.isoformat()).json()
    novo = AMANHA + timedelta(days=1)
    r = cliente.post(f"/workspace/appointments/{a['id']}/reschedule",
                     json={"inicio": com_fuso(novo, -3)}, headers=csrf(cliente))
    assert r.status_code == 200, r.text
    assert gravado(db, Appointment, Appointment.start_at, a["id"]) == novo


def test_filtro_de_periodo_com_fuso(cliente, pessoa):
    """Janela 13:00–15:00 em -03:00 é 16:00–18:00 UTC: o das 17h entra."""
    agendar(cliente, pessoa, AMANHA.isoformat())
    params = {"de": com_fuso(AMANHA - timedelta(hours=1), -3),
              "ate": com_fuso(AMANHA + timedelta(hours=1), -3)}
    r = cliente.get("/workspace/appointments", params=params)
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1

    # A mesma janela lida como UTC (14:00–16:00) não alcança as 17h.
    fora = {"de": (AMANHA - timedelta(hours=3)).isoformat(),
            "ate": (AMANHA - timedelta(hours=1)).isoformat()}
    assert cliente.get("/workspace/appointments", params=fora).json() == []


# ---------------- bloqueio ----------------
def test_bloqueio_com_fuso_ocupa_o_horario_certo(cliente, db, pessoa):
    r = cliente.post("/workspace/blocks",
                     json={"inicio": com_fuso(AMANHA, -3),
                           "fim": com_fuso(AMANHA + timedelta(hours=2), -3),
                           "titulo": "Supervisão"},
                     headers=csrf(cliente))
    assert r.status_code == 201, r.text
    bloqueio = r.json()["bloqueio"]
    assert gravado(db, ScheduleBlock, ScheduleBlock.start_at, bloqueio["id"]) == AMANHA
    assert agendar(cliente, pessoa, (AMANHA + timedelta(hours=1)).isoformat()).status_code == 409


# ---------------- prontuário ----------------
def test_nota_com_fuso_nao_quebra_e_grava_o_instante_certo(cliente, db, pessoa):
    """Antes: 500, por comparar data com fuso contra `agora()` sem fuso."""
    r = cliente.post(f"/workspace/clients/{pessoa['id']}/notes",
                     json={"conteudo": "Sessão de acolhimento.", "ocorrido_em": com_fuso(ONTEM, -3)},
                     headers=csrf(cliente))
    assert r.status_code == 201, r.text
    assert gravado(db, ClinicalNote, ClinicalNote.occurred_at, r.json()["id"]) == ONTEM


def test_nota_no_futuro_com_fuso_e_recusada_sem_500(cliente, pessoa):
    r = cliente.post(f"/workspace/clients/{pessoa['id']}/notes",
                     json={"conteudo": "Ainda não aconteceu.", "ocorrido_em": com_fuso(AMANHA, -3)},
                     headers=csrf(cliente))
    assert r.status_code == 422


# ---------------- financeiro ----------------
def test_baixa_com_fuso(cliente, db, pessoa):
    a = agendar(cliente, pessoa, ONTEM.isoformat()).json()
    cliente.post(f"/workspace/appointments/{a['id']}/status",
                 json={"status": "done"}, headers=csrf(cliente))
    r = cliente.post(f"/workspace/appointments/{a['id']}/payment",
                     json={"metodo": "pix", "pago_em": com_fuso(ONTEM, -3)},
                     headers=csrf(cliente))
    assert r.status_code == 201, r.text
    assert gravado(db, Payment, Payment.paid_at, r.json()["id"]) == ONTEM


def test_pagamento_no_futuro_com_fuso_e_recusado_sem_500(cliente, pessoa):
    r = cliente.post(f"/workspace/clients/{pessoa['id']}/payment",
                     json={"metodo": "pix", "valor": "100.00", "pago_em": com_fuso(AMANHA, -3)},
                     headers=csrf(cliente))
    assert r.status_code == 422
