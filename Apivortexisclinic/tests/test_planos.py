"""
Planos, limites e uso.

As regras travadas aqui:

* o plano carrega os números — o código pergunta "quantos posso ter?";
* **limite recusa, nunca apaga**: estourar impede criar o próximo, e quem
  cai de plano continua enxergando tudo o que cadastrou;
* `None` é sem limite;
* não existe rota para trocar de plano — é comando, porque sem cobrança
  atrás seria um botão de "vire Pro de graça".

A tabela `plans` é preservada entre testes (vem do seed). Por isso nenhum
teste altera os planos do catálogo: quem precisa de um limite apertado cria
um plano próprio, e a fixture o remove no fim.
"""
import sys
from datetime import timedelta

import pytest
from sqlalchemy import delete, select

from app.db.context import sem_escopo_de_tenant
from app.ids import novo_ulid
from app.models.billing import Plan, Subscription
from app.models.membership import Membership
from app.models.rbac import Role
from app.models.tenant import Tenant
from app.models.user import User
from app.services import billing
from app.services.sessions import agora
from tests.conftest import cadastrar, csrf, entrar

CHAVE_TESTE = "teste_apertado"


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
def plano_apertado(db):
    """Fábrica de plano de teste. Remove o plano (e quem o assina) no fim."""
    criados = []

    def criar(**limites):
        dados = dict(max_professionals=None, max_members=None, max_clients=None,
                     max_storage_mb=None, allows_clinical=True, allows_documents=True,
                     allows_export=True, allows_reminders=True)
        dados.update(limites)
        chave = f"{CHAVE_TESTE}_{len(criados)}"
        plano = Plan(public_id=novo_ulid(), key=chave, name="Teste", active=True,
                     sort_order=99, **dados)
        db.add(plano)
        db.commit()
        criados.append(plano.id)
        return chave

    yield criar

    with sem_escopo_de_tenant():
        for pid in criados:
            db.execute(delete(Subscription).where(Subscription.plan_id == pid))
            db.execute(delete(Plan).where(Plan.id == pid))
        db.commit()


def mudar_plano(db, tenant_id, chave):
    with sem_escopo_de_tenant():
        billing.trocar_plano(db, tenant_id, chave)
        db.commit()


def nova_pessoa(cliente, nome):
    return cliente.post("/workspace/clients", json={"nome": nome}, headers=csrf(cliente))


# ---------------- o que a tela lê ----------------
def test_conta_nova_nasce_no_plano_padrao_em_teste(cliente, conta):
    r = cliente.get("/workspace/plan")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["plano"] == "essencial"
    assert corpo["status"] == "trialing"
    assert corpo["vigente"] is True
    assert corpo["trial_ate"] is not None


def test_uso_vem_ao_lado_do_limite(cliente, conta):
    nova_pessoa(cliente, "Ana Beatriz")
    nova_pessoa(cliente, "Bruno Lima")
    corpo = cliente.get("/workspace/plan").json()
    assert corpo["uso"]["clientes"] == 2
    assert corpo["limites"]["clientes"] == 500
    assert corpo["uso"]["profissionais"] == 1


def test_preco_vem_do_banco_sem_inventar(cliente, db, conta):
    """O preço é o do catálogo: nulo se não definido, nunca um valor da tela."""
    with sem_escopo_de_tenant():
        no_banco = db.execute(select(Plan.monthly_price).where(Plan.key == "essencial")).scalar_one()
    esperado = None if no_banco is None else float(no_banco)
    assert cliente.get("/workspace/plan").json()["preco_mensal"] == esperado


def test_plano_sem_teto_responde_none_e_nao_9999(cliente, db, tenant_id):
    mudar_plano(db, tenant_id, "clinica")
    limites = cliente.get("/workspace/plan").json()["limites"]
    assert limites["profissionais"] is None
    assert limites["clientes"] is None


def test_recepcao_nao_le_o_plano(cliente, db, tenant_id):
    """Plano é informação de conta (`settings.manage`), não de atendimento."""
    cliente.cookies.clear()
    cadastrar(cliente, nome="Rita Recepção", email="rita@exemplo.com",
              workspace="Conta da Rita")
    with sem_escopo_de_tenant():
        rita = db.execute(select(User).where(User.email == "rita@exemplo.com")).scalar_one()
        papel = db.execute(select(Role).where(Role.key == "ASSISTANT")).scalar_one()
        db.add(Membership(public_id=novo_ulid(), tenant_id=tenant_id, user_id=rita.id,
                          role_id=papel.id, data_scope="all", status="active"))
        db.commit()
        publico = db.execute(select(Tenant.public_id).where(Tenant.id == tenant_id)).scalar_one()

    cliente.cookies.clear()
    entrar(cliente, "rita@exemplo.com")
    assert cliente.post("/session/workspace", json={"workspace_id": publico},
                        headers=csrf(cliente)).status_code == 200
    assert cliente.get("/workspace/plan").status_code == 403


# ---------------- limite recusa ----------------
def test_estourar_o_limite_recusa_o_proximo(cliente, db, tenant_id, plano_apertado):
    mudar_plano(db, tenant_id, plano_apertado(max_clients=2))
    assert nova_pessoa(cliente, "Ana Beatriz").status_code == 201
    assert nova_pessoa(cliente, "Bruno Lima").status_code == 201

    r = nova_pessoa(cliente, "Carla Dias")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "limite_do_plano"
    assert "2" in r.json()["detail"]["message"]


def test_arquivar_libera_vaga(cliente, db, tenant_id, plano_apertado):
    """O limite conta pessoas ATIVAS: quem foi arquivado não ocupa vaga."""
    mudar_plano(db, tenant_id, plano_apertado(max_clients=1))
    ana = nova_pessoa(cliente, "Ana Beatriz").json()
    assert nova_pessoa(cliente, "Bruno Lima").status_code == 409

    assert cliente.post(f"/workspace/clients/{ana['id']}/archive", json={},
                        headers=csrf(cliente)).status_code == 200
    assert nova_pessoa(cliente, "Bruno Lima").status_code == 201


def test_limite_de_membros_e_conferido_no_convite(cliente, db, tenant_id, plano_apertado):
    """No convite, não no aceite: recusar quem já clicou no link seria a
    pior hora para descobrir o limite."""
    mudar_plano(db, tenant_id, plano_apertado(max_members=1))
    r = cliente.post("/workspace/invitations",
                     json={"email": "novo@exemplo.com", "papel": "PROFESSIONAL"},
                     headers=csrf(cliente))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "limite_do_plano"


def test_recurso_fora_do_plano_responde_409_com_o_que_fazer(cliente, db, tenant_id, plano_apertado):
    pessoa = nova_pessoa(cliente, "Ana Beatriz").json()
    ontem = (agora() - timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    a = cliente.post("/workspace/appointments",
                     json={"cliente_id": pessoa["id"], "inicio": ontem.isoformat()},
                     headers=csrf(cliente)).json()
    cliente.post(f"/workspace/appointments/{a['id']}/status",
                 json={"status": "done"}, headers=csrf(cliente))

    mudar_plano(db, tenant_id, plano_apertado(allows_documents=False))
    r = cliente.post(f"/workspace/clients/{pessoa['id']}/documents/attendance",
                     json={"atendimento_id": a["id"]}, headers=csrf(cliente))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "recurso_do_plano"


# ---------------- limite nunca apaga ----------------
def test_cair_de_plano_nao_apaga_nem_esconde(cliente, db, tenant_id, plano_apertado):
    for nome in ("Ana Beatriz", "Bruno Lima", "Carla Dias"):
        assert nova_pessoa(cliente, nome).status_code == 201

    mudar_plano(db, tenant_id, plano_apertado(max_clients=2))

    lista = cliente.get("/workspace/clients").json()
    assert len(lista) == 3                         # continua enxergando tudo
    assert cliente.get("/workspace/plan").json()["uso"]["clientes"] == 3
    assert nova_pessoa(cliente, "Davi Souza").status_code == 409   # só não cria mais


# ---------------- troca de plano ----------------
def test_nao_existe_rota_para_trocar_de_plano(cliente, conta):
    for metodo in ("post", "put", "patch"):
        r = getattr(cliente, metodo)("/workspace/plan", json={"plano": "clinica"},
                                     headers=csrf(cliente))
        assert r.status_code == 405


def test_plano_inexistente_e_recusado(db, tenant_id):
    from app.errors import ApiError

    with sem_escopo_de_tenant(), pytest.raises(ApiError):
        billing.trocar_plano(db, tenant_id, "vire_pro_de_graca")


def test_comando_troca_o_plano(cliente, db, conta, tenant_id, monkeypatch, capsys):
    """O comando roda no processo do teste, contra o banco de teste: chamá-lo
    em subprocesso leria o .env de verdade."""
    from app.jobs import assinatura

    with sem_escopo_de_tenant():
        slug = db.execute(select(Tenant.slug).where(Tenant.id == tenant_id)).scalar_one()
    monkeypatch.setattr(sys, "argv", ["assinatura", "--tenant", slug, "--plano", "clinica",
                                      "--nota", "teste"])
    assert assinatura.main() == 0
    assert "Clínica" in capsys.readouterr().out
    assert cliente.get("/workspace/plan").json()["plano"] == "clinica"
