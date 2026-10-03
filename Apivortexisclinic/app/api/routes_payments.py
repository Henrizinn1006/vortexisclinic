"""
Rotas do financeiro: baixa, estorno, isenção e livro-caixa.

Permissão: **ler** o financeiro é `finance.read`; **mexer** no dinheiro é
`finance.write`. A separação importa — na matriz atual o profissional lê o
próprio financeiro mas não dá baixa; quem opera o caixa é o dono da conta
ou a recepção.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request

from app import errors, schemas_negocio as sn
from app.api import apresentacao
from app.api.deps import Contexto, exigir
from app.api.routes_auth import registrar_evento
from app.services import appointments as servico_atendimentos
from app.services import payments as servico

router = APIRouter(prefix="/workspace", tags=["payments"])


def saida(p) -> sn.PagamentoOut:
    return sn.PagamentoOut(
        id=p.public_id,
        valor=p.amount,
        metodo=p.method,
        status=p.status,
        pago_em=p.paid_at,
        observacao=p.note,
        estornado_em=p.refunded_at,
        motivo_estorno=p.refund_reason,
        cliente=apresentacao.cliente_resumido(p.client),
        atendimento_id=p.appointment.public_id if p.appointment is not None else None,
    )


# ---------------- livro-caixa ----------------
@router.get("/payments", response_model=List[sn.PagamentoOut])
def listar(
    de: Optional[sn.Instante] = Query(None),
    ate: Optional[sn.Instante] = Query(None),
    metodo: Optional[str] = Query(None, max_length=20),
    incluir_estornados: bool = Query(True),
    limite: int = Query(200, ge=1, le=500),
    ctx: Contexto = Depends(exigir("finance.read")),
):
    linhas = servico.listar(ctx.db, ctx, de=de, ate=ate, metodo=metodo,
                            incluir_estornados=incluir_estornados, limite=limite)
    return [saida(p) for p in linhas]


@router.get("/appointments/{public_id}/payments", response_model=List[sn.PagamentoOut])
def do_atendimento(public_id: str, ctx: Contexto = Depends(exigir("finance.read"))):
    atendimento = servico_atendimentos.obter(ctx.db, ctx, public_id)
    return [saida(p) for p in servico.do_atendimento(ctx.db, ctx, atendimento)]


# ---------------- baixa ----------------
@router.post("/appointments/{public_id}/payment", response_model=sn.PagamentoOut, status_code=201)
def dar_baixa(public_id: str, dados: sn.BaixaIn, request: Request,
              ctx: Contexto = Depends(exigir("finance.write"))):
    atendimento = servico_atendimentos.obter(ctx.db, ctx, public_id)
    try:
        pagamento = servico.registrar(ctx.db, ctx, atendimento, dados)
        registrar_evento(ctx.db, request=request, action="payment_create", outcome="allowed",
                         user_id=ctx.usuario.id, tenant_id=ctx.tenant_id,
                         meta=f"metodo={dados.metodo}")
        corpo = saida(pagamento)
        ctx.db.commit()          # livro-caixa e bandeira do atendimento juntos
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise
    except Exception:
        ctx.db.rollback()
        raise errors.conflito("falha_na_baixa", "Não foi possível registrar o pagamento agora.")


@router.post("/clients/{public_id}/payment", response_model=sn.PagamentoOut, status_code=201)
def pagamento_avulso(public_id: str, dados: sn.PagamentoAvulsoIn, request: Request,
                     ctx: Contexto = Depends(exigir("finance.write"))):
    """Pacote, sinal, acerto — dinheiro que não nasce de um atendimento.

    O livro-caixa sempre aceitou (a coluna do atendimento é opcional); o
    que faltava era caminho para criar. Sem ele, um pacote de dez sessões
    pago adiantado só entrava distorcendo a agenda.
    """
    from app.services import clients as servico_clientes

    cliente = servico_clientes.obter(ctx.db, ctx, public_id)
    try:
        pagamento = servico.registrar_avulso(ctx.db, ctx, cliente, dados)
        registrar_evento(ctx.db, request=request, action="payment_standalone",
                         outcome="allowed", user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
        corpo = saida(pagamento)
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise


@router.post("/appointments/{public_id}/waive", response_model=sn.AtendimentoOut)
def isentar(public_id: str, dados: sn.MotivoIn, request: Request,
            ctx: Contexto = Depends(exigir("finance.write"))):
    atendimento = servico_atendimentos.obter(ctx.db, ctx, public_id)
    try:
        servico.isentar(ctx.db, ctx, atendimento, dados.motivo)
        registrar_evento(ctx.db, request=request, action="payment_waive", outcome="allowed",
                         user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
        mapa = apresentacao.MapaDeProfissionais(ctx.db, [atendimento.professional_id])
        corpo = apresentacao.atendimento(atendimento, mapa.publico(atendimento.professional_id))
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise


@router.post("/payments/{public_id}/refund", response_model=sn.PagamentoOut)
def estornar(public_id: str, dados: sn.MotivoIn, request: Request,
             ctx: Contexto = Depends(exigir("finance.write"))):
    """Estorno marca a linha e devolve o atendimento para pendente.

    A linha original continua no livro-caixa: apagar lançamento é rasurar
    a explicação junto com o erro.
    """
    pagamento = servico.obter(ctx.db, ctx, public_id)
    try:
        servico.estornar(ctx.db, ctx, pagamento, dados.motivo)
        registrar_evento(ctx.db, request=request, action="payment_refund", outcome="allowed",
                         user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
        corpo = saida(pagamento)
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise
