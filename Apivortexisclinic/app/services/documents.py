"""
Documentos: emitir, guardar cifrado, entregar — e registrar quem pegou.

**Emitir é diferente de anexar**

Recibo e declaração o sistema **gera**: o conteúdo vem dos dados que já
estão no banco, então não há como divergir do que aconteceu. Anexo a
pessoa manda, e aí o sistema não sabe o que tem dentro — por isso anexo
entra como clínico por precaução.

**Quem abre depende da classe, não do papel**

Recibo é administrativo: recepção emite, dono confere, porque é dinheiro.
Declaração e laudo são clínicos: ler é a mesma porta do prontuário, com as
mesmas quatro perguntas (tenant, permissão, alcance, autoria). Uma
permissão só para os dois acabaria de um jeito previsível — a recepção
enxergando laudo para conseguir imprimir recibo.

**Baixar documento clínico entra na trilha**

Pela mesma razão que abrir uma evolução entra: o estrago de uma leitura
indevida não tem conserto, e a trilha é o que permite descobrir.
"""
import hashlib
import os
import pathlib
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import errors
from app.config import settings
from app.ids import novo_ulid
from app.models.appointment import Appointment
from app.models.client import Client
from app.models.document import CLASSE_DE_TIPO, Document
from app.models.payment import Payment
from app.security import crypto
from app.services import scope
from app.services.sessions import agora

MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")


def _por_extenso(d: datetime) -> str:
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def _moeda(v) -> str:
    return ("R$ " + f"{Decimal(v or 0):,.2f}").replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------- disco ----------------
def _raiz() -> pathlib.Path:
    caminho = pathlib.Path(settings.VC_FILES_DIR)
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho


def _gravar(documento: Document, conteudo: bytes) -> None:
    """Cifra e grava. O nome no disco não diz nada sobre o conteúdo."""
    sal = crypto.novo_sal()
    cifrado, nonce, versao = crypto.cifrar_bytes(
        conteudo, sal=sal, tenant_id=documento.tenant_id, documento_id=documento.id)

    pasta = _raiz() / str(documento.tenant_id)
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"{documento.public_id}.bin"
    caminho.write_bytes(cifrado)

    documento.storage_key = f"{documento.tenant_id}/{documento.public_id}.bin"
    documento.key_salt = sal
    documento.nonce = nonce
    documento.key_version = versao
    documento.size_bytes = len(conteudo)
    documento.content_hash = hashlib.sha256(conteudo).hexdigest()


def ler_arquivo(documento: Document) -> bytes:
    if documento.content_erased_at is not None or not documento.key_salt:
        raise errors.conflito("conteudo_apagado",
                              "O arquivo foi apagado a pedido do titular.")
    caminho = _raiz() / documento.storage_key
    if not caminho.exists():
        raise errors.conflito("arquivo_ausente",
                              "O arquivo não está mais disponível no armazenamento.")
    try:
        return crypto.decifrar_bytes(
            caminho.read_bytes(), nonce=documento.nonce, sal=documento.key_salt,
            versao_chave=documento.key_version, tenant_id=documento.tenant_id,
            documento_id=documento.id)
    except crypto.ConteudoIlegivel:
        raise errors.conflito("conteudo_ilegivel",
                              "O arquivo não pôde ser aberto. O registro foi preservado.")


# ---------------- permissão ----------------
def permissao_de_leitura(documento: Document) -> str:
    return "documents.read" if documento.eh_clinico else "finance.read"


def permissao_de_escrita(tipo: str) -> str:
    return "documents.write" if CLASSE_DE_TIPO.get(tipo) == "clinical" else "finance.write"


def _exigir_leitura(db: Session, ctx, documento: Document) -> None:
    if not ctx.pode(permissao_de_leitura(documento)):
        raise errors.sem_permissao()
    if not scope.alcanca_cliente(db, ctx, documento.client_id):
        raise errors.nao_encontrado("documento")
    # Documento clínico de outro profissional segue a regra do prontuário.
    if (documento.eh_clinico and documento.professional_id
            and documento.professional_id != ctx.professional_id
            and not ctx.pode("clinical_records.read_others")):
        raise errors.nao_encontrado("documento")


# ---------------- leitura ----------------
def listar(db: Session, ctx, cliente: Client) -> List[Document]:
    consulta = select(Document).where(Document.client_id == cliente.id)
    achados = list(db.execute(consulta.order_by(Document.id.desc())).scalars())
    # Filtra em Python porque a regra mistura permissão e autoria — e
    # errar para menos aqui é melhor do que uma cláusula esperta.
    saida = []
    for d in achados:
        try:
            _exigir_leitura(db, ctx, d)
        except errors.ApiError:
            continue
        saida.append(d)
    return saida


def obter(db: Session, ctx, public_id: str) -> Document:
    achado = db.execute(
        select(Document).where(Document.public_id == public_id)
    ).scalar_one_or_none()
    if achado is None:
        raise errors.nao_encontrado("documento")
    _exigir_leitura(db, ctx, achado)
    return achado


# ---------------- emissão ----------------
def _cabecalho(doc, ctx, titulo: str) -> None:
    from app.domain.pdf import NEGRITO

    tenant = ctx.membership.tenant
    doc.linha(tenant.name.upper(), tamanho=15, fonte=NEGRITO)
    doc.linha("Documento emitido pelo Vortexis Clinic", tamanho=9)
    doc.regua()
    doc.titulo_secao(titulo)


def _assinatura(doc, ctx) -> None:
    from sqlalchemy import select as sel

    from app.domain.pdf import NEGRITO
    from app.models.professional import Professional

    doc.espaco(28)
    doc.linha("_" * 40)
    if ctx.professional_id:
        perfil = ctx.db.get(Professional, ctx.professional_id)
        if perfil is not None:
            doc.linha(perfil.display_name, fonte=NEGRITO)
            registro = " ".join(x for x in [perfil.council, perfil.registration_number] if x)
            if registro:
                doc.linha(registro, tamanho=9)
            return
    doc.linha(ctx.usuario.name, fonte=NEGRITO)


def _novo(db: Session, ctx, cliente: Client, *, tipo: str, titulo: str,
          nome_arquivo: str, conteudo: bytes, mime: str = "application/pdf") -> Document:
    from app.services import billing

    billing.exige_recurso(db, ctx.tenant_id, "documents")
    billing.conferir_armazenamento(db, ctx.tenant_id, len(conteudo))

    documento = Document(
        public_id=novo_ulid(),
        tenant_id=ctx.tenant_id,
        client_id=cliente.id,
        professional_id=ctx.professional_id if CLASSE_DE_TIPO[tipo] == "clinical" else None,
        kind=tipo,
        data_class=CLASSE_DE_TIPO[tipo],
        title=titulo[:160],
        file_name=nome_arquivo[:160],
        mime=mime,
        storage_key="",
        content_hash="",
        nonce=b"",
        created_by_user_id=ctx.usuario.id,
    )
    db.add(documento)
    db.flush()          # precisa do id: ele entra no AAD da cifra
    _gravar(documento, conteudo)
    db.flush()
    return documento


def emitir_recibo(db: Session, ctx, cliente: Client, dados) -> Document:
    """Recibo do que foi efetivamente RECEBIDO no período.

    Regime de caixa, igual ao resto do financeiro: recibo é comprovante de
    dinheiro que entrou, não de atendimento que aconteceu.
    """
    from app.domain.pdf import ITALICO, NEGRITO, Documento

    de = dados.de or (agora() - timedelta(days=30))
    ate = dados.ate or agora()

    consulta = select(Payment).where(
        Payment.client_id == cliente.id,
        Payment.status == "paid",
        Payment.paid_at >= de,
        Payment.paid_at <= ate,
    ).order_by(Payment.paid_at)
    pagamentos = list(db.execute(consulta).scalars())
    if not pagamentos:
        raise errors.conflito("sem_pagamentos",
                              "Não há pagamentos recebidos nesse período para esta pessoa.")

    total = sum((p.amount for p in pagamentos), Decimal("0.00"))

    doc = Documento(titulo="Recibo", autor=ctx.membership.tenant.name)
    _cabecalho(doc, ctx, "Recibo de pagamento")
    doc.paragrafo(
        f"Recebi de {cliente.name} a importância de {_moeda(total)} "
        f"({len(pagamentos)} pagamento(s)), referente a serviços prestados no período de "
        f"{_por_extenso(de)} a {_por_extenso(ate)}.")
    doc.espaco(10)
    doc.linha("Pagamentos", fonte=NEGRITO)
    for p in pagamentos:
        doc.linha(f"{p.paid_at.strftime('%d/%m/%Y')} — {_moeda(p.amount)} ({p.method})",
                  tamanho=10, recuo=12)
    doc.espaco(10)
    doc.linha(f"Total: {_moeda(total)}", fonte=NEGRITO)
    doc.espaco(6)
    doc.linha(f"Emitido em {_por_extenso(agora())}.", tamanho=10, fonte=ITALICO)
    _assinatura(doc, ctx)

    return _novo(db, ctx, cliente, tipo="receipt",
                 titulo=f"Recibo — {_moeda(total)}",
                 nome_arquivo=f"recibo-{ate.strftime('%Y-%m')}.pdf",
                 conteudo=doc.bytes())


def emitir_declaracao(db: Session, ctx, cliente: Client, dados) -> Document:
    """Declaração de comparecimento.

    Diz que a pessoa esteve, quando e por quanto tempo — e **nada** sobre
    o que foi tratado. Declaração que vaza conteúdo clínico é a forma mais
    comum de vazar prontuário sem perceber.
    """
    from app.domain.pdf import ITALICO, Documento

    atendimento = db.execute(
        scope.atendimentos(
            select(Appointment).where(Appointment.public_id == dados.atendimento_id), ctx)
    ).scalar_one_or_none()
    if atendimento is None or atendimento.client_id != cliente.id:
        raise errors.nao_encontrado("atendimento")
    if atendimento.status not in ("done", "confirmed"):
        raise errors.conflito(
            "atendimento_nao_realizado",
            "A declaração vale para atendimento realizado — este não está.")

    fim = atendimento.start_at + timedelta(minutes=atendimento.duration_min or 0)

    doc = Documento(titulo="Declaração de comparecimento", autor=ctx.membership.tenant.name)
    _cabecalho(doc, ctx, "Declaração de comparecimento")
    doc.paragrafo(
        f"Declaro, para os devidos fins, que {cliente.name} compareceu a atendimento "
        f"nesta unidade em {_por_extenso(atendimento.start_at)}, das "
        f"{atendimento.start_at.strftime('%H:%M')} às {fim.strftime('%H:%M')}.")
    doc.espaco(8)
    doc.paragrafo(
        "Esta declaração atesta apenas o comparecimento. Não contém informação "
        "sobre o conteúdo do atendimento, protegido por sigilo profissional.",
        tamanho=10)
    doc.espaco(6)
    doc.linha(f"Emitida em {_por_extenso(agora())}.", tamanho=10, fonte=ITALICO)
    _assinatura(doc, ctx)

    return _novo(db, ctx, cliente, tipo="attendance",
                 titulo=f"Declaração — {atendimento.start_at.strftime('%d/%m/%Y')}",
                 nome_arquivo=f"declaracao-{atendimento.start_at.strftime('%Y-%m-%d')}.pdf",
                 conteudo=doc.bytes())


def exportar_prontuario(db: Session, ctx, cliente: Client) -> Document:
    """Cópia do prontuário em PDF — só do que esta pessoa já podia ler.

    A exportação não é atalho: ela passa pelo mesmo filtro da leitura, nota
    por nota, e cada uma é registrada na trilha como leitura. Um PDF com
    tudo dentro é o pior lugar para uma regra de acesso falhar.
    """
    from app.domain.pdf import ITALICO, NEGRITO, Documento
    from app.services import clinical as servico_clinical

    notas = servico_clinical.listar(db, ctx, cliente)
    if not notas:
        raise errors.conflito("sem_registros",
                              "Não há registros clínicos que você possa exportar.")

    doc = Documento(titulo="Prontuário", autor=ctx.membership.tenant.name)
    _cabecalho(doc, ctx, f"Prontuário — {cliente.name}")
    doc.linha(f"{len(notas)} registro(s) · exportado em {_por_extenso(agora())}", tamanho=9)
    doc.espaco(6)

    for nota in notas:
        doc.regua()
        doc.linha(f"{nota.kind} — {_por_extenso(nota.occurred_at)}", fonte=NEGRITO, tamanho=12)
        estado = "assinada" if nota.assinada else "rascunho"
        doc.linha(f"versão {nota.current_version} · {estado}", tamanho=9)
        doc.espaco(4)
        try:
            texto, _versao = servico_clinical.ler(db, ctx, nota)
            doc.paragrafo(texto)
        except errors.ApiError:
            doc.paragrafo("[conteúdo indisponível]", fonte=ITALICO, tamanho=10)
        doc.espaco(8)

    _assinatura(doc, ctx)

    documento = _novo(db, ctx, cliente, tipo="record_copy",
                      titulo=f"Prontuário — {_por_extenso(agora())}",
                      nome_arquivo=f"prontuario-{agora().strftime('%Y-%m-%d')}.pdf",
                      conteudo=doc.bytes())
    servico_clinical.registrar(db, ctx, acao="export", client_id=cliente.id)
    return documento


def anexar(db: Session, ctx, cliente: Client, dados) -> Document:
    """Arquivo enviado por quem usa. Entra como clínico por precaução."""
    import base64
    import binascii

    try:
        conteudo = base64.b64decode(dados.conteudo_base64 or "", validate=True)
    except (binascii.Error, ValueError):
        raise errors.dados_invalidos("Arquivo inválido.")
    if not conteudo:
        raise errors.dados_invalidos("Arquivo vazio.")

    limite = settings.VC_MAX_UPLOAD_MB * 1024 * 1024
    if len(conteudo) > limite:
        raise errors.dados_invalidos(
            f"Arquivo acima do limite de {settings.VC_MAX_UPLOAD_MB} MB.")

    nome = (dados.nome_arquivo or "arquivo").strip()
    # Nome de arquivo é dado de fora: some com caminho e com o que não é
    # nome. Ele volta em cabeçalho HTTP, e cabeçalho aceita coisas demais.
    nome = os.path.basename(nome).replace("\\", "").replace('"', "")[:160] or "arquivo"

    return _novo(db, ctx, cliente, tipo="upload",
                 titulo=(dados.titulo or nome)[:160],
                 nome_arquivo=nome,
                 conteudo=conteudo,
                 mime=(dados.mime or "application/octet-stream")[:100])


def apagar_conteudo(db: Session, ctx, documento: Document, motivo: str) -> Document:
    """Destrói o arquivo sem apagar o registro de que ele existiu.

    O sal some (nada abre mais, nem de backup) e o arquivo sai do disco. A
    linha fica, com a data — é o que permite responder "houve, foi apagado
    em tal dia, a pedido".
    """
    if not (motivo or "").strip():
        raise errors.dados_invalidos("Apagar arquivo exige motivo registrado.")
    caminho = _raiz() / documento.storage_key
    try:
        if caminho.exists():
            caminho.unlink()
    except OSError:
        pass          # o sal já foi: o conteúdo não abre nem que o arquivo fique
    documento.key_salt = None
    documento.content_erased_at = agora()
    db.flush()
    return documento
