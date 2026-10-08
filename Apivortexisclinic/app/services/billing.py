"""
Limites do plano: quem pergunta, pergunta pelo número.

**A regra de ouro deste arquivo**

Nenhum `if plano == "pro"` em lugar nenhum do sistema. O plano carrega os
números; o código pergunta "quantos profissionais posso ter?" e recebe um
número (ou `None`, que é *sem limite*). Mudar o que o plano Pro permite
vira um `UPDATE`, não um deploy.

**Limite recusa, não apaga**

Estourar o limite impede criar o próximo. Nunca apaga o que já existe, e
nunca esconde: uma conta que caiu de plano continua enxergando tudo o que
cadastrou — ela só não cadastra mais até resolver. Apagar dado de gente
por causa de fatura é o tipo de coisa que não se desfaz.

**Sem assinatura, a conta funciona**

Conta criada antes desta etapa (ou por um caminho que não passou por
aqui) recebe o plano padrão na primeira consulta. Fail-closed vale para
acesso a dado, não para cobrança — travar o trabalho de alguém porque
uma linha de assinatura não existe seria errado.
"""
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import errors
from app.config import settings
from app.ids import novo_ulid
from app.models.billing import Plan, Subscription
from app.services.sessions import agora

PLANO_PADRAO = "essencial"


# ---------------- assinatura ----------------
def plano_padrao(db: Session) -> Plan:
    achado = db.execute(select(Plan).where(Plan.key == PLANO_PADRAO)).scalar_one_or_none()
    if achado is None:
        # Catálogo ainda não semeado: o primeiro plano ativo serve.
        achado = db.execute(
            select(Plan).where(Plan.active.is_(True)).order_by(Plan.sort_order)
        ).scalars().first()
    if achado is None:
        raise RuntimeError("nenhum plano cadastrado — rode as migrations")
    return achado


def assinatura(db: Session, tenant_id: int) -> Subscription:
    """A assinatura da conta. Cria a padrão se não existir."""
    achada = db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if achada is not None:
        return achada

    plano = plano_padrao(db)
    achada = Subscription(
        public_id=novo_ulid(),
        tenant_id=tenant_id,
        plan_id=plano.id,
        status="trialing",
        trial_ends_at=agora() + timedelta(days=settings.VC_TRIAL_DAYS)
        if settings.VC_TRIAL_DAYS else None,
    )
    db.add(achada)
    db.flush()
    return achada


def plano(db: Session, tenant_id: int) -> Plan:
    return assinatura(db, tenant_id).plan


def trocar_plano(db: Session, tenant_id: int, chave: str, *, nota: str = "") -> Subscription:
    """Troca o plano de uma conta, sem cobrança.

    Não tem rota de propósito: é o atalho do suporte
    (`python -m app.jobs.assinatura`). A rota de autoatendimento é o
    checkout, que só troca o plano depois do pagamento confirmado.
    """
    novo = db.execute(select(Plan).where(Plan.key == chave)).scalar_one_or_none()
    if novo is None:
        raise errors.dados_invalidos(f"Plano '{chave}' não existe.")
    atual = assinatura(db, tenant_id)
    atual.plan_id = novo.id
    if nota:
        atual.note = nota[:300]
    db.flush()
    return atual


# ---------------- cobrança (Asaas) ----------------
EVENTOS_PAGO = {"PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"}
EVENTOS_ATRASO = {"PAYMENT_OVERDUE"}
EVENTOS_CANCELADO = {"SUBSCRIPTION_DELETED", "SUBSCRIPTION_INACTIVATED"}


def iniciar_checkout(db: Session, tenant_id: int, chave: str, *, nome: str, email: str,
                     cpf_cnpj: str) -> dict:
    """Cria a assinatura no Asaas e devolve o link da primeira fatura.

    Não muda o plano: ele fica em `pending_plan_id` até o webhook confirmar
    o pagamento. Sem isso, abrir o checkout e não pagar daria o plano.
    """
    from app.models.tenant import Tenant
    from app.services import asaas

    if not asaas.ativo():
        raise errors.ApiError(503, "cobranca_indisponivel",
                              "A cobrança está indisponível no momento.")
    novo = db.execute(
        select(Plan).where(Plan.key == chave, Plan.active.is_(True))
    ).scalar_one_or_none()
    if novo is None:
        raise errors.dados_invalidos(f"Plano '{chave}' não existe.")
    if novo.monthly_price is None or novo.monthly_price <= 0:
        raise errors.conflito("plano_sem_preco", "Este plano ainda não tem preço definido.")

    atual = assinatura(db, tenant_id)
    if atual.provider == asaas.PROVEDOR and atual.external_ref and atual.status != "canceled":
        raise errors.conflito(
            "assinatura_existente",
            "Esta conta já tem uma assinatura ativa. Cancele-a antes de contratar outra.",
        )

    tenant = db.get(Tenant, tenant_id)
    cliente_id = asaas.criar_cliente(nome=nome, email=email, cpf_cnpj=cpf_cnpj,
                                     ref=tenant.public_id)
    # O primeiro vencimento é amanhã: dá tempo de abrir a fatura e pagar.
    vencimento = (agora() + timedelta(days=1)).date().isoformat()
    ref_assinatura = asaas.criar_assinatura(
        cliente_id=cliente_id, valor=novo.monthly_price, primeiro_vencimento=vencimento,
        descricao=f"Vortexis Clinic — plano {novo.name}", ref=atual.public_id,
    )
    atual.provider = asaas.PROVEDOR
    atual.external_ref = ref_assinatura
    atual.pending_plan_id = novo.id
    atual.canceled_at = None
    db.flush()
    return {"plano": novo.key, "link_pagamento": asaas.link_da_primeira_cobranca(ref_assinatura)}


def cancelar_assinatura(db: Session, tenant_id: int) -> Subscription:
    from app.services import asaas

    atual = assinatura(db, tenant_id)
    if atual.provider != asaas.PROVEDOR or not atual.external_ref or atual.status == "canceled":
        raise errors.conflito("sem_assinatura_paga", "Não há assinatura paga para cancelar.")
    asaas.cancelar_assinatura(atual.external_ref)
    atual.status = "canceled"
    atual.canceled_at = agora()
    atual.pending_plan_id = None
    db.flush()
    return atual


def _somar_mes(d):
    from calendar import monthrange

    ano, mes = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return d.replace(year=ano, month=mes, day=min(d.day, monthrange(ano, mes)[1]))


def aplicar_evento_asaas(db: Session, corpo: dict) -> str:
    """Aplica um webhook do Asaas. Devolve o que aconteceu (para o log).

    Idempotente: o `id` do evento é único, então reenvio não muda nada.
    Evento de assinatura que não conhecemos é registrado e ignorado — o
    Asaas precisa de 200 para não pausar a fila de webhooks.
    """
    from datetime import date

    from sqlalchemy.exc import IntegrityError

    from app.models.billing import BillingEvent
    from app.services import asaas

    evento = str(corpo.get("event") or "")[:60]
    evento_id = str(corpo.get("id") or "")[:120]
    pagamento = corpo.get("payment") or {}
    ref = pagamento.get("subscription") or (corpo.get("subscription") or {}).get("id")
    if not evento or not evento_id:
        return "ignorado: sem evento ou id"

    sub = None
    if ref:
        sub = db.execute(
            select(Subscription).where(Subscription.provider == asaas.PROVEDOR,
                                       Subscription.external_ref == str(ref))
        ).scalar_one_or_none()

    try:
        with db.begin_nested():
            db.add(BillingEvent(provider=asaas.PROVEDOR, event_id=evento_id, event=evento,
                                subscription_id=sub.id if sub else None))
            db.flush()
    except IntegrityError:
        return "duplicado"

    if sub is None:
        return "ignorado: assinatura desconhecida"

    if evento in EVENTOS_PAGO:
        if sub.pending_plan_id:
            sub.plan_id = sub.pending_plan_id
            sub.pending_plan_id = None
        sub.status = "active"
        sub.canceled_at = None
        try:
            sub.current_period_end = _somar_mes(date.fromisoformat(pagamento["dueDate"]))
        except (KeyError, ValueError, TypeError):
            pass
    elif evento in EVENTOS_ATRASO:
        # Atraso não derruba um cancelamento já feito.
        if sub.status != "canceled":
            sub.status = "past_due"
    elif evento in EVENTOS_CANCELADO:
        sub.status = "canceled"
        sub.canceled_at = sub.canceled_at or agora()
        sub.pending_plan_id = None
    else:
        return "registrado: evento sem efeito"
    db.flush()
    return f"aplicado: {evento}"


# ---------------- limites ----------------
def _contar(db: Session, modelo, tenant_id: int, **extra) -> int:
    from app.db.context import sem_escopo_de_tenant

    with sem_escopo_de_tenant():
        consulta = select(func.count(modelo.id)).where(modelo.tenant_id == tenant_id)
        for coluna, valor in extra.items():
            consulta = consulta.where(getattr(modelo, coluna) == valor)
        return int(db.execute(consulta).scalar_one())


def uso(db: Session, tenant_id: int) -> dict:
    """Quanto a conta já usa de cada limite. Serve à tela e à checagem."""
    from app.db.context import sem_escopo_de_tenant
    from app.models.client import Client
    from app.models.document import Document
    from app.models.membership import Membership
    from app.models.professional import Professional

    with sem_escopo_de_tenant():
        bytes_usados = int(db.execute(
            select(func.coalesce(func.sum(Document.size_bytes), 0))
            .where(Document.tenant_id == tenant_id)
        ).scalar_one() or 0)

    return {
        "profissionais": _contar(db, Professional, tenant_id, active=True),
        "membros": _contar(db, Membership, tenant_id, status="active"),
        "clientes": _contar(db, Client, tenant_id, status="active"),
        "armazenamento_mb": round(bytes_usados / (1024 * 1024), 2),
    }


def _recusar(o_que: str, limite: int) -> None:
    raise errors.conflito(
        "limite_do_plano",
        f"O plano atual permite {limite} {o_que}. Para incluir mais, é preciso mudar de plano.",
    )


def conferir_profissional(db: Session, tenant_id: int) -> None:
    p = plano(db, tenant_id)
    if p.max_professionals is None:
        return
    if uso(db, tenant_id)["profissionais"] >= p.max_professionals:
        _recusar("profissional(is)", p.max_professionals)


def conferir_membro(db: Session, tenant_id: int) -> None:
    p = plano(db, tenant_id)
    if p.max_members is None:
        return
    if uso(db, tenant_id)["membros"] >= p.max_members:
        _recusar("pessoa(s) na conta", p.max_members)


def conferir_cliente(db: Session, tenant_id: int) -> None:
    p = plano(db, tenant_id)
    if p.max_clients is None:
        return
    if uso(db, tenant_id)["clientes"] >= p.max_clients:
        _recusar("pessoas atendidas ativas", p.max_clients)


def conferir_armazenamento(db: Session, tenant_id: int, bytes_novos: int) -> None:
    p = plano(db, tenant_id)
    if p.max_storage_mb is None:
        return
    usado = uso(db, tenant_id)["armazenamento_mb"]
    if usado + (bytes_novos / (1024 * 1024)) > p.max_storage_mb:
        raise errors.conflito(
            "limite_do_plano",
            f"O plano atual permite {p.max_storage_mb} MB de arquivos "
            f"(em uso: {usado} MB). Apague o que não precisa ou mude de plano.",
        )


def exige_recurso(db: Session, tenant_id: int, recurso: str) -> None:
    """Recurso que o plano não abre responde como recurso indisponível.

    Não é 403 ("você não pode") nem 404 ("não existe"): é 409, porque a
    resposta certa é "a conta não tem isso contratado" — coisa que se
    resolve, e a mensagem diz como.
    """
    p = plano(db, tenant_id)
    mapa = {
        "clinical": (p.allows_clinical, "registros clínicos"),
        "documents": (p.allows_documents, "documentos"),
        "export": (p.allows_export, "exportação"),
        "reminders": (p.allows_reminders, "lembretes por e-mail"),
    }
    permitido, nome = mapa.get(recurso, (True, recurso))
    if not permitido:
        raise errors.conflito(
            "recurso_do_plano",
            f"O plano atual não inclui {nome}. Mude de plano para usar.",
        )


def resumo(db: Session, tenant_id: int) -> dict:
    """O que a tela de conta mostra: plano, limites, uso e situação."""
    a = assinatura(db, tenant_id)
    p = a.plan
    return {
        "plano": p.key,
        "plano_nome": p.name,
        "status": a.status,
        "vigente": a.vigente,
        "trial_ate": a.trial_ends_at,
        "periodo_ate": a.current_period_end,
        "plano_pendente": a.pending_plan.key if a.pending_plan else None,
        "cobranca_ativa": settings.VC_ASAAS_API_KEY != "",
        # Há assinatura no gateway que ainda cobra: habilita "cancelar".
        "assinatura_paga": bool(a.provider and a.external_ref and a.status != "canceled"),
        # Só planos com preço: plano sem preço não dá para contratar.
        "catalogo": [
            {"plano": q.key, "nome": q.name, "descricao": q.description,
             "preco_mensal": q.monthly_price}
            for q in db.execute(
                select(Plan).where(Plan.active.is_(True), Plan.monthly_price.is_not(None))
                .order_by(Plan.sort_order)
            ).scalars()
        ],
        "preco_mensal": p.monthly_price,
        "limites": {
            "profissionais": p.max_professionals,
            "membros": p.max_members,
            "clientes": p.max_clients,
            "armazenamento_mb": p.max_storage_mb,
        },
        "recursos": {
            "clinico": p.allows_clinical,
            "documentos": p.allows_documents,
            "exportacao": p.allows_export,
            "lembretes": p.allows_reminders,
        },
        "uso": uso(db, tenant_id),
    }
