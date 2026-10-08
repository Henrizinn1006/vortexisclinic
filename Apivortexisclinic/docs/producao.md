# Produção — checklist de deploy, backup e variáveis

Para quem vai colocar a API no ar ou mantê-la rodando. Cada item tem o porquê: quase toda regra aqui tem um atalho que parece inofensivo e não é.

---

## 1. Onde cada parte roda

| Parte | Onde | Por quê |
|---|---|---|
| Site (`Sitevortexisclinic`) | Hospedagem compartilhada da Hostinger, `public_html/` | É HTML estático; o `.htaccess` já cuida de HTTPS, cabeçalhos e 404. |
| Banco (MariaDB) | Hostinger, `u187622719_clinic` | Já existe, com a estrutura importada (versão `0011_planos` — falta aplicar a `0012_cobranca`: `alembic upgrade head`). |
| API (`Apivortexisclinic`) | **VPS** (ainda não escolhida) | Hospedagem compartilhada não roda Python. |
| Painel (`Appvortexisclinic`) | Mesma VPS, servido pelo nginx na **mesma origem** da API | Mesma origem dispensa CORS e mantém o cookie de sessão simples. |

Quando a VPS existir, troque o IP liberado em **hPanel → MySQL Remoto** pelo IP da VPS e remova o IP de desenvolvimento.

---

## 2. Antes de cada deploy

```bash
cd Apivortexisclinic
python scripts/verificar_producao.py            # 0 falhas, ou não sobe
python scripts/backup.py gerar                  # sempre antes de migration
python -m alembic upgrade head                  # só se houver migration nova
```

`verificar_producao.py` confere tudo de uma vez e **nunca imprime segredo**. Use também como trava de boot (seção 5). `Settings.validar_producao()` já recusa subir nos casos mais graves; o script vai além (formato da chave, HTTPS, e-mail, pasta de arquivos, versão do banco).

---

## 3. Variáveis obrigatórias em produção

O `.env` fica só no servidor, com permissão `600`, fora do git. Nunca por chat ou e-mail.

| Variável | Valor em produção | Se errar |
|---|---|---|
| `VC_ENV` | `production` | Liga as travas de produção. |
| `VC_DEBUG` | `false` | Erro detalhado vaza estrutura interna. |
| `VC_DB_HOST` | IP do banco | Use o **IPv4** (`212.85.3.45`): pelo nome `srv720.hstgr.io` a conexão pode sair por IPv6 e ser recusada. |
| `VC_DB_NAME` / `VC_DB_USER` | `u187622719_clinic` | Nunca um banco `_test`: a suíte apaga tudo nele. |
| `VC_DB_PASSWORD` | senha do banco | Troque no hPanel antes de dado real. |
| `VC_DB_SSL_CA` | caminho do CA, ou vazio | **Comentário nunca na mesma linha de valor vazio**: vira o valor e a conexão morre com `FileNotFoundError` sem explicar. |
| `VC_DB_ECHO` | `false` | `true` imprime todo SQL no log, com dado de gente. |
| `VC_COOKIE_SECURE` | `true` | Cookie de sessão viajaria sem HTTPS. |
| `VC_CORS_ORIGINS` | vazio (mesma origem) ou só `https://…` | Origem diferente = `403 origem_nao_permitida`. |
| `VC_PANEL_URL` | `https://app.vortexisclinic.com.br` | Links de convite e de senha saem quebrados. |
| `VC_CLINICAL_KEYS` | `1:<32 bytes base64>` | **Perdeu, perdeu o prontuário.** Ver seção 6. |
| `VC_CLINICAL_KEY_VERSION` | a versão usada para gravar (`1`) | Se não existir em `VC_CLINICAL_KEYS`, a primeira nota dá erro. |
| `VC_MAIL_BACKEND` | `smtp` (ou `queue` até ter SMTP) | `console` imprime e-mail com link de troca de senha no log. |
| `VC_SMTP_*` | credenciais do provedor, `VC_SMTP_TLS=true` | Sem SMTP o e-mail fica na fila — não some, mas não sai. |
| `VC_FILES_DIR` | caminho absoluto, ex. `/srv/vortexis/arquivos` | É onde ficam recibos e anexos cifrados. Entra no backup. |

---

## 4. Servidor (VPS)

- **Python 3.11+** e `pip install -r requirements.txt` num `.venv`. O `tzdata` está na lista: sem ele, em sistema sem base de fusos (Windows, contêiner mínimo), a API nem sobe.
- **Um worker só.** O rate limit guarda os contadores em memória: com vários workers, cada um conta o seu e o limite vira N vezes maior. Trocar por Redis é dívida técnica registrada em `app/security/ratelimit.py`.
- **Atrás do nginx, com `--proxy-headers`.** O IP do rate limit vem da conexão; sem isso, todo mundo parece vir de `127.0.0.1`, e uma pessoa errando a senha bloqueia o login de todas.

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 \
    --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1
```

- nginx com HTTPS (certificado Let's Encrypt), servindo o painel estático em `/` e repassando a API. Toda requisição precisa de `Origin` válido. Toda escrita precisa do cabeçalho `X-CSRF-Token`, com o valor do cookie `vc_csrf`.
- O `service-worker.js` do painel tem lista de permissão: dado clínico nunca entra em cache. Não troque por "cache tudo".

---

## 5. Trava de boot (systemd)

```ini
[Service]
WorkingDirectory=/srv/vortexis/Apivortexisclinic
ExecStartPre=/srv/vortexis/Apivortexisclinic/.venv/bin/python scripts/verificar_producao.py
ExecStart=/srv/vortexis/Apivortexisclinic/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=on-failure
```

Com uma falha, `verificar_producao.py` sai com código 1 e o systemd não sobe a API.

---

## 6. A chave clínica

- O prontuário e os documentos são cifrados com AES-256-GCM a partir da `VC_CLINICAL_KEYS`. **Não existe recuperação**: sem a chave, nada clínico abre — nem do backup.
- Guarde a chave em **dois lugares fora do servidor** (ex.: gerenciador de senhas + cópia impressa em local seguro). Nunca ao lado do backup: quem leva os dois leva tudo.
- Trocar de chave: acrescente a nova versão (`1:<antiga>,2:<nova>`) e mude `VC_CLINICAL_KEY_VERSION=2`. As notas antigas continuam abrindo com a versão 1. **Nunca remova uma versão** enquanto houver nota gravada com ela.
- Gerar uma chave nova:
  ```bash
  python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
  ```

---

## 7. Backup

```bash
python scripts/backup.py gerar                    # → backups/vortexis-AAAAMMDD-HHMMSS.zip (mantém 30)
python scripts/backup.py conferir <arquivo.zip>   # integridade, sem tocar em banco
python scripts/backup.py restaurar <arquivo.zip>  # só em banco VAZIO
```

- **O que entra:** o banco inteiro em SQL (também importável pelo phpMyAdmin) e a pasta `VC_FILES_DIR` (recibos e anexos cifrados), com um manifesto de contagens e hashes.
- **O que não entra:** o `.env` e a chave. Por isso o backup sozinho não abre prontuário.
- **O que vai em claro:** nome, contato, agenda e financeiro. O `.zip` é dado pessoal: pasta com acesso restrito e cópia fora do servidor **cifrada**.
- **Rotina sugerida:** diária, por cron na VPS, com cópia para fora dela.
  ```cron
  30 3 * * * cd /srv/vortexis/Apivortexisclinic && .venv/bin/python scripts/backup.py gerar --destino /srv/vortexis/backups >> /var/log/vortexis-backup.log 2>&1
  ```
- **Ensaio de restauração mensal.** Restaure o último backup num banco vazio (nunca no de produção) e abra uma nota pelo painel. Backup que nunca foi restaurado não é backup. O teste `tests/test_backup.py` faz isso a cada rodada da suíte, contra o banco de teste.
- **Antes de qualquer migration**, um backup manual.

---

## 8. Testes

```bash
python -m pytest            # API, contra o banco _test (cerca de 2 min)
node ../Appvortexisclinic/tests/run.js   # painel, sem rede
```

A suíte da API exige o `.env.test` apontando para um banco cujo nome termina em `_test`, e uma pasta de arquivos cujo nome contém `test`. Sem isso, ela se recusa a rodar, porque esvazia os dois a cada teste. O `.env.test` tem chave clínica e pasta de arquivos **próprias**: os testes nunca tocam a chave nem os documentos reais.

**O banco de teste é local**, não da Hostinger: um MariaDB 11.8.9 portátil (mesma versão da Hostinger), instalado sem administrador em `%LOCALAPPDATA%\vortexis-mariadb`, ouvindo só em `127.0.0.1:3307`. Ele não sobe sozinho com o Windows. Antes de rodar os testes:

```powershell
& "$env:LOCALAPPDATA\vortexis-mariadb\mariadb-11.8.9-winx64\bin\mariadbd.exe" `
  --defaults-file="$env:LOCALAPPDATA\vortexis-mariadb\data\my.ini" --console
```

Deixe essa janela aberta enquanto testa. A senha de root fica em `root-senha.txt`, na mesma pasta. Ali não há dado real: só o que a suíte cria e apaga.

---

> **Isolamento do banco:** a API usa `READ COMMITTED` (em `app/db/session.py`). No MariaDB 11.6+ o padrão faz requisições simultâneas falharem com o erro 1020 ao atualizar a sessão; não volte ao padrão.

## 9. O que ainda depende de decisão

- **Cobrança (Asaas):** integrada, falta configurar. No painel do Asaas: gere a chave de API (`VC_ASAAS_API_KEY`), cadastre o webhook em `https://<api>/billing/asaas/webhook` com um token à sua escolha (`VC_ASAAS_WEBHOOK_TOKEN`; marque os eventos de cobrança e de assinatura) e use `VC_ASAAS_BASE_URL=https://api.asaas.com/v3` em produção (o padrão é o sandbox, e a API recusa subir em produção com sandbox ou sem token). **Os preços dos planos nascem nulos** e o checkout recusa plano sem preço: defina (valores sugeridos, ajuste à vontade):

  ```sql
  UPDATE plans SET monthly_price = 59.90 WHERE `key` = 'essencial';
  UPDATE plans SET monthly_price = 79.90 WHERE `key` = 'profissional';
  UPDATE plans SET monthly_price = 99.90 WHERE `key` = 'clinica';
  ```

  O Asaas recusa cobrança abaixo de R$ 5,00. Fluxo: `POST /workspace/plan/checkout` cria a assinatura no Asaas e devolve o link da fatura; o plano só muda quando o webhook de pagamento confirmado chega. Cancelar: `POST /workspace/plan/cancel`. Troca manual pelo suporte continua: `python -m app.jobs.assinatura --tenant <slug> --plano <chave>`.
- **Prazo de retenção do prontuário:** não inventar. A política nasce vazia e recusa prazo sem base legal.
- **SMTP:** sem credencial, o e-mail fica na fila.
- **VPS, domínio da API e certificado.**
