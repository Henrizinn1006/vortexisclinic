"""
Senha: Argon2id, via argon2-cffi.

Nada de algoritmo próprio, nada de sha256 com sal caseiro. Argon2id é o
padrão atual recomendado para senha (vencedor do Password Hashing
Competition), e a biblioteca cuida de sal, formato e verificação em tempo
constante.

`precisa_rehash` permite subir o custo no futuro sem forçar ninguém a
trocar de senha: no próximo login válido o hash é regravado.
"""
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError, VerificationError

from app.config import settings

_hasher = PasswordHasher(
    time_cost=settings.VC_ARGON2_TIME_COST,
    memory_cost=settings.VC_ARGON2_MEMORY_KB,
    parallelism=settings.VC_ARGON2_PARALLELISM,
)

# Hash descartável usado para gastar o mesmo tempo quando o e-mail não
# existe. Sem isso, "usuário inexistente" responde bem mais rápido que
# "senha errada" — e isso enumera contas pelo relógio.
_HASH_FALSO = _hasher.hash("senha-que-nunca-sera-usada-apenas-para-tempo-constante")


def gerar_hash(senha: str) -> str:
    return _hasher.hash(senha)


def conferir(hash_armazenado: str, senha: str) -> bool:
    try:
        return _hasher.verify(hash_armazenado, senha)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def gastar_tempo_equivalente(senha: str) -> None:
    """Chamada quando o e-mail não existe, para o tempo de resposta não entregar isso."""
    try:
        _hasher.verify(_HASH_FALSO, senha)
    except Exception:
        pass


def precisa_rehash(hash_armazenado: str) -> bool:
    try:
        return _hasher.check_needs_rehash(hash_armazenado)
    except InvalidHashError:
        return True
