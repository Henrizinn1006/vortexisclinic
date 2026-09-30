/* =============================================================
   EQUIPE — quem está na conta, e quem foi convidado.

   A tela mostra o acesso de cada pessoa em português claro, porque
   é isso que evita erro: "toda a conta" e "só os seus" dizem o que
   `data_scope` significa sem exigir que alguém decore a palavra.

   O link do convite aparece uma vez, logo depois de criar, com um
   botão de copiar. Ele não volta em listagem nenhuma — o servidor
   guarda só o hash do token. Quando o envio de e-mail existir, o
   link passa a ir direto para a pessoa e some daqui.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var html = VC.safe.html;
  var ui = VC.ui, fmt = VC.fmt;

  var PAPEIS = [
    { valor: "PROFESSIONAL", rotulo: "Profissional — atende e escreve prontuário" },
    { valor: "ASSISTANT", rotulo: "Apoio administrativo — agenda e financeiro, nunca prontuário" },
    { valor: "OWNER", rotulo: "Dono da conta — administra tudo, menos prontuário alheio" }
  ];

  function papeisDisponiveis() {
    /* Só dono cria dono. O servidor recusa de qualquer jeito; tirar
       da lista evita oferecer o que vai dar 403. */
    var meuPapel = (VC.session.membership() || {}).papel;
    return PAPEIS.filter(function (p) { return p.valor !== "OWNER" || meuPapel === "OWNER"; });
  }

  function badgeDoStatus(m) {
    if (!m.ativo) return html`<span class="badge badge--neutral">${m.statusRotulo}</span>`;
    return html`<span class="badge badge--ok">ativo</span>`;
  }

  function linhaDeMembro(m) {
    return html`
      <tr>
        <td class="cell-first">
          <div class="row" style="gap:var(--sp-3)">
            ${ui.avatar(m.nome, "sm")}
            <span>
              <span class="cell-main">${m.nome}${m.souEu ? " (você)" : ""}</span>
              <span class="cell-sub" style="display:block">${m.email}</span>
            </span>
          </div>
        </td>
        <td data-label="Papel">${m.papelRotulo}</td>
        <td data-label="Enxerga">${m.escopoRotulo}</td>
        <td data-label="Prontuário">${m.atende
          ? html`<span class="badge badge--info">atende</span>`
          : html`<span class="soft">não atende</span>`}</td>
        <td data-label="Situação">${badgeDoStatus(m)}</td>
        <td data-label="" class="num">${m.souEu
          ? html`<span class="soft" title="Mudança no seu próprio acesso passa por outra pessoa">—</span>`
          : html`
            <button class="btn btn--ghost btn--sm" type="button" data-acao="editar-membro"
                    data-membro="${m.id}" data-nome="${m.nome}" data-papel="${m.papel}"
                    data-escopo="${m.escopo}" data-status="${m.status}">Acesso</button>`}
        </td>
      </tr>`;
  }

  function linhaDeConvite(c) {
    return html`
      <div class="slot" style="grid-template-columns:1fr auto">
        <div>
          <div class="name">${c.email}</div>
          <div class="meta">${c.papelRotulo}${c.profissao ? " · atende" : ""} ·
            expira ${fmt.dataRelativa(c.expiraEm)}${
            c.convidadoPor ? " · convidado por " + c.convidadoPor : ""}</div>
        </div>
        <div class="slot__side">
          <button class="btn btn--quiet btn--sm" type="button" data-acao="revogar-convite"
                  data-convite="${c.id}" data-email="${c.email}">Revogar</button>
        </div>
      </div>`;
  }

  function corpo(dados) {
    var colunas = [
      { rotulo: "Pessoa" }, { rotulo: "Papel" }, { rotulo: "Enxerga" },
      { rotulo: "Prontuário" }, { rotulo: "Situação" }, { rotulo: "" }
    ];
    return html`
      <div class="card" style="margin-bottom:var(--sp-5)">
        <div class="card__body">
          ${ui.tabela(colunas, dados.membros.map(linhaDeMembro))}
        </div>
      </div>

      <h2 style="font-size:var(--fs-base);margin-bottom:var(--sp-3)">Convites abertos</h2>
      ${dados.convites.length
        ? html`<div class="slot-list">${html.juntar(dados.convites.map(linhaDeConvite))}</div>`
        : ui.vazio({
            titulo: "Nenhum convite aberto",
            texto: "Convites expiram em 7 dias. Quem não aceitar a tempo precisa de um novo."
          })}`;
  }

  function carregar() {
    VC.services.equipe.listar().then(function (dados) {
      VC.safe.render(VC.dom.el("[data-equipe]"), corpo(dados));
    }, function () {
      VC.safe.render(VC.dom.el("[data-equipe]"), ui.vazio({
        titulo: "Não foi possível carregar", texto: "Tente novamente em instantes."
      }));
    });
  }

  function render() {
    return html`
      <div class="page-head">
        <div class="page-head__title">
          <h1>Equipe</h1>
          <p>Quem entra na conta, com qual papel e enxergando o quê</p>
        </div>
        <div class="page-head__actions">
          <button class="btn btn--accent" type="button" data-acao="convidar">Convidar pessoa</button>
        </div>
      </div>

      <div class="notice" style="margin-bottom:var(--sp-4)">
        <div><b>Papel administrativo não abre prontuário.</b> Quem administra a conta
        gerencia agenda, cadastro e financeiro. Ler registro clínico depende de atender —
        e, mesmo assim, só o que é seu.</div>
      </div>

      <div data-equipe>${ui.skeletonLinhas(4)}</div>`;
  }

  function mount(params, alvo) {
    VC.shell.definirTitulo("Equipe", "Pessoas com acesso a esta conta");
    carregar();
  }

  VC.views = VC.views || {};
  VC.views.equipe = { render: render, mount: mount, recarregar: carregar };
  VC.views.equipe.papeis = papeisDisponiveis;
})(window);
