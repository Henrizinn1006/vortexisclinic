"""
Rotas dos direitos do titular e da trilha de auditoria.

Tudo aqui exige `data_requests.manage`, com duas exceções pensadas:

* **A trilha geral** exige `audit.read` — ver quem fez o quê não deve
  exigir, nem conceder, acesso ao conteúdo.
* **O pacote de portabilidade** exige também `patients.read`, e só inclui
  conteúdo clínico se quem gera já podia lê-lo. Portabilidade não é atalho
  para o prontuário alheio.

A rota de exclusão de conteúdo clínico mora aqui, e não junto do
prontuário, de propósito: apagar é ato de tratamento de dados pessoais,
não ato clínico. Quem executa é quem responde pelos pedidos do titular.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request, Response

from app import errors, schemas_negocio as sn
from app.api import apresentacao
from app.api.deps import Contexto, com_tenant, exigir
from app.api.routes_auth import registrar_evento
from app.services import clients as servico_clientes
from app.services import lgpd as servico

router = APIRouter(prefix="/workspace", tags=["lgpd"])


def consentimento_out(c) -> sn.ConsentimentoOut:
    return sn.ConsentimentoOut(
        id=c.public_id, tipo=c.kind, versao=c.version, aceito_em=c.granted_at,
        revogado_em=c.revoked_at, vigente=c.vigente, origem=c.source, observacao=c.note,
    )


def decisao_out(i) -> sn.DecisaoOut:
    return sn.DecisaoOut(
        id=i.public_id, alvo=i.target, decisao=i.decision, motivo=i.reason,
        base_legal=i.legal_basis, aplicado_em=i.applied_at, resultado=i.result,
    )


def pedido_out(p, itens=None) -> sn.PedidoOut:
    return sn.PedidoOut(
        id=p.public_id, tipo=p.kind, status=p.status, solicitante=p.requester,
        pedido_em=p.requested_at, prazo=p.due_at, encerrado_em=p.closed_at,
        observacao=p.note, desfecho=p.outcome_note,
        cliente=apresentacao.cliente_resumido(p.client) if p.client else None,
        decisoes=[decisao_out(i) for i in (p.itens if itens is None else itens)],
    )


# ---------------- consentimento ----------------
@router.get("/clients/{public_id}/consents", response_model=List[sn.ConsentimentoOut])
def listar_consentimentos(public_id: str, ctx: Contexto = Depends(exigir("patients.read"))):
    cliente = servico_clientes.obter(ctx.db, ctx, public_id)
    return [consentimento_out(c) for c in servico.consentimentos(ctx.db, ctx, cliente)]


@router.post("/clients/{public_id}/consents", response_model=sn.ConsentimentoOut, status_code=201)
def registrar_consentimento(public_id: str, dados: sn.ConsentimentoIn, request: Request,
                            ctx: Contexto = Depends(exigir("patients.write"))):
    cliente = servico_clientes.obter(ctx.db, ctx, public_id)
    try:
        c = servico.registrar_consentimento(ctx.db, ctx, cliente, dados)
        registrar_evento(ctx.db, request=request, action="consent_grant", outcome="allowed",
                         user_id=ctx.usuario.id, tenant_id=ctx.tenant_id, meta=f"tipo={dados.tipo}")
        corpo = consentimento_out(c)
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise


@router.post("/consents/{public_id}/revoke", response_model=sn.ConsentimentoOut)
def revogar_consentimento(public_id: str, request: Request,
                          ctx: Contexto = Depends(exigir("patients.write"))):
    try:
        c = servico.revogar_consentimento(ctx.db, ctx, public_id)
        registrar_evento(ctx.db, request=request, action="consent_revoke", outcome="allowed",
                         user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
        corpo = consentimento_out(c)
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise


# ---------------- pedidos do titular ----------------
@router.get("/data-requests", response_model=List[sn.PedidoOut])
def listar_pedidos(status: Optional[str] = Query(None),
                   ctx: Contexto = Depends(exigir("data_requests.manage"))):
    return [pedido_out(p) for p in servico.listar_pedidos(ctx.db, ctx, status=status)]


@router.get("/data-requests/{public_id}", response_model=sn.PedidoOut)
def ver_pedido(public_id: str, ctx: Contexto = Depends(exigir("data_requests.manage"))):
    return pedido_out(servico.obter_pedido(ctx.db, ctx, public_id))


@router.post("/clients/{public_id}/data-requests", response_model=sn.PedidoOut, status_code=201)
def abrir_pedido(public_id: str, dados: sn.PedidoIn, request: Request,
                 ctx: Contexto = Depends(exigir("data_requests.manage"))):
    cliente = servico_clientes.obter(ctx.db, ctx, public_id)
    try:
        pedido = servico.abrir_pedido(ctx.db, ctx, cliente, dados)
        registrar_evento(ctx.db, request=request, action="data_request_open", outcome="allowed",
                         user_id=ctx.usuario.id, tenant_id=ctx.tenant_id, meta=f"tipo={dados.tipo}")
        corpo = pedido_out(pedido)
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise


@router.post("/data-requests/{public_id}/decisions", response_model=sn.PedidoOut, status_code=201)
def decidir(public_id: str, dados: sn.DecisaoIn, request: Request,
            ctx: Contexto = Depends(exigir("data_requests.manage"))):
    """Registra uma decisão. Não executa — executar é o passo seguinte.

    Separar as duas coisas é o que permite alguém revisar o plano antes de
    ele virar ação irreversível.
    """
    pedido = servico.obter_pedido(ctx.db, ctx, public_id)
    try:
        servico.decidir(ctx.db, ctx, pedido, dados)
        registrar_evento(ctx.db, request=request, action="data_request_decide",
                         outcome="allowed", user_id=ctx.usuario.id, tenant_id=ctx.tenant_id,
                         meta=f"{dados.alvo}={dados.decisao}")
        corpo = pedido_out(pedido, servico.itens_do_pedido(ctx.db, pedido))
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise


@router.post("/data-requests/{public_id}/decisions/{item_id}/apply",
             response_model=sn.PedidoOut)
def aplicar(public_id: str, item_id: str, request: Request,
            ctx: Contexto = Depends(exigir("data_requests.manage"))):
    """Executa a decisão. Daqui em diante não tem volta — e é para não ter."""
    pedido = servico.obter_pedido(ctx.db, ctx, public_id)
    item = [i for i in servico.itens_do_pedido(ctx.db, pedido) if i.public_id == item_id]
    if not item:
        raise errors.nao_encontrado("decisão")
    try:
        servico.aplicar(ctx.db, ctx, pedido, item[0])
        registrar_evento(ctx.db, request=request, action="data_request_apply",
                         outcome="allowed", user_id=ctx.usuario.id, tenant_id=ctx.tenant_id,
                         meta=f"{item[0].target}={item[0].decision}")
        ctx.db.flush()
        corpo = pedido_out(pedido, servico.itens_do_pedido(ctx.db, pedido))
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise


@router.post("/data-requests/{public_id}/close", response_model=sn.PedidoOut)
def encerrar(public_id: str, dados: sn.EncerrarPedidoIn, request: Request,
             ctx: Contexto = Depends(exigir("data_requests.manage"))):
    pedido = servico.obter_pedido(ctx.db, ctx, public_id)
    try:
        servico.encerrar(ctx.db, ctx, pedido, status=dados.status, observacao=dados.observacao)
        registrar_evento(ctx.db, request=request, action="data_request_close",
                         outcome="allowed", user_id=ctx.usuario.id, tenant_id=ctx.tenant_id,
                         meta=f"status={dados.status}")
        corpo = pedido_out(pedido, servico.itens_do_pedido(ctx.db, pedido))
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise


# ---------------- portabilidade e anonimização ----------------
@router.get("/clients/{public_id}/data-package")
def pacote(public_id: str, request: Request, ctx: Contexto = Depends(exigir("patients.read"))):
    """Tudo o que a conta tem sobre a pessoa, em JSON.

    Conteúdo clínico entra só se quem gera já podia ler. Quando fica de
    fora, o pacote **diz** que existe e não foi incluído — omitir em
    silêncio seria responder mal a um pedido de acesso.
    """
    cliente = servico_clientes.obter(ctx.db, ctx, public_id)
    dados = servico.pacote(ctx.db, ctx, cliente, com_clinico=True)
    registrar_evento(ctx.db, request=request, action="data_package", outcome="allowed",
                     user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
    ctx.db.commit()

    import json

    nome = f"dados-{cliente.public_id}.json"
    return Response(
        content=json.dumps(dados, ensure_ascii=False, indent=2).encode("utf-8"),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.post("/clients/{public_id}/anonymize", response_model=sn.ClienteOut)
def anonimizar(public_id: str, dados: sn.MotivoIn, request: Request,
               ctx: Contexto = Depends(exigir("data_requests.manage"))):
    """Remove o que identifica. **Irreversível.**

    A série de atendimentos e os valores continuam, desidentificados — é o
    que permite a clínica seguir existindo como negócio sem seguir sabendo
    quem era aquela pessoa.
    """
    cliente = servico_clientes.obter(ctx.db, ctx, public_id)
    if not (dados.motivo or "").strip():
        raise errors.dados_invalidos("Anonimizar exige motivo registrado.")
    try:
        servico.anonimizar(ctx.db, ctx, cliente, motivo=dados.motivo)
        registrar_evento(ctx.db, request=request, action="client_anonymize", outcome="allowed",
                         user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
        corpo = apresentacao.cliente(cliente)
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise


# ---------------- exclusão de conteúdo ----------------
@router.post("/notes/{public_id}/erase-content", status_code=200)
def apagar_nota(public_id: str, dados: sn.MotivoIn, request: Request,
                ctx: Contexto = Depends(exigir("data_requests.manage"))):
    """Destrói o conteúdo da nota descartando o sal de derivação.

    Nenhuma linha é apagada: a ficha, o histórico de versões e a trilha
    continuam. O texto some — inclusive de backup, que guarda ciphertext e
    não guarda o sal.
    """
    from sqlalchemy import select

    from app.models.clinical import ClinicalNote
    from app.services import clinical as servico_clinical

    nota = ctx.db.execute(
        select(ClinicalNote).where(ClinicalNote.public_id == public_id)
    ).scalar_one_or_none()
    if nota is None:
        raise errors.nao_encontrado("registro clínico")
    try:
        servico_clinical.esquecer_conteudo(ctx.db, ctx, nota, dados.motivo or "")
        registrar_evento(ctx.db, request=request, action="clinical_erase", outcome="allowed",
                         user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
        ctx.db.commit()
        return {"apagado_em": nota.content_erased_at, "id": nota.public_id}
    except errors.ApiError:
        ctx.db.rollback()
        raise


@router.post("/documents/{public_id}/erase-content", status_code=200)
def apagar_documento(public_id: str, dados: sn.MotivoIn, request: Request,
                     ctx: Contexto = Depends(exigir("data_requests.manage"))):
    from sqlalchemy import select

    from app.models.document import Document
    from app.services import documents as servico_documentos

    documento = ctx.db.execute(
        select(Document).where(Document.public_id == public_id)
    ).scalar_one_or_none()
    if documento is None:
        raise errors.nao_encontrado("documento")
    try:
        servico_documentos.apagar_conteudo(ctx.db, ctx, documento, dados.motivo or "")
        registrar_evento(ctx.db, request=request, action="document_erase", outcome="allowed",
                         user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
        ctx.db.commit()
        return {"apagado_em": documento.content_erased_at, "id": documento.public_id}
    except errors.ApiError:
        ctx.db.rollback()
        raise


# ---------------- política de retenção ----------------
@router.get("/retention-policies", response_model=List[sn.PoliticaOut])
def listar_politicas(ctx: Contexto = Depends(exigir("settings.manage"))):
    """Nasce vazia. Enquanto estiver vazia, nada é apagado automaticamente."""
    from sqlalchemy import select

    from app.models.profession import Profession

    linhas = servico.politicas(ctx.db, ctx)
    slugs = {}
    ids = {p.profession_id for p in linhas if p.profession_id}
    if ids:
        slugs = dict(ctx.db.execute(
            select(Profession.id, Profession.slug).where(Profession.id.in_(ids))).all())
    return [
        sn.PoliticaOut(id=p.public_id, alvo=p.record_kind, profissao=slugs.get(p.profession_id),
                       meses=p.months, base_legal=p.legal_basis, observacao=p.note,
                       aplicavel=p.aplicavel)
        for p in linhas
    ]


@router.put("/retention-policies", response_model=sn.PoliticaOut)
def definir_politica(dados: sn.PoliticaIn, request: Request,
                     ctx: Contexto = Depends(exigir("settings.manage"))):
    try:
        politica = servico.definir_politica(ctx.db, ctx, dados)
        registrar_evento(ctx.db, request=request, action="retention_policy", outcome="allowed",
                         user_id=ctx.usuario.id, tenant_id=ctx.tenant_id,
                         meta=f"{dados.alvo}={dados.meses}")
        corpo = sn.PoliticaOut(id=politica.public_id, alvo=politica.record_kind,
                               profissao=dados.profissao, meses=politica.months,
                               base_legal=politica.legal_basis, observacao=politica.note,
                               aplicavel=politica.aplicavel)
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise


# ---------------- trilha de segurança ----------------
@router.get("/audit", response_model=List[sn.EventoOut])
def auditoria(limite: int = Query(200, ge=1, le=500),
              ctx: Contexto = Depends(exigir("audit.read"))):
    """Quem fez o quê nesta conta. Nunca conteúdo — só o ato.

    `security_events` não herda o escopo automático (ele nasce antes de
    haver tenant, no login), então o filtro por conta é explícito aqui.
    """
    from sqlalchemy import select

    from app.models.security import SecurityEvent
    from app.models.user import User

    linhas = list(ctx.db.execute(
        select(SecurityEvent)
        .where(SecurityEvent.tenant_id == ctx.tenant_id)
        .order_by(SecurityEvent.id.desc())
        .limit(limite)
    ).scalars())

    nomes = {}
    ids = {e.user_id for e in linhas if e.user_id}
    if ids:
        nomes = dict(ctx.db.execute(
            select(User.id, User.name).where(User.id.in_(ids))).all())

    return [
        sn.EventoOut(id=e.public_id, quando=e.created_at, acao=e.action,
                     resultado=e.outcome, quem=nomes.get(e.user_id), detalhe=e.meta)
        for e in linhas
    ]
