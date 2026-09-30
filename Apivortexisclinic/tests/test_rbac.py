"""
RBAC — primeira versão.

O que estes testes protegem, para sempre:

  - OWNER **não** é bypass universal;
  - nenhuma permissão administrativa alcança a classe clínica;
  - ASSISTANT nunca recebe permissão clínica;
  - concessão explícita funciona, e com validade.
"""
from sqlalchemy import select

from app import rbac
from app.models.membership import Membership, MembershipPermission
from app.models.rbac import Permission, Role
from app.services import permissions as servico
from tests.conftest import cadastrar, entrar


# ---------------- matriz ----------------
def test_owner_nao_recebe_permissao_clinica_pelo_papel():
    permissoes = rbac.permissoes_do_papel(rbac.OWNER)
    clinicas = [p for p in permissoes if rbac.eh_clinica(p)]
    assert clinicas == [], f"OWNER não pode ter permissão clínica pelo papel: {clinicas}"


def test_assistant_nunca_tem_clinico():
    permissoes = rbac.permissoes_do_papel(rbac.ASSISTANT)
    assert not any(rbac.eh_clinica(p) for p in permissoes)
    assert not any(p.startswith("documents.") for p in permissoes)


def test_professional_ve_o_proprio_clinico_mas_nao_o_dos_outros():
    permissoes = rbac.permissoes_do_papel(rbac.PROFESSIONAL)
    assert "clinical_records.read" in permissoes
    assert "clinical_records.write" in permissoes
    assert "clinical_records.read_others" not in permissoes


def test_nenhum_papel_tem_todas_as_permissoes():
    todas = {chave for chave, _n, _c in rbac.PERMISSOES}
    for papel, permissoes in rbac.PAPEL_PERMISSOES.items():
        assert set(permissoes) != todas, f"{papel} virou bypass universal"


def test_catalogo_do_banco_bate_com_o_catalogo_do_codigo(db):
    """O seed da migration e o rbac.py não podem divergir em silêncio."""
    no_banco = {p.key for p in db.execute(select(Permission)).scalars()}
    no_codigo = {chave for chave, _n, _c in rbac.PERMISSOES}
    assert no_banco == no_codigo

    papeis = {r.key for r in db.execute(select(Role)).scalars()}
    assert papeis == set(rbac.PAPEL_PERMISSOES.keys())


# ---------------- na prática, pela API ----------------
def test_owner_entra_na_area_administrativa(cliente):
    cadastrar(cliente, nome="Dono", email="dono@exemplo.com", workspace="Clínica Dono")
    assert cliente.get("/workspace/members").status_code == 200


def test_owner_e_barrado_na_area_clinica(cliente):
    """Administrar a conta não abre prontuário. Esta é a regra que mais importa."""
    cadastrar(cliente, nome="Dono", email="dono2@exemplo.com", workspace="Clínica Dono 2")
    r = cliente.get("/workspace/clinical-check")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "sem_permissao"


def test_permissoes_do_me_nao_trazem_clinico_para_o_owner(cliente):
    r = cadastrar(cliente, nome="Dono", email="dono3@exemplo.com", workspace="Clínica Dono 3")
    permissoes = r.json()["permissoes"]
    assert "members.manage" in permissoes
    assert not any(rbac.eh_clinica(p) for p in permissoes)


# ---------------- exceções ----------------
def _membership_do(db, email) -> Membership:
    from app.models.user import User

    usuario = db.execute(select(User).where(User.email == email)).scalar_one()
    return db.execute(select(Membership).where(Membership.user_id == usuario.id)).scalar_one()


def test_concessao_explicita_abre_o_acesso_clinico(cliente, db):
    """O dono que também atende recebe acesso por concessão registrada, não pelo cargo."""
    cadastrar(cliente, nome="Dono Atende", email="dono4@exemplo.com", workspace="Consultório Dono")
    membership = _membership_do(db, "dono4@exemplo.com")
    permissao = db.execute(
        select(Permission).where(Permission.key == "clinical_records.read")
    ).scalar_one()

    from app.ids import novo_ulid

    db.add(MembershipPermission(
        public_id=novo_ulid(),
        tenant_id=membership.tenant_id,
        membership_id=membership.id,
        permission_id=permissao.id,
        effect="grant",
        reason="dono também atende — acesso ao próprio conteúdo clínico",
    ))
    db.commit()

    assert cliente.get("/workspace/clinical-check").status_code == 200


def test_concessao_vencida_nao_vale(cliente, db):
    from datetime import timedelta

    from app.ids import novo_ulid
    from app.services.sessions import agora

    cadastrar(cliente, nome="Cobertura", email="dono5@exemplo.com", workspace="Clínica Cobertura")
    membership = _membership_do(db, "dono5@exemplo.com")
    permissao = db.execute(
        select(Permission).where(Permission.key == "clinical_records.read")
    ).scalar_one()

    db.add(MembershipPermission(
        public_id=novo_ulid(),
        tenant_id=membership.tenant_id,
        membership_id=membership.id,
        permission_id=permissao.id,
        effect="grant",
        reason="cobertura de férias",
        starts_at=agora() - timedelta(days=30),
        expires_at=agora() - timedelta(days=1),      # venceu ontem
    ))
    db.commit()

    assert cliente.get("/workspace/clinical-check").status_code == 403


def test_deny_vence_grant(cliente, db):
    from app.ids import novo_ulid

    cadastrar(cliente, nome="Bloqueado", email="dono6@exemplo.com", workspace="Clínica Bloqueio")
    membership = _membership_do(db, "dono6@exemplo.com")
    permissao = db.execute(select(Permission).where(Permission.key == "members.manage")).scalar_one()

    db.add(MembershipPermission(
        public_id=novo_ulid(), tenant_id=membership.tenant_id, membership_id=membership.id,
        permission_id=permissao.id, effect="deny", reason="afastamento temporário",
    ))
    db.commit()

    assert cliente.get("/workspace/members").status_code == 403


def test_membership_suspensa_nao_tem_permissao_nenhuma(db, cliente):
    cadastrar(cliente, nome="Suspenso", email="dono7@exemplo.com", workspace="Clínica Suspensa")
    membership = _membership_do(db, "dono7@exemplo.com")
    membership.status = "suspended"
    db.commit()
    assert servico.efetivas(db, membership) == set()
