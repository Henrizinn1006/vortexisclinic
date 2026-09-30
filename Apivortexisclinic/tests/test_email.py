"""
Fila de e-mail, verificação de endereço e lembretes.

A regra que mais importa aqui não é "o e-mail chegou": é **o que vai
dentro dele**. A fila guarda o corpo do que saiu, então um lembrete que
carregasse motivo da consulta seria uma cópia de prontuário fora da cifra,
num canal que ninguém controla. Há teste para isso.
"""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.context import sem_escopo_de_tenant
from app.models.email import EmailMessage, EmailVerification
from app.services.sessions import agora
from tests.conftest import cadastrar, csrf, entrar

TEXTO_CLINICO = "Sessão sobre luto e crise de ansiedade no trabalho."


@pytest.fixture
def conta(cliente):
    r = cadastrar(cliente, nome="Clara Mendes", email="clara@exemplo.com",
                  workspace="Clínica Bem Viver", profissao="terapia_integrativa")
    assert r.status_code == 201
    return r.json()


def fila(db, tipo=None):
    with sem_escopo_de_tenant():
        consulta = select(EmailMessage)
        if tipo:
            consulta = consulta.where(EmailMessage.kind == tipo)
        return list(db.execute(consulta.order_by(EmailMessage.id)).scalars())


# ---------------- redefinição de senha ----------------
def test_esqueci_a_senha_enfileira_o_email(cliente, db, conta):
    r = cliente.post("/auth/password/forgot", json={"email": "clara@exemplo.com"})
    assert r.status_code == 200

    mensagens = fila(db, "password_reset")
    assert len(mensagens) == 1
    assert mensagens[0].to_email == "clara@exemplo.com"
    assert mensagens[0].status == "queued"
    assert "redefinir" in mensagens[0].subject.lower()


def test_email_inexistente_nao_enfileira_nem_denuncia(cliente, db, conta):
    """A resposta é igual; a fila é que não ganha linha."""
    r = cliente.post("/auth/password/forgot", json={"email": "ninguem@exemplo.com"})
    assert r.status_code == 200
    assert fila(db, "password_reset") == []


def test_o_token_nao_aparece_na_fila_em_claro_no_banco(cliente, db, conta):
    """O corpo tem o link (é o objetivo), mas o que está guardado no
    `password_reset_tokens` é o hash — não dá para voltar do banco."""
    from app.models.security import PasswordResetToken

    cliente.post("/auth/password/forgot", json={"email": "clara@exemplo.com"})
    corpo = fila(db, "password_reset")[0].body
    with sem_escopo_de_tenant():
        guardado = db.execute(select(PasswordResetToken.token_hash)).scalar_one()
    assert guardado not in corpo
    assert len(guardado) == 64


# ---------------- verificação de e-mail ----------------
def test_conta_nasce_sem_email_verificado(cliente, conta):
    assert conta["usuario"]["email_verificado"] is False


def test_pedir_verificacao_enfileira(cliente, db, conta):
    r = cliente.post("/auth/email/verify/request", headers=csrf(cliente))
    assert r.status_code == 200
    mensagens = fila(db, "verify_email")
    assert len(mensagens) == 1
    assert "#/verificar/" in mensagens[0].body


def test_verificar_marca_a_conta(cliente, db, conta):
    cliente.post("/auth/email/verify/request", headers=csrf(cliente))
    corpo = fila(db, "verify_email")[0].body
    token = corpo.split("#/verificar/")[1].split()[0]

    r = cliente.post("/auth/email/verify", json={"token": token}, headers=csrf(cliente))
    assert r.status_code == 200
    assert cliente.get("/auth/me").json()["usuario"]["email_verificado"] is True


def test_token_de_verificacao_nao_serve_duas_vezes(cliente, db, conta):
    cliente.post("/auth/email/verify/request", headers=csrf(cliente))
    token = fila(db, "verify_email")[0].body.split("#/verificar/")[1].split()[0]
    cliente.post("/auth/email/verify", json={"token": token}, headers=csrf(cliente))
    r = cliente.post("/auth/email/verify", json={"token": token}, headers=csrf(cliente))
    assert r.status_code == 422


def test_token_vencido_nao_vale(cliente, db, conta):
    cliente.post("/auth/email/verify/request", headers=csrf(cliente))
    token = fila(db, "verify_email")[0].body.split("#/verificar/")[1].split()[0]
    with sem_escopo_de_tenant():
        registro = db.execute(select(EmailVerification)).scalar_one()
        registro.expires_at = agora() - timedelta(minutes=1)
        db.commit()
    r = cliente.post("/auth/email/verify", json={"token": token}, headers=csrf(cliente))
    assert r.status_code == 422


def test_token_inventado_responde_igual(cliente, conta):
    r = cliente.post("/auth/email/verify", json={"token": "x" * 40}, headers=csrf(cliente))
    assert r.status_code == 422


def test_pedir_verificacao_de_novo_nao_duplica_quando_ja_verificado(cliente, db, conta):
    cliente.post("/auth/email/verify/request", headers=csrf(cliente))
    token = fila(db, "verify_email")[0].body.split("#/verificar/")[1].split()[0]
    cliente.post("/auth/email/verify", json={"token": token}, headers=csrf(cliente))

    cliente.post("/auth/email/verify/request", headers=csrf(cliente))
    assert len(fila(db, "verify_email")) == 1, "já verificado não pede de novo"


# ---------------- convite ----------------
def test_convite_enfileira_o_email(cliente, db, conta):
    cliente.post("/workspace/invitations",
                 json={"email": "marcos@exemplo.com", "papel": "PROFESSIONAL"},
                 headers=csrf(cliente))
    mensagens = fila(db, "invitation")
    assert len(mensagens) == 1
    assert mensagens[0].to_email == "marcos@exemplo.com"
    assert "Clínica Bem Viver" in mensagens[0].subject
    assert "#/convite/" in mensagens[0].body


# ---------------- lembretes ----------------
@pytest.fixture
def com_atendimento(cliente, conta):
    pessoa = cliente.post("/workspace/clients",
                          json={"nome": "Ana Beatriz", "email": "ana@exemplo.com"},
                          headers=csrf(cliente)).json()
    quando = agora() + timedelta(hours=24)
    a = cliente.post("/workspace/appointments",
                     json={"cliente_id": pessoa["id"], "inicio": quando.isoformat()},
                     headers=csrf(cliente)).json()
    return pessoa, a


def test_lembrete_e_enfileirado_para_amanha(db, com_atendimento):
    from app.jobs import lembretes

    assert lembretes.executar(24) == 1
    mensagens = fila(db, "appointment_reminder")
    assert len(mensagens) == 1
    assert mensagens[0].to_email == "ana@exemplo.com"


def test_o_lembrete_nao_carrega_nada_clinico(cliente, db, com_atendimento):
    """A fila guarda o corpo. Se o lembrete carregasse o motivo da
    consulta, seria prontuário fora da cifra, num canal sem controle."""
    from app.jobs import lembretes

    pessoa, _a = com_atendimento
    cliente.post(f"/workspace/clients/{pessoa['id']}/notes",
                 json={"conteudo": TEXTO_CLINICO}, headers=csrf(cliente))
    lembretes.executar(24)

    corpo = fila(db, "appointment_reminder")[0].body.lower()
    assert "luto" not in corpo
    assert "ansiedade" not in corpo
    assert "atendimento" in corpo        # diz quando e onde, e para


def test_lembrete_nao_sai_duas_vezes(db, com_atendimento):
    from app.jobs import lembretes

    lembretes.executar(24)
    assert lembretes.executar(24) == 0, "rodar de novo não pode duplicar"
    assert len(fila(db, "appointment_reminder")) == 1


def test_quem_revogou_contato_nao_recebe(cliente, db, com_atendimento):
    from app.jobs import lembretes

    pessoa, _a = com_atendimento
    c = cliente.post(f"/workspace/clients/{pessoa['id']}/consents",
                     json={"tipo": "communication"}, headers=csrf(cliente)).json()
    cliente.post(f"/workspace/consents/{c['id']}/revoke", headers=csrf(cliente))

    assert lembretes.executar(24) == 0
    assert fila(db, "appointment_reminder") == []


def test_cadastro_anonimizado_nao_recebe(cliente, db, com_atendimento):
    from app.jobs import lembretes

    pessoa, _a = com_atendimento
    cliente.post(f"/workspace/clients/{pessoa['id']}/anonymize",
                 json={"motivo": "pedido do titular"}, headers=csrf(cliente))
    assert lembretes.executar(24) == 0


def test_sem_email_nao_ha_lembrete(cliente, db, conta):
    from app.jobs import lembretes

    pessoa = cliente.post("/workspace/clients", json={"nome": "Sem E-mail"},
                          headers=csrf(cliente)).json()
    quando = agora() + timedelta(hours=24)
    cliente.post("/workspace/appointments",
                 json={"cliente_id": pessoa["id"], "inicio": quando.isoformat()},
                 headers=csrf(cliente))
    assert lembretes.executar(24) == 0


def test_lembrete_usa_o_fuso_da_conta(cliente, db, conta):
    """Lembrete com a hora errada é pior do que nenhum lembrete."""
    from zoneinfo import ZoneInfo

    from app.domain import calendario
    from app.jobs import lembretes

    pessoa = cliente.post("/workspace/clients",
                          json={"nome": "Ana Beatriz", "email": "ana@exemplo.com"},
                          headers=csrf(cliente)).json()
    quando = agora() + timedelta(hours=24)
    cliente.post("/workspace/appointments",
                 json={"cliente_id": pessoa["id"], "inicio": quando.isoformat()},
                 headers=csrf(cliente))
    lembretes.executar(24)

    local = calendario.para_local(quando, ZoneInfo("America/Sao_Paulo"))
    corpo = fila(db, "appointment_reminder")[0].body
    assert local.strftime("%H:%M") in corpo
    assert quando.strftime("%H:%M") not in corpo or local.hour == quando.hour


# ---------------- entrega ----------------
def test_sem_backend_configurado_a_mensagem_fica_na_fila(cliente, db, conta):
    """Melhor esperar visível do que sumir com aparência de entregue."""
    from app.jobs import emails

    cliente.post("/auth/password/forgot", json={"email": "clara@exemplo.com"})
    emails.executar()

    mensagem = fila(db, "password_reset")[0]
    db.refresh(mensagem)
    assert mensagem.status == "queued"
    assert mensagem.attempts == 0, "falta de configuração não gasta tentativa"
    assert "backend" in (mensagem.last_error or "")


def test_backend_console_entrega(cliente, db, conta):
    from app.config import settings
    from app.jobs import emails

    cliente.post("/auth/password/forgot", json={"email": "clara@exemplo.com"})
    original = settings.VC_MAIL_BACKEND
    try:
        settings.VC_MAIL_BACKEND = "console"
        assert emails.executar() == 1
    finally:
        settings.VC_MAIL_BACKEND = original

    mensagem = fila(db, "password_reset")[0]
    db.refresh(mensagem)
    assert mensagem.status == "sent"
    assert mensagem.sent_at is not None


def test_limpeza_esvazia_o_corpo_de_mensagens_antigas(cliente, db, conta):
    """Endereço e corpo são dado pessoal: a linha fica, o conteúdo some."""
    from app.config import settings
    from app.jobs import emails
    from app.services import mailer

    cliente.post("/auth/password/forgot", json={"email": "clara@exemplo.com"})
    original = settings.VC_MAIL_BACKEND
    try:
        settings.VC_MAIL_BACKEND = "console"
        emails.executar()
    finally:
        settings.VC_MAIL_BACKEND = original

    with sem_escopo_de_tenant():
        m = db.execute(select(EmailMessage)).scalars().first()
        m.sent_at = agora() - timedelta(days=200)
        db.commit()
        assert mailer.limpar_antigas(db, 90) == 1
        db.commit()
        db.refresh(m)
    assert m.body == ""
    assert m.status == "sent"          # continua respondendo "saiu ou não"


def test_a_fila_nao_guarda_senha_de_smtp(cliente, db, conta):
    from app.config import settings
    from app.jobs import emails

    cliente.post("/auth/password/forgot", json={"email": "clara@exemplo.com"})
    originais = (settings.VC_MAIL_BACKEND, settings.VC_SMTP_HOST,
                 settings.VC_SMTP_PASSWORD, settings.VC_SMTP_PORT)
    try:
        settings.VC_MAIL_BACKEND = "smtp"
        settings.VC_SMTP_HOST = "127.0.0.1"
        settings.VC_SMTP_PORT = 1          # porta que ninguém escuta
        settings.VC_SMTP_PASSWORD = "x" * 32
        emails.executar()
    finally:
        (settings.VC_MAIL_BACKEND, settings.VC_SMTP_HOST,
         settings.VC_SMTP_PASSWORD, settings.VC_SMTP_PORT) = originais

    mensagem = fila(db, "password_reset")[0]
    db.refresh(mensagem)
    assert mensagem.attempts == 1
    assert "senha-super-secreta" not in (mensagem.last_error or "")
