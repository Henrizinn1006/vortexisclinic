"""
Cobrança pelo Asaas, com o gateway simulado (`httpx.MockTransport`).

Regras travadas aqui:

* o checkout **não muda o plano** — só o webhook de pagamento confirmado;
* webhook sem token certo é recusado, e sem token configurado também;
* o mesmo evento reenviado não muda nada (idempotência);
* gateway fora do ar não vaza detalhe e não deixa a conta pela metade.

Planos do catálogo não são alterados: o preço entra num plano de teste.
"""
import json
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import delete, select

from app.config import settings
from app.db.context import sem_escopo_de_tenant
from app.ids import novo_ulid
from app.models.billing import BillingEvent, Plan, Subscription
from app.models.tenant import Tenant
from app.services import asaas
from tests.conftest import cadastrar, csrf

TOKEN = "token-de-webhook-de-teste"
CPF = "529.982.247-25"


@pytest.fixture
def gateway(monkeypatch):
    """Asaas de mentira. `chamadas` guarda (método, caminho, corpo)."""
    monkeypatch.setattr(settings, "VC_ASAAS_API_KEY", "chave-de-teste")
    monkeypatch.setattr(settings, "VC_ASAAS_WEBHOOK_TOKEN", TOKEN)
    estado = {"chamadas": [], "falhar": None}

    def tratar(req: httpx.Request) -> httpx.Response:
        corpo = json.loads(req.content) if req.content else None
        estado["chamadas"].append((req.method, req.url.path, corpo))
        assert req.headers["access_token"] == "chave-de-teste"
        if estado["falhar"]:
            return httpx.Response(estado["falhar"], text="erro com cpf 52998224725")
        if req.url.path.endswith("/customers"):
            return httpx.Response(200, json={"id": "cus_1"})
        if req.url.path.endswith("/payments"):
            return httpx.Response(200, json={"data": [{"invoiceUrl": "https://asaas.test/i/1"}]})
        if req.method == "DELETE":
            return httpx.Response(200, json={"deleted": True})
        return httpx.Response(200, json={"id": "sub_1"})

    monkeypatch.setattr(asaas, "_transporte", httpx.MockTransport(tratar))
    return estado


@pytest.fixture
def conta(cliente):
    r = cadastrar(cliente, nome="Clara Mendes", email="clara@exemplo.com",
                  workspace="Clínica Bem Viver", profissao="terapia_integrativa")
    assert r.status_code == 201
    return r.json()


@pytest.fixture
def tenant_id(db, conta):
    with sem_escopo_de_tenant():
        return db.execute(
            select(Tenant.id).where(Tenant.public_id == conta["workspace_ativo"]["id"])
        ).scalar_one()


@pytest.fixture
def plano_pago(db):
    with sem_escopo_de_tenant():
        p = Plan(public_id=novo_ulid(), key="teste_pago", name="Teste Pago", active=True,
                 sort_order=99, monthly_price=Decimal("99.90"))
        db.add(p)
        db.commit()
        pid = p.id
    yield "teste_pago"
    with sem_escopo_de_tenant():
        db.execute(delete(Subscription).where(Subscription.plan_id == pid))
        db.execute(delete(Subscription).where(Subscription.pending_plan_id == pid))
        db.execute(delete(Plan).where(Plan.id == pid))
        db.commit()


def sub(db, tenant_id) -> Subscription:
    db.expire_all()
    with sem_escopo_de_tenant():
        return db.execute(
            select(Subscription).where(Subscription.tenant_id == tenant_id)
        ).scalar_one()


def checkout(cliente, plano="teste_pago", cpf=CPF):
    return cliente.post("/workspace/plan/checkout", json={"plano": plano, "cpf_cnpj": cpf},
                        headers=csrf(cliente))


def webhook(cliente, evento, *, id_evento="evt_1", sub_ref="sub_1", token=TOKEN, vence="2026-10-09"):
    return cliente.post(
        "/billing/asaas/webhook",
        json={"id": id_evento, "event": evento,
              "payment": {"id": "pay_1", "subscription": sub_ref, "dueDate": vence}},
        headers={"asaas-access-token": token},
    )


# ---------------- checkout ----------------
def test_checkout_devolve_link_e_nao_muda_o_plano(cliente, db, tenant_id, gateway, plano_pago):
    r = checkout(cliente)
    assert r.status_code == 200, r.text
    assert r.json()["link_pagamento"] == "https://asaas.test/i/1"

    s = sub(db, tenant_id)
    assert s.plan.key == "essencial"              # ainda não pagou
    assert s.pending_plan.key == plano_pago
    assert (s.provider, s.external_ref) == ("asaas", "sub_1")

    criar = next(c for c in gateway["chamadas"]
                 if c[0] == "POST" and c[1].endswith("/subscriptions"))
    assert criar[2]["value"] == 99.9
    assert criar[2]["billingType"] == "UNDEFINED"


def test_cpf_vai_ao_gateway_e_nao_fica_no_banco(cliente, db, tenant_id, gateway, plano_pago):
    checkout(cliente)
    cliente_asaas = next(c for c in gateway["chamadas"] if c[1].endswith("/customers"))
    assert cliente_asaas[2]["cpfCnpj"] == "52998224725"
    s = sub(db, tenant_id)
    assert "52998224725" not in json.dumps([s.note, s.external_ref, s.provider])


def test_checkout_recusa_cpf_invalido(cliente, conta, gateway, plano_pago):
    assert checkout(cliente, cpf="123").status_code == 422


def test_checkout_plano_sem_preco(cliente, db, conta, gateway):
    with sem_escopo_de_tenant():
        p = Plan(public_id=novo_ulid(), key="teste_sem_preco", name="Sem Preco",
                 active=True, sort_order=98, monthly_price=None)
        db.add(p)
        db.commit()
        pid = p.id
    try:
        r = checkout(cliente, plano="teste_sem_preco")
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "plano_sem_preco"
    finally:
        with sem_escopo_de_tenant():
            db.execute(delete(Plan).where(Plan.id == pid))
            db.commit()


def test_checkout_sem_chave_fica_indisponivel(cliente, conta, plano_pago, monkeypatch):
    monkeypatch.setattr(settings, "VC_ASAAS_API_KEY", "")
    assert checkout(cliente).status_code == 503


def test_gateway_fora_do_ar_nao_vaza_nem_deixa_pela_metade(cliente, db, tenant_id, gateway, plano_pago):
    gateway["falhar"] = 500
    r = checkout(cliente)
    assert r.status_code == 503
    assert "52998224725" not in r.text
    s = sub(db, tenant_id)
    assert s.external_ref is None and s.pending_plan_id is None


def test_segundo_checkout_com_assinatura_ativa_e_recusado(cliente, conta, gateway, plano_pago):
    assert checkout(cliente).status_code == 200
    r = checkout(cliente)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "assinatura_existente"


# ---------------- webhook ----------------
def test_webhook_sem_token_certo_e_recusado(cliente, conta, gateway):
    assert webhook(cliente, "PAYMENT_CONFIRMED", token="errado").status_code == 401
    assert webhook(cliente, "PAYMENT_CONFIRMED", token="").status_code == 401


def test_webhook_sem_token_configurado_recusa_tudo(cliente, conta, gateway, monkeypatch):
    monkeypatch.setattr(settings, "VC_ASAAS_WEBHOOK_TOKEN", "")
    assert webhook(cliente, "PAYMENT_CONFIRMED", token="").status_code == 401


def test_pagamento_confirmado_efetiva_o_plano(cliente, db, tenant_id, gateway, plano_pago):
    checkout(cliente)
    assert webhook(cliente, "PAYMENT_CONFIRMED").status_code == 200
    s = sub(db, tenant_id)
    assert s.plan.key == plano_pago
    assert s.pending_plan_id is None
    assert s.status == "active"
    assert s.current_period_end.isoformat().startswith("2026-11-09")


def test_evento_repetido_nao_muda_nada(cliente, db, tenant_id, gateway, plano_pago):
    checkout(cliente)
    webhook(cliente, "PAYMENT_CONFIRMED", id_evento="evt_a")
    with sem_escopo_de_tenant():
        s = db.execute(select(Subscription).where(Subscription.tenant_id == tenant_id)).scalar_one()
        s.status = "past_due"             # algo que o reenvio não pode desfazer
        db.commit()
    assert webhook(cliente, "PAYMENT_CONFIRMED", id_evento="evt_a").status_code == 200
    assert sub(db, tenant_id).status == "past_due"
    with sem_escopo_de_tenant():
        assert len(db.execute(select(BillingEvent)).scalars().all()) == 1


def test_atraso_marca_past_due_e_conta_continua_vigente(cliente, db, tenant_id, gateway, plano_pago):
    checkout(cliente)
    webhook(cliente, "PAYMENT_CONFIRMED", id_evento="evt_1")
    webhook(cliente, "PAYMENT_OVERDUE", id_evento="evt_2")
    s = sub(db, tenant_id)
    assert s.status == "past_due" and s.vigente is True


def test_assinatura_removida_no_gateway_cancela(cliente, db, tenant_id, gateway, plano_pago):
    checkout(cliente)
    webhook(cliente, "PAYMENT_CONFIRMED", id_evento="evt_1")
    webhook(cliente, "SUBSCRIPTION_DELETED", id_evento="evt_2")
    s = sub(db, tenant_id)
    assert s.status == "canceled" and s.canceled_at is not None


def test_evento_de_assinatura_desconhecida_responde_200(cliente, conta, gateway):
    assert webhook(cliente, "PAYMENT_CONFIRMED", sub_ref="sub_de_ninguem").status_code == 200


def test_evento_sem_efeito_responde_200(cliente, db, tenant_id, gateway, plano_pago):
    checkout(cliente)
    assert webhook(cliente, "PAYMENT_CREATED", id_evento="evt_x").status_code == 200
    assert sub(db, tenant_id).plan.key == "essencial"


# ---------------- cancelamento ----------------
def test_cancelar_chama_o_gateway_e_marca_cancelada(cliente, db, tenant_id, gateway, plano_pago):
    checkout(cliente)
    webhook(cliente, "PAYMENT_CONFIRMED")
    r = cliente.post("/workspace/plan/cancel", headers=csrf(cliente))
    assert r.status_code == 200, r.text
    assert any(m == "DELETE" and c.endswith("/subscriptions/sub_1")
               for m, c, _ in gateway["chamadas"])
    assert sub(db, tenant_id).status == "canceled"


def test_cancelar_sem_assinatura_paga(cliente, conta, gateway):
    assert cliente.post("/workspace/plan/cancel", headers=csrf(cliente)).status_code == 409


# ---------------- o que a tela lê ----------------
def test_resumo_traz_catalogo_so_com_preco_e_estado_da_cobranca(cliente, conta, gateway, plano_pago):
    corpo = cliente.get("/workspace/plan").json()
    chaves = [c["plano"] for c in corpo["catalogo"]]
    assert plano_pago in chaves
    assert all(c["preco_mensal"] is not None for c in corpo["catalogo"])
    assert corpo["cobranca_ativa"] is True
    assert corpo["assinatura_paga"] is False and corpo["plano_pendente"] is None

    checkout(cliente)
    corpo = cliente.get("/workspace/plan").json()
    assert corpo["plano_pendente"] == plano_pago
    assert corpo["assinatura_paga"] is True
