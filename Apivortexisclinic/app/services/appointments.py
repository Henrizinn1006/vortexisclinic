"""
Atendimentos — agenda, situação e conflito de horário.

O ponto delicado é o **conflito de horário**. Sobreposição não é `UNIQUE`:
duas sessões conflitam quando os intervalos se cruzam, e isso é regra de
negócio, não restrição de coluna. Por isso a checagem acontece dentro da
transação, com `SELECT ... FOR UPDATE` na agenda daquele profissional —
senão dois cliques simultâneos criam dois atendimentos no mesmo horário.

Cancelado libera a vaga: quem cancelou desmarcou, e o horário volta a valer.
"""
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import errors
from app.ids import novo_ulid
from app.models.appointment import OCUPAM_HORARIO, Appointment
from app.models.client import Client
from app.models.professional import Professional
from app.services import scope
from app.services.sessions import agora

DURACAO_MAXIMA_MIN = 8 * 60


# ---------------- leitura ----------------
def listar(
    db: Session,
    ctx,
    *,
    de: Optional[datetime] = None,
    ate: Optional[datetime] = None,
    cliente_id: Optional[int] = None,
    profissional_id: Optional[int] = None,
    status: Optional[str] = None,
    modalidade: Optional[str] = None,
    pagamento: Optional[str] = None,
    limite: int = 500,
    pagina: int = 0,
) -> List[Appointment]:
    """`pagina` 0 = sem paginação (é o que o dashboard e a agenda usam,
    porque ali o recorte já é a janela de datas)."""
    consulta = scope.atendimentos(select(Appointment), ctx)

    if de is not None:
        consulta = consulta.where(Appointment.start_at >= de)
    if ate is not None:
        consulta = consulta.where(Appointment.start_at <= ate)
    if cliente_id is not None:
        consulta = consulta.where(Appointment.client_id == cliente_id)
    if profissional_id is not None:
        consulta = consulta.where(Appointment.professional_id == profissional_id)
    if status and status != "todos":
        consulta = consulta.where(Appointment.status == status)
    if modalidade and modalidade != "todas":
        consulta = consulta.where(Appointment.modality == modalidade)
    if pagamento and pagamento != "todos":
        consulta = consulta.where(Appointment.payment_status == pagamento)

    consulta = consulta.order_by(Appointment.start_at.asc())
    if pagina and pagina > 0:
        from app.services import paginacao

        deslocamento, tamanho = paginacao.limites(pagina, limite)
        consulta = consulta.offset(deslocamento).limit(tamanho)
    else:
        consulta = consulta.limit(min(limite, 1000))
    return list(db.execute(consulta).scalars())


def contar(db: Session, ctx, **filtros) -> int:
    """Quantos atendimentos casam com o filtro, sem trazer nenhum."""
    from app.services import paginacao

    consulta = scope.atendimentos(select(Appointment), ctx)
    if filtros.get("de") is not None:
        consulta = consulta.where(Appointment.start_at >= filtros["de"])
    if filtros.get("ate") is not None:
        consulta = consulta.where(Appointment.start_at <= filtros["ate"])
    if filtros.get("cliente_id") is not None:
        consulta = consulta.where(Appointment.client_id == filtros["cliente_id"])
    if filtros.get("status") and filtros["status"] != "todos":
        consulta = consulta.where(Appointment.status == filtros["status"])
    if filtros.get("modalidade") and filtros["modalidade"] != "todas":
        consulta = consulta.where(Appointment.modality == filtros["modalidade"])
    if filtros.get("pagamento") and filtros["pagamento"] != "todos":
        consulta = consulta.where(Appointment.payment_status == filtros["pagamento"])
    return paginacao.total(db, consulta)


def obter(db: Session, ctx, public_id: str) -> Appointment:
    consulta = scope.atendimentos(
        select(Appointment).where(Appointment.public_id == public_id), ctx
    )
    achado = db.execute(consulta).scalar_one_or_none()
    if achado is None:
        raise errors.nao_encontrado("atendimento")
    return achado


def do_dia(db: Session, ctx, dia, fuso=None) -> List[Appointment]:
    """Atendimentos de um dia. Com `fuso`, o dia é o da conta.

    Aceita `date` ou `datetime` para não quebrar chamada antiga; o que
    importa é a data. Sem fuso, o corte sai em UTC — que é o que estava
    errado antes e continua servindo só a código interno sem tenant.
    """
    from app.domain import calendario

    d = dia.date() if isinstance(dia, datetime) else dia
    if fuso is not None:
        inicio, fim = calendario.dia(d, fuso)
    else:
        inicio = datetime.combine(d, datetime.min.time())
        fim = inicio + timedelta(days=1) - timedelta(milliseconds=1)
    return listar(db, ctx, de=inicio, ate=fim)


def proximos(db: Session, ctx, quantidade: int = 5) -> List[Appointment]:
    consulta = scope.atendimentos(
        select(Appointment).where(
            Appointment.start_at >= agora(),
            Appointment.status.in_(("scheduled", "confirmed")),
        ), ctx
    ).order_by(Appointment.start_at.asc()).limit(quantidade)
    return list(db.execute(consulta).scalars())


# ---------------- conflito ----------------
def _conflito(
    db: Session, tenant_id: int, professional_id: int,
    inicio: datetime, duracao: int, ignorar_id: Optional[int] = None,
) -> Optional[Appointment]:
    """Devolve o atendimento que ocupa a faixa, se houver.

    Sobreposição: `inicio_novo < fim_existente` E `fim_novo > inicio_existente`.
    Como o banco não guarda `fim`, a janela é limitada pela duração máxima
    permitida e o cruzamento é conferido em Python — com as linhas
    travadas, que é o que impede a corrida.
    """
    fim = inicio + timedelta(minutes=duracao)
    janela_inicio = inicio - timedelta(minutes=DURACAO_MAXIMA_MIN)

    consulta = (
        select(Appointment)
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.professional_id == professional_id,
            Appointment.status.in_(OCUPAM_HORARIO),
            Appointment.start_at >= janela_inicio,
            Appointment.start_at < fim,
        )
        .with_for_update()          # trava a agenda desse profissional
    )
    if ignorar_id is not None:
        consulta = consulta.where(Appointment.id != ignorar_id)

    for existente in db.execute(consulta).scalars():
        fim_existente = existente.start_at + timedelta(minutes=existente.duration_min or 0)
        if inicio < fim_existente and fim > existente.start_at:
            return existente
    return None


def _recusar_se_bloqueado(db: Session, ctx, professional_id: int,
                          inicio: datetime, duracao: int) -> None:
    """Férias, feriado e almoço ocupam horário como qualquer atendimento.

    A checagem fica aqui, e não na rota, porque tem que valer para todo
    caminho que marca horário — criar, remarcar e a recorrência.
    """
    from app.services import agenda as servico_agenda

    bloqueio = servico_agenda.bloqueio_que_cobre(db, ctx, professional_id, inicio, duracao)
    if bloqueio is not None:
        raise errors.conflito(
            "horario_bloqueado",
            f"Esse horário está bloqueado: {bloqueio.title}.")


def _validar_horario(inicio: datetime, duracao: int) -> None:
    if duracao <= 0 or duracao > DURACAO_MAXIMA_MIN:
        raise errors.dados_invalidos("Duração inválida.")
    if inicio.year < 2000 or inicio.year > 2100:
        raise errors.dados_invalidos("Data fora do intervalo aceito.")


# ---------------- escrita ----------------
def criar(db: Session, ctx, dados) -> Appointment:
    cliente = db.execute(
        scope.clientes(select(Client).where(Client.public_id == dados.cliente_id), ctx)
    ).scalar_one_or_none()
    if cliente is None:
        # Cliente de outra conta, ou fora do seu escopo: não existe.
        raise errors.nao_encontrado("cliente")

    profissional_id = scope.profissional_alvo(ctx, None)
    if dados.profissional_id and ctx.ve_tudo:
        alvo = db.execute(
            select(Professional).where(Professional.public_id == dados.profissional_id)
        ).scalar_one_or_none()
        if alvo is None:
            raise errors.dados_invalidos("Profissional não encontrado nesta conta.")
        profissional_id = alvo.id

    if profissional_id is None:
        raise errors.dados_invalidos(
            "É preciso um profissional responsável — seu acesso não tem perfil profissional."
        )

    duracao = dados.duracao_min or 50
    _validar_horario(dados.inicio, duracao)

    ocupado = _conflito(db, ctx.tenant_id, profissional_id, dados.inicio, duracao)
    if ocupado is not None:
        raise errors.conflito(
            "conflito_de_horario",
            "Já existe um atendimento deste profissional nesse horário.",
        )

    _recusar_se_bloqueado(db, ctx, profissional_id, dados.inicio, duracao)

    atendimento = Appointment(
        public_id=novo_ulid(),
        tenant_id=ctx.tenant_id,
        client_id=cliente.id,
        professional_id=profissional_id,
        start_at=dados.inicio,
        duration_min=duracao,
        modality=dados.modalidade or cliente.default_modality,
        status="scheduled",
        price=dados.valor if dados.valor is not None else cliente.default_price,
        payment_status="pending",
        note=(dados.observacao or None),
        created_by_user_id=ctx.usuario.id,
    )
    db.add(atendimento)
    db.flush()
    return atendimento


def reagendar(db: Session, ctx, atendimento: Appointment, inicio: datetime,
              duracao: Optional[int] = None) -> Appointment:
    if atendimento.status == "cancelled":
        raise errors.conflito("atendimento_cancelado", "Um atendimento cancelado não é remarcado.")

    duracao = duracao or atendimento.duration_min
    _validar_horario(inicio, duracao)

    ocupado = _conflito(db, ctx.tenant_id, atendimento.professional_id, inicio, duracao,
                        ignorar_id=atendimento.id)
    if ocupado is not None:
        raise errors.conflito(
            "conflito_de_horario",
            "Já existe um atendimento deste profissional nesse horário.",
        )

    _recusar_se_bloqueado(db, ctx, atendimento.professional_id, inicio, duracao)

    atendimento.start_at = inicio
    atendimento.duration_min = duracao
    db.flush()
    return atendimento


def mudar_status(db: Session, ctx, atendimento: Appointment, novo: str,
                 motivo: Optional[str] = None) -> Appointment:
    """Transições vivem no modelo. Aqui só se aplica o efeito colateral."""
    if novo == atendimento.status:
        return atendimento
    if not atendimento.pode_ir_para(novo):
        raise errors.conflito(
            "transicao_invalida",
            f"Não dá para ir de '{atendimento.status}' para '{novo}'.",
        )

    atendimento.status = novo
    if novo == "cancelled":
        atendimento.cancelled_reason = (motivo or None)
        # Cancelado não gera cobrança por padrão: sai das pendências.
        if atendimento.payment_status == "pending":
            atendimento.payment_status = "waived"
    db.flush()
    return atendimento


def atualizar(db: Session, ctx, atendimento: Appointment, dados) -> Appointment:
    if dados.modalidade is not None:
        atendimento.modality = dados.modalidade
    if dados.valor is not None:
        atendimento.price = dados.valor
    if dados.observacao is not None:
        atendimento.note = dados.observacao or None
    db.flush()
    return atendimento
