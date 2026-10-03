"""
Escopo de dados dentro da mesma conta.

Isolamento entre contas já está coberto. Aqui é o degrau de dentro: numa
clínica com várias pessoas, `data_scope = "own"` precisa significar
**só os meus**, e a falha tem que ser para menos (lista vazia), nunca para
mais (a conta inteira).
"""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.context import sem_escopo_de_tenant
from app.ids import novo_ulid
from app.models.membership import Membership
from app.models.professional import Professional
from app.models.tenant import Tenant
from app.models.user import User
from app.services.sessions import agora
from tests.conftest import SENHA_PADRAO, cadastrar, csrf, entrar, hoje_na_conta

AMANHA = (agora() + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)


@pytest.fixture
def clinica(cliente, db):
    """Uma clínica com a dona (escopo 'all') e um profissional (escopo 'own')."""
    r = cadastrar(cliente, nome="Dona Clara", email="clara@exemplo.com",
                  workspace="Clínica Bem Viver", profissao="terapia_integrativa")
    assert r.status_code == 201
    tenant_publico = r.json()["workspace_ativo"]["id"]

    # O segundo usuário nasce com a própria conta; o vínculo com a clínica
    # é criado direto no banco porque o convite entra numa etapa futura.
    cliente_aux_cookies = dict(cliente.cookies)
    cliente.cookies.clear()
    cadastrar(cliente, nome="Marcos Prof", email="marcos@exemplo.com",
              workspace="Consultório Marcos", profissao="terapia_integrativa")
    cliente.cookies.clear()

    with sem_escopo_de_tenant():
        tenant = db.execute(select(Tenant).where(Tenant.public_id == tenant_publico)).scalar_one()
        marcos = db.execute(select(User).where(User.email == "marcos@exemplo.com")).scalar_one()
        from app.models.rbac import Role

        role = db.execute(select(Role).where(Role.key == "PROFESSIONAL")).scalar_one()

        vinculo = Membership(
            public_id=novo_ulid(), tenant_id=tenant.id, user_id=marcos.id,
            role_id=role.id, data_scope="own", status="active",
        )
        db.add(vinculo)
        db.flush()

        perfil = Professional(
            public_id=novo_ulid(), tenant_id=tenant.id, membership_id=vinculo.id,
            profession_id=db.execute(select(Professional.profession_id)).scalars().first(),
            display_name="Marcos Prof", active=True,
        )
        db.add(perfil)
        db.commit()
        dados = {"tenant_id": tenant.id, "tenant_publico": tenant_publico,
                 "perfil_marcos": perfil.public_id}

    # volta para a sessão da dona
    cliente.cookies.clear()
    for k, v in cliente_aux_cookies.items():
        cliente.cookies.set(k, v)
    return dados


def entrar_como_marcos(cliente, clinica):
    cliente.cookies.clear()
    entrar(cliente, "marcos@exemplo.com")
    r = cliente.post("/session/workspace", json={"workspace_id": clinica["tenant_publico"]},
                     headers=csrf(cliente))
    assert r.status_code == 200
    assert r.json()["workspace_ativo"]["escopo"] == "own"
    return r.json()


def novo_cliente(cliente, nome):
    return cliente.post("/workspace/clients", json={"nome": nome, "valor_sessao": "150.00"},
                        headers=csrf(cliente)).json()


# ---------------- pessoas atendidas ----------------
def test_dona_enxerga_a_conta_toda(cliente, clinica):
    novo_cliente(cliente, "Pessoa da Dona")
    entrar_como_marcos(cliente, clinica)
    do_marcos = novo_cliente(cliente, "Pessoa do Marcos")

    cliente.cookies.clear()
    entrar(cliente, "clara@exemplo.com")
    nomes = [c["nome"] for c in cliente.get("/workspace/clients").json()]
    assert sorted(nomes) == ["Pessoa da Dona", "Pessoa do Marcos"]


def test_profissional_enxerga_so_os_seus(cliente, clinica):
    da_dona = novo_cliente(cliente, "Pessoa da Dona")

    entrar_como_marcos(cliente, clinica)
    novo_cliente(cliente, "Pessoa do Marcos")

    nomes = [c["nome"] for c in cliente.get("/workspace/clients").json()]
    assert nomes == ["Pessoa do Marcos"]

    # A pessoa da dona existe na mesma conta — mas não para ele.
    assert cliente.get(f"/workspace/clients/{da_dona['id']}").status_code == 404


def test_profissional_sem_nenhum_vinculo_ve_lista_vazia(cliente, clinica):
    novo_cliente(cliente, "Pessoa da Dona")
    entrar_como_marcos(cliente, clinica)
    assert cliente.get("/workspace/clients").json() == []       # vazio, nunca "tudo"


def test_quem_cadastra_passa_a_enxergar(cliente, clinica):
    """O vínculo criado no cadastro é o que evita 'cadastrei e sumiu'."""
    entrar_como_marcos(cliente, clinica)
    criado = novo_cliente(cliente, "Pessoa do Marcos")
    assert cliente.get(f"/workspace/clients/{criado['id']}").status_code == 200


# ---------------- atendimentos ----------------
def test_atendimento_de_outro_profissional_nao_aparece(cliente, clinica):
    pessoa_dona = novo_cliente(cliente, "Pessoa da Dona")
    da_dona = cliente.post("/workspace/appointments",
                           json={"cliente_id": pessoa_dona["id"], "inicio": AMANHA.isoformat()},
                           headers=csrf(cliente)).json()

    entrar_como_marcos(cliente, clinica)
    pessoa_marcos = novo_cliente(cliente, "Pessoa do Marcos")
    cliente.post("/workspace/appointments",
                 json={"cliente_id": pessoa_marcos["id"],
                       "inicio": (AMANHA + timedelta(hours=1)).isoformat()},
                 headers=csrf(cliente))

    lista = cliente.get("/workspace/appointments").json()
    assert [a["cliente"]["nome"] for a in lista] == ["Pessoa do Marcos"]
    assert cliente.get(f"/workspace/appointments/{da_dona['id']}").status_code == 404


def test_conflito_de_horario_nao_vaza_agenda_alheia(cliente, clinica):
    """Agendas diferentes, mesmo horário: cada profissional tem a sua."""
    pessoa_dona = novo_cliente(cliente, "Pessoa da Dona")
    r = cliente.post("/workspace/appointments",
                     json={"cliente_id": pessoa_dona["id"], "inicio": AMANHA.isoformat()},
                     headers=csrf(cliente))
    assert r.status_code == 201

    entrar_como_marcos(cliente, clinica)
    pessoa_marcos = novo_cliente(cliente, "Pessoa do Marcos")
    r = cliente.post("/workspace/appointments",
                     json={"cliente_id": pessoa_marcos["id"], "inicio": AMANHA.isoformat()},
                     headers=csrf(cliente))
    assert r.status_code == 201       # mesmo horário, agenda de outra pessoa


def test_dashboard_do_profissional_conta_so_o_dele(cliente, clinica):
    hoje = hoje_na_conta(14)
    pessoa_dona = novo_cliente(cliente, "Pessoa da Dona")
    cliente.post("/workspace/appointments",
                 json={"cliente_id": pessoa_dona["id"], "inicio": hoje.isoformat()},
                 headers=csrf(cliente))

    entrar_como_marcos(cliente, clinica)
    d = cliente.get("/workspace/dashboard").json()
    assert d["resumo_dia"]["total"] == 0
    assert d["clientes"]["ativos"] == 0


def test_profissional_nao_administra_a_conta(cliente, clinica):
    entrar_como_marcos(cliente, clinica)
    assert cliente.get("/workspace/members").status_code == 403


def test_profissional_alcanca_o_proprio_clinico(cliente, clinica):
    """PROFESSIONAL tem clinical_records.read pelo papel."""
    entrar_como_marcos(cliente, clinica)
    assert cliente.get("/workspace/clinical-check").status_code == 200


def test_dona_que_atende_entra_pelo_perfil_e_nao_pelo_papel(cliente, clinica):
    """Clara abriu a conta declarando profissão: atende, logo tem prontuário.

    O acesso NÃO vem do papel — OWNER continua sem nada de clínico na
    matriz. Vem de uma concessão explícita, com motivo, criada no
    cadastro. A diferença importa: dá para ver por que ela tem, e dá para
    tirar sem mexer no papel de ninguém.
    """
    cliente.cookies.clear()
    entrar(cliente, "clara@exemplo.com")
    assert cliente.get("/workspace/clinical-check").status_code == 200


def test_dono_que_nao_atende_continua_fora_do_clinico(cliente):
    """A regra que sustenta tudo: administrar a conta não abre prontuário."""
    cliente.cookies.clear()
    cadastrar(cliente, nome="Gestor Puro", email="gestor.puro@exemplo.com",
              workspace="Clínica Administrada")     # sem profissão
    assert cliente.get("/workspace/clinical-check").status_code == 403
