"""
Documentos e exportação.

O que está travado aqui: recibo é administrativo e declaração é clínica —
e isso muda quem consegue abrir; declaração não vaza conteúdo de sessão;
arquivo não fica legível no disco; e exportar prontuário não é atalho para
ler o que não podia.
"""
import base64
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.context import sem_escopo_de_tenant
from app.models.document import Document
from app.services.sessions import agora
from tests.conftest import cadastrar, csrf, entrar

ONTEM = (agora() - timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
TEXTO_CLINICO = "Sessão 3. Trabalhamos o episódio do trabalho. Sono melhorou."


@pytest.fixture
def conta(cliente):
    r = cadastrar(cliente, nome="Clara Mendes", email="clara@exemplo.com",
                  workspace="Clínica Bem Viver", profissao="terapia_integrativa")
    assert r.status_code == 201
    return r.json()


@pytest.fixture
def pessoa(cliente, conta):
    return cliente.post("/workspace/clients",
                        json={"nome": "Ana Beatriz", "valor_sessao": "180.00"},
                        headers=csrf(cliente)).json()


@pytest.fixture
def realizado(cliente, pessoa):
    a = cliente.post("/workspace/appointments",
                     json={"cliente_id": pessoa["id"], "inicio": ONTEM.isoformat()},
                     headers=csrf(cliente)).json()
    cliente.post(f"/workspace/appointments/{a['id']}/status",
                 json={"status": "done"}, headers=csrf(cliente))
    return a


def pagar(cliente, atendimento):
    return cliente.post(f"/workspace/appointments/{atendimento['id']}/payment",
                        json={"metodo": "pix"}, headers=csrf(cliente))


# ---------------- recibo ----------------
def test_recibo_sai_do_que_foi_recebido(cliente, pessoa, realizado):
    pagar(cliente, realizado)
    r = cliente.post(f"/workspace/clients/{pessoa['id']}/documents/receipt",
                     json={}, headers=csrf(cliente))
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["tipo"] == "receipt"
    assert doc["classe"] == "administrative"
    assert doc["tamanho"] > 500


def test_recibo_sem_pagamento_e_recusado(cliente, pessoa, realizado):
    r = cliente.post(f"/workspace/clients/{pessoa['id']}/documents/receipt",
                     json={}, headers=csrf(cliente))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "sem_pagamentos"


def test_recibo_e_um_pdf_de_verdade(cliente, pessoa, realizado):
    pagar(cliente, realizado)
    doc = cliente.post(f"/workspace/clients/{pessoa['id']}/documents/receipt",
                       json={}, headers=csrf(cliente)).json()
    r = cliente.get(f"/workspace/documents/{doc['id']}/content")
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-")
    assert r.content.rstrip().endswith(b"%%EOF")
    assert "attachment" in r.headers["content-disposition"]
    assert "no-store" in r.headers.get("cache-control", "")


def test_o_texto_do_recibo_bate_com_o_pagamento(cliente, pessoa, realizado):
    pagar(cliente, realizado)
    doc = cliente.post(f"/workspace/clients/{pessoa['id']}/documents/receipt",
                       json={}, headers=csrf(cliente)).json()
    conteudo = cliente.get(f"/workspace/documents/{doc['id']}/content").content
    from pdfminer.high_level import extract_text
    import io

    texto = extract_text(io.BytesIO(conteudo))
    assert "Ana Beatriz" in texto
    assert "180,00" in texto


# ---------------- declaração ----------------
def test_declaracao_diz_que_esteve_sem_dizer_o_que_houve(cliente, pessoa, realizado):
    """Declaração que vaza conteúdo é a forma mais comum de vazar prontuário."""
    cliente.post(f"/workspace/clients/{pessoa['id']}/notes",
                 json={"conteudo": TEXTO_CLINICO}, headers=csrf(cliente))

    r = cliente.post(f"/workspace/clients/{pessoa['id']}/documents/attendance",
                     json={"atendimento_id": realizado["id"]}, headers=csrf(cliente))
    assert r.status_code == 201
    assert r.json()["classe"] == "clinical"

    conteudo = cliente.get(f"/workspace/documents/{r.json()['id']}/content").content
    from pdfminer.high_level import extract_text
    import io

    texto = extract_text(io.BytesIO(conteudo))
    assert "compareceu" in texto
    assert "Ana Beatriz" in texto
    assert "sigilo" in texto
    assert "sono" not in texto.lower(), "declaração não pode carregar conteúdo de sessão"


def test_declaracao_exige_atendimento_realizado(cliente, pessoa):
    futuro = (agora() + timedelta(days=2)).isoformat()
    a = cliente.post("/workspace/appointments",
                     json={"cliente_id": pessoa["id"], "inicio": futuro},
                     headers=csrf(cliente)).json()
    r = cliente.post(f"/workspace/clients/{pessoa['id']}/documents/attendance",
                     json={"atendimento_id": a["id"]}, headers=csrf(cliente))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "atendimento_nao_realizado"


# ---------------- o arquivo no disco ----------------
def test_arquivo_nao_fica_legivel_no_disco(cliente, db, pessoa, realizado):
    import pathlib

    from app.config import settings

    pagar(cliente, realizado)
    cliente.post(f"/workspace/clients/{pessoa['id']}/documents/receipt",
                 json={}, headers=csrf(cliente))

    with sem_escopo_de_tenant():
        doc = db.execute(select(Document)).scalar_one()
    caminho = pathlib.Path(settings.VC_FILES_DIR) / doc.storage_key
    assert caminho.exists()
    bruto = caminho.read_bytes()
    assert not bruto.startswith(b"%PDF-"), "o PDF foi para o disco em claro"
    assert b"Ana Beatriz" not in bruto


def test_arquivo_adulterado_nao_abre(cliente, db, pessoa, realizado):
    import pathlib

    from app.config import settings

    pagar(cliente, realizado)
    doc_json = cliente.post(f"/workspace/clients/{pessoa['id']}/documents/receipt",
                            json={}, headers=csrf(cliente)).json()
    with sem_escopo_de_tenant():
        doc = db.execute(select(Document)).scalar_one()
    caminho = pathlib.Path(settings.VC_FILES_DIR) / doc.storage_key
    caminho.write_bytes(caminho.read_bytes() + b"\x00")

    r = cliente.get(f"/workspace/documents/{doc_json['id']}/content")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "conteudo_ilegivel"


# ---------------- anexo ----------------
def test_anexo_entra_como_clinico(cliente, pessoa):
    r = cliente.post(f"/workspace/clients/{pessoa['id']}/documents",
                     json={"nome_arquivo": "exame.txt",
                           "conteudo_base64": base64.b64encode(b"resultado").decode(),
                           "mime": "text/plain"},
                     headers=csrf(cliente))
    assert r.status_code == 201
    assert r.json()["classe"] == "clinical"
    assert r.json()["tipo"] == "upload"


def test_nome_de_arquivo_e_saneado(cliente, pessoa):
    """Nome vem de fora e volta em cabeçalho HTTP — não pode levar caminho."""
    r = cliente.post(f"/workspace/clients/{pessoa['id']}/documents",
                     json={"nome_arquivo": "../../etc/pa\"sswd",
                           "conteudo_base64": base64.b64encode(b"x").decode()},
                     headers=csrf(cliente))
    assert r.status_code == 201
    nome = r.json()["nome_arquivo"]
    assert "/" not in nome and "\\" not in nome and '"' not in nome


def test_anexo_grande_e_recusado(cliente, pessoa):
    from app.config import settings

    grande = base64.b64encode(b"x" * (settings.VC_MAX_UPLOAD_MB * 1024 * 1024 + 10)).decode()
    r = cliente.post(f"/workspace/clients/{pessoa['id']}/documents",
                     json={"nome_arquivo": "grande.bin", "conteudo_base64": grande},
                     headers=csrf(cliente))
    assert r.status_code == 422


def test_base64_invalido_e_recusado(cliente, pessoa):
    r = cliente.post(f"/workspace/clients/{pessoa['id']}/documents",
                     json={"nome_arquivo": "x.bin", "conteudo_base64": "não é base64!!"},
                     headers=csrf(cliente))
    assert r.status_code == 422


# ---------------- exportar prontuário ----------------
def test_exportar_prontuario_gera_pdf_com_o_conteudo(cliente, pessoa):
    cliente.post(f"/workspace/clients/{pessoa['id']}/notes",
                 json={"conteudo": TEXTO_CLINICO}, headers=csrf(cliente))
    r = cliente.post(f"/workspace/clients/{pessoa['id']}/documents/record",
                     headers=csrf(cliente))
    assert r.status_code == 201
    assert r.json()["tipo"] == "record_copy"

    conteudo = cliente.get(f"/workspace/documents/{r.json()['id']}/content").content
    from pdfminer.high_level import extract_text
    import io

    texto = extract_text(io.BytesIO(conteudo))
    assert "Sono melhorou" in texto or "sono melhorou" in texto.lower()


def test_exportar_prontuario_entra_na_trilha(cliente, db, pessoa):
    from app.models.clinical import ClinicalAccessLog

    cliente.post(f"/workspace/clients/{pessoa['id']}/notes",
                 json={"conteudo": TEXTO_CLINICO}, headers=csrf(cliente))
    cliente.post(f"/workspace/clients/{pessoa['id']}/documents/record", headers=csrf(cliente))

    with sem_escopo_de_tenant():
        acoes = [l.action for l in db.execute(select(ClinicalAccessLog)).scalars()]
    assert "export" in acoes


def test_exportar_sem_registro_e_recusado(cliente, pessoa):
    r = cliente.post(f"/workspace/clients/{pessoa['id']}/documents/record",
                     headers=csrf(cliente))
    assert r.status_code == 409


# ---------------- permissão por classe ----------------
def test_quem_nao_atende_ve_recibo_e_nao_ve_declaracao(cliente, db, pessoa, realizado):
    """A recepção imprime recibo sem enxergar laudo. É esse o ponto."""
    pagar(cliente, realizado)
    recibo = cliente.post(f"/workspace/clients/{pessoa['id']}/documents/receipt",
                          json={}, headers=csrf(cliente)).json()
    declaracao = cliente.post(f"/workspace/clients/{pessoa['id']}/documents/attendance",
                              json={"atendimento_id": realizado["id"]},
                              headers=csrf(cliente)).json()

    # Tira o acesso clínico da titular: vira o caso da recepção.
    from app.models.membership import Membership, MembershipPermission
    from app.models.rbac import Permission
    from app.ids import novo_ulid

    with sem_escopo_de_tenant():
        membership = db.execute(select(Membership)).scalar_one()
        for chave in ("documents.read", "clinical_records.read"):
            permissao = db.execute(
                select(Permission).where(Permission.key == chave)).scalar_one()
            db.add(MembershipPermission(
                public_id=novo_ulid(), tenant_id=membership.tenant_id,
                membership_id=membership.id, permission_id=permissao.id,
                effect="deny", reason="teste: perfil de recepção"))
        db.commit()

    assert cliente.get(f"/workspace/documents/{recibo['id']}/content").status_code == 200
    assert cliente.get(f"/workspace/documents/{declaracao['id']}/content").status_code == 403

    lista = cliente.get(f"/workspace/clients/{pessoa['id']}/documents").json()
    assert [d["tipo"] for d in lista] == ["receipt"]


def test_emitir_recibo_exige_permissao_de_dinheiro(cliente, db, pessoa, realizado):
    pagar(cliente, realizado)
    from app.models.membership import Membership, MembershipPermission
    from app.models.rbac import Permission
    from app.ids import novo_ulid

    with sem_escopo_de_tenant():
        membership = db.execute(select(Membership)).scalar_one()
        permissao = db.execute(
            select(Permission).where(Permission.key == "finance.write")).scalar_one()
        db.add(MembershipPermission(
            public_id=novo_ulid(), tenant_id=membership.tenant_id,
            membership_id=membership.id, permission_id=permissao.id,
            effect="deny", reason="teste: separar dinheiro de clínico"))
        db.commit()

    r = cliente.post(f"/workspace/clients/{pessoa['id']}/documents/receipt",
                     json={}, headers=csrf(cliente))
    assert r.status_code == 403


# ---------------- isolamento ----------------
def test_documento_de_outra_conta_nao_existe(cliente, pessoa, realizado):
    pagar(cliente, realizado)
    doc = cliente.post(f"/workspace/clients/{pessoa['id']}/documents/receipt",
                       json={}, headers=csrf(cliente)).json()

    cliente.cookies.clear()
    cadastrar(cliente, nome="Bia Outra", email="bia@exemplo.com", workspace="Clínica da Bia",
              profissao="terapia_integrativa")
    assert cliente.get(f"/workspace/documents/{doc['id']}/content").status_code == 404


# ---------------- exportação do financeiro ----------------
def test_csv_do_caixa(cliente, pessoa, realizado):
    pagar(cliente, realizado)
    r = cliente.get("/workspace/finance/export")
    assert r.status_code == 200
    texto = r.content.decode("utf-8")
    assert texto.startswith("﻿"), "o Excel brasileiro precisa do BOM"
    assert "pessoa;valor" in texto.replace("data;", "")
    assert "Ana Beatriz" in texto
    assert "180,00" in texto


def test_csv_nao_carrega_nada_clinico(cliente, pessoa, realizado):
    cliente.post(f"/workspace/clients/{pessoa['id']}/notes",
                 json={"conteudo": TEXTO_CLINICO}, headers=csrf(cliente))
    pagar(cliente, realizado)
    texto = cliente.get("/workspace/finance/export").content.decode("utf-8")
    assert "sono" not in texto.lower()


def test_csv_exige_permissao_de_exportar(cliente, db, pessoa, realizado):
    from app.models.membership import Membership, MembershipPermission
    from app.models.rbac import Permission
    from app.ids import novo_ulid

    with sem_escopo_de_tenant():
        membership = db.execute(select(Membership)).scalar_one()
        permissao = db.execute(
            select(Permission).where(Permission.key == "finance.export")).scalar_one()
        db.add(MembershipPermission(
            public_id=novo_ulid(), tenant_id=membership.tenant_id,
            membership_id=membership.id, permission_id=permissao.id,
            effect="deny", reason="teste"))
        db.commit()
    assert cliente.get("/workspace/finance/export").status_code == 403


# ---------------- apagar a pedido do titular ----------------
def test_apagar_arquivo_preserva_o_registro(cliente, db, pessoa, realizado):
    import pathlib

    from app.api.deps import Contexto
    from app.config import settings
    from app.models.membership import Membership
    from app.models.user import User
    from app.services import documents as servico

    pagar(cliente, realizado)
    doc_json = cliente.post(f"/workspace/clients/{pessoa['id']}/documents/receipt",
                            json={}, headers=csrf(cliente)).json()

    with sem_escopo_de_tenant():
        doc = db.execute(select(Document)).scalar_one()
        caminho = pathlib.Path(settings.VC_FILES_DIR) / doc.storage_key
        usuario = db.execute(select(User)).scalars().first()
        membership = db.execute(select(Membership)).scalar_one()
        ctx = Contexto(db=db, usuario=usuario, sessao=None, membership=membership,
                       permissoes=set(), professional_id=None)
        servico.apagar_conteudo(db, ctx, doc, "pedido do titular")
        db.commit()
        assert not caminho.exists()

    lista = cliente.get(f"/workspace/clients/{pessoa['id']}/documents").json()
    assert len(lista) == 1
    assert lista[0]["conteudo_apagado_em"]
    r = cliente.get(f"/workspace/documents/{doc_json['id']}/content")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "conteudo_apagado"
