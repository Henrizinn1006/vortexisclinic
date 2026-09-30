"""
Cifra do conteúdo clínico.

**Por que cifrar isto e não o resto**

O banco inteiro pode (e deve) ficar em disco cifrado, mas isso protege
contra o disco ser levado embora — não contra quem tem acesso legítimo ao
banco. O conteúdo do prontuário é a única coisa no sistema cuja leitura
indevida não tem conserto: agenda errada se corrige, evolução lida não se
desle. Então ele é cifrado na aplicação, com uma chave que **não mora no
banco**.

A consequência prática é a resposta à regra que o produto assumiu: quem
administra a plataforma tem acesso ao banco, e acesso ao banco entrega
texto cifrado. Ler exige também a chave, que vive na configuração do
servidor de aplicação, fora do dump.

**Como a chave é derivada**

    chave_da_nota = HKDF(mestre_da_versão, sal_da_nota, info="vc-clinical|<tenant>")

Duas propriedades saem daí de graça:

1. Cada nota tem sal próprio. Apagar o sal torna o conteúdo daquela nota
   irrecuperável **sem apagar linha nenhuma** — é o caminho honesto para
   um pedido de exclusão do titular: o texto some, a trilha de auditoria e
   os metadados contábeis sobrevivem. (Ver `esquecer_conteudo`.)
2. O tenant entra na derivação. Chave de uma conta não abre nota de outra
   nem por engano de código.

**O isolamento também é criptográfico**

O AAD do AES-GCM é `vc1|<tenant>|<nota>|<versão>`. AAD não é guardado no
registro: é reconstruído na leitura. Se uma linha for movida de uma conta
para outra — no banco, por fora da aplicação — a decifragem **falha**, em
vez de devolver o texto para a conta errada. É o isolamento multi-tenant
sustentado por matemática, não só por cláusula WHERE.

**Rotação**

`VC_CLINICAL_KEYS` guarda várias versões (`1:...,2:...`).
`VC_CLINICAL_KEY_VERSION` diz qual escreve. As antigas continuam
disponíveis para leitura, então rotacionar não exige reescrever o acervo.
Nenhuma chave aparece neste arquivo nem no repositório.
"""
import base64
import hashlib
import logging
import os
from typing import Dict, Optional, Tuple

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import settings

log = logging.getLogger("vc.crypto")

TAMANHO_SAL = 16
TAMANHO_NONCE = 12
TAMANHO_CHAVE = 32

# Usada só quando VC_CLINICAL_KEYS está vazio, e só fora de produção.
# `validar_producao()` recusa subir em produção sem chave configurada, então
# este caminho não existe em produção.
_DEV = b"vortexis-clinic-desenvolvimento-nao-usar-em-producao"


class ConteudoIlegivel(Exception):
    """Ciphertext que não abre: chave errada, versão sumida ou registro adulterado."""


def _decodificar(valor: str) -> bytes:
    bruto = valor.strip()
    faltando = (-len(bruto)) % 4
    return base64.urlsafe_b64decode(bruto + "=" * faltando)


def _carregar_chaves() -> Tuple[Dict[int, bytes], int]:
    """Lê VC_CLINICAL_KEYS. Nunca registra o valor — só quantas versões achou."""
    cru = (settings.VC_CLINICAL_KEYS or "").strip()
    if not cru:
        if settings.is_production:      # cinto além do suspensório de validar_producao()
            raise RuntimeError("VC_CLINICAL_KEYS é obrigatório em produção")
        log.warning(
            "VC_CLINICAL_KEYS vazio: usando chave de desenvolvimento. "
            "O conteúdo clínico NÃO está protegido nesta instância."
        )
        derivada = hashlib.sha256(_DEV).digest()
        return {0: derivada}, 0

    chaves: Dict[int, bytes] = {}
    for parte in cru.split(","):
        parte = parte.strip()
        if not parte:
            continue
        if ":" not in parte:
            raise RuntimeError("VC_CLINICAL_KEYS: formato esperado 'versao:chave_base64'")
        versao, material = parte.split(":", 1)
        try:
            bruto = _decodificar(material)
        except Exception:
            raise RuntimeError("VC_CLINICAL_KEYS: chave não é base64 válido")
        if len(bruto) != TAMANHO_CHAVE:
            raise RuntimeError("VC_CLINICAL_KEYS: cada chave precisa ter 32 bytes")
        chaves[int(versao)] = bruto

    atual = settings.VC_CLINICAL_KEY_VERSION
    if atual not in chaves:
        raise RuntimeError("VC_CLINICAL_KEY_VERSION não consta em VC_CLINICAL_KEYS")
    return chaves, atual


_cache: Optional[Tuple[Dict[int, bytes], int]] = None


def _chaves() -> Tuple[Dict[int, bytes], int]:
    global _cache
    if _cache is None:
        _cache = _carregar_chaves()
    return _cache


def recarregar() -> None:
    """Esquece o cache de chaves. Serve aos testes; não é chamado em requisição."""
    global _cache
    _cache = None


def versao_de_escrita() -> int:
    return _chaves()[1]


def novo_sal() -> bytes:
    return os.urandom(TAMANHO_SAL)


def _derivar(versao_chave: int, sal: bytes, tenant_id: int) -> bytes:
    chaves, _ = _chaves()
    mestre = chaves.get(versao_chave)
    if mestre is None:
        raise ConteudoIlegivel(f"versão de chave {versao_chave} não está configurada")
    return HKDF(
        algorithm=hashes.SHA256(),
        length=TAMANHO_CHAVE,
        salt=sal,
        info=b"vc-clinical|" + str(int(tenant_id)).encode(),
    ).derive(mestre)


def _aad(tenant_id: int, nota_id: int, versao: int) -> bytes:
    """Amarra o texto ao lugar dele. Não é guardado: é reconstruído na leitura."""
    return f"vc1|{int(tenant_id)}|{int(nota_id)}|{int(versao)}".encode()


def impressao(texto: str) -> str:
    """sha256 do texto em claro.

    Serve a duas coisas: detectar salvamento sem mudança (não cria versão
    nova) e permitir conferir integridade depois de decifrar. Não é
    substituto de assinatura — e por ser hash de texto livre, não vira
    caminho de volta ao conteúdo.
    """
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def cifrar(texto: str, *, sal: bytes, tenant_id: int, nota_id: int, versao: int):
    """Devolve (ciphertext, nonce, versao_da_chave)."""
    versao_chave = versao_de_escrita()
    chave = _derivar(versao_chave, sal, tenant_id)
    nonce = os.urandom(TAMANHO_NONCE)
    cifrado = AESGCM(chave).encrypt(
        nonce, texto.encode("utf-8"), _aad(tenant_id, nota_id, versao)
    )
    return cifrado, nonce, versao_chave


def decifrar(cifrado: bytes, *, nonce: bytes, sal: Optional[bytes], versao_chave: int,
             tenant_id: int, nota_id: int, versao: int) -> str:
    if not sal:
        # Sal apagado: conteúdo destruído de propósito (pedido do titular).
        raise ConteudoIlegivel("conteúdo apagado a pedido do titular")
    chave = _derivar(versao_chave, sal, tenant_id)
    try:
        aberto = AESGCM(chave).decrypt(
            bytes(nonce), bytes(cifrado), _aad(tenant_id, nota_id, versao)
        )
    except InvalidTag:
        # Chave errada, registro adulterado ou linha movida entre contas.
        raise ConteudoIlegivel("conteúdo não confere")
    return aberto.decode("utf-8")


# ---------------- arquivos ----------------
# Documento é o mesmo problema do prontuário com outra casca: conteúdo
# sensível que não pode ficar legível para quem tem o disco. Mesma chave
# mestra, mesma derivação por registro, AAD com prefixo próprio — para
# que um ciphertext de nota nunca abra como documento, nem o contrário.
def _aad_arquivo(tenant_id: int, documento_id: int) -> bytes:
    return f"vc1d|{int(tenant_id)}|{int(documento_id)}".encode()


def cifrar_bytes(conteudo: bytes, *, sal: bytes, tenant_id: int, documento_id: int):
    versao_chave = versao_de_escrita()
    chave = _derivar(versao_chave, sal, tenant_id)
    nonce = os.urandom(TAMANHO_NONCE)
    cifrado = AESGCM(chave).encrypt(nonce, conteudo, _aad_arquivo(tenant_id, documento_id))
    return cifrado, nonce, versao_chave


def decifrar_bytes(cifrado: bytes, *, nonce: bytes, sal: Optional[bytes], versao_chave: int,
                   tenant_id: int, documento_id: int) -> bytes:
    if not sal:
        raise ConteudoIlegivel("arquivo apagado a pedido do titular")
    chave = _derivar(versao_chave, sal, tenant_id)
    try:
        return AESGCM(chave).decrypt(bytes(nonce), bytes(cifrado),
                                     _aad_arquivo(tenant_id, documento_id))
    except InvalidTag:
        raise ConteudoIlegivel("arquivo não confere")
