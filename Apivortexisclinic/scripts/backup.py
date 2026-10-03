"""
Backup e restauração — banco E documentos, num arquivo só.

    python scripts/backup.py gerar                       # → backups/vortexis-AAAAMMDD-HHMMSS.zip
    python scripts/backup.py gerar --destino /srv/bkp --manter 30
    python scripts/backup.py conferir backups/vortexis-....zip
    python scripts/backup.py restaurar backups/vortexis-....zip [--env /caminho/.env]

**Por que os dois juntos.** Recibo, declaração e anexo não moram no banco:
ficam cifrados em disco, em `VC_FILES_DIR`. Backup só do banco devolveria
a linha do documento apontando para um arquivo que não existe mais.

**O que NÃO vai no backup: a chave.** O prontuário e os documentos saem
cifrados, como estão no disco. Sem a `VC_CLINICAL_KEYS`, o backup restaura
tudo — e nada clínico abre. Guarde a chave em outro lugar (gerenciador de
senhas), nunca ao lado do backup: quem leva os dois leva tudo.

**O que vai em claro**: nome, e-mail e telefone das pessoas atendidas, a
agenda e o financeiro. O .zip é dado pessoal — trate como tal (pasta com
acesso restrito, cópia fora do servidor cifrada).

**Restaurar só em banco vazio.** Igual à importação da estrutura: se houver
qualquer tabela no destino, recusa. Errar e ver um erro é melhor do que
errar e misturar dois bancos.

O `banco.sql` é SQL comum e também pode ser importado pelo phpMyAdmin.
"""
import argparse
import datetime as dt
import hashlib
import io
import json
import pathlib
import sys
import zipfile
from decimal import Decimal

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

LINHAS_POR_INSERT = 200
PREFIXO = "vortexis-"


# ---------------- conexão ----------------
def _conectar(s, *, banco=True):
    import pymysql

    args = dict(host=s.VC_DB_HOST, port=s.VC_DB_PORT, user=s.VC_DB_USER,
                password=s.VC_DB_PASSWORD, charset="utf8mb4", autocommit=False)
    if banco:
        args["database"] = s.VC_DB_NAME
    if s.VC_DB_SSL_CA:
        args["ssl"] = {"ca": s.VC_DB_SSL_CA}
    return pymysql.connect(**args)


def _tabelas(cur) -> list:
    cur.execute("SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE' ORDER BY table_name")
    return [linha[0] for linha in cur.fetchall()]


def _pasta_arquivos(s) -> pathlib.Path:
    pasta = pathlib.Path(s.VC_FILES_DIR)
    return pasta if pasta.is_absolute() else RAIZ / pasta


# ---------------- SQL ----------------
def _literal(v) -> str:
    from pymysql.converters import escape_string

    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (bytes, bytearray)):
        return "X'" + bytes(v).hex() + "'"       # cifra, nonce, sal, IP: binário intacto
    if isinstance(v, (int, Decimal)):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, dt.datetime):
        return "'" + v.strftime("%Y-%m-%d %H:%M:%S.%f") + "'"
    if isinstance(v, dt.date):
        return "'" + v.isoformat() + "'"
    if isinstance(v, dt.timedelta):              # coluna TIME volta como timedelta
        total = int(v.total_seconds())
        sinal = "-" if total < 0 else ""
        total = abs(total)
        return f"'{sinal}{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}'"
    # escape_string troca quebra de linha por \n: nenhum valor ocupa duas linhas,
    # e por isso "linha terminada em ;" separa comandos com segurança.
    return "'" + escape_string(str(v)) + "'"


def _despejar(s, saida: io.TextIOBase) -> dict:
    """Escreve o banco inteiro em SQL. Devolve {tabela: linhas}."""
    conexao = _conectar(s)
    contagem = {}
    try:
        cur = conexao.cursor()
        # Uma foto só do banco inteiro: quem gravar durante o backup não
        # deixa pagamento sem atendimento nem nota sem versão no arquivo.
        cur.execute("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        cur.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
        saida.write("-- Vortexis Clinic — backup gerado por scripts/backup.py\n")
        saida.write(f"-- {dt.datetime.now(dt.timezone.utc).isoformat()} (UTC)\n")
        saida.write("-- Importe num banco VAZIO. Não há DROP TABLE aqui, de propósito.\n\n")
        saida.write("SET NAMES utf8mb4;\nSET FOREIGN_KEY_CHECKS = 0;\nSET UNIQUE_CHECKS = 0;\n"
                    "SET SQL_MODE = 'NO_AUTO_VALUE_ON_ZERO';\nSET time_zone = '+00:00';\n\n")
        for tabela in _tabelas(cur):
            cur.execute(f"SHOW CREATE TABLE `{tabela}`")
            saida.write(cur.fetchone()[1] + ";\n\n")

            leitor = conexao.cursor()
            leitor.execute(f"SELECT * FROM `{tabela}`")
            colunas = ", ".join(f"`{c[0]}`" for c in leitor.description)
            n = 0
            while True:
                lote = leitor.fetchmany(LINHAS_POR_INSERT)
                if not lote:
                    break
                valores = ",".join("(" + ", ".join(_literal(v) for v in linha) + ")" for linha in lote)
                saida.write(f"INSERT INTO `{tabela}` ({colunas}) VALUES {valores};\n")
                n += len(lote)
            leitor.close()
            contagem[tabela] = n
            saida.write("\n")
        saida.write("SET FOREIGN_KEY_CHECKS = 1;\nSET UNIQUE_CHECKS = 1;\n")
        conexao.rollback()
    finally:
        conexao.close()
    return contagem


def _comandos(sql: str):
    """Separa o despejo em comandos: cada um termina numa linha que acaba em ';'."""
    atual = []
    for linha in sql.splitlines():
        if not linha.strip() and not atual:
            continue
        if linha.startswith("--") and not atual:
            continue
        atual.append(linha)
        if linha.rstrip().endswith(";"):
            yield "\n".join(atual)
            atual = []
    if "".join(atual).strip():
        yield "\n".join(atual)


# ---------------- gerar ----------------
def gerar(s, destino: pathlib.Path, manter: int = 0) -> pathlib.Path:
    destino.mkdir(parents=True, exist_ok=True)
    carimbo = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    final = destino / f"{PREFIXO}{carimbo}.zip"
    temporario = final.with_suffix(".zip.parcial")

    buffer = io.StringIO()
    contagem = _despejar(s, buffer)
    sql = buffer.getvalue().encode("utf-8")

    pasta = _pasta_arquivos(s)
    arquivos = sorted(p for p in pasta.rglob("*") if p.is_file()) if pasta.exists() else []

    versao = None
    for linha in sql.decode("utf-8").splitlines():
        if linha.startswith("INSERT INTO `alembic_version`"):
            versao = linha.split("VALUES ('", 1)[1].split("'", 1)[0]

    manifesto = {
        "gerado_em_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "banco": s.VC_DB_NAME,
        "versao_alembic": versao,
        "tabelas": contagem,
        "banco_sql_sha256": hashlib.sha256(sql).hexdigest(),
        "arquivos": {str(p.relative_to(pasta)).replace("\\", "/"):
                     hashlib.sha256(p.read_bytes()).hexdigest() for p in arquivos},
        "aviso": "Conteúdo clínico cifrado. Sem a VC_CLINICAL_KEYS, nada clínico abre.",
    }

    # Escreve em .parcial e só renomeia no fim: backup cortado no meio (disco
    # cheio, queda) nunca fica com cara de backup bom.
    with zipfile.ZipFile(temporario, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("banco.sql", sql)
        for p in arquivos:
            z.write(p, "arquivos/" + str(p.relative_to(pasta)).replace("\\", "/"))
        z.writestr("manifesto.json", json.dumps(manifesto, ensure_ascii=False, indent=2))
    temporario.replace(final)

    if manter > 0:
        antigos = sorted(destino.glob(f"{PREFIXO}*.zip"))[:-manter]
        for velho in antigos:
            velho.unlink()
    return final


# ---------------- conferir ----------------
def conferir(arquivo: pathlib.Path) -> dict:
    """Confere a integridade do .zip sem tocar em banco nenhum."""
    with zipfile.ZipFile(arquivo) as z:
        manifesto = json.loads(z.read("manifesto.json"))
        if hashlib.sha256(z.read("banco.sql")).hexdigest() != manifesto["banco_sql_sha256"]:
            raise ValueError("banco.sql não confere com o manifesto: arquivo corrompido")
        for nome, esperado in manifesto["arquivos"].items():
            if hashlib.sha256(z.read("arquivos/" + nome)).hexdigest() != esperado:
                raise ValueError(f"documento corrompido no backup: {nome}")
    return manifesto


# ---------------- restaurar ----------------
def restaurar(s, arquivo: pathlib.Path) -> dict:
    manifesto = conferir(arquivo)

    conexao = _conectar(s)
    try:
        cur = conexao.cursor()
        existentes = _tabelas(cur)
        if existentes:
            raise RuntimeError(
                f"o banco {s.VC_DB_NAME} não está vazio ({len(existentes)} tabelas). "
                "Restauração só em banco vazio — nada foi alterado.")

        pasta = _pasta_arquivos(s)
        with zipfile.ZipFile(arquivo) as z:
            # Documentos primeiro conferidos: arquivo com mesmo nome e conteúdo
            # diferente no destino é sinal de que algo está errado.
            for nome in manifesto["arquivos"]:
                alvo = pasta / nome
                if alvo.exists() and alvo.read_bytes() != z.read("arquivos/" + nome):
                    raise RuntimeError(f"já existe um arquivo diferente em {alvo}; nada foi alterado")

            sql = z.read("banco.sql").decode("utf-8")
            for comando in _comandos(sql):
                cur.execute(comando)
            conexao.commit()

            for nome in manifesto["arquivos"]:
                alvo = pasta / nome
                alvo.parent.mkdir(parents=True, exist_ok=True)
                if not alvo.exists():
                    alvo.write_bytes(z.read("arquivos/" + nome))

        # A prova: cada tabela com o mesmo número de linhas do momento do backup.
        divergentes = {}
        for tabela, esperado in manifesto["tabelas"].items():
            cur.execute(f"SELECT COUNT(*) FROM `{tabela}`")
            achado = cur.fetchone()[0]
            if achado != esperado:
                divergentes[tabela] = (esperado, achado)
        if divergentes:
            raise RuntimeError(f"restauração incompleta: {divergentes}")
    finally:
        conexao.close()
    return manifesto


# ---------------- linha de comando ----------------
def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Backup e restauração da Vortexis Clinic")
    p.add_argument("--env", default=str(RAIZ / ".env"), help="arquivo .env do banco")
    sub = p.add_subparsers(dest="acao", required=True)
    g = sub.add_parser("gerar", help="gera um backup")
    g.add_argument("--destino", default=str(RAIZ / "backups"))
    g.add_argument("--manter", type=int, default=30, help="quantos backups manter (0 = todos)")
    c = sub.add_parser("conferir", help="confere a integridade de um backup")
    c.add_argument("arquivo")
    r = sub.add_parser("restaurar", help="restaura num banco VAZIO")
    r.add_argument("arquivo")
    args = p.parse_args(argv)

    if args.acao == "conferir":
        m = conferir(pathlib.Path(args.arquivo))
        print(f"íntegro: {sum(m['tabelas'].values())} linhas em {len(m['tabelas'])} tabelas, "
              f"{len(m['arquivos'])} documento(s), versão {m['versao_alembic']}, "
              f"gerado em {m['gerado_em_utc']}")
        return 0

    from app.config import Settings

    s = Settings(_env_file=args.env)
    if args.acao == "gerar":
        final = gerar(s, pathlib.Path(args.destino), manter=args.manter)
        m = conferir(final)
        print(f"backup gerado: {final}")
        print(f"  {sum(m['tabelas'].values())} linhas, {len(m['arquivos'])} documento(s), "
              f"versão {m['versao_alembic']}")
        print("  lembrete: a chave clínica NÃO está no backup — guarde-a separada.")
        return 0

    m = restaurar(s, pathlib.Path(args.arquivo))
    print(f"restaurado em {s.VC_DB_NAME}: {sum(m['tabelas'].values())} linhas e "
          f"{len(m['arquivos'])} documento(s), conferidos tabela a tabela.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
