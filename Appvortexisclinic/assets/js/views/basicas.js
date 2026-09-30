/* =============================================================
   REGISTROS · RELATÓRIOS · CONFIGURAÇÕES · PERFIL · ERROS
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var html = VC.safe.html;
  var ui = VC.ui, fmt = VC.fmt, t = VC.terms.t;

  function cabecalho(titulo, subtitulo, acoes) {
    return ui.cabecalhoPagina(titulo, subtitulo, acoes);
  }

  function campo(rotulo, valor, dica) {
    return html`
      <div class="card"><div class="card__body">
        <div class="stat__label">${rotulo}</div>
        <div style="font-size:var(--fs-base);font-weight:600;margin:2px 0">${valor}</div>
        ${dica ? html`<div class="muted" style="font-size:var(--fs-xs)">${dica}</div>` : html.vazio}
      </div></div>`;
  }

  /* ---------------- Registros clínicos ---------------- */
  var anotacoes = {
    render: function () { return cabecalho(t("record.many"), "Área protegida"); },
    mount: function (params, alvo) {
      VC.shell.definirTitulo(t("record.many"), "Área protegida");
      VC.safe.render(alvo, html`
        ${cabecalho(t("record.many"), "Registros de sessão e evolução",
          VC.session.pode("clinical_records.write")
            ? html`<button class="btn btn--accent" type="button" data-acao="em-breve"
                    data-recurso="Editor de registro clínico">${t("record.new")}</button>`
            : html.vazio)}

        <div class="notice">
          <div><b>Conteúdo sensível.</b> ${t("record.many")} são dados de saúde: o acesso pertence ao
          profissional responsável, não ao cargo. Quem administra a conta não enxerga este conteúdo sem
          concessão explícita, e todo acesso fica registrado em auditoria.</div>
        </div>

        <div class="card" style="margin-top:var(--sp-4)"><div class="card__body">${ui.vazio({
          titulo: "Editor entra na etapa do prontuário",
          texto: "A estrutura já prevê: vínculo com pessoa e atendimento, versionamento imutável, " +
                 "cifra do conteúdo e trilha de quem acessou."
        })}</div></div>`);
    }
  };

  /* ---------------- Relatórios ---------------- */
  var RELATORIOS = [
    { nome: "Atendimentos por período", texto: "Volume, presença, faltas e cancelamentos.", permissao: "appointments.read" },
    { nome: "Receita e recebimentos", texto: "Entradas por mês, forma de pagamento e inadimplência.", permissao: "finance.read" },
    { nome: "Pessoas atendidas", texto: "Ativos, inativos, frequência e tempo de acompanhamento.", permissao: "patients.read" },
    { nome: "Faltas e cancelamentos", texto: "Recorrência por pessoa e por dia da semana.", permissao: "appointments.read" }
  ];

  var relatorios = {
    render: function () { return cabecalho("Relatórios", "Números do consultório"); },
    mount: function (params, alvo) {
      VC.shell.definirTitulo("Relatórios", "Números do consultório");
      var cards = RELATORIOS.filter(function (r) { return VC.session.pode(r.permissao); }).map(function (r) {
        return html`
          <div class="card"><div class="card__body stack" style="gap:var(--sp-2)">
            <h3>${r.nome}</h3>
            <p class="muted" style="font-size:var(--fs-sm)">${r.texto}</p>
            <div class="row" style="gap:var(--sp-2);margin-top:var(--sp-2)">
              <button class="btn btn--ghost btn--sm" type="button" data-acao="em-breve" data-recurso="${r.nome}">Ver na tela</button>
              <button class="btn btn--quiet btn--sm" type="button" data-acao="em-breve" data-recurso="Exportar ${r.nome}">Exportar PDF</button>
            </div>
          </div></div>`;
      });

      VC.safe.render(alvo, html`
        ${cabecalho("Relatórios", "Números do consultório")}
        <div class="grid grid--2">${html.juntar(cards)}</div>
        <div class="notice" style="margin-top:var(--sp-4)">
          <div>Os números virão da camada de negócio do servidor — a mesma que alimenta o painel —
          para relatório e tela nunca divergirem. A geração de arquivo sai do servidor, não do navegador.</div>
        </div>`);
    }
  };

  /* ---------------- Configurações ---------------- */
  /* A tela de Configurações virou arquivo próprio e gravável:
     assets/js/views/configuracoes.js */

  /* ---------------- Perfil ---------------- */
  var perfil = {
    render: function () { return cabecalho("Perfil profissional", "Seus dados"); },
    mount: function (params, alvo) {
      VC.shell.definirTitulo("Perfil", "Dados do profissional");
      var u = VC.session.usuario();
      var p = VC.session.profissional();
      var m = VC.session.membership();
      var tenant = VC.session.tenant();
      var espacos = VC.session.workspaces();

      /* Campos da profissão: conselho e registro só aparecem quando
         a categoria profissional exige. */
      var camposProfissao = p && p.council
        ? html`${campo("Conselho", p.council)}${campo("Registro", p.registrationNumber)}`
        : campo("Registro profissional", html`<span class="soft">Não se aplica a esta categoria</span>`,
                "Nem toda profissão tem conselho");

      VC.safe.render(alvo, html`
        <div class="page-head">
          <div class="page-head__title">
            <div class="row" style="gap:var(--sp-4)">
              ${ui.avatar(u.nome, "lg")}
              <div>
                <h1>${u.nome}</h1>
                <p>${p ? p.displayName : u.email} · ${tenant ? tenant.nome : ""}</p>
              </div>
            </div>
          </div>
          <div class="page-head__actions">
            <button class="btn btn--ghost" type="button" data-acao="em-breve" data-recurso="Edição de perfil">Editar dados</button>
          </div>
        </div>

        <div class="grid grid--3">
          ${campo("E-mail", html`<span class="private">${u.email}</span>`)}
          ${campo("Profissão", p ? fmt.capitalizar(p.professionSlug.replace(/_/g, " ")) : "—", "Define campos e termos")}
          ${camposProfissao}
          ${campo("Papel nesta conta", html`<span class="badge badge--info">${m ? m.role : "—"}</span>`,
                  "Define o que aparece no painel")}
          ${campo("Alcance dos dados", m && m.dataScope === "all" ? "Toda a conta" : "Somente os seus",
                  "Definido pelo administrador")}
          ${campo("Conta ativa", tenant ? tenant.nome : "—", tenant ? tenant.id : "")}
        </div>

        <h2 style="font-size:var(--fs-base);margin:var(--sp-5) 0 var(--sp-3)">Suas contas</h2>
        <div class="grid grid--2">${html.juntar(espacos.map(function (w) {
          return html`
            <div class="card"><div class="card__body row row--between">
              <div>
                <b>${w.nome}</b>
                <p class="muted" style="font-size:var(--fs-xs)">${w.papel}${w.ativo ? " · em uso" : ""}</p>
              </div>
              ${w.ativo
                ? html`<span class="badge badge--ok">Ativa</span>`
                : html`<button class="btn btn--ghost btn--sm" type="button" data-trocar-para="${w.tenantId}">Entrar</button>`}
            </div></div>`;
        }))}</div>

        <div class="card" style="margin-top:var(--sp-5)"><div class="card__body row row--between row--wrap">
          <div><b>Sair da conta</b>
            <p class="muted" style="font-size:var(--fs-sm)">Disponível quando o login entrar.</p></div>
          <button class="btn btn--ghost" type="button" data-acao="sair">Sair</button>
        </div></div>`);
    }
  };

  /* ---------------- Erros ---------------- */
  var naoEncontrada = {
    render: function () { return null; },
    mount: function (params, alvo) {
      VC.shell.definirTitulo("Página não encontrada");
      VC.safe.render(alvo, html`<div class="card"><div class="card__body">${ui.vazio({
        titulo: "Não encontramos esta tela",
        texto: "O endereço pode ter mudado. Volte ao início para continuar.",
        acao: { href: "#/", rotulo: "Ir para o início" }
      })}</div></div>`);
    }
  };

  var semPermissao = {
    render: function () { return null; },
    mount: function (params, alvo) {
      VC.shell.definirTitulo("Sem acesso");
      VC.safe.render(alvo, html`<div class="card"><div class="card__body">${ui.vazio({
        titulo: "Esta área não está disponível para o seu acesso",
        texto: "O que você pode ver depende do papel nesta conta. Fale com quem administra a conta se precisar deste acesso.",
        acao: { href: "#/", rotulo: "Voltar ao início" }
      })}</div></div>`);
    }
  };

  VC.views = VC.views || {};
  VC.views.anotacoes = anotacoes;
  VC.views.relatorios = relatorios;
  VC.views.perfil = perfil;
  VC.views.naoEncontrada = naoEncontrada;
  VC.views.semPermissao = semPermissao;
})(window);
