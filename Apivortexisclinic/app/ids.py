"""
Identificador público: ULID em Crockford base32 (26 caracteres).

Por que não UUID4: ULID é ordenável por tempo, o que mantém o índice
secundário saudável no InnoDB. Por que não o id sequencial: expor
"paciente 1832" entrega volume de negócio e convida a enumeração.

Implementação própria e minúscula porque a alternativa era mais uma
dependência para 20 linhas. Aleatoriedade vem de `secrets`.
"""
import os
import time

_ALFABETO = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford: sem I, L, O, U


def _b32(valor: int, tamanho: int) -> str:
    saida = []
    for _ in range(tamanho):
        saida.append(_ALFABETO[valor & 31])
        valor >>= 5
    return "".join(reversed(saida))


def novo_ulid() -> str:
    ms = int(time.time() * 1000)
    aleatorio = int.from_bytes(os.urandom(10), "big")
    return _b32(ms, 10) + _b32(aleatorio, 16)


def valido(valor: str) -> bool:
    return (
        isinstance(valor, str)
        and len(valor) == 26
        and all(c in _ALFABETO for c in valor.upper())
    )
