"""
Configurações da conta e fuso horário.

Duas coisas travadas aqui: terminologia é rótulo (não passa marcação,
mesmo que o painel deixasse), e "hoje" é o dia da conta — não o de
Greenwich.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services.sessions import agora
from tests.conftest import cadastrar, csrf, entrar

SENHA_OUTRA = "OutraSenhaBoa!2026"


@pytest.fixture
def conta(cliente):
    r = cadastrar(cliente, nome="Clara Mendes", email="clara@exemplo.com",
                  workspace="Clínica Bem Viver", profissao="terapia_integrativa")
    assert r.status_code == 201
    return r.json()


# ---------------- leitura ----------------
def test_configuracao_nasce_com_padrao_util(cliente, conta):
    c = cliente.get("/workspace/settings").json()
    assert c["jornada_inicio"] == "08:00"
    assert c["jornada_fim"] == "20:00"
    assert c["dias_da_semana"] == [1, 2, 3, 4, 5]
    assert c["duracao_padrao"] == 50
    assert c["fuso"] == "America/Sao_Paulo"


def test_meta_nasce_vazia(cliente, conta):
    """Meta inventada vira cobrança sobre número que ninguém escolheu."""
    assert cliente.get("/workspace/settings").json()["meta_mensal"] is None
    assert cliente.get("/workspace/finance/summary").json()["meta"] is None


def test_qualquer_pessoa_da_conta_le_a_configuracao(cliente, conta):
    """A jornada desenha a agenda e a terminologia troca os rótulos:
    esconder isso de quem atende só quebraria a tela."""
    from app.db.context import sem_escopo_de_tenant
    from app.ids import novo_ulid
    from app.models.membership import Membership, MembershipPermission
    from app.models.rbac import Permission
    from sqlalchemy import select

    from app.db.session import SessionLocal

    with sem_escopo_de_tenant():
        db = SessionLocal()
        membership = db.execute(select(Membership)).scalar_one()
        permissao = db.execute(
            select(Permission).where(Permission.key == "settings.manage")).scalar_one()
        db.add(MembershipPermission(
            public_id=novo_ulid(), tenant_id=membership.tenant_id,
            membership_id=membership.id, permission_id=permissao.id,
            effect="deny", reason="teste: separar leitura de escrita"))
        db.commit()
        db.close()

    assert cliente.get("/workspace/settings").status_code == 200
    r = cliente.patch("/workspace/settings", json={"duracao_padrao": 40}, headers=csrf(cliente))
    assert r.status_code == 403


# ---------------- gravação ----------------
def test_gravar_jornada_e_duracao(cliente, conta):
    r = cliente.patch("/workspace/settings", json={
        "jornada_inicio": "07:30", "jornada_fim": "19:00",
        "dias_da_semana": [1, 2, 3, 4, 5, 6], "duracao_padrao": 45, "intervalo": 15
    }, headers=csrf(cliente))
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["jornada_inicio"] == "07:30"
    assert c["dias_da_semana"] == [1, 2, 3, 4, 5, 6]
    assert c["duracao_padrao"] == 45
    # E persiste.
    assert cliente.get("/workspace/settings").json()["intervalo"] == 15


def test_jornada_invertida_e_recusada(cliente, conta):
    r = cliente.patch("/workspace/settings",
                      json={"jornada_inicio": "20:00", "jornada_fim": "08:00"},
                      headers=csrf(cliente))
    assert r.status_code == 422


def test_semana_sem_nenhum_dia_e_recusada(cliente, conta):
    r = cliente.patch("/workspace/settings", json={"dias_da_semana": []},
                      headers=csrf(cliente))
    assert r.status_code == 422


def test_meta_entra_no_financeiro(cliente, conta):
    cliente.patch("/workspace/settings", json={"meta_mensal": "8000.00"}, headers=csrf(cliente))
    resumo = cliente.get("/workspace/finance/summary").json()
    assert float(resumo["meta"]) == 8000.0
    assert resumo["percentual_meta"] is not None


def test_meta_pode_ser_limpa(cliente, conta):
    cliente.patch("/workspace/settings", json={"meta_mensal": "8000.00"}, headers=csrf(cliente))
    r = cliente.patch("/workspace/settings", json={"limpar_meta": True}, headers=csrf(cliente))
    assert r.json()["meta_mensal"] is None


# ---------------- terminologia ----------------
def test_terminologia_troca_o_rotulo(cliente, conta):
    r = cliente.patch("/workspace/settings", json={
        "terminologia": {"client.one": "Cliente", "client.many": "Clientes"}
    }, headers=csrf(cliente))
    assert r.status_code == 200
    assert r.json()["terminologia"]["client.one"] == "Cliente"
    assert r.json()["recusados"] == []


def test_terminologia_nao_aceita_marcacao(cliente, conta):
    """O painel já recusa. O servidor recusa de novo — validação de frente
    nunca é a única."""
    r = cliente.patch("/workspace/settings", json={
        "terminologia": {"client.one": "<b>Cliente</b>", "client.many": "Clientes"}
    }, headers=csrf(cliente))
    assert r.status_code == 200
    assert "client.one" in r.json()["recusados"]
    assert r.json()["terminologia"].get("client.one") is None
    assert r.json()["terminologia"]["client.many"] == "Clientes"


def test_terminologia_recusa_chave_fora_do_catalogo(cliente, conta):
    r = cliente.patch("/workspace/settings",
                      json={"terminologia": {"qualquer.coisa": "Oi"}}, headers=csrf(cliente))
    assert "qualquer.coisa" in r.json()["recusados"]
    assert r.json()["terminologia"] == {}


def test_terminologia_recusa_rotulo_gigante(cliente, conta):
    r = cliente.patch("/workspace/settings",
                      json={"terminologia": {"client.one": "P" * 80}}, headers=csrf(cliente))
    assert "client.one" in r.json()["recusados"]


def test_termo_vazio_volta_para_o_padrao(cliente, conta):
    cliente.patch("/workspace/settings", json={"terminologia": {"client.one": "Cliente"}},
                  headers=csrf(cliente))
    r = cliente.patch("/workspace/settings", json={"terminologia": {"client.one": ""}},
                      headers=csrf(cliente))
    assert "client.one" not in r.json()["terminologia"]


# ---------------- fuso ----------------
def test_fuso_invalido_e_recusado(cliente, conta):
    r = cliente.patch("/workspace/settings", json={"fuso": "Marte/Olympus"},
                      headers=csrf(cliente))
    assert r.status_code == 422


def test_fuso_da_conta_decide_onde_o_dia_comeca(cliente, conta):
    """Atendimento às 22h no Brasil já é o dia seguinte em UTC.

    Antes, ele sumia do 'hoje' e aparecia no de amanhã. Agora o recorte é
    o da conta.
    """
    pessoa = cliente.post("/workspace/clients", json={"nome": "Ana Beatriz"},
                          headers=csrf(cliente)).json()

    # 22h de hoje em São Paulo (UTC-3) = 01h de amanhã em UTC.
    from zoneinfo import ZoneInfo

    sp = ZoneInfo("America/Sao_Paulo")
    hoje_sp = datetime.now(timezone.utc).astimezone(sp).date()
    as_22 = datetime.combine(hoje_sp, datetime.min.time()).replace(hour=22)
    em_utc = as_22.replace(tzinfo=sp).astimezone(timezone.utc).replace(tzinfo=None)

    r = cliente.post("/workspace/appointments",
                     json={"cliente_id": pessoa["id"], "inicio": em_utc.isoformat()},
                     headers=csrf(cliente))
    assert r.status_code == 201, r.text

    painel = cliente.get("/workspace/dashboard").json()
    ids_de_hoje = [a["id"] for a in painel["hoje"]]
    assert r.json()["id"] in ids_de_hoje, "o atendimento das 22h é de hoje, não de amanhã"


def test_trocar_o_fuso_muda_o_recorte(cliente, conta):
    cliente.patch("/workspace/settings", json={"fuso": "America/Manaus"},
                  headers=csrf(cliente))
    assert cliente.get("/workspace/settings").json()["fuso"] == "America/Manaus"
    # E o dashboard continua respondendo (o recorte agora é de Manaus).
    assert cliente.get("/workspace/dashboard").status_code == 200


def test_configuracao_nao_vaza_entre_contas(cliente, conta):
    cliente.patch("/workspace/settings", json={"meta_mensal": "8000.00",
                                               "terminologia": {"client.one": "Cliente"}},
                  headers=csrf(cliente))
    cliente.cookies.clear()
    cadastrar(cliente, nome="Bia Outra", email="bia@exemplo.com", workspace="Clínica da Bia")
    c = cliente.get("/workspace/settings").json()
    assert c["meta_mensal"] is None
    assert c["terminologia"] == {}
