"""
Erros da API.

Duas regras valem em todo o arquivo:

1. **Mensagem não explica o interior.** O cliente recebe um código curto e
   uma frase genérica. Stack trace, nome de tabela, driver e SQL ficam no
   log do servidor.
2. **Recurso de outro tenant "não existe".** Responder 403 confirma que o
   registro existe — isso já é vazamento. O padrão é 404.
"""
from typing import Optional

from fastapi import HTTPException, status


class ApiError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, headers: Optional[dict] = None):
        super().__init__(status_code=status_code, detail={"code": code, "message": message}, headers=headers)


def nao_autenticado(code: str = "nao_autenticado") -> ApiError:
    return ApiError(status.HTTP_401_UNAUTHORIZED, code, "Sessão ausente ou expirada.")


def credenciais_invalidas() -> ApiError:
    # Mesma resposta para e-mail inexistente e senha errada.
    return ApiError(status.HTTP_401_UNAUTHORIZED, "credenciais_invalidas", "E-mail ou senha incorretos.")


def sem_permissao(permissao: str = "") -> ApiError:
    return ApiError(status.HTTP_403_FORBIDDEN, "sem_permissao", "Seu acesso não permite esta ação.")


def nao_encontrado(recurso: str = "") -> ApiError:
    return ApiError(status.HTTP_404_NOT_FOUND, "nao_encontrado", "Recurso não encontrado.")


def sem_contexto_de_tenant() -> ApiError:
    return ApiError(status.HTTP_409_CONFLICT, "sem_workspace_ativo", "Nenhum workspace ativo nesta sessão.")


def conflito(code: str, mensagem: str) -> ApiError:
    return ApiError(status.HTTP_409_CONFLICT, code, mensagem)


def dados_invalidos(mensagem: str = "Dados inválidos.") -> ApiError:
    return ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "dados_invalidos", mensagem)


def csrf_invalido() -> ApiError:
    return ApiError(status.HTTP_403_FORBIDDEN, "csrf_invalido", "Requisição bloqueada por verificação de origem.")


def excesso_de_tentativas(espera_s: int) -> ApiError:
    return ApiError(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "excesso_de_tentativas",
        "Muitas tentativas. Tente novamente em instantes.",
        headers={"Retry-After": str(espera_s)},
    )
