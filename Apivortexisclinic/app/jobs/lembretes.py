"""
Enfileira os lembretes de atendimento.

    python -m app.jobs.lembretes [--horas 24]

Roda uma vez por hora. Pega os atendimentos que acontecem daqui a
~`VC_REMINDER_HOURS` e enfileira um lembrete para cada pessoa que tem
e-mail.

**Três regras que não são detalhe:**

1. **Um lembrete por atendimento, para sempre.** A chave de deduplicação
   da fila garante isso mesmo se o job rodar dez vezes no mesmo dia.
2. **Quem revogou o consentimento de contato não recebe.** A revogação
   vale imediatamente, sem depender de ninguém lembrar de checar.
3. **O corpo não carrega nada clínico.** Data, hora e se é presencial ou
   online. Ver `services/mailer.py`.

O horário sai no **fuso da conta** — um lembrete com a hora errada é pior
do que nenhum lembrete.
"""
import argparse
import logging
from datetime import timedelta

from sqlalchemy import select

from app.config import settings
from app.db.context import sem_escopo_de_tenant
from app.db.session import SessionLocal
from app.models.appointment import Appointment
from app.models.client import Client
from app.models.lgpd import Consent
from app.models.tenant import Tenant
from app.services import mailer
from app.services.sessions import agora

log = logging.getLogger("vc.jobs.lembretes")


def _recusou_contato(db, cliente: Client) -> bool:
    """A revogação vale na hora, sem depender de alguém lembrar de checar."""
    ultimo = db.execute(
        select(Consent)
        .where(Consent.client_id == cliente.id, Consent.kind == "communication")
        .order_by(Consent.id.desc())
    ).scalars().first()
    return ultimo is not None and ultimo.revoked_at is not None


def executar(horas: int = None) -> int:
    from app.services.settings import fuso_do_tenant

    horas = horas or settings.VC_REMINDER_HOURS
    inicio = agora() + timedelta(hours=horas - 1)
    fim = agora() + timedelta(hours=horas + 1)

    enfileirados = 0
    db = SessionLocal()
    try:
        with sem_escopo_de_tenant():
            atendimentos = list(db.execute(
                select(Appointment).where(
                    Appointment.start_at >= inicio,
                    Appointment.start_at < fim,
                    Appointment.status.in_(("scheduled", "confirmed")),
                )
            ).scalars())

            for atendimento in atendimentos:
                cliente = db.get(Client, atendimento.client_id)
                if cliente is None or not cliente.email:
                    continue
                if cliente.anonymized_at is not None:
                    continue          # não há mais a quem escrever
                if _recusou_contato(db, cliente):
                    continue

                tenant = db.get(Tenant, atendimento.tenant_id)
                if tenant is None:
                    continue

                if mailer.lembrete(db, cliente=cliente, atendimento=atendimento,
                                   tenant=tenant, fuso=fuso_do_tenant(db, tenant.id)):
                    enfileirados += 1
            db.commit()
    finally:
        db.close()

    print(f"lembretes: {enfileirados} enfileirado(s) para daqui a ~{horas}h")
    return enfileirados


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Enfileira lembretes de atendimento")
    p.add_argument("--horas", type=int, default=None)
    args = p.parse_args()
    executar(args.horas)
