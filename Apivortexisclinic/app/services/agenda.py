"""
Recorrência e bloqueios de horário.

**A série gera, e depois solta**

Criar uma recorrência gera atendimentos de verdade, um por ocorrência, até
um horizonte finito. Depois disso a série não manda mais em ninguém: cada
sessão é remarcada, cancelada ou cobrada por conta própria. A série
continua existindo só para responder "quais são irmãos deste" quando
alguém quiser mexer em todos de uma vez.

**Conflito não cancela a série inteira**

Se um dos horários já está ocupado, a ocorrência é **pulada** e volta na
resposta, listada. Recusar as doze porque a terceira bateu seria obedecer
à máquina em vez de à pessoa — que quer as onze livres marcadas e saber da
uma que faltou.

**Bloqueio ocupa horário e nada mais**

Férias, feriado e almoço não são atendimentos de um cliente falso: se
fossem, entrariam em contagem, presença e financeiro, e um dia alguém
tentaria cobrar por eles. São tabela própria, e a única coisa que fazem é
impedir agendamento em cima.

Criar bloqueio por cima de atendimento já marcado é **recusado** por
padrão, com a lista do que está lá dentro. Quem quiser bloquear assim
mesmo passa `forcar=true` — e nesse caso os atendimentos **continuam de
pé**: o sistema não cancela sessão de ninguém por conta própria.
"""
from datetime import date, datetime, time, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import errors
from app.ids import novo_ulid
from app.models.agenda import MAX_OCORRENCIAS, AppointmentSeries, ScheduleBlock
from app.models.appointment import OCUPAM_HORARIO, Appointment
from app.models.client import Client
from app.models.professional import Professional
from app.services import scope
from app.services.sessions import agora

PASSO = {"weekly": 7, "biweekly": 14}


# ---------------- bloqueios ----------------
def bloqueios_no_periodo(db: Session, ctx, de: datetime, ate: datetime,
                         professional_id: Optional[int] = None) -> List[ScheduleBlock]:
    consulta = select(ScheduleBlock).where(
        ScheduleBlock.start_at < ate, ScheduleBlock.end_at > de
    )
    if professional_id is not None:
        # Bloqueio da conta (professional_id nulo) vale para todo mundo.
        consulta = consulta.where(
            (ScheduleBlock.professional_id == professional_id)
            | (ScheduleBlock.professional_id.is_(None))
        )
    return list(db.execute(consulta.order_by(ScheduleBlock.start_at)).scalars())


def bloqueio_que_cobre(db: Session, ctx, professional_id: int,
                       inicio: datetime, duracao: int) -> Optional[ScheduleBlock]:
    fim = inicio + timedelta(minutes=duracao)
    for b in bloqueios_no_periodo(db, ctx, inicio, fim, professional_id):
        if b.cobre(inicio, fim):
            return b
    return None


def listar_bloqueios(db: Session, ctx, *, de: Optional[datetime] = None,
                     ate: Optional[datetime] = None, limite: int = 200) -> List[ScheduleBlock]:
    consulta = select(ScheduleBlock)
    if de is not None:
        consulta = consulta.where(ScheduleBlock.end_at > de)
    if ate is not None:
        consulta = consulta.where(ScheduleBlock.start_at < ate)
    if not ctx.ve_tudo and ctx.professional_id is not None:
        consulta = consulta.where(
            (ScheduleBlock.professional_id == ctx.professional_id)
            | (ScheduleBlock.professional_id.is_(None))
        )
    return list(db.execute(
        consulta.order_by(ScheduleBlock.start_at).limit(limite)).scalars())


def obter_bloqueio(db: Session, ctx, public_id: str) -> ScheduleBlock:
    achado = db.execute(
        select(ScheduleBlock).where(ScheduleBlock.public_id == public_id)
    ).scalar_one_or_none()
    if achado is None:
        raise errors.nao_encontrado("bloqueio")
    return achado


def criar_bloqueio(db: Session, ctx, dados) -> Tuple[ScheduleBlock, List[Appointment]]:
    if dados.fim <= dados.inicio:
        raise errors.dados_invalidos("O fim do bloqueio precisa ser depois do início.")
    if (dados.fim - dados.inicio) > timedelta(days=366):
        raise errors.dados_invalidos("Bloqueio de mais de um ano: divida em períodos.")

    # Padrão: bloqueia a SUA agenda. Marcar férias não deveria fechar a
    # clínica inteira por descuido — travar todo mundo é uma decisão que
    # precisa ser dita (`conta_inteira`).
    professional_id = None
    if dados.profissional_id:
        alvo = db.execute(
            select(Professional).where(Professional.public_id == dados.profissional_id)
        ).scalar_one_or_none()
        if alvo is None:
            raise errors.dados_invalidos("Profissional não encontrado nesta conta.")
        professional_id = alvo.id
    elif dados.conta_inteira:
        if not ctx.ve_tudo:
            # Quem só enxerga o próprio não fecha a agenda dos outros.
            raise errors.sem_permissao()
        professional_id = None
    else:
        professional_id = ctx.professional_id
        if professional_id is None:
            if not ctx.ve_tudo:
                raise errors.dados_invalidos(
                    "Seu acesso não tem perfil profissional para bloquear horário.")
            # Administra e não atende: só faz sentido bloquear a conta.
            professional_id = None

    # O que já está marcado dentro da faixa.
    consulta = scope.atendimentos(
        select(Appointment).where(
            Appointment.start_at < dados.fim,
            Appointment.start_at >= dados.inicio - timedelta(hours=8),
            Appointment.status.in_(OCUPAM_HORARIO),
        ), ctx
    )
    if professional_id is not None:
        consulta = consulta.where(Appointment.professional_id == professional_id)

    dentro = []
    for a in db.execute(consulta).scalars():
        fim_a = a.start_at + timedelta(minutes=a.duration_min or 0)
        if a.start_at < dados.fim and fim_a > dados.inicio:
            dentro.append(a)

    if dentro and not dados.forcar:
        raise errors.conflito(
            "atendimentos_no_periodo",
            f"Há {len(dentro)} atendimento(s) marcado(s) nesse período. "
            "Remarque antes, ou confirme para bloquear mesmo assim.")

    bloqueio = ScheduleBlock(
        public_id=novo_ulid(),
        tenant_id=ctx.tenant_id,
        professional_id=professional_id,
        start_at=dados.inicio,
        end_at=dados.fim,
        kind=dados.tipo or "other",
        title=(dados.titulo or "").strip()[:120] or "Indisponível",
        created_by_user_id=ctx.usuario.id,
    )
    db.add(bloqueio)
    db.flush()
    # Os atendimentos que já estavam lá continuam de pé: o sistema não
    # cancela sessão de ninguém por conta própria.
    return bloqueio, dentro


def remover_bloqueio(db: Session, ctx, bloqueio: ScheduleBlock) -> None:
    db.delete(bloqueio)
    db.flush()


# ---------------- recorrência ----------------
def _datas(frequencia: str, inicio: date, quantidade: int,
           ate: Optional[date]) -> List[date]:
    """Gera as datas do molde. Mensal repete o dia do mês, não a semana."""
    saida = []
    atual = inicio
    for _ in range(quantidade):
        if ate is not None and atual > ate:
            break
        saida.append(atual)
        if frequencia == "monthly":
            mes = atual.month + 1
            ano = atual.year + (1 if mes > 12 else 0)
            mes = 1 if mes > 12 else mes
            dia = atual.day
            while True:
                try:
                    atual = date(ano, mes, dia)
                    break
                except ValueError:
                    # 31 de janeiro + 1 mês não existe em fevereiro: cai
                    # para o último dia do mês, em vez de pular o mês.
                    dia -= 1
        else:
            atual = atual + timedelta(days=PASSO.get(frequencia, 7))
    return saida


def criar_serie(db: Session, ctx, dados) -> Tuple[AppointmentSeries, List[Appointment], List[dict]]:
    """Cria a série e as ocorrências. Devolve (série, criados, conflitos)."""
    from app.services import appointments as servico_atendimentos

    cliente = db.execute(
        scope.clientes(select(Client).where(Client.public_id == dados.cliente_id), ctx)
    ).scalar_one_or_none()
    if cliente is None:
        raise errors.nao_encontrado("cliente")

    professional_id = scope.profissional_alvo(ctx, None)
    if dados.profissional_id and ctx.ve_tudo:
        alvo = db.execute(
            select(Professional).where(Professional.public_id == dados.profissional_id)
        ).scalar_one_or_none()
        if alvo is None:
            raise errors.dados_invalidos("Profissional não encontrado nesta conta.")
        professional_id = alvo.id
    if professional_id is None:
        raise errors.dados_invalidos(
            "É preciso um profissional responsável — seu acesso não tem perfil profissional.")

    quantidade = int(dados.ocorrencias or 8)
    if not (1 <= quantidade <= MAX_OCORRENCIAS):
        raise errors.dados_invalidos(
            f"A recorrência vai de 1 a {MAX_OCORRENCIAS} ocorrências. "
            "Recorrência infinita vira agenda que ninguém consegue limpar.")

    duracao = int(dados.duracao_min or 50)
    primeiro = dados.inicio
    servico_atendimentos._validar_horario(primeiro, duracao)

    serie = AppointmentSeries(
        public_id=novo_ulid(),
        tenant_id=ctx.tenant_id,
        client_id=cliente.id,
        professional_id=professional_id,
        frequency=dados.frequencia or "weekly",
        start_time=time(primeiro.hour, primeiro.minute),
        duration_min=duracao,
        modality=dados.modalidade or cliente.default_modality,
        price=dados.valor if dados.valor is not None else cliente.default_price,
        starts_on=primeiro.date(),
        ends_on=dados.ate,
        occurrences=quantidade,
        status="active",
        note=(dados.observacao or None),
        created_by_user_id=ctx.usuario.id,
    )
    db.add(serie)
    db.flush()

    criados, conflitos = [], []
    for indice, dia in enumerate(_datas(serie.frequency, primeiro.date(), quantidade, dados.ate), 1):
        quando = datetime.combine(dia, time(primeiro.hour, primeiro.minute))

        ocupado = servico_atendimentos._conflito(
            db, ctx.tenant_id, professional_id, quando, duracao)
        if ocupado is not None:
            conflitos.append({"inicio": quando, "motivo": "conflito_de_horario"})
            continue

        bloqueio = bloqueio_que_cobre(db, ctx, professional_id, quando, duracao)
        if bloqueio is not None:
            conflitos.append({"inicio": quando, "motivo": "horario_bloqueado",
                              "detalhe": bloqueio.title})
            continue

        atendimento = Appointment(
            public_id=novo_ulid(),
            tenant_id=ctx.tenant_id,
            client_id=cliente.id,
            professional_id=professional_id,
            start_at=quando,
            duration_min=duracao,
            modality=serie.modality,
            status="scheduled",
            price=serie.price,
            payment_status="pending",
            note=serie.note,
            series_id=serie.id,
            series_index=indice,
            created_by_user_id=ctx.usuario.id,
        )
        db.add(atendimento)
        criados.append(atendimento)

    db.flush()
    if not criados:
        raise errors.conflito(
            "nenhuma_ocorrencia_livre",
            "Todos os horários dessa recorrência estão ocupados ou bloqueados.")
    return serie, criados, conflitos


def obter_serie(db: Session, ctx, public_id: str) -> AppointmentSeries:
    achada = db.execute(
        select(AppointmentSeries).where(AppointmentSeries.public_id == public_id)
    ).scalar_one_or_none()
    if achada is None:
        raise errors.nao_encontrado("série")
    if not ctx.ve_tudo and achada.professional_id != ctx.professional_id:
        raise errors.nao_encontrado("série")
    return achada


def futuros_da_serie(db: Session, ctx, serie: AppointmentSeries,
                     a_partir_de: Optional[datetime] = None) -> List[Appointment]:
    momento = a_partir_de or agora()
    consulta = scope.atendimentos(
        select(Appointment).where(
            Appointment.series_id == serie.id,
            Appointment.start_at >= momento,
            Appointment.status.in_(("scheduled", "confirmed")),
        ), ctx
    ).order_by(Appointment.start_at)
    return list(db.execute(consulta).scalars())


def encerrar_serie(db: Session, ctx, serie: AppointmentSeries, motivo: Optional[str],
                   cancelar_futuros: bool = True) -> Tuple[AppointmentSeries, int]:
    """Encerra o molde. Opcionalmente cancela as ocorrências futuras.

    Passado nunca é tocado: sessão que já aconteceu é fato, não plano.
    """
    serie.status = "ended"
    serie.ended_at = agora()

    cancelados = 0
    if cancelar_futuros:
        for a in futuros_da_serie(db, ctx, serie):
            a.status = "cancelled"
            a.cancelled_reason = (motivo or "Recorrência encerrada")[:200]
            cancelados += 1
    db.flush()
    return serie, cancelados
