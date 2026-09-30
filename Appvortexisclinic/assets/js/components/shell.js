/* =============================================================
   Estrutura fixa do painel: sidebar, topo, barra inferior e o
   seletor de workspace (quando o usuário tem mais de um vínculo).

   Nada aqui escreve rótulo de domínio: os nomes vêm de terms, e
   os itens que a pessoa não pode acessar não são desenhados.
   Esconder é conforto — quem nega o dado é o servidor.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var html = VC.safe.html;
  var render = VC.safe.render;
  var t = VC.terms.t;

  function rotuloDe(item) { return item.termo ? t(item.termo) : item.rotulo; }
  function rotuloCurto(item) { return item.curtoTermo ? t(item.curtoTermo) : (item.curto || rotuloDe(item)); }

  /* Itens que a membership atual alcança. */
  function itensVisiveis() {
    return VC.config.navegacao.map(function (grupo) {
      return {
        titulo: grupo.titulo,
        itens: grupo.itens.filter(function (i) { return !i.permissao || VC.session.pode(i.permissao); })
      };
    }).filter(function (g) { return g.itens.length; });
  }

  function todosItens() {
    return itensVisiveis().reduce(function (acc, g) { return acc.concat(g.itens); }, []);
  }

  /* ---------------- Sidebar / gaveta ---------------- */
  function sidebarHTML() {
    var prof = VC.session.atual();
    var tenant = VC.session.tenant();
    var espacos = VC.session.workspaces();

    var grupos = itensVisiveis().map(function (grupo) {
      var itens = grupo.itens.map(function (i) {
        return html`
          <a class="nav-item" href="#${i.rota}" data-nav="${i.id}">
            <span>${rotuloDe(i)}</span>
            ${i.contador
              ? html`<span class="nav-item__count hide" data-contador="${i.contador}"></span>`
              : html.vazio}
          </a>`;
      });
      return html`<div class="nav-group"><p class="nav-group__title">${grupo.titulo}</p>${html.juntar(itens)}</div>`;
    });

    /* O bloco do topo identifica a CONTA, não a pessoa: é ele que
       responde "onde eu estou" quando alguém atende em mais de um
       lugar. O nome de quem entrou fica embaixo, junto do papel. */
    var nomeConta = tenant ? tenant.nome : "—";
    var papelConta = tenant ? (tenant.papelNome || tenant.papel) : "";
    var legenda = papelConta ? papelConta + " · " + prof.nome : prof.nome;

    var seletor = espacos.length > 1
      ? html`
        <button class="sidebar__tenant sidebar__tenant--switch" type="button" data-acao="trocar-workspace"
                aria-haspopup="dialog" title="Trocar de conta">
          <span class="avatar avatar--dark" aria-hidden="true">${VC.fmt.iniciais(nomeConta)}</span>
          <span class="grow" style="text-align:left">
            <b>${nomeConta}</b>
            <span>${legenda} · trocar</span>
          </span>
          <span aria-hidden="true">⌄</span>
        </button>`
      : html`
        <div class="sidebar__tenant">
          <span class="avatar avatar--dark" aria-hidden="true">${VC.fmt.iniciais(nomeConta)}</span>
          <div><b>${nomeConta}</b><span>${legenda}</span></div>
        </div>`;

    return html`
      <div class="sidebar__brand">
        <img class="brand-mark" src="assets/images/simbolo-claro.png" alt="" width="256" height="247">
        <img class="brand-text" src="assets/images/marca-texto-branco.png" alt="Vortexis Clinic" width="639" height="110">
      </div>
      ${seletor}
      <nav class="sidebar__nav" aria-label="Seções do painel">${html.juntar(grupos)}</nav>
      <div class="sidebar__foot">
        <span>${VC.config.produto}</span>
        <span>Versão ${VC.config.versao}</span>
      </div>`;
  }

  /* ---------------- Topo ---------------- */
  function topbarHTML() {
    return html`
      <button class="menu-toggle" type="button" aria-label="Abrir menu" aria-expanded="false" data-acao="menu"><span></span></button>
      <div class="topbar__title"><b data-titulo>Início</b><span data-subtitulo></span></div>
      <div class="search">
        <label class="sr-only" for="busca-global">${t("client.search")}</label>
        <input id="busca-global" type="search" placeholder="${t("client.search")}…" autocomplete="off" data-busca-global>
      </div>
      <div class="topbar__actions">
        <button class="btn btn--ghost btn--sm" type="button" data-acao="privacidade" aria-pressed="false"
                title="Oculta os nomes na tela, para atender com alguém por perto">Modo discreto</button>
        <a class="btn btn--accent btn--sm" href="#/agenda" data-acao="novo-atendimento">${t("appointment.new")}</a>
      </div>`;
  }

  /* ---------------- Barra inferior (celular) ---------------- */
  function bottomnavHTML() {
    var lista = todosItens().filter(function (i) { return i.mobile; }).slice(0, 4);
    var links = lista.map(function (i) {
      return html`<a href="#${i.rota}" data-nav-mobile="${i.id}">${rotuloCurto(i)}${
        i.id === "financeiro" ? html`<span class="badge-dot hide" data-ponto-pendencia></span>` : html.vazio
      }</a>`;
    });
    return html`${html.juntar(links)}<a href="#" data-acao="menu">Menu</a>`;
  }

  /* ---------------- Estado ativo ---------------- */
  function marcarAtivo(caminho) {
    var idAtivo = null;
    todosItens().forEach(function (i) {
      var ativo = i.rota === "/" ? caminho === "/" : (caminho === i.rota || caminho.indexOf(i.rota + "/") === 0);
      if (ativo) idAtivo = i.id;
      VC.dom.els('[data-nav="' + i.id + '"], [data-nav-mobile="' + i.id + '"]').forEach(function (el) {
        if (ativo) el.setAttribute("aria-current", "page");
        else el.removeAttribute("aria-current");
      });
    });
    return idAtivo;
  }

  function definirTitulo(titulo, subtitulo) {
    VC.safe.texto(VC.dom.el("[data-titulo]"), titulo);
    VC.safe.texto(VC.dom.el("[data-subtitulo]"), subtitulo || "");
    document.title = titulo + " · " + VC.config.produto;
  }

  /* ---------------- Menu mobile ---------------- */
  function alternarMenu(forcar) {
    var sidebar = VC.dom.el(".sidebar");
    var scrim = VC.dom.el(".scrim");
    var botao = VC.dom.el('[data-acao="menu"]');
    var abrir = forcar !== undefined ? forcar : !sidebar.classList.contains("is-open");
    sidebar.classList.toggle("is-open", abrir);
    scrim.classList.toggle("is-open", abrir);
    if (botao) botao.setAttribute("aria-expanded", String(abrir));
    document.body.style.overflow = abrir ? "hidden" : "";
  }

  /* ---------------- Modo discreto ---------------- */
  function aplicarPrivacidade(ligado) {
    document.documentElement.setAttribute("data-privacy", ligado ? "on" : "off");
    var botao = VC.dom.el('[data-acao="privacidade"]');
    if (botao) {
      botao.setAttribute("aria-pressed", String(ligado));
      botao.textContent = ligado ? "Modo discreto ativo" : "Modo discreto";
      botao.classList.toggle("btn--accent", ligado);
      botao.classList.toggle("btn--ghost", !ligado);
    }
  }

  /* ---------------- Contadores ---------------- */
  function atualizarContadores() {
    if (!VC.session.pode("finance.read")) return;
    VC.services.financeiro.pendencias().then(function (lista) {
      VC.dom.els("[data-contador='pendencias']").forEach(function (el) {
        el.textContent = String(lista.length);
        el.classList.toggle("hide", !lista.length);
        el.classList.toggle("nav-item__count--alert", lista.length > 4);
      });
      VC.dom.els("[data-ponto-pendencia]").forEach(function (el) {
        el.classList.toggle("hide", !lista.length);
      });
    }).catch(function () { /* sem tenant válido: nada a contar */ });
  }

  /* ---------------- Seleção de workspace ---------------- */
  function abrirSeletorWorkspace() {
    var espacos = VC.session.workspaces();
    var opcoes = espacos.map(function (w) {
      return html`
        <button class="workspace" type="button" data-trocar-para="${w.tenantId}" ${w.ativo ? "aria-current=\"true\"" : ""}>
          <span class="avatar" aria-hidden="true">${VC.fmt.iniciais(w.nome)}</span>
          <span class="grow" style="text-align:left">
            <b>${w.nome}</b>
            <span class="muted" style="display:block;font-size:var(--fs-xs)">${w.papel}${w.ativo ? " · em uso" : ""}</span>
          </span>
        </button>`;
    });

    VC.modal.abrir({
      titulo: "Trocar de conta",
      subtitulo: "Cada conta tem seus próprios pacientes, agenda e financeiro. Nada é compartilhado entre elas.",
      corpo: html`<div class="workspace-list">${html.juntar(opcoes)}</div>`,
      cancelar: "Fechar"
    });
  }

  function trocarWorkspace(tenantId) {
    VC.session.trocarTenant(tenantId).then(function (tenant) {
      VC.modal.fechar();
      montar();
      VC.router.resolver();
      VC.toast.ok("Conta ativa: " + tenant.nome, "Os dados desta tela agora são desta conta.");
    }).catch(function () {
      /* mesma resposta do servidor para tenant sem vínculo */
      VC.modal.fechar();
      VC.toast.erro("Conta não encontrada", "Seu usuário não tem vínculo ativo com essa conta.");
    });
  }

  var ligado = false;

  /* E-mail não confirmado: um aviso discreto e permanente, com o botão
     de reenviar ali mesmo. Não bloqueia o uso — bloquear o trabalho de
     alguém porque um e-mail não chegou é punir a pessoa errada. */
  function avisarEmailNaoVerificado() {
    var alvo = VC.dom.el("[data-aviso-email]");
    var usuario = VC.session.usuario();
    if (!alvo) return;
    if (!usuario || usuario.emailVerificado) {
      VC.safe.render(alvo, VC.safe.html.vazio);
      return;
    }
    VC.safe.render(alvo, VC.safe.html`
      <div class="notice" style="margin:0 0 var(--sp-4)">
        <div class="row" style="justify-content:space-between;gap:var(--sp-3);flex-wrap:wrap">
          <span>Seu e-mail ainda não foi confirmado. Confirmar ajuda a recuperar
          o acesso se você esquecer a senha.</span>
          <button class="btn btn--ghost btn--sm" type="button"
                  data-acao="reenviar-verificacao">Reenviar link</button>
        </div>
      </div>`);
  }

  function montar() {
    /* A cor do painel segue a profissão do workspace ativo. Quem
       sabe a profissão é o perfil profissional, não o tenant. */
    var perfil = VC.session.profissional();
    document.documentElement.setAttribute("data-vertical",
      perfil && perfil.professionSlug ? perfil.professionSlug : VC.config.verticalPadrao);

    render(VC.dom.el(".sidebar"), sidebarHTML());
    render(VC.dom.el(".topbar"), topbarHTML());
    render(VC.dom.el(".bottomnav"), bottomnavHTML());

    aplicarPrivacidade(VC.store.get("privacidade"));
    atualizarContadores();
    avisarEmailNaoVerificado();

    if (ligado) return;
    ligado = true;

    VC.dom.on(document, "click", '[data-acao="menu"]', function (e) { e.preventDefault(); alternarMenu(); });
    VC.dom.on(document, "click", ".scrim", function () { alternarMenu(false); });
    VC.dom.on(document, "click", ".sidebar a[href^='#']", function () {
      if (global.matchMedia("(max-width: 1024px)").matches) alternarMenu(false);
    });
    VC.dom.on(document, "click", '[data-acao="privacidade"]', function () {
      var novo = !VC.store.get("privacidade");
      VC.store.set("privacidade", novo);
      aplicarPrivacidade(novo);
      VC.toast.info(novo ? "Modo discreto ligado" : "Modo discreto desligado",
        novo ? "Os nomes ficam borrados até você passar o mouse." : "Os nomes voltaram a aparecer.");
    });
    VC.dom.on(document, "click", '[data-acao="trocar-workspace"]', function (e) {
      e.preventDefault(); abrirSeletorWorkspace();
    });
    VC.dom.on(document, "click", "[data-trocar-para]", function (e, botao) {
      trocarWorkspace(botao.getAttribute("data-trocar-para"));
    });

    VC.dom.on(document, "keydown", "[data-busca-global]", function (e, campo) {
      if (e.key === "Enter" && campo.value.trim()) {
        VC.router.navegar("/pacientes?busca=" + encodeURIComponent(campo.value.trim()));
        campo.blur();
      }
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "/" && document.activeElement.tagName !== "INPUT" && document.activeElement.tagName !== "TEXTAREA") {
        var campo = VC.dom.el("[data-busca-global]");
        if (campo) { e.preventDefault(); campo.focus(); }
      }
      if (e.key === "Escape") alternarMenu(false);
    });
  }

  VC.shell = {
    montar: montar,
    marcarAtivo: marcarAtivo,
    definirTitulo: definirTitulo,
    atualizarContadores: atualizarContadores,
    fecharMenu: function () { alternarMenu(false); },
    abrirSeletorWorkspace: abrirSeletorWorkspace
  };
})(window);
