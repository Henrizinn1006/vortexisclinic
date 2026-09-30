"""
Rotas do prontuário.

Duas coisas para ter em mente ao ler este arquivo.

**O conteúdo tem rota própria.** Listar, abrir a ficha e ver o histórico
de versões não decifram nada — devolvem metadado. O texto sai só em
`/notes/{id}/content`, e é essa chamada que a trilha registra como
leitura. Assim "abriu a aba do prontuário" e "leu a evolução do dia 12"
são eventos diferentes, como devem ser.

**A permissão não é a última palavra.** `clinical_records.read` é a
porta de entrada; depois dela ainda valem o alcance do cliente e a
autoria da nota, decididos em `services/clinical.py`. O dono da conta não
tem a permissão na matriz, então para ele nem a primeira porta abre.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request

from app import errors, schemas_negocio as sn
from app.api import apresentacao
from app.api.deps import Contexto, exigir
from app.api.routes_auth import registrar_evento
from app.models.professional import Professional
from app.services import clients as servico_clientes
from app.services import clinical as servico

router = APIRouter(prefix="/workspace", tags=["clinical"])


class _Autores:
    """id interno → (id público, nome) sem uma consulta por linha."""

    def __init__(self, db, ids):
        from sqlalchemy import select

        ids = {i for i in ids if i}
        self._mapa = {}
        if ids:
            linhas = db.execute(
                select(Professional.id, Professional.public_id, Professional.display_name)
                .where(Professional.id.in_(ids))
            ).all()
            self._mapa = {i: (p, n) for i, p, n in linhas}

    def publico(self, interno) -> Optional[str]:
        return self._mapa.get(interno, (None, None))[0]

    def nome(self, interno) -> Optional[str]:
        return self._mapa.get(interno, (None, None))[1]


def saida(nota, autores: _Autores, ctx) -> sn.NotaOut:
    return sn.NotaOut(
        id=nota.public_id,
        tipo=nota.kind,
        status=nota.status,
        ocorrido_em=nota.occurred_at,
        versao_atual=nota.current_version,
        assinada_em=nota.signed_at,
        conteudo_apagado_em=nota.content_erased_at,
        autor=autores.nome(nota.professional_id),
        autor_id=autores.publico(nota.professional_id),
        sou_o_autor=ctx.professional_id is not None
        and nota.professional_id == ctx.professional_id,
        atendimento_id=nota.appointment.public_id if nota.appointment is not None else None,
        cliente=apresentacao.cliente_resumido(nota.client) if nota.client else None,
    )


# ---------------- leitura ----------------
@router.get("/clients/{public_id}/notes", response_model=List[sn.NotaOut])
def listar(public_id: str, ctx: Contexto = Depends(exigir("clinical_records.read"))):
    cliente = servico_clientes.obter(ctx.db, ctx, public_id)
    notas = servico.listar(ctx.db, ctx, cliente)
    autores = _Autores(ctx.db, [n.professional_id for n in notas])
    return [saida(n, autores, ctx) for n in notas]


@router.get("/notes/{public_id}", response_model=sn.NotaOut)
def ficha(public_id: str, ctx: Contexto = Depends(exigir("clinical_records.read"))):
    nota = servico.obter(ctx.db, ctx, public_id)
    return saida(nota, _Autores(ctx.db, [nota.professional_id]), ctx)


@router.get("/notes/{public_id}/versions", response_model=List[sn.VersaoOut])
def versoes(public_id: str, ctx: Contexto = Depends(exigir("clinical_records.read"))):
    """Histórico. Metadado apenas — nenhuma versão é decifrada aqui."""
    nota = servico.obter(ctx.db, ctx, public_id)
    linhas = servico.historico(ctx.db, ctx, nota)
    return [
        sn.VersaoOut(versao=v.version, criado_em=v.created_at, motivo=v.reason,
                     impressao=v.content_hash)
        for v in linhas
    ]


@router.get("/notes/{public_id}/content", response_model=sn.ConteudoOut)
def conteudo(public_id: str, versao: Optional[int] = Query(None, ge=1),
             ctx: Contexto = Depends(exigir("clinical_records.read"))):
    """A única rota que devolve conteúdo clínico. Toda chamada vira trilha."""
    nota = servico.obter(ctx.db, ctx, public_id)
    texto, linha = servico.ler(ctx.db, ctx, nota, versao)
    return sn.ConteudoOut(
        id=nota.public_id, versao=linha.version, conteudo=texto,
        impressao=linha.content_hash, criado_em=linha.created_at,
    )


# ---------------- escrita ----------------
@router.post("/clients/{public_id}/notes", response_model=sn.NotaOut, status_code=201)
def criar(public_id: str, dados: sn.NotaIn, request: Request,
          ctx: Contexto = Depends(exigir("clinical_records.write"))):
    cliente = servico_clientes.obter(ctx.db, ctx, public_id)
    try:
        nota = servico.criar(ctx.db, ctx, cliente, dados)
        registrar_evento(ctx.db, request=request, action="clinical_note_create",
                         outcome="allowed", user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
        corpo = saida(nota, _Autores(ctx.db, [nota.professional_id]), ctx)
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise


@router.put("/notes/{public_id}", response_model=sn.NotaOut)
def editar(public_id: str, dados: sn.NotaEdicaoIn, request: Request,
           ctx: Contexto = Depends(exigir("clinical_records.write"))):
    """Salvar cria a versão seguinte. Nada é sobrescrito."""
    nota = servico.obter(ctx.db, ctx, public_id, acao="update")
    try:
        servico.editar(ctx.db, ctx, nota, dados)
        registrar_evento(ctx.db, request=request, action="clinical_note_update",
                         outcome="allowed", user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
        corpo = saida(nota, _Autores(ctx.db, [nota.professional_id]), ctx)
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise


@router.post("/notes/{public_id}/sign", response_model=sn.NotaOut)
def assinar(public_id: str, request: Request,
            ctx: Contexto = Depends(exigir("clinical_records.write"))):
    nota = servico.obter(ctx.db, ctx, public_id, acao="sign")
    try:
        servico.assinar(ctx.db, ctx, nota)
        registrar_evento(ctx.db, request=request, action="clinical_note_sign",
                         outcome="allowed", user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
        corpo = saida(nota, _Autores(ctx.db, [nota.professional_id]), ctx)
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise


# ---------------- trilha ----------------
@router.get("/clients/{public_id}/clinical-access", response_model=List[sn.AcessoOut])
def trilha(public_id: str, ctx: Contexto = Depends(exigir("audit.read"))):
    """Quem abriu o prontuário desta pessoa.

    `audit.read` e não `clinical_records.read`: auditar é ver QUEM olhou,
    e isso não deve exigir — nem conceder — acesso ao conteúdo. O dono da
    conta tem esta permissão e continua sem ler uma linha do prontuário.
    """
    from sqlalchemy import select

    from app.models.user import User

    cliente = servico_clientes.obter(ctx.db, ctx, public_id)
    linhas = servico.trilha_do_cliente(ctx.db, ctx, cliente)

    nomes = {}
    ids = {linha.user_id for linha in linhas}
    if ids:
        nomes = dict(ctx.db.execute(select(User.id, User.name).where(User.id.in_(ids))).all())

    # Id público da nota: identificador opaco, não conteúdo. O auditor
    # consegue dizer "esta pessoa abriu a mesma nota seis vezes" sem
    # nenhum acesso ao que está escrito nela.
    notas = {}
    ids_notas = {linha.note_id for linha in linhas if linha.note_id}
    if ids_notas:
        from app.models.clinical import ClinicalNote

        notas = dict(ctx.db.execute(
            select(ClinicalNote.id, ClinicalNote.public_id).where(ClinicalNote.id.in_(ids_notas))
        ).all())

    return [
        sn.AcessoOut(id=linha.public_id, quando=linha.created_at, acao=linha.action,
                     resultado=linha.outcome, motivo=linha.reason,
                     quem=nomes.get(linha.user_id), nota_id=notas.get(linha.note_id))
        for linha in linhas
    ]
