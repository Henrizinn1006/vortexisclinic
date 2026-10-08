# Deploy na VPS da Hostinger — passo a passo

Para colocar API e painel no ar numa VPS Ubuntu. Detalhes e porquês de cada variável: [producao.md](producao.md). Os arquivos de configuração estão em [../deploy/](../deploy/).

O painel e a API ficam em `app.vortexisclinic.com.br`; o site institucional continua na hospedagem compartilhada, em `vortexisclinic.com.br`.

---

## 1. Criar a VPS

No hPanel: **VPS → Comprar**. Plano KVM 1 ou 2 serve para começar. No sistema operacional escolha **Ubuntu 24.04 (sem painel)**. Anote o **IP** da VPS e defina a senha de root.

## 2. Domínio

No hPanel, em **Domínios → DNS**, crie um registro:

| Tipo | Nome | Aponta para |
|---|---|---|
| A | `app` | IP da VPS |

Leva alguns minutos para propagar. Confira com `ping app.vortexisclinic.com.br`.

## 3. Liberar a VPS no banco

hPanel → **Bancos de dados → MySQL Remoto**: adicione o **IP da VPS** e remova o IP do seu computador.

## 4. Preparar o servidor

Entre por SSH (`ssh root@IP_DA_VPS`) e rode:

```bash
apt update && apt upgrade -y
apt install -y python3-venv python3-pip nginx certbot python3-certbot-nginx git ufw
ufw allow OpenSSH && ufw allow 'Nginx Full' && ufw --force enable

adduser --system --group --home /home/vortexis vortexis
```

## 5. Levar o código

Use `git clone`: é o que torna cada atualização futura um `git pull`. O repositório é `https://github.com/Henrizinn1006/vortexisclinic.git`.

**Se o repositório for público:**

```bash
cd /srv
git clone https://github.com/Henrizinn1006/vortexisclinic.git vortexis
```

**Se for privado** (recomendado, pois há código de saúde), use uma *deploy key*, que dá à VPS acesso só de leitura a este repositório:

```bash
ssh-keygen -t ed25519 -f /root/.ssh/vortexis_deploy -N ""
cat /root/.ssh/vortexis_deploy.pub        # copie a linha que aparecer
```

No GitHub: repositório → **Settings → Deploy keys → Add deploy key**, cole a linha e deixe **sem** marcar "Allow write access". Depois:

```bash
printf 'Host github.com
  IdentityFile /root/.ssh/vortexis_deploy
  IdentitiesOnly yes
' >> /root/.ssh/config
cd /srv
git clone git@github.com:Henrizinn1006/vortexisclinic.git vortexis
```

Devem existir `/srv/vortexis/Apivortexisclinic` e `/srv/vortexis/Appvortexisclinic`.

Crie as pastas de dados e libere o repositório para o `git pull` do root:

```bash
mkdir -p /srv/vortexis/arquivos /srv/vortexis/backups
git config --global --add safe.directory /srv/vortexis
```

```bash
cd /srv/vortexis/Apivortexisclinic
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 6. Configurar o `.env`

```bash
cp .env.example .env
nano .env
chmod 600 .env
```

Preencha como na seção 3 do [producao.md](producao.md). O essencial:

```
VC_ENV=production
VC_DEBUG=false
VC_COOKIE_SECURE=true
VC_DB_HOST=212.85.3.45
VC_DB_NAME=u187622719_clinic
VC_DB_USER=u187622719_clinic
VC_DB_PASSWORD=<a senha do banco>
VC_CORS_ORIGINS=
VC_PANEL_URL=https://app.vortexisclinic.com.br
VC_FILES_DIR=/srv/vortexis/arquivos
VC_CLINICAL_KEYS=1:<chave>
VC_CLINICAL_KEY_VERSION=1
VC_MAIL_BACKEND=queue
VC_ASAAS_API_KEY='$aact_prod_...'
VC_ASAAS_BASE_URL=https://api.asaas.com/v3
VC_ASAAS_WEBHOOK_TOKEN=<texto longo inventado>
```

Gere a chave clínica com:

```bash
.venv/bin/python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

> **Guarde a `VC_CLINICAL_KEYS` em dois lugares fora da VPS** (gerenciador de senhas e cópia impressa). Sem ela, o prontuário não abre — nem do backup.

Sem a chave do Asaas, o sistema funciona normalmente e só deixa a contratação desligada.

## 7. Banco

```bash
cd /srv/vortexis/Apivortexisclinic
.venv/bin/python scripts/backup.py gerar          # sempre antes de migration
.venv/bin/python -m alembic upgrade head          # aplica a 0012_cobranca
```

Depois, no phpMyAdmin do hPanel, defina os preços (ajuste os valores se quiser):

```sql
UPDATE plans SET monthly_price = 59.90 WHERE `key` = 'essencial';
UPDATE plans SET monthly_price = 79.90 WHERE `key` = 'profissional';
UPDATE plans SET monthly_price = 99.90 WHERE `key` = 'clinica';
```

## 8. Conferir a configuração

```bash
.venv/bin/python scripts/verificar_producao.py
```

Precisa terminar com **0 falhas**. Corrija o que ele apontar antes de seguir.

## 9. Subir a API

```bash
chown -R vortexis:vortexis /srv/vortexis
cp /srv/vortexis/Apivortexisclinic/deploy/vortexis-api.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now vortexis-api
systemctl status vortexis-api           # deve estar "active (running)"
curl http://127.0.0.1:8000/health
```

Se não subir: `journalctl -u vortexis-api -n 50`.

## 10. nginx e HTTPS

```bash
cp /srv/vortexis/Apivortexisclinic/deploy/nginx-vortexis.conf /etc/nginx/sites-available/vortexis
nano /etc/nginx/sites-available/vortexis      # confira o domínio
ln -s /etc/nginx/sites-available/vortexis /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

certbot --nginx -d app.vortexisclinic.com.br      # certificado gratuito, renova sozinho
```

Abra `https://app.vortexisclinic.com.br`: a tela de entrada deve aparecer, e o cadastro deve funcionar.

## 11. Asaas

1. Em **Integrações → Webhooks → Criar**, informe:
   - URL: `https://app.vortexisclinic.com.br/billing/asaas/webhook`
   - Token: o mesmo `VC_ASAAS_WEBHOOK_TOKEN` do `.env`
   - Eventos: os de cobrança (pagamentos) e os de assinatura
2. Para testar antes de usar dinheiro de verdade, faça uma vez com a chave e a URL do **sandbox** (`https://api-sandbox.asaas.com/v3`) apontando para esta mesma VPS. Assine, pague a fatura de teste e veja o plano mudar sozinho. Depois volte para a chave de produção.

## 12. Backup diário

```bash
crontab -u vortexis -e
```

Acrescente:

```
30 3 * * * cd /srv/vortexis/Apivortexisclinic && .venv/bin/python scripts/backup.py gerar --destino /srv/vortexis/backups >> /var/log/vortexis-backup.log 2>&1
```

E mantenha uma cópia fora da VPS (o snapshot da própria Hostinger ajuda, mas não substitui).

---

## Atualizar depois

```bash
cd /srv/vortexis/Apivortexisclinic
.venv/bin/python scripts/backup.py gerar
git pull
chown -R vortexis:vortexis /srv/vortexis
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m alembic upgrade head  # só se houver migration nova
systemctl restart vortexis-api
```

O painel é estático: copiar os arquivos novos já basta (o navegador pega a versão nova na próxima visita).
