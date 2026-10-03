"""
Rotas de documentos e exportação.

A permissão exigida **depende da classe do documento**, não da rota: o
mesmo endpoint de download pede `finance.read` para um recibo e
`documents.read` para uma declaração. É o que impede a recepção precisar
enxergar laudo só para conseguir imprimir recibo.

Baixar documento clínico entra na trilha de acesso, pela mesma razão que
abrir uma evolução entra: leitura indevida não tem conserto, e a trilha é
o que permite descobrir.

**Nenhuma resposta daqui é cacheável.** O middleware já põe `no-store` em
tudo; aqui o `Content-Disposition` também vai com o nome saneado, porque
nome de arquivo é dado que veio de fora.
"""
import csv
import io
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request, Response

from app import errors, schemas_negocio as sn
from app.api import apresentacao
from app.api.deps import Contexto, com_tenant, exigir
from app.api.routes_auth import registrar_evento
from app.services import clients as servico_clientes
from app.services import documents as servico

router = APIRouter(prefix="/workspace", tags=["documentos"])


def saida(d) -> sn.DocumentoOut:
    return sn.DocumentoOut(
        id=d.public_id,
        tipo=d.kind,
        classe=d.data_class,
        titulo=d.title,
        nome_arquivo=d.file_name,
        tamanho=d.size_bytes,
        criado_em=d.created_at,
        impressao=d.content_hash,
        conteudo_apagado_em=d.content_erased_at,
        cliente=apresentacao.cliente_resumido(d.client) if d.client else None,
    )


def _exigir_para_emitir(ctx: Contexto, tipo: str) -> None:
    permissao = servico.permissao_de_escrita(tipo)
    if not ctx.pode(permissao):
        raise errors.sem_permissao(permissao)


# ---------------- leitura ----------------
@router.get("/clients/{public_id}/documents", response_model=List[sn.DocumentoOut])
def listar(public_id: str, ctx: Contexto = Depends(com_tenant)):
    """Lista o que esta pessoa pode ver — administrativo e clínico juntos,
    já filtrados um a um pela regra de cada classe."""
    cliente = servico_clientes.obter(ctx.db, ctx, public_id)
    return [saida(d) for d in servico.listar(ctx.db, ctx, cliente)]


@router.get("/documents/{public_id}/content")
def baixar(public_id: str, request: Request, ctx: Contexto = Depends(com_tenant)):
    documento = servico.obter(ctx.db, ctx, public_id)
    conteudo = servico.ler_arquivo(documento)

    if documento.eh_clinico:
        from app.services import clinical as servico_clinical

        servico_clinical.registrar(ctx.db, ctx, acao="export",
                                   client_id=documento.client_id, confirmar=True)

    nome = documento.file_name.replace('"', "")
    return Response(
        content=conteudo,
        media_type=documento.mime,
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


# ---------------- emissão ----------------
@router.post("/clients/{public_id}/documents/receipt",
             response_model=sn.DocumentoOut, status_code=201)
def recibo(public_id: str, dados: sn.ReciboIn, request: Request,
           ctx: Contexto = Depends(com_tenant)):
    _exigir_para_emitir(ctx, "receipt")
    cliente = servico_clientes.obter(ctx.db, ctx, public_id)
    try:
        documento = servico.emitir_recibo(ctx.db, ctx, cliente, dados)
        registrar_evento(ctx.db, request=request, action="document_receipt",
                         outcome="allowed", user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
        corpo = saida(documento)
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise


@router.post("/clients/{public_id}/documents/attendance",
             response_model=sn.DocumentoOut, status_code=201)
def declaracao(public_id: str, dados: sn.DeclaracaoIn, request: Request,
               ctx: Contexto = Depends(com_tenant)):
    _exigir_para_emitir(ctx, "attendance")
    cliente = servico_clientes.obter(ctx.db, ctx, public_id)
    try:
        documento = servico.emitir_declaracao(ctx.db, ctx, cliente, dados)
        registrar_evento(ctx.db, request=request, action="document_attendance",
                         outcome="allowed", user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
        corpo = saida(documento)
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise


@router.post("/clients/{public_id}/documents/record",
             response_model=sn.DocumentoOut, status_code=201)
def exportar_prontuario(public_id: str, request: Request,
                        ctx: Contexto = Depends(exigir("clinical_records.read"))):
    """Cópia do prontuário em PDF — só do que esta pessoa já podia ler.

    Cada nota passa pelo mesmo filtro da leitura e entra na trilha. Um PDF
    com tudo dentro é o pior lugar para uma regra de acesso falhar.
    """
    cliente = servico_clientes.obter(ctx.db, ctx, public_id)
    try:
        documento = servico.exportar_prontuario(ctx.db, ctx, cliente)
        registrar_evento(ctx.db, request=request, action="record_export",
                         outcome="allowed", user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
        corpo = saida(documento)
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise


@router.post("/clients/{public_id}/documents", response_model=sn.DocumentoOut, status_code=201)
def anexar(public_id: str, dados: sn.AnexoIn, request: Request,
           ctx: Contexto = Depends(exigir("documents.write"))):
    """Anexo entra como clínico por precaução: ninguém sabe o que tem
    dentro de um arquivo que alguém mandou."""
    cliente = servico_clientes.obter(ctx.db, ctx, public_id)
    try:
        documento = servico.anexar(ctx.db, ctx, cliente, dados)
        registrar_evento(ctx.db, request=request, action="document_upload",
                         outcome="allowed", user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
        corpo = saida(documento)
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise


# ---------------- exportação do financeiro ----------------
@router.get("/finance/export")
def exportar_financeiro(de: Optional[sn.Instante] = Query(None),
                        ate: Optional[sn.Instante] = Query(None),
                        ctx: Contexto = Depends(exigir("finance.export"))):
    """Livro-caixa em CSV, para conferir com o extrato ou mandar ao contador.

    Sai o que entrou de dinheiro no período (inclusive estornos, marcados)
    — e nada de clínico: nome da pessoa, data, meio e valor. O CSV vai em
    UTF-8 com BOM porque é o que faz o Excel brasileiro abrir sem embolar
    os acentos.
    """
    from app.services import payments as servico_pagamentos

    linhas = servico_pagamentos.listar(ctx.db, ctx, de=de, ate=ate,
                                       incluir_estornados=True, limite=5000)

    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";")
    escritor.writerow(["data", "pessoa", "valor", "meio", "situacao",
                       "estornado_em", "observacao"])
    for p in linhas:
        escritor.writerow([
            p.paid_at.strftime("%d/%m/%Y"),
            p.client.name if p.client else "",
            f"{p.amount:.2f}".replace(".", ","),
            p.method,
            "estornado" if p.status == "refunded" else "recebido",
            p.refunded_at.strftime("%d/%m/%Y") if p.refunded_at else "",
            (p.note or "").replace("\n", " "),
        ])

    conteudo = "﻿" + buffer.getvalue()      # BOM: o Excel pede
    nome = f"caixa-{(ate or datetime.utcnow()).strftime('%Y-%m')}.csv"
    return Response(
        content=conteudo.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )
