/* =============================================================
   AGENDA — dia, semana e mês
   Interface de leitura nesta fase. Criar e mover atendimento entram
   com o formulário e a regra de conflito de horário (etapa 2.7).
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var html = VC.safe.html;
  var ui = VC.ui, fmt = VC.fmt, t = VC.terms.t;

  var estado = { visao: "dia", data: new Date() };

  function inicioSemana(d) {
    var x = new Date(d);
    x.setDate(x.getDate() - ((x.getDay() + 6) % 7));
    x.setHours(0, 0, 0, 0);
    return x;
  }

  function periodo() {
    var de = new Date(estado.data), ate = new Date(estado.data);
    if (estado.visao === "dia") {
      de.setHours(0, 0, 0, 0); ate.setHours(23, 59, 59, 999);
    } else if (estado.visao === "semana") {
      de = inicioSemana(estado.data);
      ate = new Date(de); ate.setDate(ate.getDate() + 6); ate.setHours(23, 59, 59, 999);
    } else {
      de = new Date(estado.data.getFullYear(), estado.data.getMonth(), 1);
      ate = new Date(estado.data.getFullYear(), estado.data.getMonth() + 1, 0, 23, 59, 59, 999);
    }
    return { de: de, ate: ate };
  }

  function rotuloPeriodo() {
    var p = periodo();
    if (estado.visao === "dia") return fmt.dataLonga(estado.data);
    if (estado.visao === "semana") return fmt.diaMes(p.de) + " – " + fmt.diaMes(p.ate);
    return fmt.mesAno(estado.data);
  }

  function andar(passo) {
    var d = new Date(estado.data);
    if (estado.visao === "dia") d.setDate(d.getDate() + passo);
    else if (estado.visao === "semana") d.setDate(d.getDate() + passo * 7);
    else d.setMonth(d.getMonth() + passo);
    estado.data = d;
    carregar();
  }

  function cabecalho() {
    var visoes = ["dia", "semana", "mes"].map(function (v) {
      return html`<button class="chip" type="button" role="tab" data-visao="${v}"
        aria-pressed="${estado.visao === v}">${v === "mes" ? "Mês" : fmt.capitalizar(v)}</button>`;
    });

    return html`
      <div class="page-head">
        <div class="page-head__title"><h1>${t("schedule.title")}</h1><p data-rotulo-periodo>${rotuloPeriodo()}</p></div>
        <div class="page-head__actions">
          ${VC.session.pode("agenda.write") ? html`
            <button class="btn btn--ghost" type="button" data-acao="bloquear-horario">Bloquear horário</button>`
            : html.vazio}
          <button class="btn btn--accent" type="button" data-acao="novo-atendimento">${t("appointment.new")}</button>
        </div>
      </div>

      <div class="filters row--between">
        <div class="row" style="gap:var(--sp-2)">
          <button class="btn btn--ghost btn--sm" type="button" data-andar="-1" aria-label="Período anterior">←</button>
          <button class="btn btn--ghost btn--sm" type="button" data-hoje>Hoje</button>
          <button class="btn btn--ghost btn--sm" type="button" data-andar="1" aria-label="Próximo período">→</button>
        </div>
        <div class="row" style="gap:var(--sp-1)" role="tablist" aria-label="Visualização">${html.juntar(visoes)}</div>
      </div>

      <div data-bloqueios></div>
      <div data-agenda>${ui.skeletonLinhas(6)}</div>`;
  }

  /* ---------------- Dia ---------------- */
  function visaoDia(lista) {
    if (!lista.length) {
      return html`<div class="card"><div class="card__body">${ui.vazio({
        titulo: "Dia livre",
        texto: "Nenhum " + t("appointment.one", true) + " marcado para " + fmt.dataLonga(estado.data) + "."
      })}</div></div>`;
    }
    var resumo = VC.domain.metrics.resumoDoDia(lista);
    var mostrarPagamento = VC.session.pode("finance.read");

    return html`
      <div class="card">
        <div class="card__body" style="padding:var(--sp-2)">
          <div class="slot-list">${html.juntar(lista.map(function (a) {
            return ui.linhaAtendimento(a, { mostrarPagamento: mostrarPagamento, comAcoes: true });
          }))}</div>
        </div>
        <div class="card__foot">
          ${resumo.total} ${t("appointment.many", true)}
          ${mostrarPagamento ? html` · previsto ${fmt.moeda(resumo.previsto)}` : html.vazio}
        </div>
      </div>`;
  }

  /* ---------------- Semana ---------------- */
  function visaoSemana(lista) {
    var de = inicioSemana(estado.data);
    var colunas = [];
    for (var i = 0; i < 7; i++) {
      var d = new Date(de); d.setDate(d.getDate() + i);
      colunas.push({
        data: d,
        itens: lista.filter(function (a) { return fmt.mesmoDia(a.inicio, d); })
      });
    }

    return html`<div class="week">${html.juntar(colunas.map(function (c) {
      var hoje = fmt.mesmoDia(c.data, new Date());
      var itens = c.itens.length
        ? html.juntar(c.itens.map(function (a) {
            return html`
              <div class="week__item week__item--${a.status}">
                <b class="tabular">${fmt.hora(a.inicio)}</b>
                <span class="private">${fmt.nomeCurto(a.paciente.nome)}</span>
              </div>`;
          }))
        : html`<p class="week__vazio">—</p>`;

      return html`
        <div class="week__col${hoje ? " is-today" : ""}">
          <div class="week__head"><b>${fmt.diaSemana(c.data)}</b><span>${fmt.diaMes(c.data)}</span></div>
          <div class="week__body">${itens}</div>
        </div>`;
    }))}</div>`;
  }

  /* ---------------- Mês ---------------- */
  function visaoMes(lista) {
    var primeiro = new Date(estado.data.getFullYear(), estado.data.getMonth(), 1);
    var inicioGrade = inicioSemana(primeiro);
    var celulas = [];
    for (var i = 0; i < 42; i++) {
      var d = new Date(inicioGrade); d.setDate(d.getDate() + i);
      var doDia = VC.domain.metrics.ativos(lista.filter(function (a) { return fmt.mesmoDia(a.inicio, d); }));
      celulas.push({
        data: d, qtd: doDia.length,
        fora: d.getMonth() !== estado.data.getMonth(),
        hoje: fmt.mesmoDia(d, new Date())
      });
      if (i >= 34 && d.getMonth() !== estado.data.getMonth() && d.getDay() === 0) break;
    }

    var cabecalhos = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"].map(function (d) {
      return html`<div class="month__dow">${d}</div>`;
    });
    var dias = celulas.map(function (c) {
      return html`
        <button class="month__cell${c.fora ? " is-out" : ""}${c.hoje ? " is-today" : ""}"
                type="button" data-ir-dia="${c.data.toISOString()}">
          <span class="month__num">${c.data.getDate()}</span>
          ${c.qtd ? html`<span class="month__count">${c.qtd}</span>` : html.vazio}
        </button>`;
    });

    return html`<div class="month">${html.juntar(cabecalhos)}${html.juntar(dias)}</div>`;
  }

  /* Bloqueio não é atendimento: aparece numa faixa própria, acima da
     agenda, e não entra em contagem nenhuma. */
  function pintarBloqueios(lista) {
    var caixa = VC.dom.el("[data-bloqueios]");
    if (!caixa) return;
    if (!lista.length) { VC.safe.render(caixa, html.vazio); return; }

    var podeEditar = VC.session.pode("agenda.write");
    VC.safe.render(caixa, html`
      <div class="card" style="margin-bottom:var(--sp-3)">
        <div class="card__body" style="padding:var(--sp-3)">
          <div class="cell-sub" style="margin-bottom:var(--sp-2)">Horários indisponíveis neste período</div>
          <div class="row" style="flex-wrap:wrap;gap:var(--sp-2)">${html.juntar(lista.map(function (b) {
            return html`
              <span class="badge badge--neutral" style="display:inline-flex;align-items:center;gap:var(--sp-2)">
                ${b.titulo} · ${fmt.diaMes(b.inicio)}–${fmt.diaMes(b.fim)}${
                  b.daContaInteira ? " · conta inteira" : ""}
                ${podeEditar ? html`
                  <button class="btn btn--quiet btn--sm" type="button" data-acao="remover-bloqueio"
                          data-bloqueio="${b.id}" aria-label="Remover bloqueio">✕</button>` : html.vazio}
              </span>`;
          }))}</div>
        </div>
      </div>`);
  }

  function carregar() {
    var alvo = VC.dom.el("[data-agenda]");
    if (!alvo) return;
    VC.safe.render(alvo, ui.skeletonLinhas(5));
    VC.safe.texto(VC.dom.el("[data-rotulo-periodo]"), rotuloPeriodo());

    var p = periodo();
    VC.services.agenda.bloqueios(p.de, p.ate).then(pintarBloqueios, function () {});
    VC.services.atendimentos.listar({ de: p.de, ate: p.ate }).then(function (lista) {
      if (estado.visao === "dia") VC.safe.render(alvo, visaoDia(lista));
      else if (estado.visao === "semana") VC.safe.render(alvo, visaoSemana(lista));
      else VC.safe.render(alvo, visaoMes(lista));
    }).catch(function () {
      VC.safe.render(alvo, ui.vazio({ titulo: "Não foi possível carregar a agenda", texto: "Tente novamente." }));
    });
  }

  function render() { return cabecalho(); }

  function mount(params, alvo) {
    var q = new URLSearchParams(global.location.hash.split("?")[1] || "");
    var v = q.get("v");
    if (v && ["dia", "semana", "mes"].indexOf(v) > -1 && v !== estado.visao) {
      estado.visao = v;
      VC.safe.render(alvo, cabecalho());
    }

    VC.shell.definirTitulo(t("schedule.title"), rotuloPeriodo());

    VC.dom.on(alvo, "click", "[data-visao]", function (e, botao) {
      estado.visao = botao.getAttribute("data-visao");
      VC.dom.els("[data-visao]", alvo).forEach(function (b) { b.setAttribute("aria-pressed", String(b === botao)); });
      carregar();
    });
    VC.dom.on(alvo, "click", "[data-andar]", function (e, botao) {
      andar(parseInt(botao.getAttribute("data-andar"), 10));
    });
    VC.dom.on(alvo, "click", "[data-hoje]", function () { estado.data = new Date(); carregar(); });
    VC.dom.on(alvo, "click", "[data-ir-dia]", function (e, cel) {
      estado.data = new Date(cel.getAttribute("data-ir-dia"));
      estado.visao = "dia";
      VC.dom.els("[data-visao]", alvo).forEach(function (b) {
        b.setAttribute("aria-pressed", String(b.getAttribute("data-visao") === "dia"));
      });
      carregar();
    });

    carregar();
  }

  VC.views = VC.views || {};
  VC.views.agenda = { render: render, mount: mount };
})(window);
