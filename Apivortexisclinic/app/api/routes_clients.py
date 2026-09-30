"""
Rotas de pessoas atendidas.

Toda rota aqui exige, nesta ordem: sessão válida → membership ativa no
tenant → permissão. O filtro por tenant é automático (ORM), e o escopo de
dados (`all`/`own`) é aplicado pelos services.

Repare no que NÃO existe: nenhuma rota aceita `tenant_id`, e nenhuma
devolve id interno.
"""
from typing import List

from fastapi import APIRouter, Depends, Query, Request, Response

from app import errors, schemas_negocio as sn
from app.api import apresentacao
from app.api.deps import Contexto, exigir
from app.api.routes_auth import registrar_evento
from app.services import clients as servico

router = APIRouter(prefix="/workspace/clients", tags=["clients"])


@router.get("", response_model=List[sn.ClienteOut])
def listar(
    resposta: Response,
    busca: str = Query("", max_length=120),
    status: str = Query("active", pattern="^(active|inactive|archived|todos)$"),
    com_pendencia: bool = Query(False),
    limite: int = Query(200, ge=1, le=500),
    pagina: int = Query(1, ge=1),
    ctx: Contexto = Depends(exigir("patients.read")),
):
    """A busca é insensível a acento: "jose" acha "José".

    Vem da collation das tabelas (`utf8mb4_unicode_ci`), não de código —
    e há teste garantindo que continua assim.

    O total vai em `X-Total-Count`, não no corpo: assim a resposta segue
    sendo uma lista e nenhuma tela quebra ao ganhar paginação.
    """
    from app.services import paginacao

    linhas, total = servico.listar(
        ctx.db, ctx, busca=busca, status=status,
        somente_com_pendencia=com_pendencia, limite=limite, pagina=pagina,
    )
    paginacao.cabecalhos(resposta, total_de_linhas=total, pagina=pagina, tamanho=limite)
    return [apresentacao.cliente(c, resumo) for c, resumo in linhas]


@router.get("/contagem", response_model=sn.ContagemClientesOut)
def contagem(ctx: Contexto = Depends(exigir("patients.read"))):
    return sn.ContagemClientesOut(**servico.contar(ctx.db, ctx))


@router.get("/{public_id}", response_model=sn.ClienteOut)
def obter(public_id: str, ctx: Contexto = Depends(exigir("patients.read"))):
    cliente = servico.obter(ctx.db, ctx, public_id)
    return apresentacao.cliente(cliente, servico.resumo(ctx.db, ctx, cliente))


@router.get("/{public_id}/appointments", response_model=List[sn.AtendimentoOut])
def historico(public_id: str, ctx: Contexto = Depends(exigir("patients.read"))):
    cliente = servico.obter(ctx.db, ctx, public_id)
    linhas = servico.historico(ctx.db, ctx, cliente)
    mapa = apresentacao.MapaDeProfissionais(ctx.db, [a.professional_id for a in linhas])
    return [apresentacao.atendimento(a, mapa.publico(a.professional_id)) for a in linhas]


@router.post("", response_model=sn.ClienteOut, status_code=201)
def criar(dados: sn.ClienteIn, request: Request,
          ctx: Contexto = Depends(exigir("patients.write"))):
    try:
        cliente = servico.criar(ctx.db, ctx, dados)
        registrar_evento(ctx.db, request=request, action="client_create", outcome="allowed",
                         user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
        saida = apresentacao.cliente(cliente, servico.resumo(ctx.db, ctx, cliente))
        ctx.db.commit()
        return saida
    except errors.ApiError:
        ctx.db.rollback()
        raise
    except Exception:
        ctx.db.rollback()
        raise errors.conflito("falha_ao_criar", "Não foi possível cadastrar agora.")


@router.patch("/{public_id}", response_model=sn.ClienteOut)
def atualizar(public_id: str, dados: sn.ClienteUpdateIn, request: Request,
              ctx: Contexto = Depends(exigir("patients.write"))):
    cliente = servico.obter(ctx.db, ctx, public_id)
    try:
        servico.atualizar(ctx.db, ctx, cliente, dados)
        registrar_evento(ctx.db, request=request, action="client_update", outcome="allowed",
                         user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
        saida = apresentacao.cliente(cliente, servico.resumo(ctx.db, ctx, cliente))
        ctx.db.commit()
        return saida
    except errors.ApiError:
        ctx.db.rollback()
        raise
    except Exception:
        ctx.db.rollback()
        raise errors.conflito("falha_ao_atualizar", "Não foi possível salvar agora.")


@router.post("/{public_id}/archive", response_model=sn.ClienteOut)
def arquivar(public_id: str, request: Request,
             ctx: Contexto = Depends(exigir("patients.archive"))):
    """Arquivar, não apagar. O histórico de atendimentos continua de pé."""
    cliente = servico.obter(ctx.db, ctx, public_id)
    servico.arquivar(ctx.db, ctx, cliente)
    registrar_evento(ctx.db, request=request, action="client_archive", outcome="allowed",
                     user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
    saida = apresentacao.cliente(cliente, servico.resumo(ctx.db, ctx, cliente))
    ctx.db.commit()
    return saida
