"""
Direitos do titular: exportar, anonimizar, apagar — e registrar a decisão.

**Exclusão não é DELETE**

Um pedido de exclusão chega como uma frase só ("quero meus dados
apagados") e se resolve em decisões diferentes por tipo de dado:

    cadastro comercial  → pode ser anonimizado
    prontuário          → guarda obrigatória; o CONTEÚDO pode ser
                          destruído, a série não
    financeiro          → obrigação fiscal; fica
    documentos          → depende do que é

Tratar tudo igual erra nos dois sentidos: ou some o que a lei manda
guardar, ou fica o que a pessoa pediu para apagar. Por isso cada pedido
vira itens, e cada item carrega **decisão, motivo e base legal** — inclusive
quando a decisão é *manter*. "Mantivemos" precisa ser tão justificável
quanto "apagamos".

**Anonimizar não é apagar**

O cadastro perde o que identifica (nome, contato, nascimento, responsável)
e ganha um rótulo neutro. A série de atendimentos, os valores e a trilha
continuam — desidentificados. É o que permite a clínica seguir existindo
como negócio sem seguir sabendo quem era aquela pessoa.

É **irreversível** de propósito: anonimização que dá para desfazer não é
anonimização, é pseudonimização com outro nome.

**Apagar conteúdo é descartar a chave**

Notas e documentos têm sal de derivação por registro. Descartar o sal torna
o conteúdo irrecuperável — inclusive a partir de backup, que guarda
ciphertext e não guarda o sal — sem apagar linha nenhuma. Metadado e
trilha sobrevivem, e é isso que permite responder "houve, foi apagado em
tal data, a pedido".
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import errors
from app.ids import novo_ulid
from app.models.appointment import Appointment
from app.models.client import Client
from app.models.clinical import ClinicalAccessLog, ClinicalNote
from app.models.document import Document
from app.models.lgpd import Consent, DataRequest, DataRequestItem, RetentionPolicy
from app.models.payment import Payment
from app.services import scope
from app.services.sessions import agora


# ---------------- consentimento ----------------
def consentimentos(db: Session, ctx, cliente: Client) -> List[Consent]:
    return list(db.execute(
        select(Consent).where(Consent.client_id == cliente.id).order_by(Consent.id.desc())
    ).scalars())


def registrar_consentimento(db: Session, ctx, cliente: Client, dados) -> Consent:
    import hashlib

    consentimento = Consent(
        public_id=novo_ulid(),
        tenant_id=ctx.tenant_id,
        client_id=cliente.id,
        kind=dados.tipo,
        version=(dados.versao or "1")[:40],
        text_hash=hashlib.sha256(dados.texto.encode("utf-8")).hexdigest() if dados.texto else None,
        granted_at=dados.em or agora(),
        source=dados.origem or "in_person",
        note=(dados.observacao or None),
        registered_by_user_id=ctx.usuario.id,
    )
    db.add(consentimento)
    db.flush()
    return consentimento


def revogar_consentimento(db: Session, ctx, public_id: str) -> Consent:
    achado = db.execute(
        select(Consent).where(Consent.public_id == public_id)
    ).scalar_one_or_none()
    if achado is None:
        raise errors.nao_encontrado("consentimento")
    if achado.revoked_at is not None:
        raise errors.conflito("ja_revogado", "Este consentimento já estava revogado.")
    achado.revoked_at = agora()
    db.flush()
    return achado


# ---------------- pedidos ----------------
def listar_pedidos(db: Session, ctx, *, status: Optional[str] = None) -> List[DataRequest]:
    consulta = select(DataRequest)
    if status and status != "todos":
        consulta = consulta.where(DataRequest.status == status)
    return list(db.execute(consulta.order_by(DataRequest.id.desc())).scalars())


def obter_pedido(db: Session, ctx, public_id: str) -> DataRequest:
    achado = db.execute(
        select(DataRequest).where(DataRequest.public_id == public_id)
    ).scalar_one_or_none()
    if achado is None:
        raise errors.nao_encontrado("pedido")
    return achado


def itens_do_pedido(db: Session, pedido: DataRequest) -> List[DataRequestItem]:
    """Busca as decisões direto, sem depender da relação carregada.

    A relação é `viewonly` e já vem preenchida quando o pedido é lido; uma
    decisão criada no meio da requisição não apareceria nela. Consultar de
    novo custa uma query e evita responder com a lista velha — que é o
    tipo de bug que só aparece na tela de quem está usando.
    """
    return list(db.execute(
        select(DataRequestItem)
        .where(DataRequestItem.request_id == pedido.id)
        .order_by(DataRequestItem.id)
    ).scalars())


def abrir_pedido(db: Session, ctx, cliente: Client, dados) -> DataRequest:
    pedido = DataRequest(
        public_id=novo_ulid(),
        tenant_id=ctx.tenant_id,
        client_id=cliente.id,
        kind=dados.tipo,
        status="open",
        requested_at=dados.em or agora(),
        due_at=dados.prazo,          # nulo por padrão: nenhum prazo é chutado aqui
        requester=(dados.solicitante or "titular")[:120],
        note=(dados.observacao or None),
        registered_by_user_id=ctx.usuario.id,
    )
    db.add(pedido)
    db.flush()
    return pedido


def decidir(db: Session, ctx, pedido: DataRequest, dados) -> DataRequestItem:
    """Acrescenta uma decisão ao pedido. Motivo é obrigatório — sempre.

    Inclusive para `keep`: manter prontuário contra um pedido de exclusão é
    legítimo, e é exatamente o que precisa estar escrito antes de alguém
    perguntar.
    """
    if pedido.status in ("done", "refused"):
        raise errors.conflito("pedido_encerrado", "Este pedido já foi encerrado.")
    if not (dados.motivo or "").strip():
        raise errors.dados_invalidos("Toda decisão precisa de motivo registrado.")

    item = DataRequestItem(
        public_id=novo_ulid(),
        tenant_id=ctx.tenant_id,
        request_id=pedido.id,
        target=dados.alvo,
        decision=dados.decisao,
        reason=dados.motivo.strip()[:300],
        legal_basis=(dados.base_legal or None),
    )
    db.add(item)
    if pedido.status == "open":
        pedido.status = "in_progress"
    db.flush()
    return item


def aplicar(db: Session, ctx, pedido: DataRequest, item: DataRequestItem) -> DataRequestItem:
    """Executa a decisão. É aqui que a coisa realmente acontece."""
    if item.applied_at is not None:
        raise errors.conflito("ja_aplicado", "Esta decisão já foi executada.")

    cliente = db.execute(
        select(Client).where(Client.id == pedido.client_id)
    ).scalar_one_or_none()
    if cliente is None:
        raise errors.nao_encontrado("cliente")

    resultado = ""
    if item.decision == "keep":
        resultado = "mantido por decisão registrada"

    elif item.decision == "restrict":
        # Restrição de tratamento: a pessoa sai do fluxo ativo sem perder
        # o histórico. Arquivar é exatamente isso.
        cliente.status = "archived"
        cliente.archived_at = agora()
        resultado = "cadastro arquivado (tratamento restrito)"

    elif item.decision == "anonymize":
        resultado = anonimizar(db, ctx, cliente, motivo=item.reason)

    elif item.decision == "erase":
        resultado = _apagar(db, ctx, cliente, item.target, item.reason)

    elif item.decision == "export":
        resultado = "pacote de dados gerado e entregue"

    item.applied_at = agora()
    item.applied_by_user_id = ctx.usuario.id
    item.result = resultado[:300]
    db.flush()
    return item


def _apagar(db: Session, ctx, cliente: Client, alvo: str, motivo: str) -> str:
    """Destrói conteúdo — sem apagar registro de que ele existiu."""
    from app.services import clinical as servico_clinical
    from app.services import documents as servico_documentos

    if alvo == "clinical":
        notas = list(db.execute(
            select(ClinicalNote).where(ClinicalNote.client_id == cliente.id,
                                       ClinicalNote.content_erased_at.is_(None))
        ).scalars())
        for nota in notas:
            servico_clinical.esquecer_conteudo(db, ctx, nota, motivo)
        return f"{len(notas)} registro(s) clínico(s) com conteúdo destruído"

    if alvo == "documents":
        docs = list(db.execute(
            select(Document).where(Document.client_id == cliente.id,
                                   Document.content_erased_at.is_(None))
        ).scalars())
        for doc in docs:
            servico_documentos.apagar_conteudo(db, ctx, doc, motivo)
        return f"{len(docs)} documento(s) com arquivo destruído"

    if alvo == "registration":
        return anonimizar(db, ctx, cliente, motivo=motivo)

    if alvo in ("payments", "appointments"):
        # Obrigação fiscal e registro de atendimento não se apagam a
        # pedido. A recusa é resposta, e fica escrita.
        raise errors.conflito(
            "apagar_nao_se_aplica",
            "Lançamento financeiro e histórico de atendimento têm guarda obrigatória. "
            "Registre a decisão como 'manter', com a base legal.")

    raise errors.dados_invalidos("Alvo não reconhecido para exclusão.")


ANONIMO = "Pessoa anonimizada"


def anonimizar(db: Session, ctx, cliente: Client, *, motivo: str = "") -> str:
    """Remove o que identifica. Irreversível de propósito.

    Anonimização que dá para desfazer não é anonimização — é
    pseudonimização com outro nome.
    """
    if cliente.anonymized_at is not None:
        raise errors.conflito("ja_anonimizado", "Este cadastro já foi anonimizado.")

    cliente.name = f"{ANONIMO} {cliente.public_id[-6:]}"
    cliente.email = None
    cliente.phone = None
    cliente.birth_date = None
    cliente.guardian = None
    cliente.notes = None
    cliente.status = "archived"
    cliente.anonymized_at = agora()
    if cliente.archived_at is None:
        cliente.archived_at = agora()
    db.flush()
    return "cadastro anonimizado (série de atendimentos preservada, sem titular identificável)"


def encerrar(db: Session, ctx, pedido: DataRequest, *, status: str,
             observacao: Optional[str]) -> DataRequest:
    if status not in ("done", "refused"):
        raise errors.dados_invalidos("Situação de encerramento não reconhecida.")
    if status == "refused" and not (observacao or "").strip():
        # Recusar sem explicar não é resposta.
        raise errors.dados_invalidos("Recusar um pedido do titular exige motivo escrito.")
    pendentes = [i for i in itens_do_pedido(db, pedido)
                 if i.applied_at is None and i.decision != "keep"]
    if status == "done" and pendentes:
        raise errors.conflito(
            "decisoes_pendentes",
            f"Há {len(pendentes)} decisão(ões) registrada(s) e não executada(s).")

    pedido.status = status
    pedido.closed_at = agora()
    pedido.outcome_note = (observacao or None)
    db.flush()
    return pedido


# ---------------- pacote de portabilidade ----------------
def pacote(db: Session, ctx, cliente: Client, *, com_clinico: bool) -> dict:
    """Tudo o que a conta tem sobre a pessoa, em formato legível.

    O conteúdo clínico entra **apenas** se quem está gerando já podia lê-lo
    — a portabilidade não é atalho para o prontuário alheio. Quando fica de
    fora, o pacote diz que existe e que não foi incluído, em vez de
    simplesmente omitir.
    """
    from app.services import clinical as servico_clinical

    atendimentos = list(db.execute(
        scope.atendimentos(select(Appointment).where(Appointment.client_id == cliente.id), ctx)
        .order_by(Appointment.start_at)
    ).scalars())

    pagamentos = []
    if ctx.pode("finance.read"):
        pagamentos = list(db.execute(
            select(Payment).where(Payment.client_id == cliente.id).order_by(Payment.paid_at)
        ).scalars())

    documentos = list(db.execute(
        select(Document).where(Document.client_id == cliente.id).order_by(Document.id)
    ).scalars())

    saida = {
        "gerado_em": agora().isoformat(),
        "conta": ctx.membership.tenant.name,
        "cadastro": {
            "id": cliente.public_id,
            "nome": cliente.name,
            "email": cliente.email,
            "telefone": cliente.phone,
            "nascimento": cliente.birth_date.isoformat() if cliente.birth_date else None,
            "situacao": cliente.status,
            "desde": cliente.started_at.isoformat() if cliente.started_at else None,
            "anonimizado_em": cliente.anonymized_at.isoformat() if cliente.anonymized_at else None,
        },
        "atendimentos": [
            {
                "id": a.public_id,
                "inicio": a.start_at.isoformat(),
                "duracao_min": a.duration_min,
                "modalidade": a.modality,
                "situacao": a.status,
                "valor": str(a.price) if a.price is not None else None,
                "pagamento": a.payment_status,
            }
            for a in atendimentos
        ],
        "pagamentos": [
            {
                "id": p.public_id,
                "pago_em": p.paid_at.isoformat(),
                "valor": str(p.amount),
                "meio": p.method,
                "situacao": p.status,
            }
            for p in pagamentos
        ],
        "documentos": [
            {
                "id": d.public_id,
                "tipo": d.kind,
                "titulo": d.title,
                "emitido_em": d.created_at.isoformat(),
                "conteudo_apagado_em": (d.content_erased_at.isoformat()
                                        if d.content_erased_at else None),
            }
            for d in documentos
        ],
        "consentimentos": [
            {
                "tipo": c.kind,
                "versao": c.version,
                "aceito_em": c.granted_at.isoformat(),
                "revogado_em": c.revoked_at.isoformat() if c.revoked_at else None,
            }
            for c in consentimentos(db, ctx, cliente)
        ],
    }

    notas = list(db.execute(
        select(ClinicalNote).where(ClinicalNote.client_id == cliente.id)
    ).scalars())

    if com_clinico and ctx.pode("clinical_records.read"):
        legiveis = servico_clinical.listar(db, ctx, cliente)
        registros = []
        for nota in legiveis:
            item = {
                "id": nota.public_id,
                "tipo": nota.kind,
                "ocorrido_em": nota.occurred_at.isoformat(),
                "versao": nota.current_version,
                "assinada_em": nota.signed_at.isoformat() if nota.signed_at else None,
            }
            try:
                item["conteudo"], _v = servico_clinical.ler(db, ctx, nota)
            except errors.ApiError:
                item["conteudo"] = None
                item["observacao"] = "conteúdo indisponível"
            registros.append(item)
        saida["registros_clinicos"] = registros
        if len(legiveis) < len(notas):
            saida["registros_clinicos_nao_incluidos"] = len(notas) - len(legiveis)
    else:
        # Dizer que existe e não foi incluído é diferente de omitir.
        saida["registros_clinicos"] = None
        saida["registros_clinicos_existentes"] = len(notas)
        saida["observacao_clinica"] = (
            "Os registros clínicos existem e não foram incluídos neste pacote: "
            "quem o gerou não tem acesso de leitura a eles.")

    saida["acessos_ao_prontuario"] = len(list(db.execute(
        select(ClinicalAccessLog).where(ClinicalAccessLog.client_id == cliente.id)
    ).scalars()))
    return saida


# ---------------- retenção ----------------
def politicas(db: Session, ctx) -> List[RetentionPolicy]:
    return list(db.execute(
        select(RetentionPolicy).order_by(RetentionPolicy.record_kind)
    ).scalars())


def definir_politica(db: Session, ctx, dados) -> RetentionPolicy:
    from app.models.profession import Profession

    profession_id = None
    if dados.profissao:
        achada = db.execute(
            select(Profession).where(Profession.slug == dados.profissao)
        ).scalar_one_or_none()
        if achada is None:
            raise errors.dados_invalidos("Profissão não reconhecida.")
        profession_id = achada.id

    if dados.meses is not None and not (dados.base_legal or "").strip():
        # Prazo sem base legal é chute com cara de regra.
        raise errors.dados_invalidos(
            "Prazo de guarda exige base legal escrita — sem ela, a política não vale "
            "para apagar nada.")

    existente = db.execute(
        select(RetentionPolicy).where(
            RetentionPolicy.record_kind == dados.alvo,
            RetentionPolicy.profession_id == profession_id,
        )
    ).scalar_one_or_none()

    if existente is None:
        existente = RetentionPolicy(
            public_id=novo_ulid(), tenant_id=ctx.tenant_id,
            record_kind=dados.alvo, profession_id=profession_id,
        )
        db.add(existente)

    existente.months = dados.meses
    existente.legal_basis = (dados.base_legal or None)
    existente.note = (dados.observacao or None)
    db.flush()
    return existente
