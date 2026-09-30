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
    """Troca o plano de uma conta.

    Não tem rota de propósito: enquanto não houver gateway, mudar de plano
    é operação de fora da aplicação — `python -m app.jobs.assinatura`. Uma
    rota de autoatendimento sem cobrança atrás seria um botão de "vire
    Pro de graça".
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
