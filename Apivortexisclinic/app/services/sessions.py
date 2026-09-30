"""
Ciclo de vida da sessão opaca.

Pontos que importam para segurança:

- **Session fixation**: o token é criado no login e ROTACIONADO em toda
  troca de privilégio (troca de workspace). Um token obtido antes do login
  nunca continua válido depois dele.
- **Duas expirações**: ociosidade (desliza a cada uso) e absoluta (não
  desliza). Sessão esquecida em máquina de consultório morre sozinha.
- **Revogação**: logout revoga uma; troca de senha revoga todas.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.ids import novo_ulid
from app.models.security import AuthSession
from app.security import tokens


def agora() -> datetime:
    """Sempre UTC, sem tzinfo (o MySQL guarda DATETIME sem fuso)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _prazos(inicio: datetime) -> Tuple[datetime, datetime]:
    return (
        inicio + timedelta(minutes=settings.VC_SESSION_IDLE_MINUTES),
        inicio + timedelta(hours=settings.VC_SESSION_ABSOLUTE_HOURS),
    )


def criar(
    db: Session,
    user_id: int,
    ip: Optional[bytes] = None,
    user_agent: Optional[str] = None,
    tenant_id: Optional[int] = None,
) -> Tuple[AuthSession, str, str]:
    """Cria a sessão. Devolve (linha, token_da_sessao, token_csrf).

    Os tokens em claro só existem aqui e no cookie da resposta — o banco
    guarda apenas o hash.
    """
    inicio = agora()
    idle, absoluto = _prazos(inicio)
    token = tokens.novo_token()
    csrf = tokens.novo_token()

    sessao = AuthSession(
        public_id=novo_ulid(),
        user_id=user_id,
        token_hash=tokens.hash_token(token),
        csrf_hash=tokens.hash_token(csrf),
        active_tenant_id=tenant_id,
        idle_expires_at=idle,
        absolute_expires_at=absoluto,
        last_seen_at=inicio,
        ip=ip,
        user_agent=(user_agent or "")[:255] or None,
    )
    db.add(sessao)
    db.flush()
    return sessao, token, csrf


def buscar_vigente(db: Session, token: str) -> Optional[AuthSession]:
    if not token:
        return None
    sessao = db.execute(
        select(AuthSession).where(AuthSession.token_hash == tokens.hash_token(token))
    ).scalar_one_or_none()
    if sessao is None or not sessao.vigente(agora()):
        return None
    return sessao


def tocar(db: Session, sessao: AuthSession) -> None:
    """Desliza a expiração por ociosidade. A absoluta nunca se move."""
    momento = agora()
    sessao.last_seen_at = momento
    sessao.idle_expires_at = momento + timedelta(minutes=settings.VC_SESSION_IDLE_MINUTES)


def rotacionar(db: Session, sessao: AuthSession) -> Tuple[str, str]:
    """Troca o par de tokens mantendo a mesma linha (anti session fixation)."""
    token = tokens.novo_token()
    csrf = tokens.novo_token()
    sessao.token_hash = tokens.hash_token(token)
    sessao.csrf_hash = tokens.hash_token(csrf)
    db.flush()
    return token, csrf


def revogar(db: Session, sessao: AuthSession, motivo: str = "logout") -> None:
    sessao.revoked_at = agora()
    sessao.revoked_reason = motivo[:40]
    db.flush()


def revogar_todas_do_usuario(db: Session, user_id: int, motivo: str = "password_reset") -> int:
    resultado = db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=agora(), revoked_reason=motivo[:40])
    )
    return resultado.rowcount or 0


def max_age_segundos() -> int:
    return settings.VC_SESSION_ABSOLUTE_HOURS * 3600
