/* =============================================================
   PRIVACIDADE — pedidos do titular, retenção e auditoria.

   Três blocos numa tela só porque respondem às três perguntas que
   um titular (ou a ANPD) faz na mesma conversa:

     "o que vocês fizeram com o meu pedido?"  → pedidos
     "por quanto tempo isso fica?"            → retenção
     "quem mexeu nos meus dados?"             → auditoria

   Duas coisas que a tela precisa deixar visíveis:

   1. **Decidir e executar são passos separados.** A decisão aparece
      como plano até alguém clicar em "Executar" — e aí não tem volta.
   2. **Retenção sem prazo é o estado normal**, não um erro. A tela
      diz isso em vez de mostrar um vazio que parece configuração
      faltando.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var html = VC.safe.html;
  var ui = VC.ui, fmt = VC.fmt;

  var aba = "pedidos";

  var ALVOS = [
    { valor: "registration", rotulo: "Cadastro" },
    { valor: "appointments", rotulo: "Atendimentos" },
    { valor: "payments", rotulo: "Financeiro" },
    { valor: "clinical", rotulo: "Prontuário" },
    { valor: "documents", rotulo: "Documentos" },
    { valor: "other", rotulo: "Outros" }
  ];

  /* ---------------- pedidos ---------------- */
  function badgeDoPedido(p) {
    if (p.status === "done") return html`<span class="badge badge--ok">concluído</span>`;
    if (p.status === "refused") return html`<span class="badge badge--danger">recusado</span>`;
    if (p.status === "in_progress") return html`<span class="badge badge--warn">em andamento</span>`;
    return html`<span class="badge badge--info">aberto</span>`;
  }

  function linhaDeDecisao(p, d) {
    return html`
      <div class="row" style="justify-content:space-between;align-items:flex-start;
                  gap:var(--sp-3);padding:var(--sp-2) 0;border-top:1px solid var(--border)">
        <div>
          <div class="cell-main">${d.alvoRotulo} → ${d.decisaoRotulo}</div>
          <div class="cell-sub">${d.motivo}${d.baseLegal ? " · base: " + d.baseLegal : ""}</div>
          ${d.aplicada
            ? html`<div class="cell-sub">executado em ${fmt.dataLonga(d.aplicadoEm)}${
                d.resultado ? " — " + d.resultado : ""}</div>`
            : html`<div class="cell-sub" style="color:var(--warn)">ainda não executado</div>`}
        </div>
        ${d.aplicada || p.encerrado ? html.vazio : html`
          <button class="btn btn--ghost btn--sm" type="button" data-acao="aplicar-decisao"
                  data-pedido="${p.id}" data-decisao="${d.id}"
                  data-rotulo="${d.alvoRotulo + " → " + d.decisaoRotulo}">Executar</button>`}
      </div>`;
  }

  function cartaoDePedido(p) {
    return html`
      <div class="card" style="margin-bottom:var(--sp-3)">
        <div class="card__body">
          <div class="row" style="justify-content:space-between;align-items:flex-start;gap:var(--sp-3)">
            <div>
              <div class="cell-main">${p.tipoRotulo}${p.paciente
                ? " · " + ui.nomeCliente(p.paciente.nome, true) : ""}</div>
              <div class="cell-sub">pedido em ${fmt.dataLonga(p.pedidoEm)} por ${p.solicitante}${
                p.prazo ? " · prazo " + fmt.dataLonga(p.prazo) : " · sem prazo definido"}</div>
            </div>
            <div class="row" style="gap:var(--sp-2)">
              ${badgeDoPedido(p)}
              ${p.encerrado ? html.vazio : html`
                <button class="btn btn--ghost btn--sm" type="button" data-acao="decidir"
                        data-pedido="${p.id}">Decidir</button>
                <button class="btn btn--quiet btn--sm" type="button" data-acao="encerrar-pedido"
                        data-pedido="${p.id}">Encerrar</button>`}
            </div>
          </div>

          ${p.observacao ? html`<div class="cell-sub" style="margin-top:var(--sp-2)">
            “${p.observacao}”</div>` : html.vazio}

          <div style="margin-top:var(--sp-3)">
            ${p.decisoes.length
              ? html.juntar(p.decisoes.map(function (d) { return linhaDeDecisao(p, d); }))
              : html`<div class="cell-sub">Nenhuma decisão registrada ainda.</div>`}
          </div>

          ${p.desfecho ? html`<div class="notice" style="margin-top:var(--sp-3)">
            <div><b>Desfecho:</b> ${p.desfecho}</div></div>` : html.vazio}
        </div>
      </div>`;
  }

  /* ---------------- retenção ---------------- */
  function linhaDePolitica(p) {
    return html`
      <tr>
        <td class="cell-first"><span class="cell-main">${p.alvoRotulo}</span></td>
        <td data-label="Profissão">${p.profissao || html`<span class="soft">todas</span>`}</td>
        <td data-label="Prazo">${p.meses
          ? html`<span class="tabular">${p.meses} meses</span>`
          : html`<span class="soft">sem prazo definido</span>`}</td>
        <td data-label="Base legal">${p.baseLegal || html`<span class="soft">—</span>`}</td>
        <td data-label="Vale?">${p.aplicavel
          ? html`<span class="badge badge--ok">aplicável</span>`
          : html`<span class="badge badge--neutral">não decide nada</span>`}</td>
      </tr>`;
  }

  /* ---------------- render ---------------- */
  function conteudo() {
    if (aba === "retencao") {
      return html`
        <div class="notice">
          <div><b>Nada é apagado automaticamente.</b> O prazo de guarda depende do conselho
          profissional de cada categoria — inventar um número daria aparência de conformidade
          a um chute. Enquanto não houver política com base legal escrita, a ausência fica
          visível aqui, e não vira um padrão silencioso.</div>
        </div>
        <div class="row" style="justify-content:flex-end;margin:var(--sp-4) 0">
          <button class="btn btn--accent btn--sm" type="button" data-acao="definir-politica">
            Definir política</button>
        </div>
        <div class="card"><div class="card__body" data-lista-privacidade>
          ${ui.skeletonLinhas(3)}</div></div>`;
    }

    if (aba === "auditoria") {
      return html`
        <div class="notice">
          <div>A trilha registra <b>o ato</b>, nunca o conteúdo. Ver quem mexeu não exige —
          nem concede — acesso ao que foi escrito.</div>
        </div>
        <div class="card" style="margin-top:var(--sp-4)">
          <div class="card__body" data-lista-privacidade>${ui.skeletonLinhas(5)}</div></div>`;
    }

    return html`
      <div class="notice">
        <div><b>Exclusão não é DELETE.</b> Um pedido vira decisões por tipo de dado — e cada
        uma precisa de motivo, inclusive quando a decisão é <b>manter</b>. Registrar a decisão
        não executa nada: executar é um segundo clique, e não tem volta.</div>
      </div>
      <div data-lista-privacidade style="margin-top:var(--sp-4)">${ui.skeletonLinhas(4)}</div>`;
  }

  function pintarPedidos(lista) {
    var alvo = VC.dom.el("[data-lista-privacidade]");
    if (!alvo) return;
    if (!lista.length) {
      VC.safe.render(alvo, ui.vazio({
        titulo: "Nenhum pedido registrado",
        texto: "Pedidos do titular são abertos pela ficha da pessoa, na aba Privacidade."
      }));
      return;
    }
    VC.safe.render(alvo, html.juntar(lista.map(cartaoDePedido)));
  }

  function pintarPoliticas(lista) {
    var alvo = VC.dom.el("[data-lista-privacidade]");
    if (!alvo) return;
    if (!lista.length) {
      VC.safe.render(alvo, ui.vazio({
        titulo: "Nenhuma política definida",
        texto: "É o estado esperado até alguém checar o prazo do conselho da categoria."
      }));
      return;
    }
    VC.safe.render(alvo, ui.tabela(
      [{ rotulo: "O quê" }, { rotulo: "Profissão" }, { rotulo: "Prazo" },
       { rotulo: "Base legal" }, { rotulo: "Vale?" }],
      lista.map(linhaDePolitica)));
  }

  function pintarAuditoria(lista) {
    var alvo = VC.dom.el("[data-lista-privacidade]");
    if (!alvo) return;
    if (!lista.length) {
      VC.safe.render(alvo, ui.vazio({ titulo: "Nada registrado ainda", texto: "" }));
      return;
    }
    VC.safe.render(alvo, html`<div class="slot-list">${html.juntar(lista.map(function (e) {
      return html`
        <div class="slot" style="grid-template-columns:1fr auto">
          <div>
            <div class="name">${e.quem || "—"} · ${e.acao}</div>
            <div class="meta">${fmt.dataLonga(e.quando)} · ${fmt.hora(e.quando)}${
              e.detalhe ? " · " + e.detalhe : ""}</div>
          </div>
          <div class="slot__side">${e.permitido
            ? html`<span class="badge badge--ok">ok</span>`
            : html`<span class="badge badge--danger">recusado</span>`}</div>
        </div>`;
    }))}</div>`);
  }

  function carregar() {
    if (aba === "retencao") {
      VC.services.privacidade.politicas().then(pintarPoliticas, function () {});
      return;
    }
    if (aba === "auditoria") {
      VC.services.privacidade.auditoria().then(pintarAuditoria, function () {});
      return;
    }
    VC.services.privacidade.pedidos().then(pintarPedidos, function () {});
  }

  function render() {
    var abas = [
      { id: "pedidos", rotulo: "Pedidos do titular" },
      { id: "retencao", rotulo: "Retenção" },
      { id: "auditoria", rotulo: "Auditoria" }
    ].map(function (a) {
      return html`<button class="tab" role="tab" aria-selected="${a.id === aba}"
                    data-aba-privacidade="${a.id}">${a.rotulo}</button>`;
    });

    return html`
      <div class="page-head">
        <div class="page-head__title">
          <h1>Privacidade</h1>
          <p>Direitos do titular, retenção e trilha de auditoria</p>
        </div>
      </div>
      <div class="tabs" role="tablist">${html.juntar(abas)}</div>
      <div data-painel-privacidade>${conteudo()}</div>`;
  }

  function mount(params, alvo) {
    VC.shell.definirTitulo("Privacidade", "Direitos do titular e auditoria");
    carregar();

    VC.dom.on(alvo, "click", "[data-aba-privacidade]", function (e, botao) {
      aba = botao.getAttribute("data-aba-privacidade");
      VC.dom.els("[data-aba-privacidade]", alvo).forEach(function (b) {
        b.setAttribute("aria-selected", String(b === botao));
      });
      VC.safe.render(VC.dom.el("[data-painel-privacidade]", alvo), conteudo());
      carregar();
    });
  }

  VC.views = VC.views || {};
  VC.views.privacidade = { render: render, mount: mount, recarregar: carregar, ALVOS: ALVOS };
})(window);
