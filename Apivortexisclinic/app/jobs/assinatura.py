"""
Troca o plano de uma conta.

    python -m app.jobs.assinatura --listar
    python -m app.jobs.assinatura --tenant <slug-ou-id-publico> --plano pro
    python -m app.jobs.assinatura --tenant <slug> --status active

Isto é um comando, e não uma rota, de propósito: **enquanto não houver
gateway de pagamento, mudar de plano é operação de fora da aplicação**.
Uma rota de autoatendimento sem cobrança atrás seria um botão de "vire Pro
de graça".

Quando o gateway existir, quem chama isto é o webhook dele — e o comando
continua útil para o suporte resolver o caso que o webhook não cobriu.
"""
import argparse
import sys

from sqlalchemy import select

from app.db.context import sem_escopo_de_tenant
from app.db.session import SessionLocal
from app.models.billing import Plan
from app.models.tenant import Tenant
from app.services import billing


def _tenant(db, referencia: str) -> Tenant:
    achado = db.execute(
        select(Tenant).where((Tenant.slug == referencia) | (Tenant.public_id == referencia))
    ).scalar_one_or_none()
    if achado is None:
        raise SystemExit(f"conta '{referencia}' não encontrada (use o slug ou o id público)")
    return achado


def listar(db) -> None:
    print("Planos:")
    for p in db.execute(select(Plan).order_by(Plan.sort_order)).scalars():
        limites = " · ".join([
            f"prof={p.max_professionals if p.max_professionals is not None else '∞'}",
            f"membros={p.max_members if p.max_members is not None else '∞'}",
            f"pessoas={p.max_clients if p.max_clients is not None else '∞'}",
            f"arquivos={p.max_storage_mb if p.max_storage_mb is not None else '∞'}MB",
        ])
        print(f"  {p.key:<12} {p.name:<24} {limites}")


def main() -> int:
    p = argparse.ArgumentParser(description="Assinatura de uma conta")
    p.add_argument("--listar", action="store_true", help="mostra o catálogo de planos")
    p.add_argument("--tenant", help="slug ou id público da conta")
    p.add_argument("--plano", help="chave do plano")
    p.add_argument("--status", choices=("trialing", "active", "past_due", "canceled"))
    p.add_argument("--nota", default="", help="por que a mudança foi feita")
    args = p.parse_args()

    db = SessionLocal()
    try:
        with sem_escopo_de_tenant():
            if args.listar or not args.tenant:
                listar(db)
                return 0

            tenant = _tenant(db, args.tenant)
            if args.plano:
                billing.trocar_plano(db, tenant.id, args.plano, nota=args.nota)
            assinatura = billing.assinatura(db, tenant.id)
            if args.status:
                assinatura.status = args.status
            db.commit()

            resumo = billing.resumo(db, tenant.id)
            print(f"{tenant.name} ({tenant.slug})")
            print(f"  plano:  {resumo['plano_nome']} [{resumo['plano']}]")
            print(f"  status: {resumo['status']}")
            print(f"  uso:    {resumo['uso']}")
            print(f"  limites:{resumo['limites']}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
