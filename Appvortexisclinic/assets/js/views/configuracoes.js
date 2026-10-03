/* =============================================================
   CONFIGURAÇÕES DA CONTA — agora gravável.

   Era a última tela que lia de `mock.js`. O arquivo deixou de
   existir: jornada, duração padrão, meta, fuso e terminologia vêm
   de `tenant_settings` e voltam para lá.

   Três cuidados que a tela precisa manter:

   1. **Meta vazia ≠ meta zero.** O campo em branco limpa a meta; a
      tela mostra estado vazio, não uma barra em 0%.
   2. **A terminologia é saneada aqui e no servidor.** O que o
      servidor recusar volta em `recusados` e vira aviso — não some
      em silêncio dando impressão de salvo.
   3. **Ler é de todo mundo, gravar não.** Quem não tem
      `settings.manage` vê os valores e não vê os campos.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var html = VC.safe.html;
  var ui = VC.ui, fmt = VC.fmt, f = VC.form;

  var DIAS = [
    { n: 1, r: "Seg" }, { n: 2, r: "Ter" }, { n: 3, r: "Qua" }, { n: 4, r: "Qui" },
    { n: 5, r: "Sex" }, { n: 6, r: "Sáb" }, { n: 7, r: "Dom" }
  ];

  /* Fusos do Brasil + o de quem atende de fora. Lista curta de
     propósito: o servidor aceita qualquer nome IANA válido, mas um
     seletor com 400 opções não ajuda ninguém a acertar o seu. */
  var FUSOS = [
    { valor: "America/Sao_Paulo", rotulo: "Brasília (São Paulo, Rio, Sul, Nordeste)" },
    { valor: "America/Manaus", rotulo: "Manaus (Amazonas, Roraima, Rondônia)" },
    { valor: "America/Cuiaba", rotulo: "Cuiabá (Mato Grosso)" },
    { valor: "America/Belem", rotulo: "Belém (Pará, Amapá)" },
    { valor: "America/Fortaleza", rotulo: "Fortaleza" },
    { valor: "America/Rio_Branco", rotulo: "Rio Branco (Acre)" },
    { valor: "America/Noronha", rotulo: "Fernando de Noronha" },
    { valor: "UTC", rotulo: "UTC" }
  ];

  var TERMOS_EDITAVEIS = [
    { chave: "client.one", rotulo: "Pessoa atendida (singular)", dica: "Paciente, Cliente, Aluno" },
    { chave: "client.many", rotulo: "Pessoa atendida (plural)", dica: "Pacientes, Clientes" },
    { chave: "appointment.one", rotulo: "Encontro (singular)", dica: "Atendimento, Sessão, Consulta" },
    { chave: "appointment.many", rotulo: "Encontro (plural)", dica: "Atendimentos, Sessões" },
    { chave: "record.one", rotulo: "Registro clínico", dica: "Evolução, Prontuário" }
  ];

  var atual = null;

  function podeGravar() { return VC.session.pode("settings.manage"); }

  function leitura(c) {
    var termos = VC.terms.atual();
    return html`
      <div class="grid grid--3">
        ${ui.stat({ rotulo: "Jornada", valor: c.jornadaInicio + " às " + c.jornadaFim,
                    dica: diasEmTexto(c.dias) })}
        ${ui.stat({ rotulo: "Duração padrão", valor: fmt.duracao(c.duracaoPadrao),
                    dica: "ao criar um atendimento" })}
        ${ui.stat({ rotulo: "Fuso da conta", valor: rotuloDoFuso(c.fuso),
                    dica: "define o que é “hoje”" })}
      </div>
      <div class="grid grid--3" style="margin-top:var(--sp-4)">
        ${ui.stat({ rotulo: "Meta do mês",
                    valor: c.metaMensal ? fmt.moeda(c.metaMensal) : "—",
                    dica: c.metaMensal ? "acompanhada no financeiro" : "sem meta definida" })}
        ${ui.stat({ rotulo: "Pessoa atendida", valor: termos["client.one"],
                    dica: "rótulo usado na interface" })}
        ${ui.stat({ rotulo: "Moeda", valor: c.moeda, dica: "real brasileiro" })}
      </div>`;
  }

  function diasEmTexto(dias) {
    if (!dias || !dias.length) return "nenhum dia";
    return DIAS.filter(function (d) { return dias.indexOf(d.n) > -1; })
      .map(function (d) { return d.r; }).join(", ");
  }

  function rotuloDoFuso(valor) {
    var achado = FUSOS.filter(function (fu) { return fu.valor === valor; })[0];
    return achado ? achado.rotulo.split(" (")[0] : valor;
  }

  function formulario(c) {
    var termos = c.terminologia || {};
    return html`
      ${f.erro("")}

      <h2 style="font-size:var(--fs-base);margin-bottom:var(--sp-3)">Atendimento</h2>
      <div class="grid grid--3">
        ${f.campo({ nome: "jornadaInicio", rotulo: "Início da jornada", tipo: "time",
                    valor: c.jornadaInicio })}
        ${f.campo({ nome: "jornadaFim", rotulo: "Fim da jornada", tipo: "time",
                    valor: c.jornadaFim })}
        ${f.campo({ nome: "duracaoPadrao", rotulo: "Duração padrão (min)", tipo: "number",
                    minimo: "10", valor: c.duracaoPadrao })}
      </div>
      <div class="filters" style="margin:var(--sp-3) 0">
        <span class="stat__label" style="align-self:center">Dias de atendimento</span>
        ${html.juntar(DIAS.map(function (d) {
          return html`<button class="chip" type="button" data-dia="${d.n}"
                        aria-pressed="${(c.dias || []).indexOf(d.n) > -1}">${d.r}</button>`;
        }))}
      </div>
      <div class="grid grid--3">
        ${f.campo({ nome: "intervalo", rotulo: "Intervalo entre sessões (min)", tipo: "number",
                    minimo: "0", valor: c.intervalo, obrigatorio: false,
                    dica: "evita agendamentos colados" })}
        ${f.campo({ nome: "toleranciaFalta", rotulo: "Tolerância de falta (h)", tipo: "number",
                    minimo: "0", valor: c.toleranciaFalta, obrigatorio: false,
                    dica: "cancelamento sem cobrança" })}
        ${f.campo({ nome: "fuso", rotulo: "Fuso horário", tipo: "select", valor: c.fuso,
                    opcoes: FUSOS.map(function (fu) {
                      return { valor: fu.valor, rotulo: fu.rotulo };
                    }) })}
      </div>
      <div class="notice" style="margin-top:var(--sp-3)">
        <div>A jornada <b>desenha a grade</b> da agenda e sugere horários — ela não
        bloqueia agendamento. Atender fora dela continua possível, sem precisar mudar
        a configuração da conta.</div>
      </div>

      ${VC.session.pode("finance.read") ? html`
        <h2 style="font-size:var(--fs-base);margin:var(--sp-5) 0 var(--sp-3)">Financeiro</h2>
        <div class="grid grid--2">
          ${f.campo({ nome: "metaMensal", rotulo: "Meta do mês", tipo: "number", passo: "0.01",
                      minimo: "0", valor: c.metaMensal === null ? "" : c.metaMensal,
                      obrigatorio: false,
                      dica: "em branco = sem meta (a tela não inventa um número)" })}
          ${f.campo({ nome: "moeda", rotulo: "Moeda", valor: c.moeda, obrigatorio: false,
                      dica: "só real por enquanto" })}
        </div>` : html.vazio}

      <h2 style="font-size:var(--fs-base);margin:var(--sp-5) 0 var(--sp-3)">Como este sistema chama as coisas</h2>
      <div class="grid grid--2">
        ${html.juntar(TERMOS_EDITAVEIS.map(function (t) {
          return f.campo({ nome: "termo:" + t.chave, rotulo: t.rotulo,
                           valor: termos[t.chave] || "", obrigatorio: false, dica: t.dica });
        }))}
      </div>
      <div class="notice" style="margin-top:var(--sp-3)">
        <div>Rótulo é texto curto e simples: nada de marcação, link ou símbolo estranho.
        Campo em branco volta ao padrão da profissão.</div>
      </div>

      <div class="row" style="justify-content:flex-end;gap:var(--sp-3);margin-top:var(--sp-5)">
        <button class="btn btn--ghost" type="button" data-acao="limpar-meta">Remover meta</button>
        <button class="btn btn--accent" type="button" data-acao="salvar-config">Salvar</button>
      </div>`;
  }

  /* ---------------- plano, limites e uso ----------------
     O uso aparece AO LADO do limite: "5 de 15" é o que ajuda a decidir;
     "limite: 15" sozinho não diz nada. Limite nulo é "sem limite" — e a
     tela diz isso em vez de mostrar barra vazia. Não há botão de trocar
     de plano: sem cobrança atrás, seria um "vire Pro de graça". */
  function linhaDeLimite(rotulo, usado, limite, unidade) {
    var texto = limite === null
      ? fmt.numero(usado) + (unidade || "") + " · sem limite"
      : fmt.numero(usado) + " de " + fmt.numero(limite) + (unidade || "");
    var pct = limite ? Math.min(100, Math.round((usado / limite) * 100)) : 0;
    var tom = pct >= 80 ? "meter--warn" : "meter--ok";
    return html`
      <div style="display:grid;gap:var(--sp-2)">
        <div class="row" style="justify-content:space-between;gap:var(--sp-3)">
          <span class="stat__label">${rotulo}</span>
          <b>${texto}</b>
        </div>
        ${limite === null ? html.vazio
          : html`<div class="meter ${tom}" role="img"
                   aria-label="${rotulo}: ${pct}% do limite"><i style="width:${pct}%"></i></div>`}
        ${limite !== null && usado >= limite
          ? html`<span class="stat__hint">Limite atingido: o que já existe continua
              disponível, só não dá para incluir mais.</span>`
          : html.vazio}
      </div>`;
  }

  function cartaoPlano(p) {
    var termos = VC.terms.atual();
    var situacao = p.status + (p.testeAte && p.status === "em teste"
      ? " até " + fmt.dataLonga(p.testeAte) : "");
    return html`
      <div class="grid grid--3">
        ${ui.stat({ rotulo: "Plano", valor: p.nome, dica: situacao })}
        ${ui.stat({ rotulo: "Mensalidade",
                    valor: p.precoMensal === null ? "—" : fmt.moeda(p.precoMensal),
                    dica: p.precoMensal === null ? "ainda não definida" : "por mês" })}
        ${ui.stat({ rotulo: "Situação", valor: p.vigente ? "Em dia" : "Suspensa",
                    tom: p.vigente ? "" : "warn" })}
      </div>
      <div style="display:grid;gap:var(--sp-4);margin-top:var(--sp-5)">
        ${linhaDeLimite("Profissionais", p.uso.profissionais, p.limites.profissionais)}
        ${linhaDeLimite("Pessoas da equipe", p.uso.membros, p.limites.membros)}
        ${linhaDeLimite(termos["client.many"] + " ativos", p.uso.pessoas, p.limites.pessoas)}
        ${linhaDeLimite("Arquivos", p.uso.armazenamentoMb, p.limites.armazenamentoMb, " MB")}
      </div>
      <div class="notice" style="margin-top:var(--sp-5)">
        <div>Para mudar de plano, fale com a Vortexis. Mudar para um plano menor
        <b>nunca apaga</b> nada: tudo o que já foi cadastrado continua visível.</div>
      </div>`;
  }

  function render() {
    return html`
      <div class="page-head">
        <div class="page-head__title">
          <h1>Configurações</h1>
          <p>Preferências desta conta</p>
        </div>
      </div>
      <div class="card"><div class="card__body" data-config>${ui.skeletonLinhas(5)}</div></div>
      ${podeGravar() ? html`
        <h2 style="font-size:var(--fs-base);margin:var(--sp-6) 0 var(--sp-3)">Plano e uso</h2>
        <div class="card"><div class="card__body" data-plano>${ui.skeletonLinhas(3)}</div></div>`
        : html.vazio}`;
  }

  function pintar(c) {
    atual = c;
    VC.safe.render(VC.dom.el("[data-config]"),
                   podeGravar() ? formulario(c) : leitura(c));
    if (c.recusados && c.recusados.length) {
      VC.toast.erro("Alguns rótulos não foram salvos",
                    c.recusados.length + " campo(s) com texto não aceito");
    }
  }

  function diasSelecionados(escopo) {
    return VC.dom.els("[data-dia]", escopo)
      .filter(function (b) { return b.getAttribute("aria-pressed") === "true"; })
      .map(function (b) { return Number(b.getAttribute("data-dia")); });
  }

  function mount(params, alvo) {
    VC.shell.definirTitulo("Configurações", "Preferências da conta");

    VC.services.configuracoes.obter().then(pintar, function () {
      VC.safe.render(VC.dom.el("[data-config]"), ui.vazio({
        titulo: "Não foi possível carregar", texto: "Tente novamente em instantes."
      }));
    });

    if (podeGravar()) {
      VC.services.configuracoes.plano().then(function (p) {
        VC.safe.render(VC.dom.el("[data-plano]"), cartaoPlano(p));
      }, function () {
        VC.safe.render(VC.dom.el("[data-plano]"), ui.vazio({
          titulo: "Não foi possível carregar o plano", texto: "Tente novamente em instantes."
        }));
      });
    }

    VC.dom.on(alvo, "click", "[data-dia]", function (e, botao) {
      botao.setAttribute("aria-pressed",
                         String(botao.getAttribute("aria-pressed") !== "true"));
    });

    VC.dom.on(alvo, "click", '[data-acao="salvar-config"]', function () {
      var escopo = VC.dom.el("[data-config]");
      var valores = f.valores(escopo);

      var terminologia = {};
      Object.keys(valores).forEach(function (chave) {
        if (chave.indexOf("termo:") !== 0) return;
        terminologia[chave.slice(6)] = valores[chave] === undefined ? "" : valores[chave];
      });
      /* Campo em branco precisa viajar como "" para o servidor saber
         que é "volta ao padrão" — e não "não mexi nisso". */
      TERMOS_EDITAVEIS.forEach(function (t) {
        if (terminologia[t.chave] === undefined) terminologia[t.chave] = "";
      });

      f.mostrarErro(escopo, "");
      VC.services.configuracoes.salvar({
        jornadaInicio: valores.jornadaInicio,
        jornadaFim: valores.jornadaFim,
        dias: diasSelecionados(escopo),
        duracaoPadrao: valores.duracaoPadrao,
        intervalo: valores.intervalo === undefined ? 0 : valores.intervalo,
        toleranciaFalta: valores.toleranciaFalta === undefined ? 0 : valores.toleranciaFalta,
        fuso: valores.fuso,
        metaMensal: valores.metaMensal,
        terminologia: terminologia
      }).then(function (c) {
        VC.toast.ok("Configurações salvas", "");
        /* Os rótulos mudaram: a interface inteira precisa reler. */
        VC.terms.definir(c.terminologia, "conta");
        pintar(c);
      }, function (erro) {
        f.mostrarErro(escopo, f.mensagemDe(erro));
      });
    });

    VC.dom.on(alvo, "click", '[data-acao="limpar-meta"]', function () {
      VC.services.configuracoes.salvar({ limparMeta: true }).then(function (c) {
        VC.toast.ok("Meta removida", "O financeiro volta a mostrar estado vazio");
        pintar(c);
      }, function (erro) {
        VC.toast.erro("Não foi possível remover", f.mensagemDe(erro));
      });
    });
  }

  VC.views = VC.views || {};
  /* `_cartaoPlano` exposto só para a suíte conferir o que a tela escreve. */
  VC.views.configuracoes = { render: render, mount: mount, _cartaoPlano: cartaoPlano };
})(window);
