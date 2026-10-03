"""
Ambiente dos testes.

Quatro cuidados que valem a leitura:

1. **O banco de teste é obrigatoriamente um banco `_test`.** Se a variável
   apontar para outro nome, a suíte se recusa a rodar. É a trava que
   impede um `pytest` distraído limpar o banco de desenvolvimento.
2. **O schema vem das migrations**, não de `create_all`. Testar contra um
   schema diferente do que vai para produção não prova nada.
3. **Entre testes, só as tabelas de dados são limpas.** Papéis, permissões
   e profissões vêm do seed da migration e continuam lá.
4. **A pasta de documentos também é de teste, e também é esvaziada.** Pelo
   mesmo motivo do item 1, a suíte recusa rodar se o nome da pasta não
   contiver `test`: o padrão (`arquivos`) é onde ficam os documentos reais.
"""
import os
import pathlib
import shutil
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

# A mesma trava para a pasta de documentos: a suíte também a esvazia, e o
# padrão (`arquivos`) é onde ficam os recibos e anexos de verdade.
PASTA_ARQUIVOS = pathlib.Path(settings.VC_FILES_DIR)
if not PASTA_ARQUIVOS.is_absolute():
    PASTA_ARQUIVOS = RAIZ / PASTA_ARQUIVOS
if "test" not in PASTA_ARQUIVOS.name.lower():
    raise SystemExit(
        f"Recusando rodar: VC_FILES_DIR='{settings.VC_FILES_DIR}' não é uma pasta de teste "
        "(o nome precisa conter 'test'). A suíte esvazia essa pasta."
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
    # Documento em disco sem linha no banco é lixo de teste anterior.
    shutil.rmtree(PASTA_ARQUIVOS, ignore_errors=True)
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


def hoje_na_conta(hora: int):
    """Hoje, à `hora` dada, no fuso da conta (America/Sao_Paulo) — em UTC.

    Não use `agora().replace(hour=23)` para "hoje": isso é hoje em UTC, e o
    painel conta o dia no fuso da conta. Entre 21h e meia-noite de Brasília
    as duas datas divergem, e o teste falhava sozinho — ou, pior, passava
    sem testar nada, quando esperava zero.
    """
    from datetime import datetime, time

    from app.domain.calendario import PADRAO, hoje_local, para_utc

    return para_utc(datetime.combine(hoje_local(PADRAO), time(hora)), PADRAO)


def entrar(cliente, email, senha=SENHA_PADRAO):
    return cliente.post("/auth/login", json={"email": email, "senha": senha})


def csrf(cliente):
    """O painel lê o cookie não-HttpOnly e devolve no cabeçalho."""
    from app.config import settings as s

    return {"X-CSRF-Token": cliente.cookies.get(s.VC_CSRF_COOKIE_NAME, "")}


@pytest.fixture
def cabecalho_csrf():
    return csrf
