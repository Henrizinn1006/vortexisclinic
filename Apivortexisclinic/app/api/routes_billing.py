"""
Plano da conta: o que está contratado, o que já foi usado.

Não existe rota que troque o plano direto. O caminho é o checkout: ele cria
a assinatura no Asaas e **só o webhook de pagamento confirmado** muda o
plano. Suporte ainda troca à mão por `python -m app.jobs.assinatura`.

Ler o plano exige `settings.manage`: é informação de conta, não de
atendimento.
"""
import hmac
import logging
import re

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app import errors
from app.api.deps import Contexto, exigir
from app.config import settings
from app.db.context import sem_escopo_de_tenant
from app.db.session import get_db
from app.services import billing as servico

log = logging.getLogger("vc.billing")

router = APIRouter(prefix="/workspace", tags=["plano"])


@router.get("/plan")
def plano(ctx: Contexto = Depends(exigir("settings.manage"))):
    """Plano, limites, uso e situação — tudo numa chamada.

    O uso vem junto do limite de propósito: "5 de 15 profissionais" é a
    informação útil; "limite: 15" sozinho não diz nada a quem está
    decidindo se precisa mudar de plano.
    """
    corpo = servico.resumo(ctx.db, ctx.tenant_id)
    ctx.db.commit()          # `resumo` cria a assinatura padrão se faltar
    return corpo


class CheckoutIn(BaseModel):
    plano: str
    cpf_cnpj: str

    @field_validator("cpf_cnpj")
    @classmethod
    def _so_digitos(cls, v: str) -> str:
        v = re.sub(r"\D", "", v or "")
        if len(v) not in (11, 14):
            raise ValueError("CPF deve ter 11 dígitos e CNPJ, 14.")
        return v


@router.post("/plan/checkout")
def checkout(corpo: CheckoutIn, ctx: Contexto = Depends(exigir("settings.manage"))):
    """Inicia a contratação: devolve o link da fatura no Asaas.

    O plano não muda aqui — muda quando o pagamento for confirmado.
    O CPF/CNPJ vai ao Asaas e não é guardado.
    """
    resultado = servico.iniciar_checkout(
        ctx.db, ctx.tenant_id, corpo.plano,
        nome=ctx.usuario.name, email=ctx.usuario.email, cpf_cnpj=corpo.cpf_cnpj,
    )
    ctx.db.commit()
    return resultado


@router.post("/plan/cancel")
def cancelar(ctx: Contexto = Depends(exigir("settings.manage"))):
    servico.cancelar_assinatura(ctx.db, ctx.tenant_id)
    ctx.db.commit()
    return servico.resumo(ctx.db, ctx.tenant_id)


webhooks = APIRouter(prefix="/billing", tags=["cobranca"])


@webhooks.post("/asaas/webhook")
async def webhook_asaas(request: Request, db: Session = Depends(get_db)):
    """Recebe os eventos do Asaas. Sem sessão: a autenticação é o token.

    Sem token configurado, recusa tudo (fail-closed). Responde 200 a evento
    que não entende, para o Asaas não pausar a fila; erro nosso responde
    500 e ele reenvia.
    """
    esperado = settings.VC_ASAAS_WEBHOOK_TOKEN
    enviado = request.headers.get("asaas-access-token", "")
    if not esperado or not hmac.compare_digest(enviado.encode(), esperado.encode()):
        raise errors.nao_autenticado("webhook_nao_autorizado")
    try:
        corpo = await request.json()
    except ValueError:
        raise errors.dados_invalidos("Corpo inválido.")
    if not isinstance(corpo, dict):
        raise errors.dados_invalidos("Corpo inválido.")

    with sem_escopo_de_tenant():
        resultado = servico.aplicar_evento_asaas(db, corpo)
        db.commit()
    log.info("webhook asaas %s: %s", corpo.get("event"), resultado)
    return {"ok": True}
