"""
Configurações da conta: jornada, duração padrão, meta, terminologia e fuso.

**Terminologia é rótulo, não conteúdo**

Uma conta pode trocar "Paciente" por "Cliente". O que ela **não** pode é
mandar marcação: o painel já recusa `< > & " ' \\ { }`, e o servidor recusa
de novo aqui. Repetir a regra não é redundância — é a regra do projeto de
não confiar em validação de frente. Chave fora do catálogo é ignorada em
silêncio: dicionário aberto seria um campo de texto livre viajando até o
DOM de todo mundo da conta.

**O fuso é da conta, e é levado a sério**

`tenants.timezone` existia e não era usado: tudo saía em UTC, e quem
atende em Manaus via a agenda três horas adiantada. Agora ele é validado
contra o banco de fusos do próprio Python e é o que define o que significa
"hoje", "esta semana" e "este mês" nos números.

**A jornada não bloqueia agendamento**

Ela desenha a grade e sugere horários. Marcar fora dela continua
permitido: quem atende num sábado por exceção não deveria precisar mudar a
configuração da conta para conseguir.
"""
import json
import re
from datetime import time
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import errors
from app.models.tenant import Tenant, TenantSettings

# Catálogo fechado — espelha `assets/js/core/terms.js` do painel.
CHAVES_DE_TERMO = {
    "client.one", "client.many", "client.new", "client.search",
    "appointment.one", "appointment.many", "appointment.new",
    "session.one", "session.many",
    "professional.one", "professional.many",
    "record.one", "record.many", "record.new",
    "note.one", "note.many",
    "schedule.title", "finance.title", "pending.title",
}

PROIBIDO_NO_TERMO = re.compile(r"[<>&\"'`\\{}]")
ESQUEMA_DE_URL = re.compile(r"^(https?|javascript|data):", re.IGNORECASE)
TAMANHO_DO_TERMO = 40

DURACAO_MIN, DURACAO_MAX = 10, 480
INTERVALO_MAX = 120
TOLERANCIA_MAX = 720          # 30 dias


def obter(db: Session, tenant_id: int) -> TenantSettings:
    achado = db.execute(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if achado is None:
        # Conta antiga, criada antes desta tabela: nasce com o padrão.
        achado = TenantSettings(tenant_id=tenant_id)
        db.add(achado)
        db.flush()
    return achado


def terminologia(config: TenantSettings) -> dict:
    if not config.terminology:
        return {}
    try:
        bruto = json.loads(config.terminology)
    except ValueError:
        return {}
    return bruto if isinstance(bruto, dict) else {}


def _limpar_termo(valor) -> Optional[str]:
    """Devolve o rótulo saneado, ou None quando ele não pode entrar."""
    if not isinstance(valor, str):
        return None
    limpo = " ".join(valor.split())
    if not limpo or len(limpo) > TAMANHO_DO_TERMO:
        return None
    if PROIBIDO_NO_TERMO.search(limpo):
        return None
    if ESQUEMA_DE_URL.match(limpo):
        return None
    return limpo


def _sanear_terminologia(pedido: dict) -> tuple:
    """(dicionário aceito, lista de chaves recusadas)."""
    aceitos, recusados = {}, []
    for chave, valor in (pedido or {}).items():
        if chave not in CHAVES_DE_TERMO:
            recusados.append(chave)
            continue
        limpo = _limpar_termo(valor)
        if limpo is None:
            recusados.append(chave)
            continue
        aceitos[chave] = limpo
    return aceitos, recusados


def fuso_valido(nome: str) -> bool:
    try:
        ZoneInfo(nome)
        return True
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return False


def fuso_do_tenant(db: Session, tenant_id: int) -> ZoneInfo:
    """Fuso da conta, com queda para São Paulo se o valor estiver quebrado.

    Nunca levanta: um fuso inválido no banco não pode derrubar o painel
    inteiro — ele degrada para o padrão e o resto continua de pé.
    """
    nome = db.execute(
        select(Tenant.timezone).where(Tenant.id == tenant_id)
    ).scalar_one_or_none() or "America/Sao_Paulo"
    try:
        return ZoneInfo(nome)
    except Exception:
        return ZoneInfo("America/Sao_Paulo")


def _horario(valor) -> time:
    """Aceita "08:00" ou "08:00:00"."""
    if isinstance(valor, time):
        return valor
    partes = str(valor).split(":")
    try:
        hora, minuto = int(partes[0]), int(partes[1])
    except (IndexError, ValueError):
        raise errors.dados_invalidos("Horário inválido. Use HH:MM.")
    if not (0 <= hora <= 23 and 0 <= minuto <= 59):
        raise errors.dados_invalidos("Horário inválido. Use HH:MM.")
    return time(hora, minuto)


def gravar(db: Session, ctx, dados) -> tuple:
    """Aplica o que veio. Devolve (config, chaves de termo recusadas)."""
    config = obter(db, ctx.tenant_id)
    recusados = []

    if dados.jornada_inicio is not None:
        config.workday_start = _horario(dados.jornada_inicio)
    if dados.jornada_fim is not None:
        config.workday_end = _horario(dados.jornada_fim)
    if config.workday_end <= config.workday_start:
        raise errors.dados_invalidos("O fim da jornada precisa ser depois do início.")

    if dados.dias_da_semana is not None:
        dias = sorted({int(d) for d in dados.dias_da_semana if 1 <= int(d) <= 7})
        if not dias:
            raise errors.dados_invalidos("Escolha pelo menos um dia de atendimento.")
        config.workdays = ",".join(str(d) for d in dias)

    if dados.duracao_padrao is not None:
        if not (DURACAO_MIN <= dados.duracao_padrao <= DURACAO_MAX):
            raise errors.dados_invalidos(
                f"A duração padrão precisa ficar entre {DURACAO_MIN} e {DURACAO_MAX} minutos.")
        config.default_duration_min = dados.duracao_padrao

    if dados.intervalo is not None:
        if not (0 <= dados.intervalo <= INTERVALO_MAX):
            raise errors.dados_invalidos("Intervalo entre atendimentos fora do razoável.")
        config.slot_interval_min = dados.intervalo

    if dados.tolerancia_falta is not None:
        if not (0 <= dados.tolerancia_falta <= TOLERANCIA_MAX):
            raise errors.dados_invalidos("Tolerância de falta fora do razoável.")
        config.no_show_tolerance_hours = dados.tolerancia_falta

    if dados.meta_mensal is not None:
        # Zero e vazio não são a mesma coisa: vazio é "não defini meta",
        # zero seria uma meta de zero. Vazio limpa.
        meta = Decimal(dados.meta_mensal)
        if meta < 0:
            raise errors.dados_invalidos("A meta não pode ser negativa.")
        config.monthly_goal = meta or None
    elif dados.limpar_meta:
        config.monthly_goal = None

    if dados.fuso is not None:
        if not fuso_valido(dados.fuso):
            raise errors.dados_invalidos("Fuso horário não reconhecido.")
        tenant = db.get(Tenant, ctx.tenant_id)
        tenant.timezone = dados.fuso

    if dados.terminologia is not None:
        aceitos, recusados = _sanear_terminologia(dados.terminologia)
        atual = terminologia(config)
        atual.update(aceitos)
        # Valor vazio no pedido significa "volta para o padrão".
        for chave, valor in (dados.terminologia or {}).items():
            if chave in CHAVES_DE_TERMO and isinstance(valor, str) and not valor.strip():
                atual.pop(chave, None)
                if chave in recusados:
                    recusados.remove(chave)
        config.terminology = json.dumps(atual, ensure_ascii=False) if atual else None

    db.flush()
    return config, recusados
