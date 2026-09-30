"""Financeiro: baixa, estorno, isenção e o caixa do mês."""
from datetime import timedelta

import pytest

from app.services.sessions import agora
from tests.conftest import cadastrar, csrf

ONTEM = (agora() - timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)


@pytest.fixture
def conta(cliente):
    r = cadastrar(cliente, nome="Camila Ferraz", email="camila@exemplo.com",
                  workspace="Consultório Camila", profissao="terapia_integrativa")
    assert r.status_code == 201
    return r.json()


@pytest.fixture
def realizado(cliente, conta):
    """Um atendimento de ontem, já realizado e ainda não pago."""
    pessoa = cliente.post("/workspace/clients",
                          json={"nome": "Ana Beatriz", "valor_sessao": "180.00"},
                          headers=csrf(cliente)).json()
    a = cliente.post("/workspace/appointments",
                     json={"cliente_id": pessoa["id"], "inicio": ONTEM.isoformat()},
                     headers=csrf(cliente)).json()
    cliente.post(f"/workspace/appointments/{a['id']}/status",
                 json={"status": "done"}, headers=csrf(cliente))
    return a


def baixar(cliente, atendimento, **extra):
    corpo = {"metodo": "pix"}
    corpo.update(extra)
    return cliente.post(f"/workspace/appointments/{atendimento['id']}/payment",
                        json=corpo, headers=csrf(cliente))


# ---------------- baixa ----------------
def test_baixa_registra_no_caixa_e_quita_o_atendimento(cliente, realizado):
    r = baixar(cliente, realizado)
    assert r.status_code == 201, r.text
    pagamento = r.json()
    assert float(pagamento["valor"]) == 180.0
    assert pagamento["metodo"] == "pix"
    assert pagamento["atendimento_id"] == realizado["id"]

    # A bandeira do atendimento anda junto — é a regra da transação única.
    atendimento = cliente.get(f"/workspace/appointments/{realizado['id']}").json()
    assert atendimento["pagamento"] == "paid"
    assert atendimento["metodo_pagamento"] == "pix"


def test_valor_pode_ser_diferente_do_combinado(cliente, realizado):
    r = baixar(cliente, realizado, valor="150.00")
    assert float(r.json()["valor"]) == 150.0


def test_pagar_duas_vezes_e_recusado(cliente, realizado):
    assert baixar(cliente, realizado).status_code == 201
    r = baixar(cliente, realizado)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ja_pago"


def test_atendimento_cancelado_nao_recebe_pagamento(cliente, realizado):
    cliente.post(f"/workspace/appointments/{realizado['id']}/status",
                 json={"status": "cancelled"}, headers=csrf(cliente))
    r = baixar(cliente, realizado)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "atendimento_cancelado"


def test_pagamento_no_futuro_e_recusado(cliente, realizado):
    amanha = (agora() + timedelta(days=1)).isoformat()
    r = baixar(cliente, realizado, pago_em=amanha)
    assert r.status_code == 422


def test_pagamento_sem_valor_definido_pede_o_valor(cliente, conta):
    pessoa = cliente.post("/workspace/clients", json={"nome": "Sem Valor Definido"},
                          headers=csrf(cliente)).json()
    a = cliente.post("/workspace/appointments",
                     json={"cliente_id": pessoa["id"], "inicio": ONTEM.isoformat()},
                     headers=csrf(cliente)).json()
    cliente.post(f"/workspace/appointments/{a['id']}/status",
                 json={"status": "done"}, headers=csrf(cliente))

    r = cliente.post(f"/workspace/appointments/{a['id']}/payment",
                     json={"metodo": "cash"}, headers=csrf(cliente))
    assert r.status_code == 422
    assert "valor" in r.json()["detail"]["message"].lower()

    assert cliente.post(f"/workspace/appointments/{a['id']}/payment",
                        json={"metodo": "cash", "valor": "120.00"},
                        headers=csrf(cliente)).status_code == 201


def test_escrita_sem_csrf_e_bloqueada(cliente, realizado):
    r = cliente.post(f"/workspace/appointments/{realizado['id']}/payment",
                     json={"metodo": "pix"})
    assert r.status_code == 403


# ---------------- pendências ----------------
def test_baixa_tira_da_lista_de_pendencias(cliente, realizado):
    assert len(cliente.get("/workspace/finance/pending").json()) == 1
    baixar(cliente, realizado)
    assert cliente.get("/workspace/finance/pending").json() == []


# ---------------- estorno ----------------
def test_estorno_devolve_o_atendimento_para_pendente(cliente, realizado):
    pagamento = baixar(cliente, realizado).json()

    r = cliente.post(f"/workspace/payments/{pagamento['id']}/refund",
                     json={"motivo": "cobrado por engano"}, headers=csrf(cliente))
    assert r.status_code == 200
    assert r.json()["status"] == "refunded"
    assert r.json()["motivo_estorno"] == "cobrado por engano"

    atendimento = cliente.get(f"/workspace/appointments/{realizado['id']}").json()
    assert atendimento["pagamento"] == "pending"
    assert len(cliente.get("/workspace/finance/pending").json()) == 1


def test_estorno_nao_apaga_o_lancamento(cliente, realizado):
    """Livro-caixa não se rasura: a linha continua, marcada."""
    pagamento = baixar(cliente, realizado).json()
    cliente.post(f"/workspace/payments/{pagamento['id']}/refund", json={},
                 headers=csrf(cliente))

    livro = cliente.get("/workspace/payments").json()
    assert len(livro) == 1
    assert livro[0]["status"] == "refunded"


def test_estornado_sai_do_recebido(cliente, realizado):
    pagamento = baixar(cliente, realizado).json()
    assert float(cliente.get("/workspace/finance/summary").json()["recebido"]) == 180.0

    cliente.post(f"/workspace/payments/{pagamento['id']}/refund", json={}, headers=csrf(cliente))
    assert float(cliente.get("/workspace/finance/summary").json()["recebido"]) == 0.0


def test_estornar_duas_vezes_e_recusado(cliente, realizado):
    pagamento = baixar(cliente, realizado).json()
    cliente.post(f"/workspace/payments/{pagamento['id']}/refund", json={}, headers=csrf(cliente))
    r = cliente.post(f"/workspace/payments/{pagamento['id']}/refund", json={}, headers=csrf(cliente))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ja_estornado"


def test_depois_de_estornar_da_para_cobrar_de_novo(cliente, realizado):
    pagamento = baixar(cliente, realizado).json()
    cliente.post(f"/workspace/payments/{pagamento['id']}/refund", json={}, headers=csrf(cliente))
    assert baixar(cliente, realizado, metodo="cash").status_code == 201


# ---------------- isenção ----------------
def test_isentar_tira_da_cobranca_sem_lancar_no_caixa(cliente, realizado):
    r = cliente.post(f"/workspace/appointments/{realizado['id']}/waive",
                     json={"motivo": "primeira sessão de cortesia"}, headers=csrf(cliente))
    assert r.status_code == 200
    assert r.json()["pagamento"] == "waived"

    assert cliente.get("/workspace/finance/pending").json() == []
    assert cliente.get("/workspace/payments").json() == []       # dinheiro nenhum entrou
    assert float(cliente.get("/workspace/finance/summary").json()["recebido"]) == 0.0


def test_isentar_o_que_ja_foi_pago_e_recusado(cliente, realizado):
    baixar(cliente, realizado)
    r = cliente.post(f"/workspace/appointments/{realizado['id']}/waive", json={},
                     headers=csrf(cliente))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ja_pago"


def test_motivo_da_isencao_fica_registrado(cliente, realizado):
    cliente.post(f"/workspace/appointments/{realizado['id']}/waive",
                 json={"motivo": "cortesia"}, headers=csrf(cliente))
    atendimento = cliente.get(f"/workspace/appointments/{realizado['id']}").json()
    assert "cortesia" in (atendimento["observacao"] or "")


# ---------------- regime de caixa ----------------
def test_recebido_conta_pela_data_do_pagamento(cliente, realizado):
    """Atendimento de ontem, pago hoje: entra no caixa de hoje.

    É o que a pessoa vai conferir com o extrato do banco.
    """
    baixar(cliente, realizado)          # pago_em vazio = agora
    livro = cliente.get("/workspace/payments").json()
    assert livro[0]["pago_em"][:10] == agora().date().isoformat()


def test_serie_mensal_usa_o_livro_caixa(cliente, realizado):
    baixar(cliente, realizado)
    serie = cliente.get("/workspace/finance/series?meses=2").json()
    assert float(serie[-1]["valor"]) == 180.0
    assert serie[-1]["quantidade"] == 1


def test_filtro_por_metodo(cliente, conta):
    pessoa = cliente.post("/workspace/clients", json={"nome": "Dois Pagamentos", "valor_sessao": "100.00"},
                          headers=csrf(cliente)).json()
    for i, metodo in enumerate(["pix", "cash"]):
        inicio = (ONTEM - timedelta(hours=i + 1)).isoformat()
        a = cliente.post("/workspace/appointments",
                         json={"cliente_id": pessoa["id"], "inicio": inicio},
                         headers=csrf(cliente)).json()
        cliente.post(f"/workspace/appointments/{a['id']}/status",
                     json={"status": "done"}, headers=csrf(cliente))
        baixar(cliente, a, metodo=metodo)

    assert len(cliente.get("/workspace/payments").json()) == 2
    assert len(cliente.get("/workspace/payments?metodo=pix").json()) == 1


# ---------------- isolamento e permissão ----------------
def test_pagamento_de_outra_conta_nao_existe(cliente, realizado):
    pagamento = baixar(cliente, realizado).json()

    cliente.cookies.clear()
    cadastrar(cliente, nome="Bia", email="bia@exemplo.com", workspace="Clínica da Bia")

    assert cliente.get("/workspace/payments").json() == []
    r = cliente.post(f"/workspace/payments/{pagamento['id']}/refund", json={},
                     headers=csrf(cliente))
    assert r.status_code == 404


def test_baixa_em_atendimento_de_outra_conta_responde_404(cliente, realizado):
    cliente.cookies.clear()
    cadastrar(cliente, nome="Bia", email="bia2@exemplo.com", workspace="Clínica da Bia 2")
    assert baixar(cliente, realizado).status_code == 404


def test_quem_so_le_financeiro_nao_da_baixa(cliente, db, realizado):
    """PROFESSIONAL tem finance.read e não tem finance.write."""
    from sqlalchemy import select

    from app.ids import novo_ulid
    from app.models.membership import Membership, MembershipPermission
    from app.models.rbac import Permission

    membership = db.execute(select(Membership)).scalar_one()
    permissao = db.execute(
        select(Permission).where(Permission.key == "finance.write")
    ).scalar_one()
    db.add(MembershipPermission(
        public_id=novo_ulid(), tenant_id=membership.tenant_id, membership_id=membership.id,
        permission_id=permissao.id, effect="deny", reason="teste: separar leitura de escrita",
    ))
    db.commit()

    assert cliente.get("/workspace/finance/summary").status_code == 200
    r = baixar(cliente, realizado)
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "sem_permissao"
