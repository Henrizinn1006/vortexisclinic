"""
Baixa de pagamento, estorno e isenção.

Três regras que valem a leitura:

1. **Baixa é transação.** Grava a linha no livro-caixa e atualiza a
   bandeira do atendimento juntas, ou nenhuma das duas. Sem isso, um erro
   no meio deixaria dinheiro registrado num atendimento que continua
   "pendente" — ou pior, o contrário.

2. **Pagar duas vezes não acontece por acidente.** A baixa trava a linha
   do atendimento (`FOR UPDATE`) e recusa se já estiver quitado. Dois
   cliques no mesmo botão não viram dois lançamentos.

3. **Estorno não apaga.** Marca a linha como devolvida, com motivo, e
   devolve o atendimento para pendente. Livro-caixa não se rasura.
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import errors
from app.ids import novo_ulid
from app.models.appointment import Appointment
from app.models.payment import Payment
from app.services import scope
from app.services.sessions import agora

ZERO = Decimal("0.00")


# ---------------- leitura ----------------
def listar(
    db: Session,
    ctx,
    *,
    de: Optional[datetime] = None,
    ate: Optional[datetime] = None,
    metodo: Optional[str] = None,
    incluir_estornados: bool = True,
    limite: int = 200,
) -> List[Payment]:
    consulta = select(Payment)

    # Escopo: em "own", só os pagamentos dos atendimentos da pessoa.
    # Pagamento avulso (sem atendimento) fica com quem enxerga a conta toda,
    # porque não há a quem atribuir.
    if not ctx.ve_tudo:
        if ctx.professional_id is None:
            return []
        consulta = consulta.join(
            Appointment,
            (Appointment.tenant_id == Payment.tenant_id)
            & (Appointment.id == Payment.appointment_id),
        ).where(Appointment.professional_id == ctx.professional_id)

    if de is not None:
        consulta = consulta.where(Payment.paid_at >= de)
    if ate is not None:
        consulta = consulta.where(Payment.paid_at <= ate)
    if metodo and metodo != "todos":
        consulta = consulta.where(Payment.method == metodo)
    if not incluir_estornados:
        consulta = consulta.where(Payment.status == "paid")

    consulta = consulta.order_by(Payment.paid_at.desc()).limit(min(limite, 500))
    return list(db.execute(consulta).scalars())


def obter(db: Session, ctx, public_id: str) -> Payment:
    achado = db.execute(
        select(Payment).where(Payment.public_id == public_id)
    ).scalar_one_or_none()

    # Fora do tenant o ORM já filtrou; falta o escopo dentro da conta.
    if achado is not None and not ctx.ve_tudo:
        if achado.appointment is None or achado.appointment.professional_id != ctx.professional_id:
            achado = None

    if achado is None:
        raise errors.nao_encontrado("pagamento")
    return achado


def do_atendimento(db: Session, ctx, atendimento: Appointment) -> List[Payment]:
    return list(
        db.execute(
            select(Payment)
            .where(Payment.appointment_id == atendimento.id)
            .order_by(Payment.paid_at.asc())
        ).scalars()
    )


# ---------------- escrita ----------------
def _travar_atendimento(db: Session, atendimento_id: int) -> Appointment:
    """Relê a linha travada: é o que impede duas baixas simultâneas."""
    travado = db.execute(
        select(Appointment).where(Appointment.id == atendimento_id).with_for_update()
    ).scalar_one_or_none()
    if travado is None:
        raise errors.nao_encontrado("atendimento")
    return travado


def registrar(db: Session, ctx, atendimento: Appointment, dados) -> Payment:
    """Dá baixa em um atendimento."""
    travado = _travar_atendimento(db, atendimento.id)

    if travado.status == "cancelled":
        raise errors.conflito(
            "atendimento_cancelado",
            "Atendimento cancelado não recebe pagamento.",
        )
    if travado.payment_status == "paid":
        raise errors.conflito("ja_pago", "Este atendimento já está quitado.")

    # Quanto já entrou por este atendimento (estornado não conta).
    ja_pago = _recebido_do_atendimento(db, travado.id)
    combinado = travado.price or ZERO
    falta = (combinado - ja_pago) if combinado > ZERO else ZERO

    valor = dados.valor if dados.valor is not None else (falta if falta > ZERO else travado.price)
    if valor is None or valor <= ZERO:
        raise errors.dados_invalidos(
            "Informe o valor recebido — este atendimento não tem valor definido."
        )

    quando = dados.pago_em or agora()
    if quando > agora():
        # Registrar dinheiro que ainda não entrou embaralha o caixa do mês.
        raise errors.dados_invalidos("A data do pagamento não pode estar no futuro.")

    pagamento = Payment(
        public_id=novo_ulid(),
        tenant_id=ctx.tenant_id,
        client_id=travado.client_id,
        appointment_id=travado.id,
        amount=valor,
        method=dados.metodo,
        status="paid",
        paid_at=quando,
        note=(dados.observacao or None),
        created_by_user_id=ctx.usuario.id,
    )
    db.add(pagamento)

    # A bandeira do atendimento anda junto, na mesma transação — mas só
    # vira "pago" quando o combinado foi coberto. Pagamento parcial existe
    # (metade hoje, metade na semana que vem), e marcar quitado no
    # primeiro pedaço sumiria com a cobrança do resto.
    travado.payment_method = dados.metodo
    travado.paid_at = quando
    if combinado <= ZERO or (ja_pago + valor) >= combinado:
        travado.payment_status = "paid"
    db.flush()
    return pagamento


def _recebido_do_atendimento(db: Session, appointment_id: int) -> Decimal:
    """Soma o que já entrou por aquele atendimento. Estornado não conta."""
    total = db.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.appointment_id == appointment_id, Payment.status == "paid")
    ).scalar_one()
    return Decimal(str(total or 0))


def em_aberto_do_atendimento(db: Session, atendimento: Appointment) -> Decimal:
    """Quanto falta receber. Zero quando não há valor combinado."""
    combinado = atendimento.price or ZERO
    if combinado <= ZERO:
        return ZERO
    falta = combinado - _recebido_do_atendimento(db, atendimento.id)
    return falta if falta > ZERO else ZERO


def registrar_avulso(db: Session, ctx, cliente, dados) -> Payment:
    """Pagamento que não nasce de um atendimento: pacote, sinal, acerto.

    O livro-caixa sempre aceitou isso (a coluna do atendimento é
    opcional); o que faltava era caminho para criar. Sem ele, um pacote de
    dez sessões pago adiantado só entrava distorcendo a agenda.
    """
    if dados.valor is None or Decimal(dados.valor) <= ZERO:
        raise errors.dados_invalidos("Informe o valor recebido.")

    quando = dados.pago_em or agora()
    if quando > agora():
        raise errors.dados_invalidos("A data do pagamento não pode estar no futuro.")

    pagamento = Payment(
        public_id=novo_ulid(),
        tenant_id=ctx.tenant_id,
        client_id=cliente.id,
        appointment_id=None,
        amount=Decimal(dados.valor),
        method=dados.metodo,
        status="paid",
        paid_at=quando,
        note=(dados.observacao or None),
        created_by_user_id=ctx.usuario.id,
    )
    db.add(pagamento)
    db.flush()
    return pagamento


def estornar(db: Session, ctx, pagamento: Payment, motivo: Optional[str]) -> Payment:
    if pagamento.status == "refunded":
        raise errors.conflito("ja_estornado", "Este pagamento já foi estornado.")

    pagamento.status = "refunded"
    pagamento.refunded_at = agora()
    pagamento.refund_reason = (motivo or None)

    # O atendimento volta a pendente quando o que sobrou de pagamento
    # deixa de cobrir o combinado. Com pagamento em partes, "existe outro
    # pagamento" não basta: dois pedaços cobriam o total, e tirar um deixa
    # de cobrir — a cobrança precisa voltar.
    if pagamento.appointment_id is not None:
        travado = _travar_atendimento(db, pagamento.appointment_id)
        db.flush()
        combinado = travado.price or ZERO
        ainda = _recebido_do_atendimento(db, travado.id)
        if combinado <= ZERO or ainda < combinado:
            travado.payment_status = "pending"
            travado.payment_method = None
            travado.paid_at = None

    db.flush()
    return pagamento


def isentar(db: Session, ctx, atendimento: Appointment, motivo: Optional[str]) -> Appointment:
    """Isento não é receita nem pendência: é uma decisão do profissional.

    Sem linha no livro-caixa, porque dinheiro nenhum entrou. O motivo fica
    na observação do atendimento para a decisão não virar mistério.
    """
    travado = _travar_atendimento(db, atendimento.id)
    if travado.payment_status == "paid":
        raise errors.conflito(
            "ja_pago",
            "Este atendimento já foi pago. Estorne o pagamento antes de isentar.",
        )

    travado.payment_status = "waived"
    if motivo:
        anterior = (travado.note or "").strip()
        travado.note = (anterior + "\n" if anterior else "") + "Isento: " + motivo
    db.flush()
    return travado
