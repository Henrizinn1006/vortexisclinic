"""
Tokens opacos: sessão, CSRF e recuperação de senha.

O token é aleatório puro (32 bytes de `secrets`), sem conteúdo e sem
assinatura — ele não "diz" nada, só aponta para uma linha da tabela. O que
fica guardado é o sha256 dele. Comparação sempre com `compare_digest`, para
não vazar informação pelo tempo de resposta.
"""
import hashlib
import secrets

TAMANHO_BYTES = 32


def novo_token() -> str:
    """URL-safe, ~43 caracteres, 256 bits de entropia."""
    return secrets.token_urlsafe(TAMANHO_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def confere(token: str, hash_esperado: str) -> bool:
    return secrets.compare_digest(hash_token(token), hash_esperado)
