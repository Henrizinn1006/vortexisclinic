"""
Pessoas atendidas — leitura e escrita.

A busca usa `LIKE` com o termo escapado. Não é busca textual sofisticada, e
é de propósito: índice de texto completo em nome de pessoa atendida tem
implicação de privacidade (e de custo) que não cabe nesta etapa.

Nada aqui monta SQL por concatenação — tudo passa por parâmetro ligado do
SQLAlchemy, que é o que fecha a porta para injeção.
"""
import unicodedata
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import errors
from app.ids import novo_ulid
from app.models.appointment import Appointment
from app.models.client import Client, ClientProfessional
from app.models.professional import Professional
from app.services import scope
from app.services.sessions import agora


def _normalizar(texto: str) -> str:
    return unicodedata.normalize("NFKC", (texto or "").strip())


def _escapar_like(termo: str) -> str:
    """% e _ são curingas no LIKE: quem digita não quer isso."""
    return termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def listar(
    db: Session,
    ctx,
    *,
    busca: str = "",
    status: str = "active",
    somente_com_pendencia: bool = False,
    limite: int = 200,
    pagina: int = 1,
) -> Tuple[List[Tuple[Client, dict]], int]:
    """Devolve ((cliente, resumo)..., total) já dentro do tenant e do escopo.

    A busca é **insensível a acento** de graça: as tabelas usam
    `utf8mb4_unicode_ci`, e nessa collation "José" casa com "jose" e
    "Conceição" com "conceicao". Nenhuma coluna normalizada é necessária —
    há teste garantindo que continua assim.
    """
    from app.domain import metrics
    from app.services import paginacao

    consulta = select(Client)
    consulta = scope.clientes(consulta, ctx)

    if status and status != "todos":
        consulta = consulta.where(Client.status == status)
    if busca:
        termo = f"%{_escapar_like(_normalizar(busca))}%"
        consulta = consulta.where(Client.name.like(termo, escape="\\"))

    quantas = paginacao.total(db, consulta)
    deslocamento, tamanho = paginacao.limites(pagina, limite)
    consulta = consulta.order_by(Client.name.asc()).offset(deslocamento).limit(tamanho)
    linhas = list(db.execute(consulta).scalars())
    if not linhas:
        return [], quantas

    # Uma consulta só para os atendimentos de todos eles: nada de N+1.
    ids = [c.id for c in linhas]
    atend = list(
        db.execute(
            scope.atendimentos(select(Appointment).where(Appointment.client_id.in_(ids)), ctx)
        ).scalars()
    )
    por_cliente = {}
    for a in atend:
        por_cliente.setdefault(a.client_id, []).append(a)

    momento = agora()
    saida = []
    for c in linhas:
        resumo = metrics.resumo_do_cliente(por_cliente.get(c.id, []), momento)
        if somente_com_pendencia and resumo["valor_em_aberto"] <= 0:
            continue
        saida.append((c, resumo))
    return saida, quantas


def obter(db: Session, ctx, public_id: str) -> Client:
    """Busca por id público. Fora do tenant ou fora do escopo: não existe."""
    consulta = scope.clientes(select(Client).where(Client.public_id == public_id), ctx)
    achado = db.execute(consulta).scalar_one_or_none()
    if achado is None:
        raise errors.nao_encontrado("cliente")
    return achado


def historico(db: Session, ctx, cliente: Client) -> List[Appointment]:
    consulta = scope.atendimentos(
        select(Appointment).where(Appointment.client_id == cliente.id), ctx
    ).order_by(Appointment.start_at.desc())
    return list(db.execute(consulta).scalars())


def resumo(db: Session, ctx, cliente: Client) -> dict:
    from app.domain import metrics

    return metrics.resumo_do_cliente(historico(db, ctx, cliente), agora())


def contar(db: Session, ctx) -> dict:
    consulta = scope.clientes(
        select(Client.status, func.count(Client.id)).group_by(Client.status), ctx
    )
    por_status = {status: total for status, total in db.execute(consulta).all()}
    ativos = por_status.get("active", 0)
    inativos = por_status.get("inactive", 0)
    return {
        "total": ativos + inativos + por_status.get("archived", 0),
        "ativos": ativos,
        "inativos": inativos,
        "arquivados": por_status.get("archived", 0),
    }


def _profissional_valido(db: Session, ctx, professional_id: Optional[int]) -> Optional[int]:
    alvo = scope.profissional_alvo(ctx, professional_id)
    if alvo is None:
        return None
    # A consulta é tenant-scoped: profissional de outra conta não aparece.
    existe = db.execute(select(Professional.id).where(Professional.id == alvo)).scalar_one_or_none()
    if existe is None:
        raise errors.dados_invalidos("Profissional responsável não encontrado nesta conta.")
    return alvo


def criar(db: Session, ctx, dados) -> Client:
    """Cria a pessoa atendida e já a vincula a um profissional.

    O vínculo não é decoração: sem ele, quem está em escopo `own` cadastra
    alguém e não consegue mais enxergar — o que seria um belo de um bug.
    """
    from app.services import billing

    # Limite recusa criar o próximo — nunca apaga nem esconde o que já existe.
    billing.conferir_cliente(db, ctx.tenant_id)

    cliente = Client(
        public_id=novo_ulid(),
        tenant_id=ctx.tenant_id,
        name=_normalizar(dados.nome),
        email=(dados.email or None),
        phone=(dados.telefone or None),
        birth_date=dados.nascimento,
        status="active",
        frequency=dados.frequencia or "weekly",
        default_modality=dados.modalidade or "in_person",
        default_price=dados.valor_sessao,
        started_at=dados.desde,
        notes=(dados.observacao or None),
        created_by_user_id=ctx.usuario.id,
    )
    db.add(cliente)
    db.flush()

    alvo = _profissional_valido(db, ctx, getattr(dados, "profissional_id_interno", None))
    if alvo is not None:
        db.add(ClientProfessional(
            tenant_id=ctx.tenant_id, client_id=cliente.id, professional_id=alvo,
            is_primary=True, started_at=dados.desde,
        ))
        db.flush()
    return cliente


def atualizar(db: Session, ctx, cliente: Client, dados) -> Client:
    campos = {
        "nome": "name", "email": "email", "telefone": "phone", "nascimento": "birth_date",
        "frequencia": "frequency", "modalidade": "default_modality",
        "valor_sessao": "default_price", "desde": "started_at", "observacao": "notes",
        "status": "status",
    }
    for entrada, coluna in campos.items():
        valor = getattr(dados, entrada, None)
        if valor is None:
            continue
        if entrada == "nome":
            valor = _normalizar(valor)
        setattr(cliente, coluna, valor)
    db.flush()
    return cliente


def arquivar(db: Session, ctx, cliente: Client) -> Client:
    """Arquivar é sempre lógico: o histórico de atendimentos continua.

    Exclusão de verdade só existe no fluxo de LGPD, e lá ela é decidida
    item a item (apagar, anonimizar ou reter).
    """
    cliente.status = "archived"
    cliente.archived_at = agora()
    db.flush()
    return cliente
