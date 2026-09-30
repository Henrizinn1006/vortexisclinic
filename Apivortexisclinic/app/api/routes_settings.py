"""
Configurações da conta.

Ler é para qualquer pessoa da conta: a jornada desenha a grade da agenda e
a terminologia troca os rótulos da interface inteira — esconder isso de
quem atende só quebraria a tela. **Gravar** exige `settings.manage`.

A terminologia passa pelo mesmo saneamento do painel, de novo aqui. Não é
redundância: é a regra do projeto de nunca deixar a validação de frente
ser a única. Chave fora do catálogo e rótulo com marcação voltam na
resposta, em `recusados`, para a tela avisar em vez de fingir que gravou.
"""
from fastapi import APIRouter, Depends, Request

from app import errors, schemas
from app.api.deps import Contexto, com_tenant, exigir
from app.api.routes_auth import registrar_evento
from app.services import settings as servico

router = APIRouter(prefix="/workspace", tags=["configuracoes"])


def saida(config, fuso: str, recusados=None) -> schemas.ConfiguracoesOut:
    return schemas.ConfiguracoesOut(
        jornada_inicio=config.workday_start.strftime("%H:%M"),
        jornada_fim=config.workday_end.strftime("%H:%M"),
        dias_da_semana=config.dias_da_semana,
        duracao_padrao=config.default_duration_min,
        intervalo=config.slot_interval_min,
        tolerancia_falta=config.no_show_tolerance_hours,
        meta_mensal=config.monthly_goal,
        moeda=config.currency,
        fuso=fuso,
        terminologia=servico.terminologia(config),
        recusados=recusados or [],
    )


@router.get("/settings", response_model=schemas.ConfiguracoesOut)
def ler(ctx: Contexto = Depends(com_tenant)):
    """Qualquer pessoa da conta lê: a tela inteira depende disto."""
    config = servico.obter(ctx.db, ctx.tenant_id)
    fuso = ctx.membership.tenant.timezone
    ctx.db.commit()          # `obter` cria a linha quando a conta é antiga
    return saida(config, fuso)


@router.patch("/settings", response_model=schemas.ConfiguracoesOut)
def gravar(dados: schemas.ConfiguracoesIn, request: Request,
           ctx: Contexto = Depends(exigir("settings.manage"))):
    try:
        config, recusados = servico.gravar(ctx.db, ctx, dados)
        registrar_evento(ctx.db, request=request, action="settings_update", outcome="allowed",
                         user_id=ctx.usuario.id, tenant_id=ctx.tenant_id)
        corpo = saida(config, ctx.membership.tenant.timezone, recusados)
        ctx.db.commit()
        return corpo
    except errors.ApiError:
        ctx.db.rollback()
        raise
