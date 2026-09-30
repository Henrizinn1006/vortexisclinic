"""
Cookies de sessão e CSRF.

Sessão: HttpOnly (JavaScript não lê), Secure em produção, SameSite
configurável, Path=/. O navegador manda sozinho; o painel nunca precisa
guardar token em lugar nenhum — é o que tira o vetor de XSS roubar sessão.

CSRF: double submit cookie. O token vai num cookie **legível** por JS
(precisa ser, o painel copia para o cabeçalho) e é conferido contra o hash
guardado na sessão. Cookie sozinho não autentica nada: o atacante
cross-site consegue fazer o navegador mandar o cookie, mas não consegue
ler o valor para montar o cabeçalho.
"""
from fastapi import Response

from app.config import settings


def _base_kwargs() -> dict:
    kwargs = {
        "path": settings.VC_COOKIE_PATH,
        "secure": settings.VC_COOKIE_SECURE,
        "samesite": settings.VC_COOKIE_SAMESITE,
    }
    if settings.VC_COOKIE_DOMAIN:
        kwargs["domain"] = settings.VC_COOKIE_DOMAIN
    return kwargs


def gravar_sessao(resposta: Response, token: str, max_age_s: int) -> None:
    resposta.set_cookie(
        settings.VC_SESSION_COOKIE_NAME,
        token,
        httponly=True,
        max_age=max_age_s,
        **_base_kwargs(),
    )


def gravar_csrf(resposta: Response, token: str, max_age_s: int) -> None:
    resposta.set_cookie(
        settings.VC_CSRF_COOKIE_NAME,
        token,
        httponly=False,          # o painel precisa ler para enviar no cabeçalho
        max_age=max_age_s,
        **_base_kwargs(),
    )


def apagar(resposta: Response) -> None:
    for nome in (settings.VC_SESSION_COOKIE_NAME, settings.VC_CSRF_COOKIE_NAME):
        resposta.delete_cookie(
            nome,
            path=settings.VC_COOKIE_PATH,
            domain=settings.VC_COOKIE_DOMAIN or None,
        )
