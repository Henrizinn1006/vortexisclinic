"""
Contexto da requisição: quem é o usuário e em qual tenant ele está.

Isto é um `contextvar`, não uma variável global: cada requisição tem o seu,
inclusive sob concorrência. Nada aqui vem do corpo, da query string ou de
cabeçalho enviado pelo navegador — o contexto é preenchido pelo servidor
depois de validar a sessão.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional

_tenant_id: ContextVar[Optional[int]] = ContextVar("vc_tenant_id", default=None)
_user_id: ContextVar[Optional[int]] = ContextVar("vc_user_id", default=None)
_sem_escopo: ContextVar[bool] = ContextVar("vc_sem_escopo", default=False)


class TenantContextError(RuntimeError):
    """Operação tenant-scoped sem tenant no contexto. Sempre erro, nunca consulta ampla."""


def definir_tenant(tenant_id: Optional[int]):
    return _tenant_id.set(tenant_id)


def definir_usuario(user_id: Optional[int]):
    return _user_id.set(user_id)


def tenant_atual() -> Optional[int]:
    return _tenant_id.get()


def usuario_atual() -> Optional[int]:
    return _user_id.get()


def exigir_tenant() -> int:
    tid = _tenant_id.get()
    if tid is None:
        raise TenantContextError("operação tenant-scoped sem tenant no contexto")
    return tid


def limpar():
    _tenant_id.set(None)
    _user_id.set(None)
    _sem_escopo.set(False)


def escopo_desligado() -> bool:
    return _sem_escopo.get()


@contextmanager
def sem_escopo_de_tenant():
    """Escotilha de emergência — uso administrativo, explícito e raro.

    Existe para migration, seed e rotina interna da plataforma. Nenhum
    endpoint de produto usa isto; se algum usar, é bug. Por ser explícito,
    aparece no diff e no code review.
    """
    token = _sem_escopo.set(True)
    try:
        yield
    finally:
        _sem_escopo.reset(token)
