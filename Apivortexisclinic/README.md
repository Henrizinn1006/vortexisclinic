# Vortexis Clinic — API (Etapa 3)

Backend da Vortexis Clinic: **identidade, autenticação e isolamento
multi-tenant**. FastAPI + MySQL, sem Docker.

> **O que existe:** usuários globais, workspaces (tenants), memberships, perfil
> profissional, sessões opacas, RBAC, contexto de tenant *fail-closed*,
> **pessoas atendidas**, **agenda/atendimentos** e **financeiro** — com escopo
> de dados (`all`/`own`), conflito de horário, livro-caixa com baixa, estorno e
> isenção, e números calculados no servidor.
> **O que NÃO existe ainda:** prontuário, documentos, convite de pessoas para a
> conta, configurações graváveis, exportação de relatórios.

---

## Como rodar (Windows, sem Docker)

### 1. Python

Precisa de **Python 3.10 ou mais novo**. Se ainda não tiver, instale de
python.org marcando **"Add python.exe to PATH"**.

```powershell
python --version
```

### 2. MySQL

Precisa de um **MySQL 8** (ou MariaDB 10.6+) rodando na sua máquina — serve
o MySQL Community Server, o XAMPP ou o que você já tiver. Crie o banco:

```sql
CREATE DATABASE vortexis_clinic
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE DATABASE vortexis_clinic_test
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Um usuário só para a aplicação. Não use o root do MySQL na API.
CREATE USER 'vortexis'@'localhost' IDENTIFIED BY 'a-senha-que-voce-escolher';
GRANT ALL PRIVILEGES ON vortexis_clinic.*      TO 'vortexis'@'localhost';
GRANT ALL PRIVILEGES ON vortexis_clinic_test.* TO 'vortexis'@'localhost';
FLUSH PRIVILEGES;
```

### 3. Ambiente e dependências

```powershell
cd C:\Users\htava\Vortexis\Vortexisclinic\Apivortexisclinic

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
```

### 4. Variáveis de ambiente

```powershell
copy .env.example .env
```

Abra o `.env` e preencha `VC_DB_USER`, `VC_DB_PASSWORD` e `VC_DB_NAME`.
**O `.env` nunca vai para o Git** (já está no `.gitignore`) e não deve ser
colado em chat, print ou issue.

### 5. Criar as tabelas

```powershell
python -m alembic upgrade head
```

Isso cria o schema e o seed de papéis, permissões e profissões.
Para conferir o que seria executado antes de rodar:

```powershell
python -m alembic upgrade head --sql
```

### 6. Subir a API

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

- Saúde: http://127.0.0.1:8000/health
- Documentação interativa: http://127.0.0.1:8000/docs *(some em produção)*

### 7. Subir o painel

Em outro terminal:

```powershell
cd C:\Users\htava\Vortexis\Vortexisclinic\Appvortexisclinic
python -m http.server 5500
```

Abra http://127.0.0.1:5500 — a tela de entrada aparece.
O painel aponta para `http://127.0.0.1:8000` (veja `assets/js/config/app.config.js`).

> Use `127.0.0.1` nos dois, não `localhost`: o CORS e o cookie são por origem,
> e `localhost` e `127.0.0.1` são origens diferentes para o navegador.

---

## Testes

```powershell
python -m pytest
```

A suíte exige um banco cujo nome **termine em `_test`** — é a trava que impede
rodar contra o banco de desenvolvimento por engano. Aponte pelo `.env.test`:

```
VC_ENV=test
VC_DB_NAME=vortexis_clinic_test
VC_DB_USER=vortexis
VC_DB_PASSWORD=a-senha-que-voce-escolher
VC_ARGON2_MEMORY_KB=8192
VC_ARGON2_TIME_COST=1
```

O schema dos testes vem das **migrations**, não de `create_all`: testar contra
um schema diferente do de produção não provaria nada.

---

## Organização

```
Apivortexisclinic/
├── alembic.ini                 # config do Alembic (sem credenciais)
├── .env.example                # nomes das variáveis, valores fictícios
├── requirements.txt
├── migrations/
│   ├── env.py                  # URL vem do ambiente, nunca do .ini
│   └── versions/
│       ├── 0001_fundacao.py    # identidade, workspaces, RBAC, sessões
│       ├── 0002_seed.py        # papéis, permissões e profissões
│       ├── 0003_negocio.py     # clients, client_professionals, appointments
│       └── 0004_financeiro.py  # payments (livro-caixa)
├── app/
│   ├── config.py               # tudo por variável de ambiente
│   ├── main.py                 # app, CORS, checagem de origem, erros
│   ├── rbac.py                 # catálogo de papéis e permissões
│   ├── errors.py               # respostas que não descrevem o interior
│   ├── schemas.py              # entrada e saída (Pydantic)
│   ├── ids.py                  # ULID para os ids públicos
│   ├── domain/metrics.py       # A definição dos números (fonte única)
│   ├── db/
│   │   ├── base.py             # Base, PKMixin, TenantScoped
│   │   ├── context.py          # contexto de tenant da requisição
│   │   └── session.py          # engine + FILTRO DE TENANT (fail-closed)
│   ├── models/                 # users, tenants, memberships, professionals…
│   ├── security/               # senha (Argon2id), tokens, cookies, rate limit
│   ├── services/               # auth, sessões, workspaces, permissões
│   └── api/
│       ├── deps.py             # autenticado? pertence? pode?
│       ├── routes_auth.py
│       ├── routes_workspaces.py
│       ├── routes_workspace_data.py
│       └── routes_meta.py
└── tests/
    ├── test_auth.py
    ├── test_tenant_isolation.py   # obrigatório: isolamento entre contas
    ├── test_scope_own.py          # escopo dentro da conta ("só os meus")
    ├── test_rbac.py
    ├── test_workspaces.py
    ├── test_clients.py
    ├── test_appointments.py
    ├── test_payments.py           # baixa, estorno, isenção, regime de caixa
    └── test_metrics.py            # par do teste de métricas do painel
```

---

## Decisões que valem conhecer antes de mexer

**Sessão opaca, não JWT.** O cookie carrega um token aleatório que não
significa nada sozinho; quem sabe quem é o usuário é a tabela `auth_sessions`.
Isso permite **revogar na hora** — essencial com dado de saúde — e evita token
legível por JavaScript. O que fica no banco é o *hash* do token.

**O tenant nunca vem do cliente.** Nenhuma rota aceita `tenant_id` no corpo, na
query ou em cabeçalho. O workspace ativo está na linha da sessão, e trocar de
workspace é `POST /session/workspace`, que revalida a membership e **rotaciona
o token** (anti *session fixation*).

**Fail-closed no ORM.** Toda tabela que herda `TenantScoped` recebe
`WHERE tenant_id = :contexto` automaticamente. Sem tenant no contexto, a
consulta **levanta exceção** em vez de devolver tudo. Esquecer o filtro quebra;
não vaza.

**404, não 403, para o que é de outra conta.** Responder "sem permissão"
confirmaria que o registro existe. 403 fica reservado para recurso do próprio
tenant que a pessoa não pode acessar.

**OWNER não é bypass.** Papel é um conjunto de permissões, e nenhum papel tem
"todas". `OWNER` administra a conta e **não** recebe permissão da classe
clínica. Dono que também atende recebe esse acesso pelo perfil profissional ou
por concessão explícita em `membership_permissions` — com motivo obrigatório e
validade.

**Cadastro é uma transação só.** Usuário → workspace → membership OWNER →
perfil profissional. Se qualquer passo falhar, nada fica: não existe conta
pela metade.

**Escopo de dados dentro da conta.** `memberships.data_scope` divide quem
enxerga tudo (`all`) de quem enxerga só o seu (`own`). Em `own`, pessoas
atendidas saem de `client_professionals` e atendimentos de
`professional_id`. Quem está em `own` **sem perfil profissional** enxerga
lista vazia — nunca a conta inteira. Fail-closed também aqui.

**Conflito de horário é transação, não `UNIQUE`.** Sobreposição não cabe numa
restrição de coluna. A checagem roda dentro da transação, com
`SELECT ... FOR UPDATE` na agenda daquele profissional — senão dois cliques
simultâneos criam dois atendimentos no mesmo horário. Cancelado libera a vaga.

**Livro-caixa é tabela, não campo.** `payments` guarda uma linha por dinheiro
que entrou: valor, meio, quando. `appointments.payment_status` continua como
bandeira de liquidação ("este atendimento está quitado?"), atualizada **na
mesma transação** da baixa — nunca uma sem a outra. A baixa trava a linha do
atendimento, então dois cliques não viram dois lançamentos. Estorno **marca**
a linha e devolve o atendimento para pendente: apagar lançamento é rasurar a
explicação junto com o erro.

**"Recebido" é regime de caixa.** Soma os pagamentos pela data em que o
dinheiro entrou (`paid_at`), não pela data do atendimento. Um atendimento de
agosto pago em setembro conta em setembro — é assim que bate com o extrato do
banco. Pendente e previsto continuam vindo do atendimento, porque falam de
compromisso, não de caixa.

**Ler o financeiro e mexer no dinheiro são permissões diferentes.**
`finance.read` para os números, `finance.write` para baixa, estorno e isenção.

**Números só têm uma fonte.** `app/domain/metrics.py` define o que é
recebido, pendente, presença e resumo do dia. Tela, relatório e exportação
leem dali. O painel tem auxiliares que repetem as regras, e existe um teste
espelhado dos dois lados com o mesmo exemplo para que não se soltem.

**Resposta de dados não entra em cache.** `Cache-Control: no-store` em toda
resposta: por correção (lista velha depois de um cadastro) e por privacidade
(lista de pessoas atendidas é dado de saúde por associação — não pode ficar no
disco do navegador nem em proxy).

**Erro não descreve o interior.** O cliente recebe um código curto e uma frase
genérica; stack trace, SQL e nome de tabela ficam no log do servidor. Nenhum
log guarda senha, token ou cookie.

---

## Endpoints

| Método | Rota | O que faz |
|---|---|---|
| GET | `/health` | serviço e banco de pé |
| GET | `/professions` | catálogo de profissões (usado no cadastro) |
| POST | `/auth/register` | cria conta + workspace + membership + perfil |
| POST | `/auth/login` | abre sessão |
| POST | `/auth/logout` | revoga a sessão |
| GET | `/auth/me` | usuário, workspaces, permissões, perfil |
| POST | `/auth/password/forgot` | prepara recuperação (resposta sempre igual) |
| POST | `/auth/password/reset` | redefine e derruba todas as sessões |
| GET | `/workspaces` | contas do usuário |
| POST | `/workspaces` | cria outro workspace (como OWNER) |
| POST | `/session/workspace` | troca o workspace ativo (validado no servidor) |
| GET | `/workspace/professionals` | perfis da conta ativa *(tenant-scoped)* |
| GET | `/workspace/professionals/{id}` | um perfil — 404 se for de outra conta |
| GET | `/workspace/members` | exige `members.manage` |
| GET | `/workspace/clinical-check` | exige permissão clínica — OWNER é barrado |
| GET | `/workspace/clients` | lista, com `busca`, `status`, `com_pendencia` |
| POST | `/workspace/clients` | cadastra e já vincula a um profissional |
| GET | `/workspace/clients/contagem` | ativos, inativos, arquivados |
| GET | `/workspace/clients/{id}` | ficha, com resumo calculado |
| PATCH | `/workspace/clients/{id}` | altera só o que veio |
| POST | `/workspace/clients/{id}/archive` | arquiva (nunca apaga) |
| GET | `/workspace/clients/{id}/appointments` | histórico da pessoa |
| GET | `/workspace/appointments` | `de`, `ate`, `status`, `modalidade`, `pagamento` |
| POST | `/workspace/appointments` | agenda — recusa conflito de horário (409) |
| GET | `/workspace/appointments/proximos` | próximos agendados |
| PATCH | `/workspace/appointments/{id}` | modalidade, valor, observação |
| POST | `/workspace/appointments/{id}/status` | confirmar, realizado, falta, cancelar |
| POST | `/workspace/appointments/{id}/reschedule` | remarca, revalidando conflito |
| GET | `/workspace/agenda` | período da agenda (`de`, `ate`) |
| GET | `/workspace/dashboard` | tudo da tela inicial numa chamada |
| GET | `/workspace/finance/summary` | recebido, pendente, previsto do mês |
| GET | `/workspace/finance/pending` | atendimentos realizados e não pagos |
| GET | `/workspace/finance/series` | série mensal para o gráfico |
| GET | `/workspace/payments` | livro-caixa (`de`, `ate`, `metodo`) |
| GET | `/workspace/appointments/{id}/payments` | pagamentos daquele atendimento |
| POST | `/workspace/appointments/{id}/payment` | baixa — recusa pagar duas vezes |
| POST | `/workspace/appointments/{id}/waive` | isenta (nada entra no caixa) |
| POST | `/workspace/payments/{id}/refund` | estorna — marca, não apaga |
| GET | `/workspace/clients/{id}/notes` | prontuário — metadado, **sem conteúdo** |
| POST | `/workspace/clients/{id}/notes` | novo registro clínico |
| GET | `/workspace/notes/{id}` | ficha da nota |
| GET | `/workspace/notes/{id}/versions` | histórico de versões (sem decifrar) |
| GET | `/workspace/notes/{id}/content` | **conteúdo** — decifra e registra a leitura |
| PUT | `/workspace/notes/{id}` | salva a **próxima versão**; nada é sobrescrito |
| POST | `/workspace/notes/{id}/sign` | assina — depois disso, só adendo com motivo |
| GET | `/workspace/clients/{id}/clinical-access` | trilha de acesso (exige `audit.read`) |
| GET | `/workspace/team` | membros + convites abertos (`members.manage`) |
| POST | `/workspace/invitations` | convida — devolve o link **uma vez** |
| POST | `/workspace/invitations/{id}/revoke` | encerra o convite |
| PATCH | `/workspace/members/{id}` | papel, escopo e situação |
| GET | `/invitations/{token}` | **público** — o que a tela de aceite mostra |
| POST | `/invitations/{token}/accept` | **público** — aceita e já abre sessão |
| GET | `/workspace/settings` | configurações da conta (qualquer membro lê) |
| PATCH | `/workspace/settings` | grava (`settings.manage`) |
| POST | `/workspace/series` | recorrência — devolve criados **e** conflitos |
| GET | `/workspace/clients/{id}/series` | recorrências da pessoa |
| POST | `/workspace/series/{id}/end` | encerra o molde e cancela o futuro |
| GET | `/workspace/blocks` | horários indisponíveis |
| POST | `/workspace/blocks` | bloqueia (férias, feriado, intervalo) |
| DELETE | `/workspace/blocks/{id}` | libera o horário |
| GET | `/workspace/clients/{id}/documents` | documentos que **você** pode ver |
| POST | `/workspace/clients/{id}/documents/receipt` | recibo (administrativo) |
| POST | `/workspace/clients/{id}/documents/attendance` | declaração de comparecimento (clínico) |
| POST | `/workspace/clients/{id}/documents/record` | cópia do prontuário em PDF |
| POST | `/workspace/clients/{id}/documents` | anexo (base64) |
| GET | `/workspace/documents/{id}/content` | baixa — permissão depende da **classe** |
| GET | `/workspace/finance/export` | livro-caixa em CSV |
| GET/POST | `/workspace/clients/{id}/consents` | consentimento com versão |
| POST | `/workspace/consents/{id}/revoke` | revoga |
| GET | `/workspace/data-requests` | pedidos do titular |
| POST | `/workspace/clients/{id}/data-requests` | registra o pedido |
| POST | `/workspace/data-requests/{id}/decisions` | **registra** a decisão (não executa) |
| POST | `.../decisions/{item}/apply` | **executa** — sem volta |
| POST | `/workspace/data-requests/{id}/close` | encerra (recusa exige motivo) |
| GET | `/workspace/clients/{id}/data-package` | portabilidade, em JSON |
| POST | `/workspace/clients/{id}/anonymize` | anonimiza o cadastro |
| POST | `/workspace/notes/{id}/erase-content` | destrói o conteúdo da nota |
| POST | `/workspace/documents/{id}/erase-content` | destrói o arquivo |
| GET/PUT | `/workspace/retention-policies` | retenção — **nasce vazia** |
| GET | `/workspace/audit` | trilha de segurança (`audit.read`) |
| POST | `/auth/email/verify/request` | enfileira o link de confirmação |
| POST | `/auth/email/verify` | confirma o endereço |
| POST | `/workspace/clients/{id}/payment` | pagamento avulso (pacote, sinal) |

Escrita exige o cabeçalho `X-CSRF-Token`, copiado do cookie `vc_csrf`
(*double submit*). Leitura não exige.


## Prontuário (Etapa 6)

Esta é a parte do sistema cuja falha não tem conserto. Agenda errada se
corrige; evolução lida indevidamente, não. Por isso o prontuário tem
regras próprias, e elas estão no código, não em um parágrafo de política.

### O conteúdo é cifrado na aplicação

`clinical_note_versions.ciphertext` é AES-256-GCM. A chave **não mora no
banco**: vem de `VC_CLINICAL_KEYS`, na configuração do servidor de
aplicação. A consequência é a resposta à regra que o produto assumiu —
*a equipe da Vortexis não recebe acesso irrestrito aos registros clínicos
dos clientes por ter acesso administrativo à plataforma*: acesso ao banco
entrega texto cifrado; ler exige também a chave, que não está no dump.

A derivação é por nota:

    chave = HKDF(mestre_da_versao, sal_da_nota, info="vc-clinical|<tenant>")

E o AAD do GCM é `vc1|<tenant>|<nota>|<versao>` — reconstruído na leitura,
nunca guardado. Duas propriedades caem daí:

* **O isolamento vira matemática.** Uma linha movida de uma conta para
  outra, por fora da aplicação, não decifra. Não é só a cláusula `WHERE`
  que separa as contas.
* **Existe caminho honesto de exclusão.** Descartar o sal da nota
  (`content_key_salt = NULL`) torna todas as versões dela ilegíveis
  — inclusive em backup, que guarda ciphertext e não guarda o sal — sem
  apagar uma linha sequer. A ficha, o histórico e a trilha sobrevivem, e
  dá para responder "houve atendimento; o conteúdo foi apagado em tal
  data, a pedido" em vez de fingir que nada aconteceu.
  `services/clinical.py: esquecer_conteudo()` faz isso e tem teste.
  **Ainda não tem rota**: prazo e alçada de exclusão são decisão de
  produto e não foram definidos — o mecanismo espera a regra.

Rotação: `VC_CLINICAL_KEYS` guarda várias versões (`1:...,2:...`) e
`VC_CLINICAL_KEY_VERSION` diz qual escreve. As antigas continuam
disponíveis para leitura, então rotacionar não exige reescrever o acervo.
Em produção, subir sem chave é erro de inicialização.

### Editar não altera linha

Cada salvamento insere a versão seguinte. Não existe `UPDATE` de conteúdo
no serviço, e há teste que compara a linha da v1 byte a byte depois de uma
edição. Assinar fecha a nota; depois disso, correção é **adendo com
motivo obrigatório** — e o adendo é mais uma versão, nunca uma correção
por cima.

### Quatro portas, nesta ordem

    1. tenant      — resolvido pela sessão, aplicado pelo ORM (fail-closed)
    2. permissão   — clinical_records.read / .write / .read_others
    3. alcance     — o cliente é seu? (client_professionals)
    4. autoria     — a nota é sua? senão, ler exige .read_others;
                     escrever, nunca

Nota fora do alcance responde **404**, não 403: dizer "existe, mas não é
sua" já entrega que aquela pessoa é atendida por alguém ali dentro — e num
consultório de saúde mental isso é, sozinho, a informação sensível.

**O dono da conta não tem permissão clínica pelo papel** e continua sem
ter. Quando o titular também atende, o acesso vem de uma **concessão
explícita** em `membership_permissions`, criada no cadastro, com motivo e
autoria (`permissions.conceder_clinicas_ao_titular`). A diferença importa:
dá para ver por que aquela pessoa tem acesso, e dá para tirar com um
`UPDATE`, sem afrouxar a matriz para todas as clínicas. `read_others`
nunca entra nessa concessão — nem para a dona.

### A trilha grava a negativa

`clinical_access_log` registra leitura, escrita **e recusa**. A recusa é o
que interessa: leitura autorizada é rotina, tentativa recusada é sinal. Ela
é confirmada no banco **antes** de a exceção subir — senão o rollback da
requisição apagaria justamente o registro que importa.

Auditar exige `audit.read`, que é diferente de `clinical_records.read`:
ver **quem** olhou não deve exigir — nem conceder — acesso ao conteúdo. O
dono da conta tem a primeira e não tem a segunda.

### O que esta escolha custa

* **Não existe busca dentro do prontuário.** Ciphertext não tem collation
  nem índice de texto; buscar exigiria decifrar o acervo a cada consulta.
  Filtrar por pessoa, tipo e data funciona — por palavra, não.
* **Perder as chaves é perder o acervo.** Backup do banco não basta:
  `VC_CLINICAL_KEYS` precisa do próprio cuidado, e fora do repositório.
* **A nota não tem título.** Título de evolução é conteúdo clínico
  disfarçado de metadado e ficaria em claro no índice. A nota se
  identifica por tipo e data.


## Equipe e configurações (Etapa 7)

### Convite

Até aqui, colocar uma segunda pessoa numa clínica exigia escrever a linha
de `memberships` à mão no banco. Agora existe convite — com os mesmos
cuidados do resto.

O token é aleatório e **só o sha256 dele fica guardado**, como nas sessões
e no reset de senha. O link aparece uma vez, na resposta da criação, e não
volta em listagem nenhuma. Link errado, vencido, revogado ou já usado
recebem todos a mesma resposta: 404.

Cinco travas, todas testadas:

1. **Ninguém convida para um lugar melhor que o seu.** Só OWNER cria OWNER.
2. **A conta nunca fica sem dono ativo.** A checagem roda depois da
   mudança, contando o resultado — pega rebaixar, suspender, ou os dois na
   mesma chamada.
3. **Ninguém edita a própria membership.** Nem para se promover.
4. **Aceitar não escolhe nada.** Papel, escopo e profissão vêm da linha do
   convite; o corpo do aceite não tem campo por onde pedir mais. Mandar
   `"papel": "OWNER"` ali é inócuo, e há teste provando.
5. **O convite é para um e-mail.** Aceitar logado com outra conta é
   recusado: link vazado não vira porta de entrada.

Quem entra por convite **não ganha workspace próprio** — o workspace dela é
a conta que convidou. Sem isso, cada recepcionista contratada criaria um
consultório fantasma. E quem entra com profissão nasce com perfil
profissional e a mesma concessão clínica explícita do titular que atende
(nunca `read_others`).

### Configurações

`tenant_settings` ganhou jornada, duração padrão, intervalo, tolerância de
falta e meta do mês. A **meta nasce nula** de propósito: meta inventada
vira cobrança sobre um número que ninguém escolheu.

A terminologia é saneada **duas vezes** — no painel antes de enviar e aqui
antes de gravar. Não é redundância: é a regra do projeto de nunca deixar a
validação de frente ser a única. Chave fora do catálogo e rótulo com
marcação voltam em `recusados`, e a tela avisa em vez de fingir que gravou.

Ler é de qualquer membro (a jornada desenha a agenda e os rótulos trocam a
interface inteira); gravar exige `settings.manage`.

### Fuso horário

`tenants.timezone` existia e não era usado: tudo saía em UTC, e quem
atende no Brasil via o atendimento das 22h cair no dia seguinte. Agora
`app/domain/calendario.py` é a fronteira — **recorte é calculado em local,
consulta é feita em UTC** —, e "hoje", "esta semana" e "este mês" são os
da conta. Horário de verão sai de graça: a conversão usa `zoneinfo`.


## Agenda recorrente e bloqueios (Etapa 8)

### A série é um molde, não um contrato

Criar uma recorrência **gera atendimentos de verdade**, um por ocorrência,
até um horizonte finito (52 no máximo). Depois disso a série não manda
mais em ninguém: cada sessão é remarcada, cancelada ou cobrada por conta
própria.

A alternativa era guardar a regra e expandir na hora de mostrar. Perdeu por
um motivo prático: no consultório cada sessão vira um fato próprio — uma é
remarcada, outra vira falta, outra custa diferente porque foi mais longa.
Regra expandida ao vivo não tem onde pendurar isso; precisaria de uma
tabela de exceções, e aí seriam duas fontes de verdade para a mesma
pergunta.

Encerrar a série cancela as ocorrências **futuras**. O passado nunca é
tocado: sessão que aconteceu é fato, não plano.

### Conflito não derruba a série

Se um dos horários já está ocupado, aquela ocorrência é **pulada** e volta
na resposta, com o motivo. Recusar as doze porque a terceira bateu seria
obedecer à máquina em vez da pessoa — que quer as onze livres marcadas e
quer saber da que faltou.

### Bloqueio não é atendimento fantasma

Férias, feriado e almoço poderiam ser atendimentos de um cliente falso.
Seria mais curto e estragaria o resto: entrariam em contagem, presença e
financeiro, e um dia alguém tentaria cobrar por eles. São tabela própria,
e a única coisa que fazem é ocupar horário — a checagem mora no serviço de
atendimentos, então vale para criar, remarcar e para a recorrência.

Duas decisões de comportamento:

* **O bloqueio é da sua agenda por padrão.** Fechar a clínica inteira
  exige dizer (`conta_inteira`) e enxergar a conta toda. Marcar férias não
  deveria fechar o consultório dos colegas por descuido.
* **Bloquear por cima de sessão marcada é recusado**, com a contagem do
  que está lá. Quem confirma bloqueia mesmo assim — e os atendimentos
  **continuam de pé**. Cancelar sessão de alguém é decisão de gente, não
  efeito colateral de um bloqueio de férias.


## Documentos e exportação (Etapa 9)

### A classe do documento decide quem abre

Recibo é **administrativo**: a recepção emite e o dono confere, porque é
dinheiro. Declaração, laudo e cópia de prontuário são **clínicos**: ler é a
mesma porta do prontuário, com as mesmas quatro perguntas. Uma permissão só
para os dois acabaria de um jeito previsível — a recepção enxergando laudo
para conseguir imprimir recibo.

Por isso `documents.data_class` não é decoração: é o que a rota consulta
para saber qual permissão exigir. O mesmo endpoint de download pede
`finance.read` para um e `documents.read` para outro. Anexo entra como
clínico **por precaução**: ninguém sabe o que tem dentro de um arquivo que
alguém mandou, e o erro seguro é para o lado de menos acesso.

### Declaração não vaza sessão

A declaração de comparecimento diz que a pessoa esteve, quando e por quanto
tempo — e **nada** sobre o que foi tratado. Declaração que carrega conteúdo
clínico é a forma mais comum de vazar prontuário sem perceber, então há
teste lendo o PDF de volta e conferindo que o texto da sessão não está lá.

### O arquivo não fica legível no disco

Mesma chave mestra do prontuário, derivação por documento, AAD com prefixo
próprio (`vc1d|`) — para que ciphertext de nota nunca abra como documento.
No disco fica um `.bin` sem nome falante, em `VC_FILES_DIR`.

### PDF sem dependência

`app/domain/pdf.py` gera os PDFs em ~200 linhas. Os documentos que este
sistema emite são texto em A4, sem imagem e sem fonte embutida — para isso,
uma biblioteca de diagramação seria um megabyte a mais passando perto de
conteúdo clínico. As 14 fontes padrão não precisam ser embutidas e
`WinAnsiEncoding` cobre o português inteiro.

O que ele não faz: imagem, tabela com borda, fonte fora das padrão. Quando
alguma fizer falta, aí sim vale a dependência.

### Exportar prontuário não é atalho

A cópia em PDF passa pelo **mesmo filtro da leitura**, nota por nota, e cada
uma entra na trilha. Um PDF com tudo dentro é o pior lugar para uma regra de
acesso falhar.


## Direitos do titular (Etapa 10)

### Exclusão não é DELETE

Um pedido chega como uma frase só ("quero meus dados apagados") e se
resolve em decisões diferentes por tipo de dado:

    cadastro comercial  → pode ser anonimizado
    prontuário          → guarda obrigatória; o CONTEÚDO pode ser destruído
    financeiro          → obrigação fiscal; fica
    documentos          → depende do que é

Tratar tudo igual erra nos dois sentidos: ou some o que a lei manda
guardar, ou fica o que a pessoa pediu para apagar. Por isso cada pedido
vira itens, e cada item carrega **decisão, motivo e base legal** —
inclusive quando a decisão é *manter*. "Mantivemos" precisa ser tão
justificável quanto "apagamos".

### Registrar e executar são passos separados

`POST .../decisions` registra o plano e **não apaga nada**.
`POST .../decisions/{item}/apply` executa. A separação existe para que
alguém possa revisar antes de a ação virar irreversível — e aqui quase
tudo é irreversível. Há teste garantindo que registrar não toca em nada.

### Anonimizar não é apagar

O cadastro perde o que identifica e ganha um rótulo neutro; a série de
atendimentos, os valores e a trilha continuam, desidentificados. É o que
permite a clínica seguir existindo como negócio sem seguir sabendo quem
era aquela pessoa. É irreversível de propósito: anonimização que dá para
desfazer é pseudonimização com outro nome.

### Retenção nasce vazia — e isso é a decisão

O prazo de guarda depende do conselho profissional de cada categoria.
Inventar um número daria aparência de conformidade a um chute, então
`retention_policies` nasce sem nenhuma linha e **prazo sem base legal
escrita é recusado**. Enquanto não houver política aplicável, nada é
apagado automaticamente — e a ausência fica visível na tela, em vez de
virar um padrão silencioso.

Continua sendo a decisão 4 da Etapa 2, ainda em aberto: a tabela está
pronta esperando o número que só uma fonte externa pode dar.

### O pacote de portabilidade diz o que não incluiu

Conteúdo clínico entra apenas se quem gera já podia lê-lo. Quando fica de
fora, o JSON **diz** que existe e não foi incluído — omitir em silêncio
seria responder mal a um pedido de acesso.


## E-mail (Etapa 11)

### Fila, não `smtplib` na rota

Três motivos, e nenhum é elegância:

1. **O servidor de e-mail cai.** Se a rota mandasse direto, um SMTP fora do
   ar derrubaria o cadastro junto. Com fila, a mensagem espera.
2. **Dá para ver o que foi mandado.** "A pessoa não recebeu o convite" se
   responde olhando a fila: ela diz se saiu, quando, e com que erro.
3. **Enviar é lento.** Uma conexão SMTP no meio de uma requisição é meio
   segundo de alguém olhando a tela.

Quem entrega são os comandos, rodando pelo agendador do sistema:

    python -m app.jobs.emails --lote 50 --limpar 90    # de minuto em minuto
    python -m app.jobs.lembretes                       # de hora em hora

Os dois são **idempotentes**. O de lembretes usa chave de deduplicação na
fila, então rodar dez vezes no mesmo dia manda um lembrete só.

### Sem SMTP configurado, nada some

`VC_MAIL_BACKEND=queue` é o padrão: a mensagem fica na fila, visível, e a
tentativa **não é gasta**. É melhor do que sumir com aparência de
entregue. `console` imprime no log — dá para testar o fluxo inteiro sem
mandar e-mail de verdade para ninguém.

### O corpo do e-mail nunca carrega conteúdo clínico

`email_messages` guarda o texto do que saiu, então ela é, na prática, uma
cópia de tudo que foi enviado. O lembrete diz **quando** e **onde**:

    Data:  12/10/2026
    Hora:  10:00
    Forma: online

Nunca o que foi ou será tratado. Se alguém "melhorar" o lembrete
colocando o motivo da consulta, terá copiado prontuário para uma tabela
sem cifra e mandado por um canal que ninguém controla. Há teste
impedindo, e o smoke confere no banco.

Outras três regras do lembrete:

* **Quem revogou o consentimento de contato não recebe.** A revogação vale
  na hora, sem depender de alguém lembrar de checar.
* **Cadastro anonimizado não recebe** — não há mais a quem escrever.
* **O horário sai no fuso da conta.** Lembrete com a hora errada é pior do
  que nenhum lembrete.

### Limpeza

Endereço e corpo são dado pessoal. `--limpar 90` esvazia o corpo de
mensagens enviadas há mais de 90 dias: a linha fica (para responder "saiu
ou não saiu"), o conteúdo some.


## Refinamento (Etapa 12)

### A busca já ignorava acento

Estava na lista de limitações e não era verdade: as tabelas usam
`utf8mb4_unicode_ci`, e nessa collation `José` casa com `jose` e
`Conceição` com `conceicao`. Nenhuma coluna normalizada é necessária — o
que faltava era o **teste** provando, para ninguém quebrar isso mexendo no
schema um dia. Agora existe.

### Paginação sem refazer tela

`?pagina=N&limite=M`, e o total vai em `X-Total-Count` — **não no corpo**.
A resposta continua sendo uma lista, então nenhuma tela quebrou ao ganhar
paginação. Página, e não cursor, porque as listas aqui são alfabéticas e
cronológicas, com a pessoa querendo ir para a página 3 e voltar; o `COUNT`
a mais é o que paga por mostrar "134 pessoas" em vez de "134+".

A agenda continua sem paginar (`pagina=0`): ali o recorte já são as datas.

### Pagamento parcial

Metade hoje, metade na semana que vem. O atendimento só vira `paid` quando
a soma cobre o combinado; até lá segue em aberto pelo resto. E estornar um
pedaço **devolve a cobrança** — com pagamento em partes, "existe outro
pagamento" não basta: dois pedaços cobriam o total, e tirar um deixa de
cobrir.

### Pagamento avulso

Pacote, sinal, acerto. O livro-caixa sempre aceitou (a coluna do
atendimento é opcional); faltava caminho para criar. Sem ele, um pacote de
dez sessões pago adiantado só entrava distorcendo a agenda.

### Teto de escrita

240 escritas por minuto por pessoa. Não é contenção de ataque — para isso
existe o limite do login e a barreira na frente do servidor. É para uma
automação com defeito (ou um botão preso) não encher o banco antes de
alguém perceber. Generoso de propósito: quem está atendendo e lançando
pagamento não pode esbarrar nele. Leitura não é afetada.
