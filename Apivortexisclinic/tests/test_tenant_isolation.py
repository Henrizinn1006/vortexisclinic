"""
Isolamento multi-tenant — a suíte que não pode falhar nunca.

Cenários exigidos na Etapa 3, um teste para cada:

  Usuário A → recurso do tenant A ................. permitido
  Usuário A → recurso do tenant B ................. negado (404, não 403)
  tenant_id trocado na requisição ................. negado
  usuário sem membership .......................... negado
  membership inativa .............................. negado
  operação tenant-scoped sem contexto ............. falha, nunca consulta ampla
"""
import pytest
from sqlalchemy import select

from app.db.context import TenantContextError, definir_tenant, sem_escopo_de_tenant
from app.models.membership import Membership
from app.models.professional import Professional
from app.models.tenant import Tenant
from tests.conftest import cadastrar, csrf, entrar


@pytest.fixture
def duas_contas(cliente, db):
    """Tenant A (Ana) e tenant B (Bia), cada um com seu profissional."""
    cadastrar(cliente, nome="Ana", email="ana@exemplo.com",
              workspace="Consultório Ana", profissao="terapia_integrativa")
    cliente.cookies.clear()
    cadastrar(cliente, nome="Bia", email="bia@exemplo.com",
              workspace="Clínica Bia", profissao="terapia_integrativa")
    cliente.cookies.clear()

    with sem_escopo_de_tenant():
        tenants = {t.name: t for t in db.execute(select(Tenant)).scalars()}
        profissionais = {
            p.tenant_id: p for p in db.execute(select(Professional)).scalars()
        }
    return {
        "tenant_a": tenants["Consultório Ana"],
        "tenant_b": tenants["Clínica Bia"],
        "prof_a": profissionais[tenants["Consultório Ana"].id],
        "prof_b": profissionais[tenants["Clínica Bia"].id],
    }


# ---------------- permitido ----------------
def test_usuario_acessa_recurso_do_proprio_tenant(cliente, duas_contas):
    entrar(cliente, "ana@exemplo.com")
    r = cliente.get(f"/workspace/professionals/{duas_contas['prof_a'].public_id}")
    assert r.status_code == 200
    assert r.json()["nome_exibicao"] == "Ana"


def test_listagem_traz_somente_o_tenant_ativo(cliente, duas_contas):
    entrar(cliente, "ana@exemplo.com")
    lista = cliente.get("/workspace/professionals").json()
    assert [p["nome_exibicao"] for p in lista] == ["Ana"]


# ---------------- negado ----------------
def test_recurso_de_outro_tenant_responde_404_e_nao_403(cliente, duas_contas):
    """403 confirmaria que o registro existe. Para a Ana, o da Bia não existe."""
    entrar(cliente, "ana@exemplo.com")
    r = cliente.get(f"/workspace/professionals/{duas_contas['prof_b'].public_id}")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "nao_encontrado"


def test_id_inexistente_responde_igual_a_id_de_outro_tenant(cliente, duas_contas):
    """A resposta não pode distinguir 'não existe' de 'existe e não é seu'."""
    entrar(cliente, "ana@exemplo.com")
    outro = cliente.get(f"/workspace/professionals/{duas_contas['prof_b'].public_id}")
    inventado = cliente.get("/workspace/professionals/0000000000000000000000000")
    assert outro.status_code == inventado.status_code == 404
    assert outro.json() == inventado.json()


def test_tenant_id_enviado_pelo_cliente_e_ignorado(cliente, duas_contas):
    """Nem corpo, nem query, nem cabeçalho mudam o tenant da sessão."""
    entrar(cliente, "ana@exemplo.com")
    alvo = duas_contas["tenant_b"].public_id

    tentativas = [
        cliente.get(f"/workspace/professionals?tenant_id={alvo}"),
        cliente.get("/workspace/professionals", headers={"X-Tenant-Id": alvo}),
        cliente.get("/workspace/professionals", headers={"X-Tenant": alvo}),
    ]
    for r in tentativas:
        assert r.status_code == 200
        assert [p["nome_exibicao"] for p in r.json()] == ["Ana"]     # continua no tenant dela


def test_trocar_para_workspace_sem_membership_responde_404(cliente, duas_contas):
    entrar(cliente, "ana@exemplo.com")
    r = cliente.post("/session/workspace",
                     json={"workspace_id": duas_contas["tenant_b"].public_id},
                     headers=csrf(cliente))
    assert r.status_code == 404
    assert cliente.get("/workspace/professionals").json()[0]["nome_exibicao"] == "Ana"


def test_membership_suspensa_perde_o_acesso(cliente, db, duas_contas):
    entrar(cliente, "ana@exemplo.com")
    assert cliente.get("/workspace/professionals").status_code == 200

    membership = db.execute(
        select(Membership).where(Membership.tenant_id == duas_contas["tenant_a"].id)
    ).scalar_one()
    membership.status = "suspended"
    db.commit()

    # A sessão continua válida (o usuário existe), mas o workspace sai dela.
    r = cliente.get("/workspace/professionals")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "sem_workspace_ativo"

    me = cliente.get("/auth/me").json()
    assert me["workspace_ativo"] is None
    assert me["workspaces"] == []


def test_usuario_sem_nenhuma_membership_nao_entra_em_area_de_workspace(cliente, db):
    cadastrar(cliente, nome="Zeca", email="zeca@exemplo.com", workspace="W Zeca")
    membership = db.execute(select(Membership)).scalar_one()
    membership.status = "suspended"
    db.commit()

    r = cliente.get("/workspace/professionals")
    assert r.status_code == 409


def test_sessao_expirada_nao_acessa_area_de_workspace(cliente, db, duas_contas):
    from datetime import timedelta

    from app.config import settings
    from app.models.security import AuthSession
    from app.security import tokens as tk
    from app.services.sessions import agora

    entrar(cliente, "ana@exemplo.com")

    # A sessão é localizada pelo hash do token do cookie — nada de
    # "a última linha da tabela", que erraria de alvo com facilidade.
    token = cliente.cookies.get(settings.VC_SESSION_COOKIE_NAME)
    sessao = db.execute(
        select(AuthSession).where(AuthSession.token_hash == tk.hash_token(token))
    ).scalar_one()
    sessao.idle_expires_at = agora() - timedelta(minutes=1)
    db.commit()

    assert cliente.get("/workspace/professionals").status_code == 401


# ---------------- fail-closed no ORM ----------------
def test_consulta_tenant_scoped_sem_contexto_falha(db, duas_contas):
    """O coração do fail-closed: sem tenant, a consulta quebra em vez de devolver tudo."""
    definir_tenant(None)
    with pytest.raises(TenantContextError):
        db.execute(select(Professional)).scalars().all()


def test_com_contexto_a_mesma_consulta_devolve_so_o_tenant(db, duas_contas):
    definir_tenant(duas_contas["tenant_a"].id)
    try:
        linhas = db.execute(select(Professional)).scalars().all()
        assert [p.display_name for p in linhas] == ["Ana"]

        definir_tenant(duas_contas["tenant_b"].id)
        linhas = db.execute(select(Professional)).scalars().all()
        assert [p.display_name for p in linhas] == ["Bia"]
    finally:
        definir_tenant(None)


def test_busca_por_id_de_outro_tenant_nao_encontra_nem_no_orm(db, duas_contas):
    """Nem com o id certo em mãos: o filtro é da consulta, não da rota."""
    definir_tenant(duas_contas["tenant_a"].id)
    try:
        achado = db.execute(
            select(Professional).where(Professional.public_id == duas_contas["prof_b"].public_id)
        ).scalar_one_or_none()
        assert achado is None
    finally:
        definir_tenant(None)
