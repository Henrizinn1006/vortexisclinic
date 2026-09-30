"""Pessoas atendidas: cadastro, busca, ficha, isolamento e escopo."""
import pytest
from sqlalchemy import select

from app.db.context import sem_escopo_de_tenant
from app.models.client import Client, ClientProfessional
from tests.conftest import cadastrar, csrf, entrar


@pytest.fixture
def conta(cliente):
    """Uma conta pronta, com sessão aberta como dona-que-atende."""
    r = cadastrar(cliente, nome="Camila Ferraz", email="camila@exemplo.com",
                  workspace="Consultório Camila", profissao="terapia_integrativa")
    assert r.status_code == 201
    return r.json()


def novo(cliente, nome="Ana Beatriz Moraes", **extra):
    corpo = {"nome": nome, "valor_sessao": "180.00", "frequencia": "weekly"}
    corpo.update(extra)
    return cliente.post("/workspace/clients", json=corpo, headers=csrf(cliente))


# ---------------- cadastro ----------------
def test_cadastrar_pessoa_atendida(cliente, conta):
    r = novo(cliente)
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["nome"] == "Ana Beatriz Moraes"
    assert corpo["status"] == "active"
    assert corpo["resumo"]["total"] == 0


def test_cadastro_vincula_ao_profissional(cliente, conta, db):
    """Sem o vínculo, quem está em escopo 'own' cadastraria e perderia de vista."""
    novo(cliente)
    with sem_escopo_de_tenant():
        vinculos = db.execute(select(ClientProfessional)).scalars().all()
    assert len(vinculos) == 1
    assert vinculos[0].is_primary is True


def test_nome_muito_curto_e_recusado(cliente, conta):
    assert novo(cliente, nome="A").status_code == 422


def test_valor_negativo_e_recusado(cliente, conta):
    assert novo(cliente, valor_sessao="-10").status_code == 422


def test_escrita_sem_csrf_e_bloqueada(cliente, conta):
    r = cliente.post("/workspace/clients", json={"nome": "Sem Token"})
    assert r.status_code == 403


# ---------------- leitura ----------------
def test_listar_ordena_por_nome(cliente, conta):
    for nome in ["Rafael Lima", "Ana Beatriz", "Juliana Costa"]:
        novo(cliente, nome=nome)
    nomes = [c["nome"] for c in cliente.get("/workspace/clients").json()]
    assert nomes == ["Ana Beatriz", "Juliana Costa", "Rafael Lima"]


def test_busca_por_parte_do_nome(cliente, conta):
    novo(cliente, nome="Ana Beatriz Moraes")
    novo(cliente, nome="Rafael Lima")
    achados = cliente.get("/workspace/clients?busca=beatriz").json()
    assert [c["nome"] for c in achados] == ["Ana Beatriz Moraes"]


def test_busca_nao_trata_curinga_como_curinga(cliente, conta):
    """Quem digita '%' quer o caractere, não 'tudo'."""
    novo(cliente, nome="Ana Beatriz")
    assert cliente.get("/workspace/clients?busca=%25").json() == []


def test_filtro_de_status(cliente, conta):
    r = novo(cliente, nome="Ativa Silva")
    outro = novo(cliente, nome="Inativa Souza").json()
    cliente.patch(f"/workspace/clients/{outro['id']}", json={"status": "inactive"},
                  headers=csrf(cliente))

    assert [c["nome"] for c in cliente.get("/workspace/clients?status=active").json()] == ["Ativa Silva"]
    assert [c["nome"] for c in cliente.get("/workspace/clients?status=inactive").json()] == ["Inativa Souza"]
    assert len(cliente.get("/workspace/clients?status=todos").json()) == 2


def test_contagem(cliente, conta):
    novo(cliente, nome="Um Paciente")
    novo(cliente, nome="Dois Paciente")
    c = cliente.get("/workspace/clients/contagem").json()
    assert c["ativos"] == 2 and c["inativos"] == 0


def test_ficha_traz_resumo(cliente, conta):
    criado = novo(cliente).json()
    ficha = cliente.get(f"/workspace/clients/{criado['id']}").json()
    assert ficha["id"] == criado["id"]
    assert ficha["resumo"]["presenca"] is None      # sem atendimento, presença não é 0%


def test_id_inexistente_responde_404(cliente, conta):
    assert cliente.get("/workspace/clients/0000000000000000000000000").status_code == 404


# ---------------- alteração ----------------
def test_atualizar_muda_so_o_que_veio(cliente, conta):
    criado = novo(cliente, nome="Nome Antigo").json()
    r = cliente.patch(f"/workspace/clients/{criado['id']}",
                      json={"telefone": "(11) 99999-0000"}, headers=csrf(cliente))
    assert r.status_code == 200
    assert r.json()["nome"] == "Nome Antigo"
    assert r.json()["telefone"] == "(11) 99999-0000"


def test_arquivar_nao_apaga(cliente, conta, db):
    criado = novo(cliente).json()
    r = cliente.post(f"/workspace/clients/{criado['id']}/archive", headers=csrf(cliente))
    assert r.status_code == 200
    assert r.json()["status"] == "archived"

    with sem_escopo_de_tenant():
        assert db.execute(select(Client)).scalars().first() is not None


# ---------------- isolamento ----------------
def test_pessoa_de_outra_conta_nao_existe(cliente, conta):
    da_camila = novo(cliente, nome="Ana da Camila").json()

    cliente.cookies.clear()
    cadastrar(cliente, nome="Bia Outra", email="bia@exemplo.com", workspace="Clínica da Bia")

    assert cliente.get("/workspace/clients").json() == []
    r = cliente.get(f"/workspace/clients/{da_camila['id']}")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "nao_encontrado"


def test_nao_da_para_editar_pessoa_de_outra_conta(cliente, conta):
    da_camila = novo(cliente, nome="Ana da Camila").json()
    cliente.cookies.clear()
    cadastrar(cliente, nome="Bia Outra", email="bia2@exemplo.com", workspace="Clínica da Bia 2")

    r = cliente.patch(f"/workspace/clients/{da_camila['id']}", json={"nome": "Invadida"},
                      headers=csrf(cliente))
    assert r.status_code == 404


def test_sem_workspace_ativo_nao_lista(cliente, conta, db):
    from app.models.membership import Membership

    membership = db.execute(select(Membership)).scalar_one()
    membership.status = "suspended"
    db.commit()

    r = cliente.get("/workspace/clients")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "sem_workspace_ativo"
