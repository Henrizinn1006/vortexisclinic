"""
Confere se um .env está pronto para produção — antes de subir a API.

    python scripts/verificar_producao.py                  # confere o .env
    python scripts/verificar_producao.py --env /caminho/.env
    python scripts/verificar_producao.py --sem-banco      # não tenta conectar

Sai com código 1 se houver FALHA: use como `ExecStartPre=` do systemd (ou
passo de deploy) e a API não sobe com configuração frouxa.

`Settings.validar_producao()` já recusa o boot nos casos mais graves. Este
script vai além — confere formato da chave clínica, HTTPS das origens,
e-mail, pasta de arquivos e versão do banco — e mostra TUDO de uma vez, em
vez de parar no primeiro erro.

**Nunca imprime valor de segredo.** Diz "VC_DB_PASSWORD vazia", nunca qual
é a senha. Se você mexer aqui, mantenha isso.
"""
import argparse
import hashlib
import os
import pathlib
import sys
from urllib.parse import urlparse

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

FALHA, AVISO, OK = "FALHA", "AVISO", "ok"


def _https(url: str) -> bool:
    return urlparse(url).scheme == "https"


def _local(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "0.0.0.0", "::1")


def conferir_config(s) -> list:
    r = []

    def item(nivel, texto):
        r.append((nivel, texto))

    # ---------------- ambiente ----------------
    item(OK if s.VC_ENV == "production" else FALHA,
         f"VC_ENV={s.VC_ENV} (precisa ser production)")
    item(FALHA if s.VC_DEBUG else OK, "VC_DEBUG desligado" if not s.VC_DEBUG
         else "VC_DEBUG ligado: desligue em produção")
    item(FALHA if s.VC_DB_ECHO else OK, "VC_DB_ECHO desligado" if not s.VC_DB_ECHO
         else "VC_DB_ECHO ligado: imprime todo SQL no log, inclusive dado de gente")
    if s.VC_LOG_LEVEL.upper() == "DEBUG":
        item(AVISO, "VC_LOG_LEVEL=DEBUG: verboso demais para produção")

    # ---------------- banco ----------------
    item(OK if s.VC_DB_PASSWORD else FALHA,
         "VC_DB_PASSWORD preenchida" if s.VC_DB_PASSWORD else "VC_DB_PASSWORD vazia")
    if s.VC_DB_USER == "root":
        item(FALHA, "VC_DB_USER=root: use um usuário só deste banco")
    if s.VC_DB_NAME.endswith("_test"):
        item(FALHA, "VC_DB_NAME termina em _test: este é o banco que a suíte APAGA")

    # ---------------- sessão ----------------
    item(OK if s.VC_COOKIE_SECURE else FALHA,
         "VC_COOKIE_SECURE=true" if s.VC_COOKIE_SECURE
         else "VC_COOKIE_SECURE=false: o cookie de sessão viajaria sem HTTPS")
    if s.VC_COOKIE_SAMESITE == "none" and not s.VC_COOKIE_SECURE:
        item(FALHA, "SameSite=None exige cookie Secure")

    # ---------------- origens ----------------
    origens = s.cors_origins
    if not origens:
        item(OK, "VC_CORS_ORIGINS vazio: só a mesma origem (painel e API no mesmo domínio)")
    for o in origens:
        if not _https(o) or _local(o):
            item(FALHA, f"origem do CORS sem HTTPS ou local: {o}")
    if origens and all(_https(o) and not _local(o) for o in origens):
        item(OK, f"{len(origens)} origem(ns) do CORS, todas HTTPS")

    painel = s.painel_url
    if not painel:
        item(FALHA, "VC_PANEL_URL vazio: links de convite e de senha sairiam quebrados")
    elif not _https(painel) or _local(painel):
        item(FALHA, f"VC_PANEL_URL sem HTTPS ou local: {painel}")
    else:
        item(OK, f"VC_PANEL_URL={painel}")

    # ---------------- chave clínica ----------------
    r.extend(conferir_chaves(s))

    # ---------------- e-mail ----------------
    if s.VC_MAIL_BACKEND == "console":
        item(FALHA, "VC_MAIL_BACKEND=console: imprime e-mails (com link de troca de senha) no log")
    elif s.VC_MAIL_BACKEND == "queue":
        item(AVISO, "VC_MAIL_BACKEND=queue: e-mails ficam na fila e não saem até haver SMTP")
    else:
        faltando = [n for n in ("VC_SMTP_HOST", "VC_SMTP_USER", "VC_SMTP_PASSWORD") if not getattr(s, n)]
        item(FALHA if faltando else OK,
             "SMTP sem " + ", ".join(faltando) if faltando else "SMTP configurado")
        if not s.VC_SMTP_TLS:
            item(FALHA, "VC_SMTP_TLS=false: a senha do SMTP viajaria aberta")
    if "exemplo.com" in s.VC_MAIL_FROM:
        item(AVISO, "VC_MAIL_FROM ainda é o endereço de exemplo")

    # ---------------- arquivos ----------------
    pasta = pathlib.Path(s.VC_FILES_DIR)
    if not pasta.is_absolute():
        pasta = RAIZ / pasta
    if not pasta.exists():
        item(AVISO, f"VC_FILES_DIR não existe ainda ({pasta}); será criada no primeiro upload")
    elif not os.access(pasta, os.W_OK):
        item(FALHA, f"VC_FILES_DIR sem permissão de escrita ({pasta})")
    else:
        item(OK, "VC_FILES_DIR existe e aceita escrita")
    return r


def conferir_chaves(s) -> list:
    from app.security.crypto import TAMANHO_CHAVE, _DEV, _decodificar

    cru = (s.VC_CLINICAL_KEYS or "").strip()
    if not cru:
        return [(FALHA, "VC_CLINICAL_KEYS vazia: o prontuário seria cifrado com a chave de "
                        "desenvolvimento, que está no código")]
    r, versoes = [], {}
    for parte in [p.strip() for p in cru.split(",") if p.strip()]:
        if ":" not in parte:
            return [(FALHA, "VC_CLINICAL_KEYS fora do formato 'versao:chave_base64'")]
        versao, material = parte.split(":", 1)
        try:
            bruto = _decodificar(material)
        except Exception:
            return [(FALHA, f"VC_CLINICAL_KEYS: a versão {versao} não é base64 válido")]
        if len(bruto) != TAMANHO_CHAVE:
            r.append((FALHA, f"VC_CLINICAL_KEYS: a versão {versao} não tem 32 bytes"))
        if bruto == hashlib.sha256(_DEV).digest():
            r.append((FALHA, f"VC_CLINICAL_KEYS: a versão {versao} é a chave de desenvolvimento"))
        versoes[versao.strip()] = bruto
    if str(s.VC_CLINICAL_KEY_VERSION) not in versoes:
        r.append((FALHA, f"VC_CLINICAL_KEY_VERSION={s.VC_CLINICAL_KEY_VERSION} não está em "
                         "VC_CLINICAL_KEYS: a primeira nota gravada daria erro"))
    if not r:
        r.append((OK, f"chave clínica válida ({len(versoes)} versão(ões); grava com a "
                      f"{s.VC_CLINICAL_KEY_VERSION}) — confira que há cópia fora do servidor"))
    return r


def conferir_banco(s) -> list:
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine, text

    cabeca = ScriptDirectory.from_config(Config(str(RAIZ / "alembic.ini"))).get_current_head()
    try:
        motor = create_engine(s.database_url, pool_pre_ping=True)
        with motor.connect() as c:
            versao = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
        motor.dispose()
    except Exception as e:
        # A mensagem do driver não leva a senha; mesmo assim, só o tipo e o código.
        codigo = getattr(getattr(e, "orig", None), "args", [None])[0]
        return [(FALHA, f"banco inacessível ({type(e).__name__}, código {codigo})")]
    if versao != cabeca:
        return [(FALHA, f"banco na versão {versao}, código espera {cabeca}: rode "
                        "`python -m alembic upgrade head` (depois de um backup)")]
    return [(OK, f"banco acessível e na versão {versao}")]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--env", default=str(RAIZ / ".env"), help="arquivo .env a conferir")
    p.add_argument("--sem-banco", action="store_true", help="não tenta conectar no banco")
    args = p.parse_args(argv)

    if not pathlib.Path(args.env).exists():
        print(f"FALHA  arquivo não encontrado: {args.env}")
        return 1

    from app.config import Settings

    s = Settings(_env_file=args.env)
    resultados = conferir_config(s)
    if not args.sem_banco:
        resultados.extend(conferir_banco(s))

    for nivel, texto in resultados:
        print(f"{nivel:<6} {texto}")
    falhas = sum(1 for n, _ in resultados if n == FALHA)
    avisos = sum(1 for n, _ in resultados if n == AVISO)
    print()
    print(f"{falhas} falha(s), {avisos} aviso(s).", "NÃO SUBA assim." if falhas else "Pode subir.")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
