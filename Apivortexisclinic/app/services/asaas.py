"""
Cliente do Asaas — só o que a cobrança de assinatura precisa.

Três regras:

* **Falha do gateway não vaza.** O cliente recebe "cobrança indisponível";
  o corpo do erro do Asaas (que pode ter CPF, e-mail) vai só para o log, sem
  o corpo da requisição.
* **Sem chave, desligado.** `VC_ASAAS_API_KEY` vazia faz tudo aqui recusar
  com 503, em vez de tentar e falhar de forma confusa.
* **Dado de cobrança não é guardado.** O CPF/CNPJ vai ao Asaas e não toca o
  nosso banco.
"""
import logging
from typing import Optional

import httpx

from app import errors
from app.config import settings

log = logging.getLogger("vc.asaas")

PROVEDOR = "asaas"

# Os testes trocam isto por um `httpx.MockTransport`.
_transporte: Optional[httpx.BaseTransport] = None


def ativo() -> bool:
    return bool(settings.VC_ASAAS_API_KEY)


def _indisponivel() -> errors.ApiError:
    return errors.ApiError(503, "cobranca_indisponivel",
                           "A cobrança está indisponível no momento. Tente novamente em instantes.")


def _motivo(r: httpx.Response) -> str:
    """A frase de validação do Asaas ("valor mínimo é R$ 5,00", "CPF inválido").

    São mensagens de regra, sem dado da pessoa; só a primeira, e curta.
    """
    try:
        frase = (r.json().get("errors") or [{}])[0].get("description") or ""
    except ValueError:
        frase = ""
    return f"O gateway recusou os dados: {frase[:160]}" if frase else         "O gateway recusou os dados informados."


def _chamar(metodo: str, caminho: str, corpo: Optional[dict] = None) -> dict:
    if not ativo():
        raise _indisponivel()
    try:
        with httpx.Client(
            base_url=settings.VC_ASAAS_BASE_URL.rstrip("/"),
            headers={"access_token": settings.VC_ASAAS_API_KEY,
                     "User-Agent": "vortexis-clinic"},
            timeout=settings.VC_ASAAS_TIMEOUT_S,
            transport=_transporte,
        ) as http:
            r = http.request(metodo, caminho, json=corpo)
    except httpx.HTTPError as exc:
        log.error("asaas %s %s: falha de rede (%s)", metodo, caminho, type(exc).__name__)
        raise _indisponivel()

    if r.status_code == 400:
        # Dado recusado pelo Asaas (CPF inválido, por exemplo): é erro de
        # quem digitou, não do gateway.
        log.warning("asaas %s %s: 400 %s", metodo, caminho, r.text[:300])
        raise errors.dados_invalidos(_motivo(r))
    if r.status_code == 404:
        raise errors.nao_encontrado()
    if r.status_code >= 300:
        log.error("asaas %s %s: %s %s", metodo, caminho, r.status_code, r.text[:300])
        raise _indisponivel()
    return r.json() if r.content else {}


def criar_cliente(*, nome: str, email: str, cpf_cnpj: str, ref: str) -> str:
    dados = _chamar("POST", "/customers", {
        "name": nome, "email": email, "cpfCnpj": cpf_cnpj,
        "externalReference": ref, "notificationDisabled": False,
    })
    return dados["id"]


def criar_assinatura(*, cliente_id: str, valor, primeiro_vencimento: str,
                     descricao: str, ref: str) -> str:
    dados = _chamar("POST", "/subscriptions", {
        "customer": cliente_id,
        # UNDEFINED: quem paga escolhe Pix, boleto ou cartão na fatura.
        "billingType": "UNDEFINED",
        "value": float(valor),
        "nextDueDate": primeiro_vencimento,
        "cycle": "MONTHLY",
        "description": descricao[:500],
        "externalReference": ref,
    })
    return dados["id"]


def link_da_primeira_cobranca(assinatura_id: str) -> Optional[str]:
    dados = _chamar("GET", f"/subscriptions/{assinatura_id}/payments")
    itens = dados.get("data") or []
    return itens[0].get("invoiceUrl") if itens else None


def cancelar_assinatura(assinatura_id: str) -> None:
    try:
        _chamar("DELETE", f"/subscriptions/{assinatura_id}")
    except errors.ApiError as e:
        # Já removida lá: o objetivo (não cobrar mais) está cumprido.
        if e.status_code == 404:
            return
        raise
