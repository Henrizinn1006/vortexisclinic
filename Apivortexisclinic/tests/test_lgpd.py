"""
Direitos do titular.

O que está travado aqui: pedido de exclusão não vira DELETE; decisão sem
motivo não existe; anonimizar não apaga a série; apagar conteúdo não apaga
registro; e política de retenção nasce vazia — sem prazo chutado.
"""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.context import sem_escopo_de_tenant
from app.models.client import Client
from app.models.clinical import ClinicalNote
from app.models.lgpd import RetentionPolicy
from app.services.sessions import agora
from tests.conftest import cadastrar, csrf

ONTEM = (agora() - timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
TEXTO = "Sessão 4. Trabalhamos a relação com o trabalho."


@pytest.fixture
def conta(cliente):
    r = cadastrar(cliente, nome="Clara Mendes", email="clara@exemplo.com",
                  workspace="Clínica Bem Viver", profissao="terapia_integrativa")
    assert r.status_code == 201
    return r.json()


@pytest.fixture
def pessoa(cliente, conta):
    p = cliente.post("/workspace/clients",
                     json={"nome": "Ana Beatriz", "email": "ana@exemplo.com",
                           "telefone": "11999990000", "valor_sessao": "180.00"},
                     headers=csrf(cliente)).json()
    a = cliente.post("/workspace/appointments",
                     json={"cliente_id": p["id"], "inicio": ONTEM.isoformat()},
                     headers=csrf(cliente)).json()
    cliente.post(f"/workspace/appointments/{a['id']}/status",
                 json={"status": "done"}, headers=csrf(cliente))
    cliente.post(f"/workspace/appointments/{a['id']}/payment",
                 json={"metodo": "pix"}, headers=csrf(cliente))
    cliente.post(f"/workspace/clients/{p['id']}/notes",
                 json={"conteudo": TEXTO}, headers=csrf(cliente))
    return p


def abrir(cliente, pessoa, tipo="erasure"):
    return cliente.post(f"/workspace/clients/{pessoa['id']}/data-requests",
                        json={"tipo": tipo}, headers=csrf(cliente))


def decidir(cliente, pedido_id, **extra):
    corpo = {"alvo": "clinical", "decisao": "erase", "motivo": "pedido do titular"}
    corpo.update(extra)
    return cliente.post(f"/workspace/data-requests/{pedido_id}/decisions",
                        json=corpo, headers=csrf(cliente))


# ---------------- consentimento ----------------
def test_consentimento_tem_versao_e_e_revogavel(cliente, pessoa):
    r = cliente.post(f"/workspace/clients/{pessoa['id']}/consents",
                     json={"tipo": "clinical_treatment", "versao": "2026.1",
                           "texto": "Termo de consentimento para atendimento."},
                     headers=csrf(cliente))
    assert r.status_code == 201
    assert r.json()["versao"] == "2026.1"
    assert r.json()["vigente"] is True

    r2 = cliente.post(f"/workspace/consents/{r.json()['id']}/revoke", headers=csrf(cliente))
    assert r2.status_code == 200
    assert r2.json()["vigente"] is False
    assert r2.json()["revogado_em"]


def test_o_texto_do_termo_nao_fica_guardado_inteiro(cliente, db, pessoa):
    """Guardamos o sha256 — prova QUAL texto foi aceito sem virar um
    arquivo de termos dentro do banco."""
    from app.models.lgpd import Consent

    cliente.post(f"/workspace/clients/{pessoa['id']}/consents",
                 json={"tipo": "privacy", "texto": "Texto enorme do termo de privacidade."},
                 headers=csrf(cliente))
    with sem_escopo_de_tenant():
        c = db.execute(select(Consent)).scalar_one()
    assert c.text_hash and len(c.text_hash) == 64
    assert "Texto enorme" not in (c.note or "")


def test_revogar_duas_vezes_e_recusado(cliente, pessoa):
    c = cliente.post(f"/workspace/clients/{pessoa['id']}/consents",
                     json={"tipo": "image"}, headers=csrf(cliente)).json()
    cliente.post(f"/workspace/consents/{c['id']}/revoke", headers=csrf(cliente))
    r = cliente.post(f"/workspace/consents/{c['id']}/revoke", headers=csrf(cliente))
    assert r.status_code == 409


# ---------------- pedido do titular ----------------
def test_pedido_nasce_sem_prazo_chutado(cliente, pessoa):
    """O sistema não inventa prazo de resposta."""
    r = abrir(cliente, pessoa)
    assert r.status_code == 201
    assert r.json()["prazo"] is None
    assert r.json()["status"] == "open"


def test_decisao_sem_motivo_e_recusada(cliente, pessoa):
    pedido = abrir(cliente, pessoa).json()
    r = cliente.post(f"/workspace/data-requests/{pedido['id']}/decisions",
                     json={"alvo": "clinical", "decisao": "erase", "motivo": ""},
                     headers=csrf(cliente))
    assert r.status_code == 422


def test_manter_tambem_exige_motivo_e_fica_registrado(cliente, pessoa):
    """Manter prontuário contra um pedido de exclusão é legítimo — e
    precisa estar escrito antes de alguém perguntar."""
    pedido = abrir(cliente, pessoa).json()
    r = decidir(cliente, pedido["id"], alvo="payments", decisao="keep",
                motivo="obrigação fiscal", base_legal="Guarda contábil")
    assert r.status_code == 201
    item = r.json()["decisoes"][0]
    assert item["decisao"] == "keep"
    assert item["base_legal"] == "Guarda contábil"


def test_decidir_nao_executa(cliente, db, pessoa):
    """Registrar o plano e executar são passos separados — é o que permite
    alguém revisar antes de virar ação irreversível."""
    pedido = abrir(cliente, pessoa).json()
    decidir(cliente, pedido["id"])

    with sem_escopo_de_tenant():
        nota = db.execute(select(ClinicalNote)).scalar_one()
    assert nota.content_erased_at is None, "a decisão não podia ter apagado nada ainda"


def test_aplicar_apaga_o_conteudo_sem_apagar_o_registro(cliente, db, pessoa):
    pedido = abrir(cliente, pessoa).json()
    item = decidir(cliente, pedido["id"]).json()["decisoes"][0]

    r = cliente.post(f"/workspace/data-requests/{pedido['id']}/decisions/{item['id']}/apply",
                     headers=csrf(cliente))
    assert r.status_code == 200
    aplicado = r.json()["decisoes"][0]
    assert aplicado["aplicado_em"]
    assert "conteúdo destruído" in aplicado["resultado"]

    with sem_escopo_de_tenant():
        notas = db.execute(select(ClinicalNote)).scalars().all()
    assert len(notas) == 1, "a nota não podia ter sido apagada"
    assert notas[0].content_erased_at is not None
    assert notas[0].content_key_salt is None

    # E o conteúdo não abre mais.
    nota_publica = cliente.get(f"/workspace/clients/{pessoa['id']}/notes").json()[0]
    r = cliente.get(f"/workspace/notes/{nota_publica['id']}/content")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "conteudo_apagado"


def test_aplicar_duas_vezes_e_recusado(cliente, pessoa):
    pedido = abrir(cliente, pessoa).json()
    item = decidir(cliente, pedido["id"]).json()["decisoes"][0]
    cliente.post(f"/workspace/data-requests/{pedido['id']}/decisions/{item['id']}/apply",
                 headers=csrf(cliente))
    r = cliente.post(f"/workspace/data-requests/{pedido['id']}/decisions/{item['id']}/apply",
                     headers=csrf(cliente))
    assert r.status_code == 409


def test_apagar_financeiro_e_recusado_com_explicacao(cliente, pessoa):
    """Lançamento tem guarda obrigatória. A recusa é resposta, e é escrita."""
    pedido = abrir(cliente, pessoa).json()
    item = decidir(cliente, pedido["id"], alvo="payments", decisao="erase",
                   motivo="titular pediu").json()["decisoes"][0]
    r = cliente.post(f"/workspace/data-requests/{pedido['id']}/decisions/{item['id']}/apply",
                     headers=csrf(cliente))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "apagar_nao_se_aplica"


def test_encerrar_com_decisao_pendente_e_recusado(cliente, pessoa):
    pedido = abrir(cliente, pessoa).json()
    decidir(cliente, pedido["id"])
    r = cliente.post(f"/workspace/data-requests/{pedido['id']}/close",
                     json={"status": "done"}, headers=csrf(cliente))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "decisoes_pendentes"


def test_recusar_sem_explicar_nao_e_resposta(cliente, pessoa):
    pedido = abrir(cliente, pessoa).json()
    r = cliente.post(f"/workspace/data-requests/{pedido['id']}/close",
                     json={"status": "refused"}, headers=csrf(cliente))
    assert r.status_code == 422


def test_o_pedido_guarda_a_historia_inteira(cliente, pessoa):
    pedido = abrir(cliente, pessoa).json()
    item = decidir(cliente, pedido["id"]).json()["decisoes"][0]
    cliente.post(f"/workspace/data-requests/{pedido['id']}/decisions/{item['id']}/apply",
                 headers=csrf(cliente))
    decidir(cliente, pedido["id"], alvo="payments", decisao="keep",
            motivo="obrigação fiscal", base_legal="guarda contábil")
    r = cliente.post(f"/workspace/data-requests/{pedido['id']}/close",
                     json={"status": "done", "observacao": "respondido ao titular"},
                     headers=csrf(cliente))
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["status"] == "done"
    assert len(corpo["decisoes"]) == 2
    assert {d["decisao"] for d in corpo["decisoes"]} == {"erase", "keep"}


# ---------------- anonimização ----------------
def test_anonimizar_tira_o_que_identifica_e_mantem_a_serie(cliente, db, pessoa):
    r = cliente.post(f"/workspace/clients/{pessoa['id']}/anonymize",
                     json={"motivo": "pedido do titular"}, headers=csrf(cliente))
    assert r.status_code == 200
    assert r.json()["email"] is None
    assert r.json()["telefone"] is None
    assert "Ana Beatriz" not in r.json()["nome"]

    # A série continua: atendimento e pagamento não somem.
    agenda = cliente.get("/workspace/appointments").json()
    assert len(agenda) == 1
    assert float(cliente.get("/workspace/finance/summary").json()["recebido"]) == 180.0


def test_anonimizar_exige_motivo(cliente, pessoa):
    r = cliente.post(f"/workspace/clients/{pessoa['id']}/anonymize",
                     json={}, headers=csrf(cliente))
    assert r.status_code == 422


def test_anonimizar_duas_vezes_e_recusado(cliente, pessoa):
    cliente.post(f"/workspace/clients/{pessoa['id']}/anonymize",
                 json={"motivo": "pedido"}, headers=csrf(cliente))
    r = cliente.post(f"/workspace/clients/{pessoa['id']}/anonymize",
                     json={"motivo": "de novo"}, headers=csrf(cliente))
    assert r.status_code == 409


# ---------------- pacote de portabilidade ----------------
def test_pacote_traz_tudo_o_que_a_conta_tem(cliente, pessoa):
    import json

    r = cliente.get(f"/workspace/clients/{pessoa['id']}/data-package")
    assert r.status_code == 200
    dados = json.loads(r.content)
    assert dados["cadastro"]["nome"] == "Ana Beatriz"
    assert len(dados["atendimentos"]) == 1
    assert len(dados["pagamentos"]) == 1
    assert dados["registros_clinicos"][0]["conteudo"] == TEXTO
    assert dados["acessos_ao_prontuario"] >= 1


def test_pacote_diz_o_que_nao_incluiu(cliente, db, pessoa):
    """Omitir em silêncio seria responder mal a um pedido de acesso."""
    import json

    from app.ids import novo_ulid
    from app.models.membership import Membership, MembershipPermission
    from app.models.rbac import Permission

    with sem_escopo_de_tenant():
        membership = db.execute(select(Membership)).scalar_one()
        permissao = db.execute(
            select(Permission).where(Permission.key == "clinical_records.read")).scalar_one()
        db.add(MembershipPermission(
            public_id=novo_ulid(), tenant_id=membership.tenant_id,
            membership_id=membership.id, permission_id=permissao.id,
            effect="deny", reason="teste: quem gera o pacote não lê prontuário"))
        db.commit()

    dados = json.loads(cliente.get(f"/workspace/clients/{pessoa['id']}/data-package").content)
    assert dados["registros_clinicos"] is None
    assert dados["registros_clinicos_existentes"] == 1
    assert "não foram incluídos" in dados["observacao_clinica"]
    assert TEXTO not in cliente.get(
        f"/workspace/clients/{pessoa['id']}/data-package").content.decode("utf-8")


# ---------------- retenção ----------------
def test_politica_de_retencao_nasce_vazia(cliente, conta):
    """Inventar prazo daria aparência de conformidade a um chute."""
    assert cliente.get("/workspace/retention-policies").json() == []


def test_prazo_sem_base_legal_e_recusado(cliente, conta):
    r = cliente.put("/workspace/retention-policies",
                    json={"alvo": "clinical", "meses": 240}, headers=csrf(cliente))
    assert r.status_code == 422
    assert "base legal" in r.json()["detail"]["message"].lower()


def test_politica_com_base_legal_vale(cliente, conta):
    r = cliente.put("/workspace/retention-policies",
                    json={"alvo": "clinical", "meses": 240,
                          "base_legal": "Resolução do conselho profissional"},
                    headers=csrf(cliente))
    assert r.status_code == 200
    assert r.json()["aplicavel"] is True


def test_politica_sem_prazo_nao_e_aplicavel(cliente, conta):
    r = cliente.put("/workspace/retention-policies",
                    json={"alvo": "documents", "observacao": "a definir com o contador"},
                    headers=csrf(cliente))
    assert r.status_code == 200
    assert r.json()["meses"] is None
    assert r.json()["aplicavel"] is False


def test_politica_nao_vaza_entre_contas(cliente, db, conta):
    cliente.put("/workspace/retention-policies",
                json={"alvo": "clinical", "meses": 240, "base_legal": "conselho"},
                headers=csrf(cliente))
    cliente.cookies.clear()
    cadastrar(cliente, nome="Bia Outra", email="bia@exemplo.com", workspace="Clínica da Bia")
    assert cliente.get("/workspace/retention-policies").json() == []


# ---------------- auditoria ----------------
def test_trilha_de_seguranca_mostra_os_atos(cliente, pessoa):
    linhas = cliente.get("/workspace/audit").json()
    assert linhas
    acoes = {l["acao"] for l in linhas}
    assert "register" in acoes
    assert all(TEXTO not in (l.get("detalhe") or "") for l in linhas), \
        "a trilha de segurança não carrega conteúdo"


def test_trilha_exige_permissao_de_auditoria(cliente, db, pessoa):
    from app.ids import novo_ulid
    from app.models.membership import Membership, MembershipPermission
    from app.models.rbac import Permission

    with sem_escopo_de_tenant():
        membership = db.execute(select(Membership)).scalar_one()
        permissao = db.execute(
            select(Permission).where(Permission.key == "audit.read")).scalar_one()
        db.add(MembershipPermission(
            public_id=novo_ulid(), tenant_id=membership.tenant_id,
            membership_id=membership.id, permission_id=permissao.id,
            effect="deny", reason="teste"))
        db.commit()
    assert cliente.get("/workspace/audit").status_code == 403


def test_trilha_nao_vaza_entre_contas(cliente, pessoa):
    cliente.cookies.clear()
    cadastrar(cliente, nome="Bia Outra", email="bia2@exemplo.com", workspace="Clínica da Bia 2")
    linhas = cliente.get("/workspace/audit").json()
    assert all("clara@exemplo.com" not in str(l) for l in linhas)


# ---------------- isolamento ----------------
def test_pedido_de_outra_conta_nao_existe(cliente, pessoa):
    pedido = abrir(cliente, pessoa).json()
    cliente.cookies.clear()
    cadastrar(cliente, nome="Bia Outra", email="bia3@exemplo.com", workspace="Clínica da Bia 3")
    assert cliente.get(f"/workspace/data-requests/{pedido['id']}").status_code == 404
    assert cliente.get("/workspace/data-requests").json() == []
