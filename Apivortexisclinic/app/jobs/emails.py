"""
Entrega a fila de e-mail.

    python -m app.jobs.emails [--lote 50] [--limpar 90]

Roda de fora da aplicação, no agendador do sistema. É seguro rodar de
minuto em minuto: cada mensagem sai uma vez, e o que falhou é tentado de
novo até `VC_MAIL_MAX_ATTEMPTS`.

Sem SMTP configurado (`VC_MAIL_BACKEND=queue`, o padrão), nada é enviado e
nada é perdido: as mensagens ficam na fila, visíveis, até alguém
configurar o envio. É melhor que sumirem com aparência de entregues.
"""
import argparse
import logging
import sys

from app.config import settings
from app.db.context import sem_escopo_de_tenant
from app.db.session import SessionLocal
from app.services import mailer

log = logging.getLogger("vc.jobs.emails")


def executar(lote: int = 50, limpar_dias: int = 0) -> int:
    enviadas = falhas = 0
    db = SessionLocal()
    try:
        with sem_escopo_de_tenant():
            for mensagem in mailer.pendentes(db, lote):
                if mailer.entregar(db, mensagem):
                    enviadas += 1
                else:
                    falhas += 1
                db.commit()

            if limpar_dias:
                limpas = mailer.limpar_antigas(db, limpar_dias)
                db.commit()
                if limpas:
                    log.info("corpo esvaziado em %d mensagem(ns) antiga(s)", limpas)
    finally:
        db.close()

    print(f"e-mail: {enviadas} enviada(s), {falhas} pendente(s)/falha(s) "
          f"[backend={settings.VC_MAIL_BACKEND}]")
    return enviadas


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Entrega a fila de e-mail")
    p.add_argument("--lote", type=int, default=50)
    p.add_argument("--limpar", type=int, default=0,
                   help="esvazia o corpo de mensagens enviadas há mais de N dias")
    args = p.parse_args()
    sys.exit(0 if executar(args.lote, args.limpar) >= 0 else 1)
