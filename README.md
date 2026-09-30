# Vortexis Clinic

Projeto da Vortexis Clinic, organizado em três partes:

- `Apivortexisclinic/`: API FastAPI, autenticação, isolamento de contas e dados de gestão.
- `Appvortexisclinic/`: painel web estático para profissionais.
- `Sitevortexisclinic/`: site institucional e páginas por especialidade.

## API e painel local

A API requer Python 3.10+ e MySQL 8 (ou MariaDB 10.6+). Configure a API antes de iniciar o painel:

```powershell
cd Apivortexisclinic
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edite o `.env` com os dados do seu banco e então execute as migrations e a API:

```powershell
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

Em outro terminal, sirva o painel:

```powershell
cd Appvortexisclinic
python -m http.server 5500 --bind 127.0.0.1
```

Abra `http://127.0.0.1:5500`. Para o fluxo de cadastro e login funcionar, a API e o banco precisam estar disponíveis. Use `127.0.0.1` nos dois serviços.

## Site institucional

O site não exige build. Para servi-lo localmente:

```powershell
cd Sitevortexisclinic
python -m http.server 5501 --bind 127.0.0.1
```

## Testes

API: `python -m pytest` dentro de `Apivortexisclinic/`, com um banco de testes configurado conforme o README da API.

Painel: `node tests/run.js` dentro de `Appvortexisclinic/`.

## Dados e segredos

Não versione arquivos `.env`, credenciais, bancos locais, dumps, documentos clínicos ou conteúdo de `arquivos/`. O `.gitignore` da raiz mantém esses itens fora deste repositório. Use somente dados fictícios em desenvolvimento e testes.