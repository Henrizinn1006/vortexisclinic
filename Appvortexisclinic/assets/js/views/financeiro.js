/* =============================================================
   FINANCEIRO e PENDÊNCIAS
   Ambas exigem finance.read — o roteador barra antes de montar.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var html = VC.safe.html;
  var ui = VC.ui, fmt = VC.fmt, t = VC.terms.t;

  /* ---------------- Financeiro ---------------- */
  function render() {
    return html`
      <div class="page-head"><div class="page-head__title">
        <h1>${t("finance.title")}</h1>
        <p>Recebimentos, pendências e evolução</p>
      </div></div>
      ${ui.skeletonStats(4)}
      <div class="card" style="margin-top:var(--sp-5)"><div class="card__body">${ui.skeletonLinhas(5)}</div></div>`;
  }

  function mount(params, alvo) {
    VC.shell.definirTitulo(t("finance.title"), fmt.mesAno(new Date()));

    Promise.all([
      VC.services.financeiro.resumoMes(new Date()),
      VC.services.financeiro.serieMensal(6),
      /* Livro-caixa do mês: o que entrou, por quando entrou. */
      VC.services.financeiro.pagamentos({
        de: new Date(new Date().getFullYear(), new Date().getMonth(), 1),
        ate: new Date()
      })
    ]).then(function (r) {
      var f = r[0], serie = r[1], pagos = r[2];
      var podeMexer = VC.session.pode("finance.write");

      var itens = serie.map(function (m) {
        return {
          rotulo: new Intl.DateTimeFormat("pt-BR", { month: "short" }).format(m.mes).replace(".", ""),
          valor: m.valor,
          destaque: m.mes.getMonth() === new Date().getMonth(),
          titulo: fmt.mesAno(m.mes) + ": " + fmt.moeda(m.valor)
        };
      });

      var linhasPagos = pagos.map(function (a) {
        return html`
          <tr${a.estornado ? html` class="linha--apagada"` : html.vazio}>
            <td class="cell-first"><span class="cell-main tabular">${fmt.diaMes(a.pagoEm)}</span></td>
            <td data-label="${t("client.one")}">${ui.nomeCliente(a.paciente.nome, true)}</td>
            <td data-label="Forma">${a.metodoRotulo}</td>
            <td data-label="Valor" class="num tabular">
              ${a.estornado
                ? html`<span class="muted"><s>${fmt.moeda(a.valor)}</s> · estornado</span>`
                : html`<b>${fmt.moeda(a.valor)}</b>`}
            </td>
            <td class="num">${podeMexer && !a.estornado
              ? html`<button class="btn btn--quiet btn--sm" type="button" data-acao="estornar"
                      data-pagamento="${a.id}" data-nome="${a.paciente.nome}">Estornar</button>`
              : html.vazio}</td>
          </tr>`;
      });

      VC.safe.render(alvo, html`
        <div class="page-head">
          <div class="page-head__title">
            <h1>${t("finance.title")}</h1>
            <p>${fmt.mesAno(new Date())}${f.meta ? " · meta de " + fmt.moeda(f.meta) : ""}</p>
          </div>
          ${VC.session.pode("finance.export") ? html`<div class="page-head__actions">
            ${VC.session.pode("finance.write") ? html`
              <button class="btn btn--ghost" type="button" data-acao="pagamento-avulso">Pagamento avulso</button>`
              : html.vazio}
            <button class="btn btn--ghost" type="button" data-acao="exportar-caixa">Exportar CSV</button>
          </div>` : html.vazio}
        </div>

        <div class="grid grid--4">
          ${ui.stat({ rotulo: "Recebido no mês", valor: fmt.moeda(f.recebido), tom: "ok",
                      tendencia: f.variacaoMesAnterior, dica: f.quantidadeRecebida + " atendimento(s)" })}
          ${ui.stat({ rotulo: "A receber (vencido)", valor: fmt.moeda(f.pendente), tom: f.pendente ? "warn" : "",
                      dica: f.quantidadePendente + " em aberto", href: "#/pendencias" })}
          ${ui.stat({ rotulo: "Previsto até o fim do mês", valor: fmt.moeda(f.previsto), dica: "ainda por acontecer" })}
          ${ui.stat({ rotulo: "Total do mês", valor: fmt.moeda(f.total), dica: "recebido + a receber + previsto" })}
        </div>

        <div class="cols-main" style="margin-top:var(--sp-5)">
          <div class="card">
            <div class="card__head"><h3>Últimos 6 meses</h3></div>
            <div class="card__body">${ui.barras(itens, { descricao: "Receita recebida por mês" })}</div>
          </div>

          <div class="card">
            <div class="card__head"><h3>Meta do mês</h3></div>
            <div class="card__body">
              ${f.meta ? html`
                <div class="row row--between" style="margin-bottom:8px">
                  <span class="muted" style="font-size:var(--fs-sm)">${fmt.moeda(f.recebido)} de ${fmt.moeda(f.meta)}</span>
                  <b>${fmt.porcento(f.percentualMeta)}</b>
                </div>
                <div class="meter meter--ok"><i style="width:${f.percentualMeta}%"></i></div>
                <p class="muted" style="font-size:var(--fs-xs);margin-top:var(--sp-3)">
                  A meta fica em Configurações e serve de referência interna.</p>`
              : ui.vazio({
                  titulo: "Sem meta definida",
                  texto: "A meta mensal entra com a tela de configurações gravável. " +
                         "Até lá, preferimos não inventar um número."
                })}
            </div>
          </div>
        </div>

        <div class="card" style="margin-top:var(--sp-5)">
          <div class="card__head">
            <h3>Recebido no mês</h3>
            <span class="muted" style="font-size:var(--fs-xs)">pela data do pagamento</span>
          </div>
          <div class="card__body">${linhasPagos.length
            ? ui.tabela([{ rotulo: "Data" }, { rotulo: t("client.one") }, { rotulo: "Forma" },
                         { rotulo: "Valor", num: true }, { rotulo: "" }], linhasPagos)
            : ui.vazio({ titulo: "Nenhum pagamento neste mês",
                         texto: "Os recebimentos aparecem aqui conforme forem registrados." })}
          </div>
        </div>`);
    });
  }

  /* ---------------- Pendências ---------------- */
  function renderPendencias() {
    return html`
      <div class="page-head"><div class="page-head__title">
        <h1>${t("pending.title")}</h1>
        <p>Atendimentos realizados e ainda não pagos</p>
      </div></div>
      <div class="card"><div class="card__body">${ui.skeletonLinhas(5)}</div></div>`;
  }

  function mountPendencias(params, alvo) {
    VC.shell.definirTitulo(t("pending.title"), "Cobranças em aberto");

    VC.services.financeiro.pendencias().then(function (lista) {
      var total = VC.domain.metrics.totalEmAberto(lista);
      var antigas = lista.filter(function (a) { return a.diasEmAberto > 30; });
      var podeBaixa = VC.session.pode("finance.write");

      var linhas = lista.map(function (a) {
        return html`
          <tr>
            <td class="cell-first">
              <a class="row" href="#/pacientes/${a.paciente.id}" style="gap:var(--sp-2)">
                ${ui.avatar(a.paciente.nome, "sm")}
                <span class="cell-main">${ui.nomeCliente(a.paciente.nome, true)}</span>
              </a>
            </td>
            <td data-label="${t("appointment.one")}" class="tabular">${fmt.diaMes(a.inicio)} · ${fmt.hora(a.inicio)}</td>
            <td data-label="Em aberto">
              <span class="badge ${a.diasEmAberto > 30 ? "badge--danger" : "badge--warn"}">${a.diasEmAberto} dias</span>
            </td>
            <td data-label="Situação">${ui.badgeAtendimento(a.status)}</td>
            <td data-label="Valor" class="num tabular"><b>${fmt.moeda(a.valor)}</b></td>
            <td class="num">${podeBaixa
              ? html`<div class="row" style="gap:6px;justify-content:flex-end;flex-wrap:wrap">
                  <button class="btn btn--accent btn--sm" type="button" data-acao="marcar-pago"
                          data-atendimento="${a.id}" data-valor="${a.valor}"
                          data-nome="${a.paciente.nome}">Dar baixa</button>
                  <button class="btn btn--quiet btn--sm" type="button" data-acao="isentar"
                          data-atendimento="${a.id}" data-nome="${a.paciente.nome}">Isentar</button>
                </div>`
              : html.vazio}</td>
          </tr>`;
      });

      VC.safe.render(alvo, html`
        <div class="page-head"><div class="page-head__title">
          <h1>${t("pending.title")}</h1>
          <p>${lista.length} ${t("appointment.many", true)} em aberto · ${fmt.moeda(total)}</p>
        </div></div>

        ${antigas.length ? html`
          <div class="notice notice--warn" style="margin-bottom:var(--sp-4)">
            <div><b>${antigas.length} cobrança(s) com mais de 30 dias.</b>
            Vale combinar a regularização antes do próximo ${t("appointment.one", true)}.</div>
          </div>` : html.vazio}

        <div class="card">
          <div class="card__body">${lista.length
            ? ui.tabela([{ rotulo: t("client.one") }, { rotulo: t("appointment.one") }, { rotulo: "Em aberto" },
                         { rotulo: "Situação" }, { rotulo: "Valor", num: true }, { rotulo: "" }], linhas)
            : ui.vazio({ titulo: "Nenhuma pendência", texto: "Todos os atendimentos realizados estão pagos." })}
          </div>
          ${lista.length ? html`<div class="card__foot">Total em aberto: <b>${fmt.moeda(total)}</b></div>` : html.vazio}
        </div>`);
    });
  }

  VC.views = VC.views || {};
  VC.views.financeiro = { render: render, mount: mount };
  VC.views.pendencias = { render: renderPendencias, mount: mountPendencias };
})(window);
