/* =============================================================
   ATENDIMENTOS — registro das sessões
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var html = VC.safe.html;
  var ui = VC.ui, fmt = VC.fmt, t = VC.terms.t;

  var filtros = { periodo: "30", status: "todos", modalidade: "todas", pagamento: "todos" };

  function intervalo() {
    var ate = new Date(); ate.setHours(23, 59, 59, 999);
    var de = new Date();
    if (filtros.periodo === "hoje") de.setHours(0, 0, 0, 0);
    else if (filtros.periodo === "7") de.setDate(de.getDate() - 7);
    else if (filtros.periodo === "30") de.setDate(de.getDate() - 30);
    else if (filtros.periodo === "futuros") { de = new Date(); ate.setDate(ate.getDate() + 60); }
    else de.setFullYear(de.getFullYear() - 5);
    de.setHours(0, 0, 0, 0);
    return { de: de, ate: ate };
  }

  function seletor(nome, rotulo, opcoes) {
    var itens = opcoes.map(function (o) {
      return html`<option value="${o[0]}" ${filtros[nome] === o[0] ? "selected" : ""}>${o[1]}</option>`;
    });
    return html`
      <div class="field">
        <label for="f-${nome}">${rotulo}</label>
        <select id="f-${nome}" data-filtro="${nome}">${html.juntar(itens)}</select>
      </div>`;
  }

  function cabecalho() {
    var podeFinanceiro = VC.session.pode("finance.read");
    return html`
      <div class="page-head">
        <div class="page-head__title">
          <h1>${t("appointment.many")}</h1>
          <p data-resumo-atendimentos>Carregando…</p>
        </div>
        <div class="page-head__actions">
          <button class="btn btn--accent" type="button" data-acao="novo-atendimento">Registrar ${t("appointment.one", true)}</button>
        </div>
      </div>

      <div class="filters">
        ${seletor("periodo", "Período", [["hoje", "Hoje"], ["7", "Últimos 7 dias"], ["30", "Últimos 30 dias"], ["futuros", "Próximos"], ["tudo", "Tudo"]])}
        ${seletor("status", "Situação", [["todos", "Todas"], ["agendado", "Agendado"], ["confirmado", "Confirmado"], ["realizado", "Realizado"], ["falta", "Falta"], ["cancelado", "Cancelado"]])}
        ${seletor("modalidade", "Modalidade", [["todas", "Todas"], ["presencial", "Presencial"], ["online", "Online"]])}
        ${podeFinanceiro ? seletor("pagamento", "Pagamento", [["todos", "Todos"], ["pago", "Pago"], ["pendente", "Pendente"], ["isento", "Isento"]]) : html.vazio}
      </div>

      <div class="card" data-lista-atendimentos><div class="card__body">${ui.skeletonLinhas(6)}</div></div>`;
  }

  function linha(a, podeFinanceiro) {
    return html`
      <tr>
        <td class="cell-first">
          <span class="cell-main tabular">${fmt.diaMes(a.inicio)} · ${fmt.hora(a.inicio)}</span>
          <span class="cell-sub" style="display:block">${fmt.dataRelativa(a.inicio)} · ${fmt.duracao(a.duracaoMin)}</span>
        </td>
        <td data-label="${t("client.one")}"><a href="#/pacientes/${a.paciente.id}">${ui.nomeCliente(a.paciente.nome, true)}</a></td>
        <td data-label="Modalidade">${ui.badgeModalidade(a.modalidade)}</td>
        <td data-label="Situação">${ui.badgeAtendimento(a.status)}</td>
        ${podeFinanceiro ? html`
          <td data-label="Pagamento">${ui.badgePagamento(a.pagamento)}</td>
          <td data-label="Valor" class="num tabular">${fmt.moeda(a.valor)}</td>` : html.vazio}
      </tr>`;
  }

  function carregar() {
    var alvo = VC.dom.el("[data-lista-atendimentos]");
    if (!alvo) return;
    VC.safe.render(alvo, html`<div class="card__body">${ui.skeletonLinhas(6)}</div>`);

    var i = intervalo();
    VC.services.atendimentos.listar({
      de: i.de, ate: i.ate,
      status: filtros.status,
      modalidade: filtros.modalidade,
      pagamento: filtros.pagamento
    }).then(function (lista) {
      var c = VC.domain.metrics.contagens(lista);
      VC.safe.texto(VC.dom.el("[data-resumo-atendimentos]"),
        lista.length + " registro(s) · " + c.realizados + " realizado(s) · " + c.faltas + " falta(s)");

      if (!lista.length) {
        VC.safe.render(alvo, html`<div class="card__body">${ui.vazio({
          titulo: "Nenhum registro no filtro",
          texto: "Ajuste o período ou a situação para ver outros registros."
        })}</div>`);
        return;
      }

      var podeFinanceiro = VC.session.pode("finance.read");
      var colunas = [{ rotulo: "Quando" }, { rotulo: t("client.one") }, { rotulo: "Modalidade" }, { rotulo: "Situação" }];
      if (podeFinanceiro) colunas.push({ rotulo: "Pagamento" }, { rotulo: "Valor", num: true });

      VC.safe.render(alvo, ui.tabela(colunas, lista.slice().reverse().map(function (a) {
        return linha(a, podeFinanceiro);
      })));
    });
  }

  function render() { return cabecalho(); }

  function mount(params, alvo) {
    VC.shell.definirTitulo(t("appointment.many"), "Histórico e registro de sessões");
    VC.dom.on(alvo, "change", "[data-filtro]", function (e, campo) {
      filtros[campo.getAttribute("data-filtro")] = campo.value;
      carregar();
    });
    carregar();
  }

  VC.views = VC.views || {};
  VC.views.atendimentos = { render: render, mount: mount };
})(window);
