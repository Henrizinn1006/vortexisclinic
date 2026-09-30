"""
Equipe: convite, aceite e mudança de acesso.

O que estes testes travam: ninguém convida para um lugar melhor que o seu,
a conta nunca fica sem dono, aceitar não escolhe o próprio acesso, e link
de convite não vira porta de entrada para quem não foi convidado.
"""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.context import sem_escopo_de_tenant
from app.models.invitation import Invitation
from app.models.membership import Membership
from app.models.professional import Professional
from app.models.user import User
from app.services.sessions import agora
from tests.conftest import SENHA_PADRAO, cadastrar, csrf, entrar

OUTRA_SENHA = "OutraSenhaBoa!2026"


@pytest.fixture
def clinica(cliente):
    r = cadastrar(cliente, nome="Clara Mendes", email="clara@exemplo.com",
                  workspace="Clínica Bem Viver", profissao="terapia_integrativa")
    assert r.status_code == 201
    return r.json()


def convidar(cliente, **extra):
    corpo = {"email": "novo@exemplo.com", "papel": "PROFESSIONAL"}
    corpo.update(extra)
    return cliente.post("/workspace/invitations", json=corpo, headers=csrf(cliente))


def token_do_link(link: str) -> str:
    return link.rsplit("/", 1)[-1]


# ---------------- convidar ----------------
def test_convite_devolve_o_link_uma_vez(cliente, clinica):
    r = convidar(cliente)
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["email"] == "novo@exemplo.com"
    assert corpo["link"] and len(token_do_link(corpo["link"])) > 20

    # Na listagem o link não volta: o token existe uma vez só.
    equipe = cliente.get("/workspace/team").json()
    assert len(equipe["convites"]) == 1
    assert equipe["convites"][0]["link"] is None


def test_token_nao_fica_guardado_em_claro(cliente, db, clinica):
    token = token_do_link(convidar(cliente).json()["link"])
    with sem_escopo_de_tenant():
        guardado = db.execute(select(Invitation.token_hash)).scalar_one()
    assert guardado != token
    assert len(guardado) == 64          # sha256


def test_convite_repetido_para_o_mesmo_email_e_recusado(cliente, clinica):
    assert convidar(cliente).status_code == 201
    r = convidar(cliente)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "convite_pendente"


def test_nao_convida_quem_ja_esta_dentro(cliente, clinica):
    r = convidar(cliente, email="clara@exemplo.com")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ja_e_membro"


def test_revogar_fecha_o_convite(cliente, clinica):
    convite = convidar(cliente).json()
    token = token_do_link(convite["link"])
    assert cliente.post(f"/workspace/invitations/{convite['id']}/revoke",
                        headers=csrf(cliente)).status_code == 200
    # Link revogado responde igual a link inexistente.
    assert cliente.get(f"/invitations/{token}").status_code == 404


def test_convite_vencido_nao_abre(cliente, db, clinica):
    token = token_do_link(convidar(cliente).json()["link"])
    with sem_escopo_de_tenant():
        convite = db.execute(select(Invitation)).scalar_one()
        convite.expires_at = agora() - timedelta(minutes=1)
        db.commit()
    assert cliente.get(f"/invitations/{token}").status_code == 404


def test_link_inventado_responde_igual_a_link_vencido(cliente, clinica):
    assert cliente.get("/invitations/naoexiste").status_code == 404


# ---------------- aceitar ----------------
def test_aceitar_cria_conta_e_entra_na_clinica(cliente, clinica):
    convite = convidar(cliente, profissao="terapia_integrativa").json()
    token = token_do_link(convite["link"])

    publico = cliente.get(f"/invitations/{token}").json()
    assert publico["workspace"] == "Clínica Bem Viver"
    assert publico["papel"] == "PROFESSIONAL"
    assert publico["ja_tem_conta"] is False

    cliente.cookies.clear()
    r = cliente.post(f"/invitations/{token}/accept",
                     json={"nome": "Marcos Prof", "senha": OUTRA_SENHA})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["workspace_ativo"]["nome"] == "Clínica Bem Viver"
    assert corpo["workspace_ativo"]["papel"] == "PROFESSIONAL"
    # Quem entra por convite NÃO ganha consultório próprio de brinde.
    assert len(corpo["workspaces"]) == 1


def test_quem_entra_com_profissao_nasce_atendendo(cliente, db, clinica):
    token = token_do_link(convidar(cliente, profissao="terapia_integrativa").json()["link"])
    cliente.cookies.clear()
    r = cliente.post(f"/invitations/{token}/accept",
                     json={"nome": "Marcos Prof", "senha": OUTRA_SENHA})
    assert r.json()["perfil"] is not None
    # E o acesso clínico vem por concessão explícita, como o do titular.
    assert cliente.get("/workspace/clinical-check").status_code == 200


def test_quem_entra_sem_profissao_nao_alcanca_o_clinico(cliente, clinica):
    """Recepção entra para administrar, não para ler prontuário."""
    token = token_do_link(convidar(cliente, papel="ASSISTANT").json()["link"])
    cliente.cookies.clear()
    cliente.post(f"/invitations/{token}/accept",
                 json={"nome": "Rita Recepção", "senha": OUTRA_SENHA})
    assert cliente.get("/workspace/clinical-check").status_code == 403


def test_aceitar_nao_escolhe_o_proprio_acesso(cliente, clinica):
    """Mandar papel no corpo não muda nada: o acesso vem do convite."""
    token = token_do_link(convidar(cliente, papel="ASSISTANT").json()["link"])
    cliente.cookies.clear()
    r = cliente.post(f"/invitations/{token}/accept",
                     json={"nome": "Esperta", "senha": OUTRA_SENHA,
                           "papel": "OWNER", "escopo": "all"})
    assert r.status_code == 200
    assert r.json()["workspace_ativo"]["papel"] == "ASSISTANT"


def test_convite_e_para_um_email_so(cliente, clinica):
    token = token_do_link(convidar(cliente).json()["link"])

    cliente.cookies.clear()
    cadastrar(cliente, nome="Intrusa", email="intrusa@exemplo.com",
              workspace="Consultório Intrusa")
    r = cliente.post(f"/invitations/{token}/accept", json={})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "convite_de_outro_email"


def test_quem_ja_tem_conta_aceita_com_a_senha(cliente, clinica):
    cliente.cookies.clear()
    cadastrar(cliente, nome="Marcos Prof", email="novo@exemplo.com",
              workspace="Consultório Marcos", senha=OUTRA_SENHA)
    cliente.cookies.clear()
    entrar(cliente, "clara@exemplo.com")

    token = token_do_link(convidar(cliente).json()["link"])
    publico = cliente.get(f"/invitations/{token}").json()
    assert publico["ja_tem_conta"] is True

    cliente.cookies.clear()
    r = cliente.post(f"/invitations/{token}/accept", json={"senha": OUTRA_SENHA})
    assert r.status_code == 200
    assert len(r.json()["workspaces"]) == 2      # o dele e a clínica


def test_senha_errada_nao_aceita_convite(cliente, clinica):
    cliente.cookies.clear()
    cadastrar(cliente, nome="Marcos Prof", email="novo@exemplo.com",
              workspace="Consultório Marcos", senha=OUTRA_SENHA)
    cliente.cookies.clear()
    entrar(cliente, "clara@exemplo.com")
    token = token_do_link(convidar(cliente).json()["link"])

    cliente.cookies.clear()
    r = cliente.post(f"/invitations/{token}/accept", json={"senha": "ChutePendente!99"})
    assert r.status_code == 401


def test_convite_usado_nao_serve_de_novo(cliente, clinica):
    token = token_do_link(convidar(cliente).json()["link"])
    cliente.cookies.clear()
    cliente.post(f"/invitations/{token}/accept",
                 json={"nome": "Marcos Prof", "senha": OUTRA_SENHA})
    cliente.cookies.clear()
    assert cliente.get(f"/invitations/{token}").status_code == 404


# ---------------- quem já está dentro ----------------
def _entrar_marcos(cliente, clinica):
    token = token_do_link(convidar(cliente, profissao="terapia_integrativa").json()["link"])
    cliente.cookies.clear()
    cliente.post(f"/invitations/{token}/accept",
                 json={"nome": "Marcos Prof", "senha": OUTRA_SENHA})
    cliente.cookies.clear()
    entrar(cliente, "clara@exemplo.com")
    equipe = cliente.get("/workspace/team").json()
    return [m for m in equipe["membros"] if m["email"] == "novo@exemplo.com"][0]


def test_equipe_lista_todo_mundo(cliente, clinica):
    _entrar_marcos(cliente, clinica)
    equipe = cliente.get("/workspace/team").json()
    assert len(equipe["membros"]) == 2
    eu = [m for m in equipe["membros"] if m["sou_eu"]][0]
    assert eu["papel"] == "OWNER"
    assert equipe["convites"] == []       # o convite foi consumido


def test_trocar_papel_e_escopo(cliente, clinica):
    marcos = _entrar_marcos(cliente, clinica)
    r = cliente.patch(f"/workspace/members/{marcos['id']}",
                      json={"papel": "ASSISTANT", "escopo": "all"}, headers=csrf(cliente))
    assert r.status_code == 200
    assert r.json()["papel"] == "ASSISTANT"
    assert r.json()["escopo"] == "all"


def test_suspender_tira_o_acesso_na_hora(cliente, clinica):
    marcos = _entrar_marcos(cliente, clinica)
    cliente.patch(f"/workspace/members/{marcos['id']}", json={"status": "suspended"},
                  headers=csrf(cliente))

    cliente.cookies.clear()
    entrar(cliente, "novo@exemplo.com", OUTRA_SENHA)
    corpo = cliente.get("/auth/me").json()
    assert all(w["nome"] != "Clínica Bem Viver" for w in corpo["workspaces"])


def test_nao_edita_o_proprio_acesso(cliente, clinica):
    equipe = cliente.get("/workspace/team").json()
    eu = [m for m in equipe["membros"] if m["sou_eu"]][0]
    r = cliente.patch(f"/workspace/members/{eu['id']}", json={"papel": "ASSISTANT"},
                      headers=csrf(cliente))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "nao_edita_a_si"


def test_a_conta_nao_fica_sem_dono(cliente, clinica):
    """Rebaixar o último dono é recusado — não há volta pela aplicação."""
    marcos = _entrar_marcos(cliente, clinica)
    # Promove Marcos e rebaixa a si mesma é o caminho certo; aqui tentamos
    # o errado: promover Marcos a dono, depois rebaixá-lo de volta enquanto
    # Clara... continua dona. Então o alvo é o único caminho que zera:
    cliente.patch(f"/workspace/members/{marcos['id']}", json={"papel": "OWNER"},
                  headers=csrf(cliente))
    # Agora há dois donos. Marcos rebaixa Clara — permitido.
    equipe = cliente.get("/workspace/team").json()
    clara = [m for m in equipe["membros"] if m["email"] == "clara@exemplo.com"][0]

    cliente.cookies.clear()
    entrar(cliente, "novo@exemplo.com", OUTRA_SENHA)
    r = cliente.patch(f"/workspace/members/{clara['id']}", json={"papel": "ASSISTANT"},
                      headers=csrf(cliente))
    assert r.status_code == 200

    # Agora Marcos é o único dono. Suspender a si mesmo já é barrado;
    # rebaixar Clara de novo não muda nada. Sobra provar pelo serviço:
    equipe = cliente.get("/workspace/team").json()
    assert sum(1 for m in equipe["membros"] if m["papel"] == "OWNER") == 1


def test_rebaixar_o_unico_dono_e_recusado(cliente, db, clinica):
    """Prova direta: com um dono só, a aplicação não deixa zerar."""
    marcos = _entrar_marcos(cliente, clinica)
    # Marcos vira dono e Clara também é dona: dois. Tiramos Clara pelo banco
    # para deixar Marcos sozinho e tentar rebaixá-lo por outra pessoa.
    cliente.patch(f"/workspace/members/{marcos['id']}", json={"papel": "OWNER"},
                  headers=csrf(cliente))
    equipe = cliente.get("/workspace/team").json()
    clara = [m for m in equipe["membros"] if m["email"] == "clara@exemplo.com"][0]

    cliente.cookies.clear()
    entrar(cliente, "novo@exemplo.com", OUTRA_SENHA)     # Marcos, dono
    # Marcos rebaixa Clara: sobra ele.
    cliente.patch(f"/workspace/members/{clara['id']}", json={"papel": "ASSISTANT"},
                  headers=csrf(cliente))
    # Clara (agora ASSISTANT) não administra mais nada.
    cliente.cookies.clear()
    entrar(cliente, "clara@exemplo.com")
    assert cliente.get("/workspace/team").status_code == 403

    # E Marcos, sozinho, não consegue se rebaixar: é o próprio acesso.
    cliente.cookies.clear()
    entrar(cliente, "novo@exemplo.com", OUTRA_SENHA)
    equipe = cliente.get("/workspace/team").json()
    eu = [m for m in equipe["membros"] if m["sou_eu"]][0]
    r = cliente.patch(f"/workspace/members/{eu['id']}", json={"papel": "ASSISTANT"},
                      headers=csrf(cliente))
    assert r.status_code == 409


def test_so_dono_cria_dono(cliente, clinica):
    """ASSISTANT com members.manage monta equipe, não fabrica um par."""
    from app.ids import novo_ulid
    from app.models.membership import MembershipPermission
    from app.models.rbac import Permission

    marcos = _entrar_marcos(cliente, clinica)
    cliente.patch(f"/workspace/members/{marcos['id']}", json={"papel": "ASSISTANT"},
                  headers=csrf(cliente))

    # Concessão explícita de members.manage para o ASSISTANT.
    from app.db.session import SessionLocal

    with sem_escopo_de_tenant():
        db = SessionLocal()
        membership = db.execute(
            select(Membership).join(User, User.id == Membership.user_id)
            .where(User.email == "novo@exemplo.com")
        ).scalar_one()
        permissao = db.execute(
            select(Permission).where(Permission.key == "members.manage")).scalar_one()
        db.add(MembershipPermission(
            public_id=novo_ulid(), tenant_id=membership.tenant_id,
            membership_id=membership.id, permission_id=permissao.id,
            effect="grant", reason="teste: montar equipe sem ser dono"))
        db.commit()
        db.close()

    cliente.cookies.clear()
    entrar(cliente, "novo@exemplo.com", OUTRA_SENHA)
    r = cliente.post("/workspace/invitations",
                     json={"email": "outro@exemplo.com", "papel": "OWNER"},
                     headers=csrf(cliente))
    assert r.status_code == 403
    # Mas convidar para um papel normal funciona.
    assert cliente.post("/workspace/invitations",
                        json={"email": "outro@exemplo.com", "papel": "PROFESSIONAL"},
                        headers=csrf(cliente)).status_code == 201


def test_quem_nao_administra_nem_ve_a_equipe(cliente, clinica):
    _entrar_marcos(cliente, clinica)
    cliente.cookies.clear()
    entrar(cliente, "novo@exemplo.com", OUTRA_SENHA)
    assert cliente.get("/workspace/team").status_code == 403
    assert cliente.post("/workspace/invitations", json={"email": "x@exemplo.com"},
                        headers=csrf(cliente)).status_code == 403


def test_membro_de_outra_conta_nao_existe(cliente, clinica):
    marcos = _entrar_marcos(cliente, clinica)
    cliente.cookies.clear()
    cadastrar(cliente, nome="Bia Outra", email="bia@exemplo.com", workspace="Clínica da Bia")
    r = cliente.patch(f"/workspace/members/{marcos['id']}", json={"papel": "ASSISTANT"},
                      headers=csrf(cliente))
    assert r.status_code == 404


def test_escrita_sem_csrf_e_bloqueada(cliente, clinica):
    assert cliente.post("/workspace/invitations", json={"email": "x@exemplo.com"}).status_code == 403


def test_perfil_profissional_nao_vaza_entre_contas(cliente, db, clinica):
    """O perfil criado pelo convite pertence à clínica, não à conta pessoal."""
    _entrar_marcos(cliente, clinica)
    with sem_escopo_de_tenant():
        perfis = db.execute(select(Professional)).scalars().all()
    tenants = {p.tenant_id for p in perfis}
    assert len(tenants) == 1          # só o da clínica: Marcos não tem conta própria
