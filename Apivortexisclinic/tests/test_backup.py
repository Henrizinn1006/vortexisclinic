"""
Backup que nunca foi restaurado não é backup — é esperança.

Este teste faz o caminho inteiro contra o banco de teste: cadastra conta,
pessoa, atendimento, pagamento, nota clínica e um recibo em PDF; gera o
backup; APAGA o banco e os arquivos; restaura; e confere que a pessoa
consegue entrar de novo, que a nota abre com o mesmo texto e que o PDF
sai igual.

O que ele trava em especial: binário (cifra, nonce, sal) atravessando o
backup sem um bit trocado. Um byte errado ali e o prontuário não abre
nunca mais — e ninguém descobre até precisar.
"""
import shutil
import subprocess
import sys
import zipfile
from datetime import timedelta

import pytest
from sqlalchemy import text

from app.config import settings
from app.db.session import engine
from app.services.sessions import agora
from scripts import backup
from tests.conftest import RAIZ, cadastrar, csrf, entrar

ONTEM = (agora() - timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)
TEXTO = "Sessão 4. Falou da mudança de cidade; dormiu melhor. Retomar na próxima."
NOME = "Ana D'Ávila \"Bia\" Ñúñez"          # aspas, apóstrofo e acento atravessando o SQL


def _apagar_tudo():
    with engine.begin() as c:
        c.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for (nome,) in c.execute(text("SHOW TABLES")).all():
            c.execute(text(f"DROP TABLE `{nome}`"))
        c.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    engine.dispose()


@pytest.fixture
def schema_garantido():
    """Se a restauração falhar no meio, o banco de teste fica sem tabelas e a
    suíte inteira quebra depois. Aqui o schema volta pelas migrations."""
    yield
    with engine.connect() as c:
        tabelas = len(c.execute(text("SHOW TABLES")).all())
    if tabelas < 33:
        _apagar_tudo()
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       cwd=str(RAIZ), check=True, capture_output=True)


@pytest.fixture
def cenario(cliente):
    r = cadastrar(cliente, nome="Clara Mendes", email="clara@exemplo.com",
                  workspace="Clínica Bem Viver", profissao="terapia_integrativa")
    assert r.status_code == 201
    pessoa = cliente.post("/workspace/clients", json={"nome": NOME, "valor_sessao": "180.50"},
                          headers=csrf(cliente)).json()
    a = cliente.post("/workspace/appointments",
                     json={"cliente_id": pessoa["id"], "inicio": ONTEM.isoformat()},
                     headers=csrf(cliente)).json()
    cliente.post(f"/workspace/appointments/{a['id']}/status", json={"status": "done"},
                 headers=csrf(cliente))
    assert cliente.post(f"/workspace/appointments/{a['id']}/payment", json={"metodo": "pix"},
                        headers=csrf(cliente)).status_code == 201
    nota = cliente.post(f"/workspace/clients/{pessoa['id']}/notes",
                        json={"conteudo": TEXTO, "ocorrido_em": ONTEM.isoformat()},
                        headers=csrf(cliente)).json()
    recibo = cliente.post(f"/workspace/clients/{pessoa['id']}/documents/receipt",
                          json={}, headers=csrf(cliente))
    assert recibo.status_code == 201, recibo.text
    pdf = cliente.get(f"/workspace/documents/{recibo.json()['id']}/content").content
    return {"pessoa": pessoa, "nota": nota, "recibo": recibo.json(), "pdf": pdf}


def test_backup_restaurado_devolve_tudo_inclusive_o_cifrado(cliente, cenario, tmp_path,
                                                             schema_garantido):
    arquivo = backup.gerar(settings, tmp_path)
    manifesto = backup.conferir(arquivo)
    assert manifesto["versao_alembic"] == "0011_planos"
    assert manifesto["tabelas"]["clinical_note_versions"] == 1
    assert len(manifesto["arquivos"]) == 1                  # o PDF do recibo

    # Restaurar por cima de banco com dado é recusado, sem tocar em nada.
    with pytest.raises(RuntimeError, match="não está vazio"):
        backup.restaurar(settings, arquivo)

    # O desastre: banco e arquivos somem.
    _apagar_tudo()
    shutil.rmtree(backup._pasta_arquivos(settings), ignore_errors=True)

    backup.restaurar(settings, arquivo)

    cliente.cookies.clear()
    assert entrar(cliente, "clara@exemplo.com").status_code == 200   # hash Argon2 intacto
    pessoas = cliente.get("/workspace/clients").json()
    assert [p["nome"] for p in pessoas] == [NOME]
    conteudo = cliente.get(f"/workspace/notes/{cenario['nota']['id']}/content")
    assert conteudo.status_code == 200, conteudo.text
    assert conteudo.json()["conteudo"] == TEXTO                      # cifra + nonce + sal intactos
    pdf = cliente.get(f"/workspace/documents/{cenario['recibo']['id']}/content").content
    assert pdf == cenario["pdf"]


def test_backup_corrompido_e_recusado_antes_de_tocar_no_banco(cliente, cenario, tmp_path):
    arquivo = backup.gerar(settings, tmp_path)
    estragado = tmp_path / "estragado.zip"
    with zipfile.ZipFile(arquivo) as origem, zipfile.ZipFile(estragado, "w") as destino:
        for item in origem.infolist():
            dados = origem.read(item.filename)
            if item.filename == "banco.sql":
                dados = dados.replace(b"Clara Mendes", b"Clara Mendez")
            destino.writestr(item, dados)
    with pytest.raises(ValueError, match="corrompido"):
        backup.conferir(estragado)


def test_retencao_mantem_so_os_mais_recentes(cliente, cenario, tmp_path):
    for i in range(3):
        (tmp_path / f"{backup.PREFIXO}20260101-00000{i}.zip").write_bytes(b"velho")
    backup.gerar(settings, tmp_path, manter=2)
    restantes = sorted(p.name for p in tmp_path.glob(f"{backup.PREFIXO}*.zip"))
    assert len(restantes) == 2
    assert restantes[0] == f"{backup.PREFIXO}20260101-000002.zip"


def test_backup_nao_carrega_a_chave_nem_o_env(cliente, cenario, tmp_path):
    arquivo = backup.gerar(settings, tmp_path)
    with zipfile.ZipFile(arquivo) as z:
        nomes = z.namelist()
        tudo = b"".join(z.read(n) for n in nomes)
    assert not any(n.endswith(".env") or ".env." in n for n in nomes)
    chave = settings.VC_CLINICAL_KEYS.split(":", 1)[1].encode()
    assert chave not in tudo
    assert TEXTO.encode() not in tudo                              # texto clínico só cifrado
