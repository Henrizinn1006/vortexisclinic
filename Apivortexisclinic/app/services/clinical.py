"""
Prontuário: quem pode ler, quem pode escrever, e o registro de ambos.

Este arquivo concentra as decisões que o resto da etapa apenas obedece.

**Quatro portas, nesta ordem**

    1. tenant      — resolvido pela sessão, aplicado pelo ORM (fail-closed)
    2. permissão   — `clinical_records.read` / `.write` / `.read_others`
    3. alcance     — o cliente é seu? (`client_professionals`)
    4. autoria     — a nota é sua? senão, exige `.read_others` para ler,
                     e nunca libera escrever

Administrar a conta não abre nenhuma dessas portas. O dono não tem
permissão da classe clínica na matriz, então para ele a porta 2 já fecha —
mesmo sendo dono, mesmo tendo `members.manage`, mesmo pagando a conta. Se
o dono também atende, ele passa por ter perfil profissional, não por ser
dono.

**Nota fora do alcance responde "não existe"**

Não 403. Dizer "existe, mas não é sua" já entrega que aquela pessoa é
atendida por alguém ali dentro — e num consultório de saúde mental isso
é, sozinho, a informação sensível. A lista some, o acesso direto dá 404, e
a tentativa fica registrada na trilha.

**A trilha grava a negativa**

Leitura autorizada é rotina; tentativa recusada é sinal. As duas entram em
`clinical_access_log`, e a negativa é confirmada no banco **antes** de a
exceção subir — senão o rollback da requisição apagaria justamente o
registro que interessa.

**Editar não altera linha**

Cada salvamento insere a versão seguinte. Não existe UPDATE de conteúdo
neste arquivo. Depois de assinada, a nota ainda aceita adendo — com motivo
obrigatório —, e o adendo é mais uma versão, nunca uma correção por cima.
"""
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import Select, and_, exists, select
from sqlalchemy.orm import Session

from app import errors
from app.ids import novo_ulid
from app.models.appointment import Appointment
from app.models.client import Client, ClientProfessional
from app.models.clinical import ClinicalAccessLog, ClinicalNote, ClinicalNoteVersion
from app.security import crypto
from app.services import scope
from app.services.sessions import agora

TAMANHO_MAXIMO = 20000
IMPOSSIVEL = ClinicalNote.id == None  # noqa: E711


# ---------------- trilha ----------------
def registrar(db: Session, ctx, *, acao: str, resultado: str = "allowed",
              client_id: Optional[int] = None, note_id: Optional[int] = None,
              motivo: Optional[str] = None, confirmar: bool = False) -> None:
    """Uma linha na trilha. `confirmar=True` fecha a transação na hora."""
    db.add(ClinicalAccessLog(
        public_id=novo_ulid(),
        tenant_id=ctx.tenant_id,
        user_id=ctx.usuario.id,
        membership_id=ctx.membership.id if ctx.membership else None,
        client_id=client_id,
        note_id=note_id,
        action=acao,
        outcome=resultado,
        reason=motivo,
        auth_session_id=getattr(ctx.sessao, "id", None),
    ))
    if confirmar:
        db.commit()


def negar(db: Session, ctx, *, acao: str, motivo: str,
          client_id: Optional[int] = None, note_id: Optional[int] = None,
          erro=None):
    """Registra a recusa, confirma no banco e levanta o erro.

    O commit vem antes do raise de propósito: a requisição vai ser
    descartada, e a linha da trilha não pode ir junto.
    """
    registrar(db, ctx, acao=acao, resultado="denied", client_id=client_id,
              note_id=note_id, motivo=motivo, confirmar=True)
    raise erro or errors.nao_encontrado("registro clínico")


# ---------------- alcance ----------------
def _vinculo_com_o_cliente(ctx):
    return exists().where(
        and_(
            ClientProfessional.tenant_id == ClinicalNote.tenant_id,
            ClientProfessional.client_id == ClinicalNote.client_id,
            ClientProfessional.professional_id == ctx.professional_id,
            ClientProfessional.ended_at.is_(None),
        )
    )


def legivel(consulta: Select, ctx) -> Select:
    """Filtra a consulta ao que esta pessoa pode ler. Fail-closed em tudo."""
    if not ctx.pode("clinical_records.read"):
        return consulta.where(IMPOSSIVEL)

    # Alcance do cliente: em "own", só quem é seu.
    if not ctx.ve_tudo:
        if ctx.professional_id is None:
            return consulta.where(IMPOSSIVEL)
        consulta = consulta.where(_vinculo_com_o_cliente(ctx))

    # Autoria: sem `read_others`, só as próprias — inclusive para quem
    # enxerga a conta inteira. Ver a conta toda é alcance administrativo;
    # não vira leitura de prontuário alheio.
    if not ctx.pode("clinical_records.read_others"):
        if ctx.professional_id is None:
            return consulta.where(IMPOSSIVEL)
        consulta = consulta.where(ClinicalNote.professional_id == ctx.professional_id)

    return consulta


# ---------------- leitura ----------------
def listar(db: Session, ctx, cliente: Client, *, limite: int = 200) -> List[ClinicalNote]:
    consulta = legivel(
        select(ClinicalNote).where(ClinicalNote.client_id == cliente.id), ctx
    ).order_by(ClinicalNote.occurred_at.desc()).limit(limite)
    achadas = list(db.execute(consulta).scalars())
    registrar(db, ctx, acao="list", client_id=cliente.id, confirmar=True)
    return achadas


def obter(db: Session, ctx, public_id: str, *, acao: str = "read") -> ClinicalNote:
    """Busca por id público dentro do que esta pessoa alcança.

    Fora do alcance responde "não existe" — e a tentativa fica na trilha.
    """
    nota = db.execute(
        legivel(select(ClinicalNote).where(ClinicalNote.public_id == public_id), ctx)
    ).scalar_one_or_none()
    if nota is None:
        negar(db, ctx, acao=acao, motivo="fora_do_alcance")
    return nota


def versao(db: Session, ctx, nota: ClinicalNote, numero: Optional[int] = None) -> ClinicalNoteVersion:
    alvo = numero if numero is not None else nota.current_version
    achada = db.execute(
        select(ClinicalNoteVersion).where(
            ClinicalNoteVersion.note_id == nota.id,
            ClinicalNoteVersion.version == alvo,
        )
    ).scalar_one_or_none()
    if achada is None:
        raise errors.nao_encontrado("versão")
    return achada


def ler(db: Session, ctx, nota: ClinicalNote, numero: Optional[int] = None) -> Tuple[str, ClinicalNoteVersion]:
    """Decifra e registra a leitura. É aqui — e só aqui — que o texto aparece."""
    alvo = versao(db, ctx, nota, numero)
    try:
        texto = crypto.decifrar(
            alvo.ciphertext, nonce=alvo.nonce, sal=nota.content_key_salt,
            versao_chave=alvo.key_version, tenant_id=nota.tenant_id,
            nota_id=nota.id, versao=alvo.version,
        )
    except crypto.ConteudoIlegivel:
        registrar(db, ctx, acao="read", resultado="denied", client_id=nota.client_id,
                  note_id=nota.id, motivo="conteudo_ilegivel", confirmar=True)
        if nota.content_erased_at is not None:
            raise errors.conflito("conteudo_apagado",
                                  "O conteúdo desta nota foi apagado a pedido do titular.")
        raise errors.conflito("conteudo_ilegivel",
                              "O conteúdo não pôde ser aberto. O registro foi preservado.")

    registrar(db, ctx, acao="read", client_id=nota.client_id, note_id=nota.id, confirmar=True)
    return texto, alvo


def historico(db: Session, ctx, nota: ClinicalNote) -> List[ClinicalNoteVersion]:
    """Metadado das versões — sem decifrar nada."""
    return list(db.execute(
        select(ClinicalNoteVersion)
        .where(ClinicalNoteVersion.note_id == nota.id)
        .order_by(ClinicalNoteVersion.version)
    ).scalars())


def trilha_do_cliente(db: Session, ctx, cliente: Client, *, limite: int = 200):
    """Quem abriu o prontuário desta pessoa. Exige `audit.read` na rota."""
    return list(db.execute(
        select(ClinicalAccessLog)
        .where(ClinicalAccessLog.client_id == cliente.id)
        .order_by(ClinicalAccessLog.created_at.desc())
        .limit(limite)
    ).scalars())


# ---------------- escrita ----------------
def _autor_ou_recusa(db: Session, ctx, nota: ClinicalNote, acao: str) -> None:
    if ctx.professional_id is None or nota.professional_id != ctx.professional_id:
        negar(db, ctx, acao=acao, motivo="nao_e_autor", client_id=nota.client_id,
              note_id=nota.id, erro=errors.sem_permissao())


def _texto_valido(texto: str) -> str:
    limpo = (texto or "").strip()
    if not limpo:
        raise errors.dados_invalidos("O registro não pode ficar vazio.")
    if len(limpo) > TAMANHO_MAXIMO:
        raise errors.dados_invalidos(
            f"O registro ultrapassa o limite de {TAMANHO_MAXIMO} caracteres."
        )
    return limpo


def _gravar_versao(db: Session, ctx, nota: ClinicalNote, texto: str,
                   *, motivo: Optional[str] = None) -> ClinicalNoteVersion:
    """Insere a próxima versão. Nunca altera a anterior."""
    numero = nota.current_version + 1
    cifrado, nonce, versao_chave = crypto.cifrar(
        texto, sal=nota.content_key_salt, tenant_id=nota.tenant_id,
        nota_id=nota.id, versao=numero,
    )
    linha = ClinicalNoteVersion(
        public_id=novo_ulid(),
        tenant_id=nota.tenant_id,
        note_id=nota.id,
        version=numero,
        ciphertext=cifrado,
        nonce=nonce,
        key_version=versao_chave,
        content_hash=crypto.impressao(texto),
        created_by_membership_id=ctx.membership.id if ctx.membership else None,
        reason=motivo,
    )
    db.add(linha)
    nota.current_version = numero
    return linha


def criar(db: Session, ctx, cliente: Client, dados) -> ClinicalNote:
    if ctx.professional_id is None:
        # Escrever prontuário exige atender. Quem administra a conta e não
        # atende não tem como ser autor.
        negar(db, ctx, acao="create", motivo="sem_perfil_profissional",
              client_id=cliente.id, erro=errors.conflito(
                  "sem_perfil_profissional",
                  "Só quem tem perfil profissional nesta conta registra atendimento."))
    if not scope.alcanca_cliente(db, ctx, cliente.id):
        negar(db, ctx, acao="create", motivo="fora_do_alcance", client_id=cliente.id)

    texto = _texto_valido(dados.conteudo)
    quando = dados.ocorrido_em or agora()
    if quando > agora():
        raise errors.dados_invalidos("A data do registro não pode estar no futuro.")

    appointment_id = None
    if dados.atendimento_id:
        atendimento = db.execute(
            scope.atendimentos(
                select(Appointment).where(Appointment.public_id == dados.atendimento_id), ctx
            )
        ).scalar_one_or_none()
        if atendimento is None or atendimento.client_id != cliente.id:
            raise errors.nao_encontrado("atendimento")
        appointment_id = atendimento.id

    nota = ClinicalNote(
        public_id=novo_ulid(),
        tenant_id=ctx.tenant_id,
        client_id=cliente.id,
        professional_id=ctx.professional_id,
        appointment_id=appointment_id,
        kind=dados.tipo or "session",
        status="draft",
        occurred_at=quando,
        content_key_salt=crypto.novo_sal(),
        current_version=0,
    )
    db.add(nota)
    db.flush()                      # precisa do id: ele entra no AAD da cifra

    _gravar_versao(db, ctx, nota, texto)
    registrar(db, ctx, acao="create", client_id=cliente.id, note_id=nota.id)
    return nota


def editar(db: Session, ctx, nota: ClinicalNote, dados) -> ClinicalNote:
    _autor_ou_recusa(db, ctx, nota, "update")
    if nota.content_erased_at is not None:
        raise errors.conflito("conteudo_apagado",
                              "O conteúdo desta nota foi apagado a pedido do titular.")

    texto = _texto_valido(dados.conteudo)
    motivo = (dados.motivo or "").strip() or None

    if nota.assinada and not motivo:
        # Depois de assinar, corrigir é adendo — e adendo sem motivo é
        # rasura. O motivo entra na versão e fica.
        raise errors.dados_invalidos("Nota assinada só aceita adendo com motivo.")

    atual = versao(db, ctx, nota)
    if atual.content_hash == crypto.impressao(texto):
        # Salvar sem mudar não cria versão: o histórico ficaria ilegível
        # de tanto ruído.
        return nota

    _gravar_versao(db, ctx, nota, texto, motivo=motivo)
    registrar(db, ctx, acao="update", client_id=nota.client_id, note_id=nota.id,
              motivo="adendo" if nota.assinada else None)
    return nota


def assinar(db: Session, ctx, nota: ClinicalNote) -> ClinicalNote:
    _autor_ou_recusa(db, ctx, nota, "sign")
    if nota.assinada:
        raise errors.conflito("ja_assinada", "Esta nota já está assinada.")
    if nota.current_version == 0:
        raise errors.conflito("sem_conteudo", "Não há conteúdo para assinar.")

    nota.status = "signed"
    nota.signed_at = agora()
    nota.signed_by_membership_id = ctx.membership.id if ctx.membership else None
    registrar(db, ctx, acao="sign", client_id=nota.client_id, note_id=nota.id)
    return nota


# ---------------- exclusão a pedido do titular ----------------
def esquecer_conteudo(db: Session, ctx, nota: ClinicalNote, motivo: str) -> ClinicalNote:
    """Destrói o conteúdo sem apagar o registro.

    O sal da nota é descartado; sem ele a chave não se deriva e nenhuma
    versão abre — nem a partir de backup, porque backup guarda ciphertext,
    não sal. A ficha, o histórico de versões e a trilha de acesso
    continuam: é o que permite responder "houve atendimento, o conteúdo
    foi apagado em tal data, a pedido" — em vez de fingir que nada
    aconteceu.

    Por que isto não tem rota ainda: prazo e alçada de exclusão são
    decisão do produto, e não foram definidos. O mecanismo existe,
    testado, esperando a regra.
    """
    if not (motivo or "").strip():
        raise errors.dados_invalidos("Apagar conteúdo exige motivo registrado.")
    nota.content_key_salt = None
    nota.content_erased_at = agora()
    registrar(db, ctx, acao="update", client_id=nota.client_id, note_id=nota.id,
              motivo="conteudo_apagado")
    return nota
