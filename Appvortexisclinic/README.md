# Vortexis Clinic — Painel (app.vortexisclinic.com.br)

Painel de gestão para terapeutas e profissionais de atendimento. HTML, CSS e
JavaScript puros — sem build, sem dependências. É o produto que roda atrás do
login; o site institucional fica no projeto vizinho (`Sitevortexisclinic`).

> **Etapa atual: 5 — financeiro no banco.**
> Identidade, pessoas atendidas, agenda, atendimentos e financeiro vêm da API
> (`../Apivortexisclinic`), com MySQL por trás. Dá para **cadastrar, agendar,
> confirmar, marcar falta, cancelar, remarcar, editar, dar baixa, estornar e
> isentar** — e o servidor recusa conflito de horário e pagamento duplicado.
> **Ainda mockado:** só as preferências da conta (`assets/js/data/mock.js`).
> Prontuário e documentos não existem.
> A análise de arquitetura está em [`docs/arquitetura-etapa2.md`](docs/arquitetura-etapa2.md).

---

## Como testar

O painel agora **precisa da API no ar** — sem ela, a tela de entrada aparece e
avisa que não conseguiu falar com o servidor.

1. Suba a API (veja o README de `Apivortexisclinic`):
   ```bash
   python -m uvicorn app.main:app --reload --port 8000
   ```
2. Sirva o painel em outro terminal:
   ```bash
   python -m http.server 5500
   # ou: npx serve .
   ```
3. Abra `http://127.0.0.1:5500` e crie sua conta.

> Use `127.0.0.1` nos dois endereços, não `localhost`: para o navegador são
> origens diferentes, e cookie e CORS são por origem.
>
> O endereço da API fica em `assets/js/config/app.config.js`. Em produção, com
> API e painel na mesma origem, declare `window.VC_API_BASE = ""` antes dos
> scripts no `index.html`.
3. **Testes automatizados** (Node, sem navegador):
   ```bash
   node tests/run.js
   ```
   Cobrem isolamento entre contas, escape de HTML, cálculos do domínio,
   saneamento de terminologia e matriz de permissões.

Roteiro sugerido de navegação:

| Tela | Endereço | O que observar |
|---|---|---|
| Entrada | (sem sessão) | Cadastro, login, recuperação e escolha de workspace |
| Cadastro | `#/pacientes` → "Cadastrar" | Formulário real: grava no MySQL |
| Agendamento | qualquer tela → "Novo atendimento" | Tenta o mesmo horário duas vezes e veja o conflito |
| Baixa | `#/pendencias` → "Dar baixa" | Escolha a forma; depois estorne no Financeiro e veja a pendência voltar |
| Início | `#/` | Indicadores do dia, agenda de hoje, semana, pendências |
| Agenda | `#/agenda` · `#/agenda?v=semana` · `#/agenda?v=mes` | Três visões; clicar num dia do mês abre o dia |
| Pacientes | `#/pacientes` | Busca (digite um nome), filtros de situação e pendência |
| Ficha | `#/pacientes/pac_001` | Abas: histórico, cadastro, financeiro, anotações, documentos |
| Atendimentos | `#/atendimentos` | Filtros de período, situação, modalidade e pagamento |
| Financeiro | `#/financeiro` | Recebido, a receber, meta e últimos 6 meses |
| Pendências | `#/pendencias` | Cobranças em aberto, destaque acima de 30 dias |
| Demais | `#/anotacoes` `#/relatorios` `#/configuracoes` `#/perfil` | Estrutura das telas que dependem das próximas etapas |

Testes manuais que valem a pena: encolher a janela até o celular (a barra
inferior aparece e o menu vira gaveta), apertar **/** para focar a busca, ligar o
**Modo discreto** no topo e, no Perfil, **trocar de conta** — a sessão de exemplo
tem duas, com papéis diferentes, e a tela inteira muda com ela.

---

## Organização

```
Appvortexisclinic/
├── index.html                  # casco do app; as telas são montadas por JS
├── manifest.webmanifest        # PWA
├── service-worker.js           # cache só de arquivos estáticos
├── tests/run.js                # suíte de testes (node tests/run.js)
├── docs/arquitetura-etapa2.md  # análise, modelo de dados e regras de isolamento
└── assets/
    ├── images/                 # marca (mesma do site)
    ├── css/
    │   ├── tokens.css          # cores, densidade e COR POR VERTICAL
    │   ├── base.css            # reset, tipografia, utilitários, modo discreto
    │   ├── layout.css          # sidebar, topo, conteúdo, navegação mobile
    │   ├── components.css      # botões, cards, tabelas, selos, vazios, skeletons…
    │   └── views.css           # agenda semanal e mensal
    └── js/
        ├── config/app.config.js    # navegação, endereço da API, funcionalidades
        ├── services/mapa.js        # tradução API (inglês) ↔ tela (português)
        ├── types/entities.js       # User, Tenant, Membership, papéis e permissões
        ├── core/                   # safe, api, dom, terms, format, store, toast, session, router
        ├── domain/metrics.js       # TODO cálculo de negócio mora aqui
        ├── data/mock.js            # TODOS os dados fictícios (duas contas)
        ├── services/               # única porta de acesso a dados
        ├── components/             # ui, shell, modal, form (campos e erros)
        ├── views/                  # uma por área (auth.js = telas de entrada)
        └── app.js                  # rotas protegidas + ações globais + PWA
```

Ordem de carga (importa, e está no `index.html`):
`config → types → safe → dom → terms → format → store → toast → session → router
→ domain → mock → services → components → views → app`.

---

## Decisões de arquitetura

**Tudo o que é dado vem do servidor.** `core/api.js` é o único ponto que fala
com a API: manda o cookie (`credentials: "include"`), adiciona o cabeçalho CSRF
nas escritas e normaliza erro. O painel **não guarda token em lugar nenhum** —
o cookie de sessão é HttpOnly, invisível para o JavaScript.

**Os números não são calculados aqui.** Recebido, pendente, presença e os
resumos chegam prontos da API, da camada de domínio do servidor. É o que
impede tela e relatório divergirem. `domain/metrics.js` ficou como auxiliar de
apresentação, com as mesmas definições e um teste espelhado do outro lado.

**"Recebido" é regime de caixa.** Soma os pagamentos pela data em que o
dinheiro entrou, não pela data do atendimento — é assim que bate com o extrato
do banco. O card "Recebido no mês" e a lista do Financeiro saem do livro-caixa;
estorno continua na lista, riscado, porque apagar lançamento esconde o erro
junto com a explicação.

**Nada de dado em cache.** O service worker guarda só o casco (`assets/` e o
`index.html`), por allowlist. Resposta de dados vai direto para a rede — lista
de pessoas atendidas é dado de saúde por associação e não pode ficar no disco
do navegador. Sair da conta limpa o que ficou guardado.

**Sem sessão, o painel nem é montado.** `app.js` só monta navegação e rotas
depois que o servidor confirmou a sessão e o workspace ativo. É o mesmo
fail-closed do backend, aplicado à interface.

**Dados nunca ficam nas telas.** Views chamam `VC.services.*`, que devolvem
Promise. Hoje leem o mock com latência simulada (é o que faz os *skeletons*
aparecerem); amanhã trocam por `fetch`. Nenhuma view precisa mudar.

**Isolamento *fail-closed*.** Toda leitura passa por `VC.session.tenantId()`, que
**lança** quando não há vínculo ativo — não existe caminho em que a ausência de
conta vire consulta ampla. Recurso de outra conta responde "não encontrado", nunca
"sem permissão": negar com 403 já confirmaria que o registro existe. O tenant
nunca é enviado pelo cliente; ele sai da sessão. Regras completas na §15 do
documento de arquitetura.

**O front não é a autoridade.** `VC.session.pode()` e as rotas protegidas em
`app.js` só escondem o que a pessoa não pode usar. A decisão real será do
servidor, que repete a checagem em toda requisição.

**Administrar a conta não abre prontuário.** Permissões são classificadas em
administrativas, clínicas, de conta e de auditoria (`types/entities.js`). `OWNER`
administra e **não** recebe `clinical.*` pelo papel; `ASSISTANT` nunca recebe.
Acesso ao registro de outro profissional é concessão explícita, com motivo e
validade.

**Saída segura por construção.** Nada de concatenar HTML: as telas usam o
template `html` de `core/safe.js`, que escapa **toda** interpolação. `render()`
recusa string crua, então esquecer o escape não compila. Markup literal do
projeto entra por `html.estatico`, que nunca recebe dado.

**Uma fonte para cada coisa.** Navegação vem de `VC.config.navegacao`; número vem
de `VC.domain.metrics` (tela e relatório não podem divergir); palavra vem de
`VC.terms.t()`.

**Terminologia configurável.** Nenhuma tela escreve "paciente" ou "sessão": pede
a `t("client.one")`. O dicionário vem da profissão e pode ser sobrescrito pela
conta; termo é rótulo curto e passa por saneamento — **marcação não é aceita**.

**Uma pessoa, várias contas.** Usuário é global; o acesso é o vínculo
(*membership*) com papel e escopo próprios em cada conta. Trocar de conta é ação
explícita, revalidada, e reconfigura permissões e termos.

**Privacidade na interface.** Início, agenda e listas mostram nome abreviado
("Ana M.") e nada de conteúdo clínico. O **modo discreto** borra nomes na tela
quando há alguém por perto — é conforto visual, não controle de acesso.

**Service worker conservador.** Guarda só CSS/JS/imagens. Resposta de dados não
entra em cache — dado de paciente não pode ficar no disco do navegador.

**Movimento discreto.** É ferramenta de trabalho: transições curtas, sem animação
de entrada em cada bloco.

---

## O que ainda não existe (próximas etapas)

Documentos · exportação de relatórios ·
notificações · LGPD operacional (exportar, anonimizar, retenção parametrizada) ·
verificação de e-mail · painel interno da VORTEXIS.

Equipe e configurações já existem: convite por link, papéis, escopo de dados,
suspensão, e jornada/meta/terminologia/fuso graváveis. O painel não tem mais
nenhum dado de mentira — `assets/js/data/mock.js` foi apagado.
Ver `docs/arquitetura-etapa2.md` §19.

O prontuário já existe: aba clínica na ficha da pessoa, com registro cifrado no
servidor, versão a cada salvamento, assinatura, adendo com motivo e trilha de
acesso. Ler o conteúdo é uma chamada própria — e é ela que a auditoria registra.
Ver `docs/arquitetura-etapa2.md` §18.

O que ainda não vem do banco está num arquivo só, `assets/js/data/mock.js`:
as preferências da conta. Ele some quando `GET/PATCH /tenant/settings` existir.
