"""
Vários workspaces para o mesmo usuário: entrada direta, seleção e troca segura.
"""
from app.config import settings
from tests.conftest import cadastrar, csrf, entrar


def test_um_workspace_entra_direto(cliente):
    r = cadastrar(cliente, nome="Sozinha", email="solo@exemplo.com", workspace="Consultório Solo")
    assert r.json()["workspace_ativo"]["nome"] == "Consultório Solo"

    cliente.cookies.clear()
    entrada = entrar(cliente, "solo@exemplo.com").json()
    assert entrada["workspace_ativo"] is not None       # não precisa escolher


def test_varios_workspaces_exigem_escolha(cliente):
    cadastrar(cliente, nome="Multi", email="multi@exemplo.com", workspace="Consultório Próprio")
    cliente.post("/workspaces", json={"nome": "Clínica Bem Viver", "tipo": "clinic"},
                 headers=csrf(cliente))

    cliente.cookies.clear()
    entrada = entrar(cliente, "multi@exemplo.com").json()
    assert entrada["workspace_ativo"] is None           # a sessão nasce sem workspace
    assert len(entrada["workspaces"]) == 2
    assert entrada["permissoes"] == []                  # sem workspace, sem permissão


def test_troca_de_workspace_muda_contexto_e_rotaciona_a_sessao(cliente):
    cadastrar(cliente, nome="Multi", email="multi2@exemplo.com", workspace="Consultório Próprio")
    cliente.post("/workspaces", json={"nome": "Clínica Bem Viver", "tipo": "clinic"},
                 headers=csrf(cliente))
    cliente.cookies.clear()

    entrada = entrar(cliente, "multi2@exemplo.com").json()
    token_antes = cliente.cookies.get(settings.VC_SESSION_COOKIE_NAME)
    destino = [w for w in entrada["workspaces"] if w["nome"] == "Clínica Bem Viver"][0]

    r = cliente.post("/session/workspace", json={"workspace_id": destino["id"]},
                     headers=csrf(cliente))
    assert r.status_code == 200
    assert r.json()["workspace_ativo"]["nome"] == "Clínica Bem Viver"

    # Anti session fixation: mudança de privilégio troca o token.
    assert cliente.cookies.get(settings.VC_SESSION_COOKIE_NAME) != token_antes


def test_token_antigo_para_de_valer_depois_da_troca(cliente):
    cadastrar(cliente, nome="Multi", email="multi3@exemplo.com", workspace="Consultório Próprio")
    cliente.post("/workspaces", json={"nome": "Clínica Nova", "tipo": "clinic"}, headers=csrf(cliente))
    entrada = cliente.get("/auth/me").json()

    token_antigo = cliente.cookies.get(settings.VC_SESSION_COOKIE_NAME)
    destino = [w for w in entrada["workspaces"] if w["nome"] == "Clínica Nova"][0]
    cliente.post("/session/workspace", json={"workspace_id": destino["id"]}, headers=csrf(cliente))

    cliente.cookies.clear()
    cliente.cookies.set(settings.VC_SESSION_COOKIE_NAME, token_antigo)
    assert cliente.get("/auth/me").status_code == 401


def test_workspace_id_invalido_e_recusado(cliente):
    cadastrar(cliente, nome="Curiosa", email="curiosa@exemplo.com", workspace="W Curiosa")
    for inventado in ["0000000000000000000000000A", "nao-e-ulid", ""]:
        r = cliente.post("/session/workspace", json={"workspace_id": inventado}, headers=csrf(cliente))
        assert r.status_code in (404, 422)


def test_novo_workspace_nasce_com_o_usuario_como_owner(cliente):
    cadastrar(cliente, nome="Dona", email="dona@exemplo.com", workspace="Primeiro")
    r = cliente.post("/workspaces", json={"nome": "Segundo", "tipo": "office"}, headers=csrf(cliente))
    assert r.status_code == 201
    segundo = [w for w in r.json()["workspaces"] if w["nome"] == "Segundo"][0]
    assert segundo["papel"] == "OWNER"


def test_slug_repetido_ganha_sufixo(cliente, db):
    from sqlalchemy import select

    from app.models.tenant import Tenant

    cadastrar(cliente, nome="Um", email="um@exemplo.com", workspace="Clínica Vida")
    cliente.cookies.clear()
    cadastrar(cliente, nome="Dois", email="dois@exemplo.com", workspace="Clínica Vida")

    slugs = sorted(t.slug for t in db.execute(select(Tenant)).scalars())
    assert slugs == ["clinica-vida", "clinica-vida-2"]
