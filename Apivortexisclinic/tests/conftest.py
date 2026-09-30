"""
Ambiente dos testes.

Três cuidados que valem a leitura:

1. **O banco de teste é obrigatoriamente um banco `_test`.** Se a variável
   apontar para outro nome, a suíte se recusa a rodar. É a trava que
   impede um `pytest` distraído limpar o banco de desenvolvimento.
2. **O schema vem das migrations**, não de `create_all`. Testar contra um
   schema diferente do que vai para produção não prova nada.
3. **Entre testes, só as tabelas de dados são limpas.** Papéis, permissões
   e profissões vêm do seed da migration e continuam lá.
"""
import os
import pathlib
import subprocess
import sys

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

# Carrega .env.test antes de importar a aplicação (a config é lida no import).
from dotenv import load_dotenv  # noqa: E402

load_dotenv(RAIZ / ".env.test", override=True)
os.environ.setdefault("VC_ENV", "test")

from app.config import settings  # noqa: E402

if not settings.VC_DB_NAME.endswith("_test"):
    raise SystemExit(
        f"Recusando rodar: VC_DB_NAME='{settings.VC_DB_NAME}' não termina em '_test'. "
        "A suíte limpa tabelas — aponte para um banco de teste."
    )

from sqlalchemy import text  # noqa: E402

from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security.ratelimit import limitador  # noqa: E402

# Tabelas que o seed preenche e os testes não devem apagar.
PRESERVAR = {"alembic_version", "roles", "permissions", "role_permissions", "professions",
             "plans"}


@pytest.fixture(scope="session", autouse=True)
def migrar():
    """Sobe o schema pelas migrations, uma vez por sessão de teste."""
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(RAIZ),
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0:
        raise SystemExit("alembic upgrade falhou:\n" + resultado.stdout + resultado.stderr)
    yield


@pytest.fixture(autouse=True)
def banco_limpo(migrar):
    """Cada teste começa com as tabelas de dados vazias."""
    with engine.begin() as conn:
        nomes = [
            linha[0]
            for linha in conn.execute(text("SHOW TABLES")).all()
            if linha[0] not in PRESERVAR
        ]
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for nome in nomes:
            conn.execute(text(f"DELETE FROM `{nome}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    limitador.zerar_tudo()
    yield


@pytest.fixture
def db():
    """Sessão de leitura/escrita para o teste.

    READ COMMITTED de propósito: o padrão do MySQL (REPEATABLE READ)
    congela o snapshot na primeira consulta, e o teste deixaria de
    enxergar as linhas que a API gravou depois disso — dando falso
    verde (ou falso vermelho) sem nada a ver com o código testado.
    """
    sessao = SessionLocal()
    sessao.connection(execution_options={"isolation_level": "READ COMMITTED"})
    try:
        yield sessao
    finally:
        sessao.close()


@pytest.fixture
def cliente():
    """Cliente HTTP com cookies — é assim que o navegador conversa com a API."""
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


# ---------------- atalhos ----------------
SENHA_PADRAO = "SenhaDeTeste!2026"


def cadastrar(cliente, *, nome, email, workspace, profissao=None, registro=None, senha=SENHA_PADRAO):
    corpo = {
        "nome": nome,
        "email": email,
        "senha": senha,
        "workspace": workspace,
    }
    if profissao:
        corpo["profissao"] = profissao
    if registro:
        corpo["registro"] = registro
    return cliente.post("/auth/register", json=corpo)


def entrar(cliente, email, senha=SENHA_PADRAO):
    return cliente.post("/auth/login", json={"email": email, "senha": senha})


def csrf(cliente):
    """O painel lê o cookie não-HttpOnly e devolve no cabeçalho."""
    from app.config import settings as s

    return {"X-CSRF-Token": cliente.cookies.get(s.VC_CSRF_COOKIE_NAME, "")}


@pytest.fixture
def cabecalho_csrf():
    return csrf
