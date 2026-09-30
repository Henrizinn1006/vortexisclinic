"""Cadastro, login, logout, sessão e recuperação de senha."""
from sqlalchemy import select

from app.config import settings
from app.models.membership import Membership
from app.models.professional import Professional
from app.models.tenant import Tenant
from app.models.user import User
from tests.conftest import SENHA_PADRAO, cadastrar, csrf, entrar


# ---------------- cadastro ----------------
def test_cadastro_cria_usuario_workspace_membership_e_perfil(cliente, db):
    r = cadastrar(cliente, nome="Camila Ferraz", email="camila@exemplo.com",
                  workspace="Consultório Camila", profissao="psicologia", registro="06/123456")
    assert r.status_code == 201, r.text

    corpo = r.json()
    assert corpo["usuario"]["email"] == "camila@exemplo.com"
    assert corpo["workspace_ativo"]["nome"] == "Consultório Camila"
    assert corpo["workspace_ativo"]["papel"] == "OWNER"
    assert corpo["perfil"]["registro"] == "06/123456"

    usuario = db.execute(select(User).where(User.email == "camila@exemplo.com")).scalar_one()
    membership = db.execute(select(Membership).where(Membership.user_id == usuario.id)).scalar_one()
    assert membership.status == "active"
    assert membership.role.key == "OWNER"
    assert membership.data_scope == "all"

    # O perfil profissional é tenant-scoped: ler exige contexto, então a
    # consulta aqui é feita pelo caminho administrativo explícito.
    from app.db.context import sem_escopo_de_tenant

    with sem_escopo_de_tenant():
        perfil = db.execute(select(Professional)).scalars().all()
    assert len(perfil) == 1


def test_cadastro_nunca_guarda_senha_em_texto(cliente, db):
    cadastrar(cliente, nome="Bruno", email="bruno@exemplo.com", workspace="Clínica Bruno")
    usuario = db.execute(select(User).where(User.email == "bruno@exemplo.com")).scalar_one()
    assert SENHA_PADRAO not in usuario.password_hash
    assert usuario.password_hash.startswith("$argon2id$")


def test_email_normalizado_e_unico(cliente):
    assert cadastrar(cliente, nome="Ana Paula", email="Igual@Exemplo.com", workspace="Workspace Um").status_code == 201
    r = cadastrar(cliente, nome="Bruno Dias", email="igual@exemplo.com", workspace="Workspace Dois")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "email_em_uso"


def test_cadastro_com_falha_nao_deixa_tenant_pela_metade(cliente, db):
    """Profissão inexistente derruba tudo: nem usuário, nem workspace ficam."""
    r = cadastrar(cliente, nome="Carla", email="carla@exemplo.com",
                  workspace="Workspace Fantasma", profissao="profissao-que-nao-existe")
    assert r.status_code == 422
    assert db.execute(select(User).where(User.email == "carla@exemplo.com")).first() is None
    assert db.execute(select(Tenant).where(Tenant.name == "Workspace Fantasma")).first() is None


def test_profissao_com_conselho_exige_registro(cliente):
    r = cadastrar(cliente, nome="Dora", email="dora@exemplo.com",
                  workspace="Consultório Dora", profissao="psicologia")
    assert r.status_code == 422
    assert "registro" in r.json()["detail"]["message"].lower() or "crp" in r.json()["detail"]["message"].lower()


def test_profissao_sem_conselho_nao_exige_registro(cliente):
    r = cadastrar(cliente, nome="Eva", email="eva@exemplo.com",
                  workspace="Espaço Eva", profissao="terapia_integrativa")
    assert r.status_code == 201
    assert r.json()["perfil"]["registro"] is None


def test_senha_curta_recusada(cliente):
    r = cliente.post("/auth/register", json={
        "nome": "Fábio", "email": "fabio@exemplo.com", "senha": "curta12", "workspace": "W"
    })
    assert r.status_code == 422


# ---------------- login ----------------
def test_login_abre_sessao_com_cookie_httponly(cliente):
    cadastrar(cliente, nome="Gabi", email="gabi@exemplo.com", workspace="Consultório Gabi")
    cliente.cookies.clear()

    r = entrar(cliente, "gabi@exemplo.com")
    assert r.status_code == 200
    assert settings.VC_SESSION_COOKIE_NAME in cliente.cookies

    bruto = "\n".join(str(v) for v in r.headers.get_list("set-cookie"))
    assert "HttpOnly" in bruto                       # sessão não é legível por JS
    assert "SameSite=lax" in bruto.lower() or "samesite=lax" in bruto.lower()
    assert settings.VC_CSRF_COOKIE_NAME in bruto     # CSRF precisa ser legível


def test_senha_errada_e_email_inexistente_respondem_igual(cliente):
    cadastrar(cliente, nome="Hugo", email="hugo@exemplo.com", workspace="W Hugo")
    cliente.cookies.clear()

    errada = cliente.post("/auth/login", json={"email": "hugo@exemplo.com", "senha": "outraSenha!123"})
    inexistente = cliente.post("/auth/login", json={"email": "ninguem@exemplo.com", "senha": "outraSenha!123"})

    assert errada.status_code == inexistente.status_code == 401
    assert errada.json() == inexistente.json()       # nada distingue os dois casos


def test_me_exige_sessao(cliente):
    cliente.cookies.clear()
    assert cliente.get("/auth/me").status_code == 401


def test_logout_invalida_a_sessao(cliente):
    cadastrar(cliente, nome="Ivo", email="ivo@exemplo.com", workspace="W Ivo")
    assert cliente.get("/auth/me").status_code == 200

    r = cliente.post("/auth/logout", headers=csrf(cliente))
    assert r.status_code == 200

    # Mesmo devolvendo o cookie antigo à força, a sessão está revogada.
    assert cliente.get("/auth/me").status_code == 401


def test_sessao_revogada_nao_volta_a_valer(cliente):
    cadastrar(cliente, nome="Joana", email="joana@exemplo.com", workspace="W Joana")
    token = cliente.cookies.get(settings.VC_SESSION_COOKIE_NAME)
    cabecalhos = csrf(cliente)
    cliente.post("/auth/logout", headers=cabecalhos)

    cliente.cookies.clear()
    cliente.cookies.set(settings.VC_SESSION_COOKIE_NAME, token)
    assert cliente.get("/auth/me").status_code == 401


# ---------------- CSRF ----------------
def test_escrita_sem_token_csrf_e_bloqueada(cliente):
    cadastrar(cliente, nome="Lia", email="lia@exemplo.com", workspace="W Lia")
    r = cliente.post("/auth/logout")                 # sem cabeçalho X-CSRF-Token
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "csrf_invalido"


def test_escrita_com_token_csrf_de_outra_sessao_e_bloqueada(cliente):
    cadastrar(cliente, nome="Marco", email="marco@exemplo.com", workspace="W Marco")
    r = cliente.post("/auth/logout", headers={"X-CSRF-Token": "token-inventado-que-nao-bate"})
    assert r.status_code == 403


def test_leitura_nao_exige_csrf(cliente):
    cadastrar(cliente, nome="Nara", email="nara@exemplo.com", workspace="W Nara")
    assert cliente.get("/auth/me").status_code == 200


# ---------------- rate limit ----------------
def test_login_tem_rate_limit(cliente):
    cadastrar(cliente, nome="Otto", email="otto@exemplo.com", workspace="W Otto")
    cliente.cookies.clear()

    codigos = []
    for _ in range(settings.VC_RATE_LIMIT_LOGIN + 3):
        codigos.append(
            cliente.post("/auth/login", json={"email": "otto@exemplo.com", "senha": "erradaErrada!1"}).status_code
        )
    assert 429 in codigos


# ---------------- recuperação de senha ----------------
def test_esqueci_senha_responde_igual_para_email_existente_e_inexistente(cliente):
    cadastrar(cliente, nome="Paula", email="paula@exemplo.com", workspace="W Paula")
    cliente.cookies.clear()

    existe = cliente.post("/auth/password/forgot", json={"email": "paula@exemplo.com"})
    nao_existe = cliente.post("/auth/password/forgot", json={"email": "vazio@exemplo.com"})
    assert existe.status_code == nao_existe.status_code == 200
    assert existe.json() == nao_existe.json()


def test_reset_de_senha_derruba_todas_as_sessoes(cliente, db):
    from app.services import auth as servico_auth

    cadastrar(cliente, nome="Rui", email="rui@exemplo.com", workspace="W Rui")
    assert cliente.get("/auth/me").status_code == 200

    usuario = servico_auth.buscar_por_email(db, "rui@exemplo.com")
    token = servico_auth.criar_token_de_reset(db, usuario)
    db.commit()

    r = cliente.post("/auth/password/reset", json={"token": token, "senha": "NovaSenhaForte!2026"})
    assert r.status_code == 200
    assert cliente.get("/auth/me").status_code == 401      # a sessão anterior morreu

    cliente.cookies.clear()
    assert entrar(cliente, "rui@exemplo.com", "NovaSenhaForte!2026").status_code == 200


def test_token_de_reset_e_de_uso_unico(cliente, db):
    from app.services import auth as servico_auth

    cadastrar(cliente, nome="Sara", email="sara@exemplo.com", workspace="W Sara")
    usuario = servico_auth.buscar_por_email(db, "sara@exemplo.com")
    token = servico_auth.criar_token_de_reset(db, usuario)
    db.commit()

    assert cliente.post("/auth/password/reset",
                        json={"token": token, "senha": "PrimeiraTroca!2026"}).status_code == 200
    assert cliente.post("/auth/password/reset",
                        json={"token": token, "senha": "SegundaTroca!2026"}).status_code == 422
