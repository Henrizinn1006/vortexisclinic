/* =============================================================
   Componentes de interface. Todos devolvem SafeHtml (html``):
   qualquer dado interpolado é escapado automaticamente.
   Nenhum rótulo de domínio aparece aqui como texto fixo — vem de
   core/terms.js.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var html = VC.safe.html;
  var fmt = VC.fmt;

  /* ---------- Vocabulário de estados ---------- */
  var STATUS_ATENDIMENTO = {
    agendado:   { rotulo: "Agendado",   classe: "badge--neutral" },
    confirmado: { rotulo: "Confirmado", classe: "badge--info" },
    realizado:  { rotulo: "Realizado",  classe: "badge--ok" },
    falta:      { rotulo: "Falta",      classe: "badge--danger" },
    cancelado:  { rotulo: "Cancelado",  classe: "badge--neutral" }
  };
  var STATUS_PAGAMENTO = {
    pago:     { rotulo: "Pago",     classe: "badge--ok" },
    pendente: { rotulo: "Pendente", classe: "badge--warn" },
    isento:   { rotulo: "Isento",   classe: "badge--neutral" }
  };
  var MODALIDADE = {
    presencial: { rotulo: "Presencial", classe: "badge--neutral" },
    online:     { rotulo: "Online",     classe: "badge--info" }
  };

  function badge(mapa, chave) {
    var d = mapa[chave] || { rotulo: chave || "—", classe: "badge--neutral" };
    return html`<span class="badge ${d.classe}">${d.rotulo}</span>`;
  }

  function rotuloDe(mapa, chave) {
    return (mapa[chave] || {}).rotulo || chave || "—";
  }

  /* ---------- Blocos ---------- */
  function avatar(nome, tamanho) {
    var classe = "avatar" + (tamanho ? " avatar--" + tamanho : "");
    return html`<span class="${classe}" aria-hidden="true">${fmt.iniciais(nome)}</span>`;
  }

  /* Nome de pessoa atendida: encurtado por padrão e sujeito ao modo discreto. */
  function nomeCliente(nome, completo) {
    return html`<span class="private">${completo ? nome : fmt.nomeCurto(nome)}</span>`;
  }

  function stat(opcoes) {
    var o = opcoes || {};
    var tendencia = html.vazio;
    if (o.tendencia !== null && o.tendencia !== undefined && !isNaN(o.tendencia)) {
      var up = o.tendencia >= 0;
      tendencia = html`<span class="stat__trend stat__trend--${up ? "up" : "down"}">
        ${up ? "▲" : "▼"} ${Math.abs(o.tendencia)}% vs. mês anterior</span>`;
    }
    var classe = "card stat" + (o.tom ? " stat--" + o.tom : "") + (o.href ? " card--link" : "");
    var corpo = html`
      <span class="stat__label">${o.rotulo}</span>
      <span class="stat__value">${o.valor === undefined ? "—" : o.valor}</span>
      ${o.dica ? html`<span class="stat__hint">${o.dica}</span>` : html.vazio}
      ${tendencia}`;

    return o.href
      ? html`<a class="${classe}" href="${o.href}">${corpo}</a>`
      : html`<div class="${classe}">${corpo}</div>`;
  }

  function vazio(opcoes) {
    var o = opcoes || {};
    return html`
      <div class="empty">
        <span class="empty__art" aria-hidden="true"></span>
        <h3>${o.titulo || "Nada por aqui ainda"}</h3>
        <p>${o.texto || ""}</p>
        ${o.acao ? html`<a class="btn btn--accent btn--sm" href="${o.acao.href}">${o.acao.rotulo}</a>` : html.vazio}
      </div>`;
  }

  function skeletonLinhas(quantidade) {
    var out = [];
    for (var i = 0; i < (quantidade || 4); i++) out.push(html`<div class="skel skel--row"></div>`);
    return html.juntar(out);
  }

  function skeletonStats(quantidade) {
    var out = [];
    for (var i = 0; i < (quantidade || 4); i++) out.push(html`<div class="skel skel--stat"></div>`);
    return html`<div class="grid grid--4">${html.juntar(out)}</div>`;
  }

  function cabecalhoPagina(titulo, subtitulo, acoes) {
    return html`
      <div class="page-head">
        <div class="page-head__title"><h1>${titulo}</h1><p>${subtitulo || ""}</p></div>
        ${acoes ? html`<div class="page-head__actions">${acoes}</div>` : html.vazio}
      </div>`;
  }

  function botao(opcoes) {
    var o = opcoes || {};
    var classe = "btn btn--" + (o.variante || "ghost") + (o.pequeno ? " btn--sm" : "") + (o.bloco ? " btn--block" : "");
    if (o.href) return html`<a class="${classe}" href="${o.href}">${o.rotulo}</a>`;
    return html`<button class="${classe}" type="button" data-acao="${o.acao || ""}"
      ${o.recurso ? html`data-recurso="${o.recurso}"` : html.vazio}>${o.rotulo}</button>`;
  }

  /* Botões de situação do atendimento.

     Só aparecem os destinos possíveis a partir do estado atual —
     a mesma máquina de estados do servidor, que é quem recusa de
     verdade. Aqui é para não oferecer o impossível. */
  var DESTINOS = {
    agendado:   [["confirmado", "Confirmar"], ["realizado", "Realizado"], ["falta", "Falta"]],
    confirmado: [["realizado", "Realizado"], ["falta", "Falta"]],
    realizado:  [["falta", "Corrigir para falta"]],
    falta:      [["realizado", "Corrigir para realizado"]],
    cancelado:  []
  };

  function acoesDeStatus(a) {
    if (!VC.session.pode("appointments.write")) return html.vazio;

    var botoes = (DESTINOS[a.status] || []).map(function (d) {
      return html`<button class="btn btn--quiet btn--sm" type="button"
                    data-atendimento="${a.id}" data-status-para="${d[0]}">${d[1]}</button>`;
    });

    if (a.status !== "cancelado" && VC.session.pode("appointments.cancel")) {
      botoes.push(html`<button class="btn btn--quiet btn--sm" type="button"
                         data-atendimento="${a.id}" data-status-para="cancelado">Cancelar</button>`);
    }
    if (!botoes.length) return html.vazio;
    return html`<div class="row" style="gap:6px;flex-wrap:wrap">${html.juntar(botoes)}</div>`;
  }

  /* Linha de atendimento — usada no início, na agenda e na ficha. */
  function linhaAtendimento(a, opcoes) {
    var o = opcoes || {};
    var inicio = new Date(a.inicio);
    var agora = new Date();
    var emAndamento = agora >= inicio && agora <= new Date(inicio.getTime() + a.duracaoMin * 60000);

    return html`
      <div class="slot${emAndamento ? " slot--now" : ""}">
        <div class="slot__time">
          <b>${fmt.hora(a.inicio)}</b>
          <span>${o.mostrarDia ? fmt.dataRelativa(a.inicio) : fmt.duracao(a.duracaoMin)}</span>
        </div>
        <div class="slot__who">
          ${avatar(a.paciente.nome, "sm")}
          <div class="grow">
            <div class="name">${nomeCliente(a.paciente.nome)}</div>
            <div class="meta">${rotuloDe(MODALIDADE, a.modalidade)}${o.mostrarValor ? " · " + fmt.moeda(a.valor) : ""}</div>
          </div>
        </div>
        <div class="slot__side">
          ${o.mostrarPagamento ? badge(STATUS_PAGAMENTO, a.pagamento) : html.vazio}
          ${badge(STATUS_ATENDIMENTO, a.status)}
          ${o.comAcoes ? acoesDeStatus(a) : html.vazio}
        </div>
      </div>`;
  }

  /* Gráfico de barras simples (sem biblioteca). */
  function barras(itens, opcoes) {
    var o = opcoes || {};
    var maior = Math.max.apply(null, itens.map(function (i) { return i.valor; }).concat([1]));
    var colunas = itens.map(function (i) {
      var altura = Math.max(Math.round((i.valor / maior) * 100), i.valor ? 6 : 2);
      return html`
        <div class="bars__col${i.destaque ? " is-today" : ""}" title="${i.titulo || ""}">
          <div class="bars__bar" style="height:${altura}%"></div>
          <span class="bars__label">${i.rotulo}</span>
        </div>`;
    });
    return html`<div class="bars" role="img" aria-label="${o.descricao || "Gráfico de barras"}">${html.juntar(colunas)}</div>`;
  }

  /* Tabela: cabeçalhos e células já chegam seguros. */
  function tabela(colunas, linhas) {
    if (!linhas.length) return html.vazio;
    var cabecalho = colunas.map(function (c) {
      return html`<th class="${c.num ? "num" : ""}">${c.rotulo}</th>`;
    });
    return html`
      <div class="table-wrap">
        <table class="table table--stack">
          <thead><tr>${html.juntar(cabecalho)}</tr></thead>
          <tbody>${html.juntar(linhas)}</tbody>
        </table>
      </div>`;
  }

  VC.ui = {
    STATUS_ATENDIMENTO: STATUS_ATENDIMENTO,
    STATUS_PAGAMENTO: STATUS_PAGAMENTO,
    MODALIDADE: MODALIDADE,
    badge: badge,
    rotuloDe: rotuloDe,
    acoesDeStatus: acoesDeStatus,
    badgeAtendimento: function (s) { return badge(STATUS_ATENDIMENTO, s); },
    badgePagamento: function (s) { return badge(STATUS_PAGAMENTO, s); },
    badgeModalidade: function (s) { return badge(MODALIDADE, s); },
    avatar: avatar,
    nomeCliente: nomeCliente,
    nomePaciente: nomeCliente,       // nome antigo, mantido enquanto as views migram
    stat: stat,
    vazio: vazio,
    skeletonLinhas: skeletonLinhas,
    skeletonStats: skeletonStats,
    cabecalhoPagina: cabecalhoPagina,
    botao: botao,
    linhaAtendimento: linhaAtendimento,
    barras: barras,
    tabela: tabela
  };
})(window);
