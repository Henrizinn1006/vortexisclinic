"""
Plano da conta: o que está contratado, o que já foi usado.

**Só leitura.** Não existe rota para trocar de plano, e é de propósito:
enquanto não houver gateway de pagamento, autoatendimento de plano seria
um botão de "vire Pro de graça". A troca é feita de fora
(`python -m app.jobs.assinatura`), e quando o gateway existir é o webhook
dele que chama a mesma função.

Ler o plano exige `settings.manage`: é informação de conta, não de
atendimento.
"""
from fastapi import APIRouter, Depends

from app.api.deps import Contexto, exigir
from app.services import billing as servico

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
