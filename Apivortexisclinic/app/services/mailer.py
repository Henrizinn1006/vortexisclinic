"""
Envio de e-mail: enfileirar, redigir e entregar.

**Enfileirar é o que a requisição faz. Entregar é outro processo.**

A rota chama `enfileirar()` e acabou — nada de conexão SMTP no meio de uma
requisição. Quem entrega é `app/jobs/emails.py`, rodando de fora (cron,
serviço, o que for). Se o servidor de e-mail estiver fora do ar, a
mensagem espera na fila em vez de derrubar o cadastro junto.

**Os textos moram aqui, num lugar só**

Não porque fica bonito: porque é o único jeito de garantir a regra que
importa — **nenhum e-mail carrega conteúdo clínico**. O lembrete diz "você
tem atendimento amanhã às 10h", e para. A fila guarda o corpo do que foi
enviado; se um dia alguém "melhorar" o lembrete colocando o motivo da
consulta, terá copiado prontuário para uma tabela sem cifra e mandado por
um canal que ninguém controla. Há teste impedindo isso.

**Três backends**

    queue    (padrão) só enfileira. Sem SMTP configurado, nada some.
    console  imprime no log — o fluxo inteiro testável sem mandar e-mail
             de verdade para ninguém.
    smtp     entrega.
"""
import logging
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage as MimeMessage
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.ids import novo_ulid
from app.models.email import EmailMessage
from app.services.sessions import agora

log = logging.getLogger("vc.email")

ASSINATURA = "\n\n—\nEsta mensagem foi enviada automaticamente. Não responda."


# ---------------- fila ----------------
def enfileirar(db: Session, *, para: str, assunto: str, corpo: str, tipo: str,
               nome: Optional[str] = None, tenant_id: Optional[int] = None,
               quando: Optional[datetime] = None,
               chave: Optional[str] = None) -> Optional[EmailMessage]:
    """Coloca a mensagem na fila. `chave` impede duplicata.

    Devolve None quando a chave já existe — é o caso do job de lembretes
    rodando duas vezes no mesmo dia, e o certo ali é não fazer nada.
    """
    para = (para or "").strip().lower()
    if "@" not in para:
        return None

    if chave:
        ja = db.execute(
            select(EmailMessage).where(EmailMessage.dedupe_key == chave)
        ).scalar_one_or_none()
        if ja is not None:
            return None

    mensagem = EmailMessage(
        public_id=novo_ulid(),
        tenant_id=tenant_id,
        to_email=para,
        to_name=(nome or None),
        kind=tipo,
        subject=assunto[:200],
        body=corpo + ASSINATURA,
        status="queued",
        scheduled_for=quando or agora(),
        dedupe_key=chave,
    )
    db.add(mensagem)
    db.flush()
    return mensagem


def pendentes(db: Session, limite: int = 50) -> List[EmailMessage]:
    return list(db.execute(
        select(EmailMessage)
        .where(EmailMessage.status == "queued",
               EmailMessage.scheduled_for <= agora(),
               EmailMessage.attempts < settings.VC_MAIL_MAX_ATTEMPTS)
        .order_by(EmailMessage.id)
        .limit(limite)
    ).scalars())


# ---------------- entrega ----------------
def _montar(mensagem: EmailMessage) -> MimeMessage:
    mime = MimeMessage()
    mime["From"] = settings.VC_MAIL_FROM
    mime["To"] = (f"{mensagem.to_name} <{mensagem.to_email}>"
                  if mensagem.to_name else mensagem.to_email)
    mime["Subject"] = mensagem.subject
    if settings.VC_MAIL_REPLY_TO:
        mime["Reply-To"] = settings.VC_MAIL_REPLY_TO
    mime.set_content(mensagem.body)
    return mime


def entregar(db: Session, mensagem: EmailMessage) -> bool:
    """Tenta entregar uma mensagem. Devolve se saiu."""
    mensagem.attempts += 1

    if settings.VC_MAIL_BACKEND == "queue":
        # Sem backend configurado, a mensagem fica na fila — visível, em
        # vez de sumir com a aparência de ter sido enviada.
        mensagem.last_error = "nenhum backend de e-mail configurado"
        mensagem.attempts -= 1        # não gasta tentativa por falta de config
        return False

    if settings.VC_MAIL_BACKEND == "console":
        log.info("[e-mail] para=%s assunto=%s", mensagem.to_email, mensagem.subject)
        log.debug("[e-mail] corpo:\n%s", mensagem.body)
        mensagem.status = "sent"
        mensagem.sent_at = agora()
        mensagem.last_error = None
        return True

    try:
        if settings.VC_SMTP_TLS:
            servidor = smtplib.SMTP(settings.VC_SMTP_HOST, settings.VC_SMTP_PORT, timeout=20)
            servidor.starttls()
        else:
            servidor = smtplib.SMTP(settings.VC_SMTP_HOST, settings.VC_SMTP_PORT, timeout=20)
        with servidor:
            if settings.VC_SMTP_USER:
                servidor.login(settings.VC_SMTP_USER, settings.VC_SMTP_PASSWORD)
            servidor.send_message(_montar(mensagem))
    except Exception as erro:
        # A mensagem de erro vai para a linha — nunca a senha do SMTP.
        mensagem.last_error = str(erro)[:300]
        if mensagem.attempts >= settings.VC_MAIL_MAX_ATTEMPTS:
            mensagem.status = "failed"
        log.warning("falha ao enviar e-mail %s: %s", mensagem.public_id, mensagem.last_error)
        return False

    mensagem.status = "sent"
    mensagem.sent_at = agora()
    mensagem.last_error = None
    return True


def limpar_antigas(db: Session, dias: int = 90) -> int:
    """Esvazia o corpo de mensagens antigas já enviadas.

    Endereço e corpo são dado pessoal; guardar para sempre uma cópia de
    tudo que saiu não serve a ninguém. A linha fica (para responder "saiu
    ou não saiu"), o conteúdo some.
    """
    limite = agora() - timedelta(days=dias)
    antigas = list(db.execute(
        select(EmailMessage).where(EmailMessage.status == "sent",
                                   EmailMessage.sent_at < limite,
                                   EmailMessage.body != "")
    ).scalars())
    for m in antigas:
        m.body = ""
    db.flush()
    return len(antigas)


# ---------------- textos ----------------
def _link(caminho: str) -> str:
    base = settings.painel_url
    return f"{base}/#{caminho}" if base else f"#{caminho}"


def verificacao(db: Session, usuario, token: str) -> Optional[EmailMessage]:
    return enfileirar(
        db, para=usuario.email, nome=usuario.name, tipo="verify_email",
        assunto="Confirme seu e-mail — Vortexis Clinic",
        corpo=(
            f"Olá, {usuario.name}.\n\n"
            "Para confirmar este endereço de e-mail, acesse:\n\n"
            f"{_link('/verificar/' + token)}\n\n"
            f"O link vale por {settings.VC_EMAIL_VERIFY_TTL_HOURS} horas.\n"
            "Se não foi você quem pediu, ignore esta mensagem."
        ),
    )


def redefinicao(db: Session, usuario, token: str) -> Optional[EmailMessage]:
    return enfileirar(
        db, para=usuario.email, nome=usuario.name, tipo="password_reset",
        assunto="Redefinir sua senha — Vortexis Clinic",
        corpo=(
            f"Olá, {usuario.name}.\n\n"
            "Recebemos um pedido para redefinir a sua senha. Para criar uma nova:\n\n"
            f"{_link('/redefinir/' + token)}\n\n"
            f"O link vale por {settings.VC_PASSWORD_RESET_TTL_MINUTES} minutos e só "
            "pode ser usado uma vez.\n"
            "Se não foi você, ignore esta mensagem — sua senha continua a mesma."
        ),
    )


def convite(db: Session, convite_linha, token: str, quem_convidou: str) -> Optional[EmailMessage]:
    recado = f'\n\nRecado de quem convidou:\n"{convite_linha.message}"\n' if convite_linha.message else ""
    return enfileirar(
        db, para=convite_linha.email, tipo="invitation",
        tenant_id=convite_linha.tenant_id,
        assunto=f"Convite para {convite_linha.tenant.name} — Vortexis Clinic",
        corpo=(
            f"{quem_convidou} convidou você para fazer parte de "
            f"{convite_linha.tenant.name} no Vortexis Clinic.{recado}\n\n"
            "Para aceitar:\n\n"
            f"{_link('/convite/' + token)}\n\n"
            "O convite vale por 7 dias e só funciona para este endereço de e-mail."
        ),
    )


def lembrete(db: Session, *, cliente, atendimento, tenant, fuso) -> Optional[EmailMessage]:
    """Lembrete de sessão.

    Diz **quando** e **onde**. Nunca o que foi ou será tratado — a fila
    guarda o corpo, e o corpo não pode virar uma cópia de prontuário fora
    da cifra, num canal que ninguém controla.
    """
    from app.domain import calendario

    local = calendario.para_local(atendimento.start_at, fuso)
    onde = "presencial" if atendimento.modality == "in_person" else "online"
    return enfileirar(
        db, para=cliente.email, nome=cliente.name, tipo="appointment_reminder",
        tenant_id=tenant.id,
        assunto=f"Lembrete: seu atendimento em {local.strftime('%d/%m')} — {tenant.name}",
        corpo=(
            f"Olá, {cliente.name}.\n\n"
            f"Este é um lembrete do seu atendimento em {tenant.name}:\n\n"
            f"  Data:  {local.strftime('%d/%m/%Y')}\n"
            f"  Hora:  {local.strftime('%H:%M')}\n"
            f"  Forma: {onde}\n\n"
            "Se precisar remarcar, entre em contato com antecedência."
        ),
        # Um lembrete por atendimento, para sempre — mesmo que o job rode
        # dez vezes no mesmo dia.
        chave=f"lembrete:{atendimento.public_id}",
    )
