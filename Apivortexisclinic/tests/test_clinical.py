"""
Prontuário: cifra, versões que não se apagam, e quem pode abrir o quê.

Os testes daqui existem para travar as regras que, se cederem um dia,
cedem em silêncio: administrar a conta não abre prontuário; nota de
colega não é sua; correção não sobrescreve; e toda tentativa — inclusive
a recusada — fica registrada.
"""
from datetime import timedelta

import pytest
from sqlalchemy import select, text

from app.db.context import sem_escopo_de_tenant
from app.ids import novo_ulid
from app.models.clinical import ClinicalAccessLog, ClinicalNote, ClinicalNoteVersion
from app.models.membership import Membership, MembershipPermission
from app.models.professional import Professional
from app.models.rbac import Permission, Role
from app.models.tenant import Tenant
from app.models.user import User
from app.security import crypto
from app.services.sessions import agora
from tests.conftest import cadastrar, csrf, entrar

TEXTO = "Sessão 12. Paciente relatou melhora do sono. Manteve o plano combinado."
ONTEM = (agora() - timedelta(days=1)).replace(hour=15, minute=0, second=0, microsecond=0)


# ---------------- cenário ----------------
@pytest.fixture
def clinica(cliente, db):
    """Clara (dona, atende, escopo 'all') e Marcos (profissional, escopo 'own')."""
    r = cadastrar(cliente, nome="Clara Mendes", email="clara@exemplo.com",
                  workspace="Clínica Bem Viver", profissao="terapia_integrativa")
    assert r.status_code == 201
    tenant_publico = r.json()["workspace_ativo"]["id"]
    cookies_clara = dict(cliente.cookies)

    cliente.cookies.clear()
    cadastrar(cliente, nome="Marcos Prof", email="marcos@exemplo.com",
              workspace="Consultório Marcos", profissao="terapia_integrativa")
    cliente.cookies.clear()

    with sem_escopo_de_tenant():
        tenant = db.execute(select(Tenant).where(Tenant.public_id == tenant_publico)).scalar_one()
        marcos = db.execute(select(User).where(User.email == "marcos@exemplo.com")).scalar_one()
        papel = db.execute(select(Role).where(Role.key == "PROFESSIONAL")).scalar_one()

        vinculo = Membership(public_id=novo_ulid(), tenant_id=tenant.id, user_id=marcos.id,
                             role_id=papel.id, data_scope="own", status="active")
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
                 "membership_marcos": vinculo.id, "perfil_marcos": perfil.id}

    cliente.cookies.clear()
    for k, v in cookies_clara.items():
        cliente.cookies.set(k, v)
    return dados


@pytest.fixture
def pessoa(cliente, clinica):
    """Uma pessoa atendida, cadastrada pela Clara."""
    return cliente.post("/workspace/clients", json={"nome": "Ana Beatriz"},
                        headers=csrf(cliente)).json()


def como_marcos(cliente, clinica):
    cliente.cookies.clear()
    entrar(cliente, "marcos@exemplo.com")
    r = cliente.post("/session/workspace", json={"workspace_id": clinica["tenant_publico"]},
                     headers=csrf(cliente))
    assert r.status_code == 200
    return r


def como_clara(cliente):
    cliente.cookies.clear()
    entrar(cliente, "clara@exemplo.com")


def vincular(db, clinica, pessoa, professional_id):
    with sem_escopo_de_tenant():
        db.execute(text(
            "INSERT INTO client_professionals (tenant_id, client_id, professional_id, "
            "is_primary, created_at, updated_at) "
            "SELECT :t, c.id, :p, 1, NOW(3), NOW(3) FROM clients c WHERE c.public_id = :pid"
        ), {"t": clinica["tenant_id"], "p": professional_id, "pid": pessoa["id"]})
        db.commit()


def criar_nota(cliente, pessoa, texto=TEXTO, **extra):
    corpo = {"conteudo": texto, "ocorrido_em": ONTEM.isoformat()}
    corpo.update(extra)
    return cliente.post(f"/workspace/clients/{pessoa['id']}/notes", json=corpo,
                        headers=csrf(cliente))


# ---------------- o básico ----------------
def test_criar_e_ler_de_volta(cliente, pessoa):
    r = criar_nota(cliente, pessoa)
    assert r.status_code == 201, r.text
    nota = r.json()
    assert nota["versao_atual"] == 1
    assert nota["status"] == "draft"
    assert nota["sou_o_autor"] is True

    conteudo = cliente.get(f"/workspace/notes/{nota['id']}/content").json()
    assert conteudo["conteudo"] == TEXTO
    assert conteudo["versao"] == 1


def test_a_lista_nao_carrega_conteudo(cliente, pessoa):
    criar_nota(cliente, pessoa)
    corpo = cliente.get(f"/workspace/clients/{pessoa['id']}/notes").text
    assert TEXTO not in corpo          # listar é metadado, não leitura


def test_conteudo_nao_fica_em_texto_puro_no_banco(cliente, db, pessoa):
    criar_nota(cliente, pessoa)
    with sem_escopo_de_tenant():
        linhas = db.execute(text("SELECT ciphertext FROM clinical_note_versions")).all()
    assert linhas
    for (bruto,) in linhas:
        assert TEXTO.encode("utf-8") not in bytes(bruto)
        assert b"sono" not in bytes(bruto)


def test_resposta_de_conteudo_nao_e_cacheavel(cliente, pessoa):
    nota = criar_nota(cliente, pessoa).json()
    r = cliente.get(f"/workspace/notes/{nota['id']}/content")
    assert "no-store" in r.headers.get("cache-control", "")


def test_conteudo_vazio_e_recusado(cliente, pessoa):
    r = criar_nota(cliente, pessoa, texto="    ")
    assert r.status_code == 422


def test_data_no_futuro_e_recusada(cliente, pessoa):
    amanha = (agora() + timedelta(days=1)).isoformat()
    r = cliente.post(f"/workspace/clients/{pessoa['id']}/notes",
                     json={"conteudo": TEXTO, "ocorrido_em": amanha}, headers=csrf(cliente))
    assert r.status_code == 422


# ---------------- versão não se apaga ----------------
def test_editar_cria_versao_e_preserva_a_anterior(cliente, pessoa):
    nota = criar_nota(cliente, pessoa).json()
    novo = TEXTO + " Ajuste: reavaliar em duas semanas."

    r = cliente.put(f"/workspace/notes/{nota['id']}", json={"conteudo": novo},
                    headers=csrf(cliente))
    assert r.status_code == 200
    assert r.json()["versao_atual"] == 2

    atual = cliente.get(f"/workspace/notes/{nota['id']}/content").json()
    assert atual["conteudo"] == novo

    # A versão 1 continua lá, e continua legível: histórico não se rasura.
    antiga = cliente.get(f"/workspace/notes/{nota['id']}/content?versao=1").json()
    assert antiga["conteudo"] == TEXTO

    versoes = cliente.get(f"/workspace/notes/{nota['id']}/versions").json()
    assert [v["versao"] for v in versoes] == [1, 2]


def test_a_linha_da_versao_antiga_nao_muda(cliente, db, pessoa):
    """Append-only de verdade: a linha da v1 fica byte a byte como nasceu."""
    nota = criar_nota(cliente, pessoa).json()
    with sem_escopo_de_tenant():
        antes = db.execute(text(
            "SELECT content_hash, ciphertext, nonce FROM clinical_note_versions "
            "WHERE version = 1")).one()

    cliente.put(f"/workspace/notes/{nota['id']}", json={"conteudo": TEXTO + " mudou"},
                headers=csrf(cliente))

    with sem_escopo_de_tenant():
        depois = db.execute(text(
            "SELECT content_hash, ciphertext, nonce FROM clinical_note_versions "
            "WHERE version = 1")).one()
    assert bytes(antes[1]) == bytes(depois[1])
    assert antes[0] == depois[0]


def test_salvar_sem_mudar_nao_cria_versao(cliente, pessoa):
    nota = criar_nota(cliente, pessoa).json()
    r = cliente.put(f"/workspace/notes/{nota['id']}", json={"conteudo": TEXTO},
                    headers=csrf(cliente))
    assert r.json()["versao_atual"] == 1


# ---------------- assinatura ----------------
def test_assinar_fecha_a_nota(cliente, pessoa):
    nota = criar_nota(cliente, pessoa).json()
    r = cliente.post(f"/workspace/notes/{nota['id']}/sign", headers=csrf(cliente))
    assert r.status_code == 200
    assert r.json()["status"] == "signed"
    assert r.json()["assinada_em"]


def test_assinada_so_aceita_adendo_com_motivo(cliente, pessoa):
    nota = criar_nota(cliente, pessoa).json()
    cliente.post(f"/workspace/notes/{nota['id']}/sign", headers=csrf(cliente))

    sem_motivo = cliente.put(f"/workspace/notes/{nota['id']}",
                             json={"conteudo": TEXTO + " correção"}, headers=csrf(cliente))
    assert sem_motivo.status_code == 422

    com_motivo = cliente.put(f"/workspace/notes/{nota['id']}",
                             json={"conteudo": TEXTO + " correção",
                                   "motivo": "erro de digitação na data"},
                             headers=csrf(cliente))
    assert com_motivo.status_code == 200
    assert com_motivo.json()["versao_atual"] == 2
    assert com_motivo.json()["status"] == "signed"    # adendo não reabre a nota

    versoes = cliente.get(f"/workspace/notes/{nota['id']}/versions").json()
    assert versoes[1]["motivo"] == "erro de digitação na data"


def test_assinar_duas_vezes_e_recusado(cliente, pessoa):
    nota = criar_nota(cliente, pessoa).json()
    cliente.post(f"/workspace/notes/{nota['id']}/sign", headers=csrf(cliente))
    r = cliente.post(f"/workspace/notes/{nota['id']}/sign", headers=csrf(cliente))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ja_assinada"


# ---------------- quem pode ----------------
def test_quem_administra_a_conta_e_nao_atende_nao_entra(cliente, pessoa):
    """Conta aberta SEM profissão: administra tudo, não abre prontuário."""
    cliente.cookies.clear()
    r = cadastrar(cliente, nome="Gestor Só", email="gestor@exemplo.com",
                  workspace="Clínica do Gestor")
    assert r.status_code == 201
    alguem = cliente.post("/workspace/clients", json={"nome": "Fulano"},
                          headers=csrf(cliente)).json()

    assert cliente.get(f"/workspace/clients/{alguem['id']}/notes").status_code == 403
    r = cliente.post(f"/workspace/clients/{alguem['id']}/notes",
                     json={"conteudo": TEXTO}, headers=csrf(cliente))
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "sem_permissao"


def test_o_titular_que_atende_entra_por_concessao_explicita(cliente, db, clinica):
    """Clara lê prontuário — e a razão está registrada, não embutida no papel."""
    with sem_escopo_de_tenant():
        linhas = db.execute(
            select(Permission.key, MembershipPermission.reason, MembershipPermission.effect)
            .join(MembershipPermission, MembershipPermission.permission_id == Permission.id)
            .join(Membership, Membership.id == MembershipPermission.membership_id)
            .join(User, User.id == Membership.user_id)
            .where(User.email == "clara@exemplo.com")
        ).all()
    concedidas = {chave for chave, _m, efeito in linhas if efeito == "grant"}
    assert "clinical_records.write" in concedidas
    assert "clinical_records.read_others" not in concedidas     # nem para a dona
    assert all(motivo for _k, motivo, _e in linhas)             # concessão sem motivo não existe


def test_nota_de_colega_nao_aparece_para_quem_enxerga_a_conta_toda(cliente, db, clinica, pessoa):
    """Escopo 'all' é alcance administrativo. Não vira leitura de prontuário alheio."""
    vincular(db, clinica, pessoa, clinica["perfil_marcos"])
    como_marcos(cliente, clinica)
    nota = criar_nota(cliente, pessoa).json()

    como_clara(cliente)
    assert cliente.get(f"/workspace/clients/{pessoa['id']}/notes").json() == []
    r = cliente.get(f"/workspace/notes/{nota['id']}")
    assert r.status_code == 404                                  # não existe, não "é de outro"
    assert cliente.get(f"/workspace/notes/{nota['id']}/content").status_code == 404


def test_com_read_others_a_nota_do_colega_abre(cliente, db, clinica, pessoa):
    vincular(db, clinica, pessoa, clinica["perfil_marcos"])
    como_marcos(cliente, clinica)
    nota = criar_nota(cliente, pessoa).json()

    with sem_escopo_de_tenant():
        clara = db.execute(select(Membership).join(User, User.id == Membership.user_id)
                           .where(User.email == "clara@exemplo.com",
                                  Membership.tenant_id == clinica["tenant_id"])).scalar_one()
        permissao = db.execute(select(Permission)
                               .where(Permission.key == "clinical_records.read_others")).scalar_one()
        db.add(MembershipPermission(
            public_id=novo_ulid(), tenant_id=clinica["tenant_id"], membership_id=clara.id,
            permission_id=permissao.id, effect="grant",
            reason="supervisão clínica combinada com a equipe",
            expires_at=agora() + timedelta(days=30)))
        db.commit()

    como_clara(cliente)
    assert cliente.get(f"/workspace/notes/{nota['id']}").status_code == 200
    assert cliente.get(f"/workspace/notes/{nota['id']}/content").json()["conteudo"] == TEXTO


def test_ler_o_do_colega_nao_e_poder_escrever_nele(cliente, db, clinica, pessoa):
    vincular(db, clinica, pessoa, clinica["perfil_marcos"])
    como_marcos(cliente, clinica)
    nota = criar_nota(cliente, pessoa).json()

    with sem_escopo_de_tenant():
        clara = db.execute(select(Membership).join(User, User.id == Membership.user_id)
                           .where(User.email == "clara@exemplo.com",
                                  Membership.tenant_id == clinica["tenant_id"])).scalar_one()
        permissao = db.execute(select(Permission)
                               .where(Permission.key == "clinical_records.read_others")).scalar_one()
        db.add(MembershipPermission(
            public_id=novo_ulid(), tenant_id=clinica["tenant_id"], membership_id=clara.id,
            permission_id=permissao.id, effect="grant", reason="supervisão"))
        db.commit()

    como_clara(cliente)
    r = cliente.put(f"/workspace/notes/{nota['id']}", json={"conteudo": "reescrevendo"},
                    headers=csrf(cliente))
    assert r.status_code == 403
    assert cliente.post(f"/workspace/notes/{nota['id']}/sign",
                        headers=csrf(cliente)).status_code == 403


def test_profissional_sem_vinculo_com_a_pessoa_nao_alcanca(cliente, db, clinica, pessoa):
    """Marcos não atende Ana: para ele, o prontuário dela não existe."""
    como_marcos(cliente, clinica)
    assert cliente.get(f"/workspace/clients/{pessoa['id']}/notes").status_code == 404
    r = criar_nota(cliente, pessoa)
    assert r.status_code == 404


def test_escrita_sem_csrf_e_bloqueada(cliente, pessoa):
    r = cliente.post(f"/workspace/clients/{pessoa['id']}/notes", json={"conteudo": TEXTO})
    assert r.status_code == 403


# ---------------- isolamento entre contas ----------------
def test_nota_de_outra_conta_nao_existe(cliente, pessoa):
    nota = criar_nota(cliente, pessoa).json()

    cliente.cookies.clear()
    cadastrar(cliente, nome="Bia Outra", email="bia@exemplo.com",
              workspace="Clínica da Bia", profissao="terapia_integrativa")

    assert cliente.get(f"/workspace/notes/{nota['id']}").status_code == 404
    assert cliente.get(f"/workspace/notes/{nota['id']}/content").status_code == 404
    r = cliente.put(f"/workspace/notes/{nota['id']}", json={"conteudo": "invadindo"},
                    headers=csrf(cliente))
    assert r.status_code == 404


# ---------------- a cifra amarra o lugar ----------------
def test_ciphertext_movido_para_outra_nota_nao_abre(cliente, db, pessoa):
    """O AAD carrega a nota. Trocar a linha de lugar quebra a decifragem."""
    primeira = criar_nota(cliente, pessoa, texto=TEXTO).json()
    segunda = criar_nota(cliente, pessoa, texto="Outro registro, outra nota.").json()

    with sem_escopo_de_tenant():
        db.execute(text("""
            UPDATE clinical_note_versions destino
              JOIN clinical_notes n2 ON n2.public_id = :b
              JOIN clinical_notes n1 ON n1.public_id = :a
              JOIN clinical_note_versions origem
                   ON origem.note_id = n1.id AND origem.version = 1
               SET destino.ciphertext = origem.ciphertext,
                   destino.nonce = origem.nonce
             WHERE destino.note_id = n2.id AND destino.version = 1
        """), {"a": primeira["id"], "b": segunda["id"]})
        db.commit()

    r = cliente.get(f"/workspace/notes/{segunda['id']}/content")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "conteudo_ilegivel"


def test_ciphertext_adulterado_nao_abre(cliente, db, pessoa):
    nota = criar_nota(cliente, pessoa).json()
    with sem_escopo_de_tenant():
        db.execute(text(
            "UPDATE clinical_note_versions SET ciphertext = CONCAT(ciphertext, 0x00)"))
        db.commit()
    r = cliente.get(f"/workspace/notes/{nota['id']}/content")
    assert r.status_code == 409


def test_chave_de_um_tenant_nao_abre_o_do_outro():
    """Prova direta da amarração: mesmo sal, mesma chave mestra, tenants diferentes."""
    sal = crypto.novo_sal()
    cifrado, nonce, versao = crypto.cifrar("segredo clínico", sal=sal, tenant_id=1,
                                           nota_id=7, versao=1)
    assert crypto.decifrar(cifrado, nonce=nonce, sal=sal, versao_chave=versao,
                           tenant_id=1, nota_id=7, versao=1) == "segredo clínico"

    with pytest.raises(crypto.ConteudoIlegivel):
        crypto.decifrar(cifrado, nonce=nonce, sal=sal, versao_chave=versao,
                        tenant_id=2, nota_id=7, versao=1)


def test_sal_diferente_nao_abre():
    sal = crypto.novo_sal()
    cifrado, nonce, versao = crypto.cifrar("texto", sal=sal, tenant_id=1, nota_id=1, versao=1)
    with pytest.raises(crypto.ConteudoIlegivel):
        crypto.decifrar(cifrado, nonce=nonce, sal=crypto.novo_sal(), versao_chave=versao,
                        tenant_id=1, nota_id=1, versao=1)


def test_versao_de_chave_ausente_nao_abre():
    sal = crypto.novo_sal()
    cifrado, nonce, _v = crypto.cifrar("texto", sal=sal, tenant_id=1, nota_id=1, versao=1)
    with pytest.raises(crypto.ConteudoIlegivel):
        crypto.decifrar(cifrado, nonce=nonce, sal=sal, versao_chave=99,
                        tenant_id=1, nota_id=1, versao=1)


# ---------------- trilha de acesso ----------------
def test_leitura_entra_na_trilha(cliente, db, pessoa):
    nota = criar_nota(cliente, pessoa).json()
    cliente.get(f"/workspace/notes/{nota['id']}/content")

    with sem_escopo_de_tenant():
        acoes = [l.action for l in db.execute(
            select(ClinicalAccessLog).order_by(ClinicalAccessLog.id)).scalars()]
    assert "create" in acoes
    assert "read" in acoes


def test_a_tentativa_recusada_tambem_fica_registrada(cliente, db, clinica, pessoa):
    """É a negativa que interessa: sem ela ninguém descobre quem tentou."""
    vincular(db, clinica, pessoa, clinica["perfil_marcos"])
    como_marcos(cliente, clinica)
    nota = criar_nota(cliente, pessoa).json()

    como_clara(cliente)
    assert cliente.get(f"/workspace/notes/{nota['id']}/content").status_code == 404

    with sem_escopo_de_tenant():
        negadas = db.execute(
            select(ClinicalAccessLog).where(ClinicalAccessLog.outcome == "denied")
        ).scalars().all()
    assert negadas, "a recusa precisa sobreviver ao rollback da requisição"
    assert negadas[-1].reason == "fora_do_alcance"


def test_auditoria_mostra_quem_olhou_sem_mostrar_o_que(cliente, db, clinica, pessoa):
    """Clara audita a trilha de uma nota que ela não pode ler."""
    vincular(db, clinica, pessoa, clinica["perfil_marcos"])
    como_marcos(cliente, clinica)
    nota = criar_nota(cliente, pessoa).json()
    cliente.get(f"/workspace/notes/{nota['id']}/content")

    como_clara(cliente)
    r = cliente.get(f"/workspace/clients/{pessoa['id']}/clinical-access")
    assert r.status_code == 200
    corpo = r.text
    assert "Marcos Prof" in corpo
    assert TEXTO not in corpo                       # trilha nunca carrega conteúdo
    assert cliente.get(f"/workspace/notes/{nota['id']}/content").status_code == 404


def test_trilha_exige_permissao_de_auditoria(cliente, clinica, pessoa, db):
    vincular(db, clinica, pessoa, clinica["perfil_marcos"])
    como_marcos(cliente, clinica)      # PROFESSIONAL não tem audit.read
    r = cliente.get(f"/workspace/clients/{pessoa['id']}/clinical-access")
    assert r.status_code == 403


# ---------------- exclusão a pedido do titular ----------------
def test_apagar_conteudo_preserva_ficha_e_trilha(cliente, db, pessoa):
    """Descarta o sal: o texto morre, o registro de que houve atendimento não."""
    from app.api.deps import Contexto
    from app.services import clinical as servico

    nota_json = criar_nota(cliente, pessoa).json()
    cliente.get(f"/workspace/notes/{nota_json['id']}/content")

    with sem_escopo_de_tenant():
        nota = db.execute(select(ClinicalNote)
                          .where(ClinicalNote.public_id == nota_json["id"])).scalar_one()
        versoes_antes = db.execute(
            select(ClinicalNoteVersion).where(ClinicalNoteVersion.note_id == nota.id)
        ).scalars().all()
        assert versoes_antes

        usuario = db.execute(select(User).where(User.email == "clara@exemplo.com")).scalar_one()
        membership = db.execute(select(Membership)
                                .where(Membership.user_id == usuario.id)).scalars().first()
        ctx = Contexto(db=db, usuario=usuario, sessao=None, membership=membership,
                       permissoes=set(), professional_id=None)
        servico.esquecer_conteudo(db, ctx, nota, "pedido de exclusão do titular")
        db.commit()

        # As versões continuam na tabela: nenhuma linha foi apagada.
        assert len(db.execute(
            select(ClinicalNoteVersion).where(ClinicalNoteVersion.note_id == nota.id)
        ).scalars().all()) == len(versoes_antes)

    como_clara(cliente)
    ficha = cliente.get(f"/workspace/notes/{nota_json['id']}")
    assert ficha.status_code == 200
    assert ficha.json()["conteudo_apagado_em"]

    r = cliente.get(f"/workspace/notes/{nota_json['id']}/content")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "conteudo_apagado"


def test_apagar_conteudo_exige_motivo(cliente, db, pessoa):
    from app.api.deps import Contexto
    from app import errors
    from app.services import clinical as servico

    nota_json = criar_nota(cliente, pessoa).json()
    with sem_escopo_de_tenant():
        nota = db.execute(select(ClinicalNote)
                          .where(ClinicalNote.public_id == nota_json["id"])).scalar_one()
        usuario = db.execute(select(User).where(User.email == "clara@exemplo.com")).scalar_one()
        membership = db.execute(select(Membership)
                                .where(Membership.user_id == usuario.id)).scalars().first()
        ctx = Contexto(db=db, usuario=usuario, sessao=None, membership=membership,
                       permissoes=set(), professional_id=None)
        with pytest.raises(errors.ApiError):
            servico.esquecer_conteudo(db, ctx, nota, "   ")


# ---------------- chaves e rotação ----------------
def test_rotacao_de_chave_nao_quebra_o_acervo():
    """Escrever com a chave nova; o que foi escrito com a antiga continua abrindo."""
    import base64
    import os

    from app.config import settings

    antiga = base64.urlsafe_b64encode(os.urandom(32)).decode()
    nova = base64.urlsafe_b64encode(os.urandom(32)).decode()
    originais = (settings.VC_CLINICAL_KEYS, settings.VC_CLINICAL_KEY_VERSION)
    try:
        settings.VC_CLINICAL_KEYS = f"1:{antiga}"
        settings.VC_CLINICAL_KEY_VERSION = 1
        crypto.recarregar()

        sal = crypto.novo_sal()
        velho, nonce_velho, v1 = crypto.cifrar("escrito antes da rotação", sal=sal,
                                               tenant_id=1, nota_id=1, versao=1)
        assert v1 == 1

        # Rotaciona: a versão 2 passa a escrever, a 1 continua na lista.
        settings.VC_CLINICAL_KEYS = f"1:{antiga},2:{nova}"
        settings.VC_CLINICAL_KEY_VERSION = 2
        crypto.recarregar()

        novo, nonce_novo, v2 = crypto.cifrar("escrito depois", sal=sal,
                                             tenant_id=1, nota_id=1, versao=2)
        assert v2 == 2
        assert crypto.decifrar(velho, nonce=nonce_velho, sal=sal, versao_chave=1,
                               tenant_id=1, nota_id=1, versao=1) == "escrito antes da rotação"
        assert crypto.decifrar(novo, nonce=nonce_novo, sal=sal, versao_chave=2,
                               tenant_id=1, nota_id=1, versao=2) == "escrito depois"
    finally:
        settings.VC_CLINICAL_KEYS, settings.VC_CLINICAL_KEY_VERSION = originais
        crypto.recarregar()


def test_producao_nao_sobe_sem_chave_clinica():
    """Sem chave, o prontuário seria gravado com a chave que está no código."""
    from app.config import Settings

    producao = Settings(VC_ENV="production", VC_COOKIE_SECURE=True,
                        VC_DB_PASSWORD="x", VC_CLINICAL_KEYS="")
    with pytest.raises(RuntimeError) as falha:
        producao.validar_producao()
    assert "VC_CLINICAL_KEYS" in str(falha.value)
