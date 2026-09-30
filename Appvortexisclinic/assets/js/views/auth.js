/* =============================================================
   ENTRADA — login, criação de conta e escolha de workspace
   -------------------------------------------------------------
   Estas telas ficam FORA do painel: enquanto não há sessão, nem a
   navegação nem os dados são montados. É o mesmo fail-closed do
   servidor, aplicado à interface.

   Nada aqui guarda senha, token ou identidade: o campo de senha vai
   direto para a requisição e a resposta vira estado da sessão. O
   cookie é responsabilidade do navegador.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var html = VC.safe.html;


  var alvo = null;
  var aoEntrar = null;
  var profissoes = [];
  var tela = "login";
  var ocupado = false;
  var convite = null;        /* {token, dados} enquanto a tela de convite está aberta */
  var tokenDeLink = null;    /* token de verificação ou de redefinição de senha */

  /* ---------------- moldura ---------------- */
  function moldura(titulo, subtitulo, conteudo, rodape) {
    return html`
      <div class="auth">
        <div class="auth__card">
          <div class="auth__marca">
            <img src="assets/images/marca-texto.png" alt="Vortexis Clinic" height="30"
                 onerror="this.style.display='none'">
          </div>
          <h1>${titulo}</h1>
          <p class="auth__sub">${subtitulo}</p>
          ${conteudo}
          ${rodape || html.vazio}
        </div>
        <p class="auth__nota">
          Seus dados e os das pessoas que você atende ficam isolados por conta.
          Ninguém de outra conta enxerga o que é seu.
        </p>
      </div>`;
  }

  function campo(id, rotulo, tipo, extras) {
    extras = extras || {};
    var auto = extras.autocomplete || "off";
    var valor = extras.valor || "";
    /* Duas variantes em vez de montar atributo por concatenação:
       toda interpolação passa pelo escape do html``, inclusive
       dentro de aspas de atributo. */
    var entrada = extras.obrigatorio === false
      ? html`<input id="${id}" name="${id}" type="${tipo}" autocomplete="${auto}" value="${valor}">`
      : html`<input id="${id}" name="${id}" type="${tipo}" autocomplete="${auto}" value="${valor}" required>`;

    return html`
      <label class="auth__campo" for="${id}">
        <span>${rotulo}</span>
        ${entrada}
        ${extras.dica ? html`<small>${extras.dica}</small>` : html.vazio}
      </label>`;
  }

  function erroCaixa(mensagem) {
    return mensagem
      ? html`<div class="auth__erro" role="alert">${mensagem}</div>`
      : html.vazio;
  }

  /* ---------------- login ---------------- */
  function renderLogin(mensagem) {
    VC.safe.render(alvo, moldura(
      "Entrar",
      "Acesse o painel da sua conta.",
      html`
        <form data-form="login" novalidate>
          ${erroCaixa(mensagem)}
          ${campo("email", "E-mail", "email", { autocomplete: "username" })}
          ${campo("senha", "Senha", "password", { autocomplete: "current-password" })}
          <button class="btn btn--accent btn--block" type="submit" data-enviar>Entrar</button>
        </form>`,
      html`
        <div class="auth__rodape">
          <button class="btn btn--quiet btn--sm" type="button" data-ir="cadastro">Criar uma conta</button>
          <button class="btn btn--quiet btn--sm" type="button" data-ir="esqueci">Esqueci minha senha</button>
        </div>`
    ));
  }

  /* ---------------- cadastro ---------------- */
  function renderCadastro(mensagem, valores) {
    valores = valores || {};
    var opcoes = profissoes.map(function (p) {
      return html`<option value="${p.slug}">${p.nome}</option>`;
    });

    VC.safe.render(alvo, moldura(
      "Criar conta",
      "Sua conta e seu espaço de trabalho nascem juntos.",
      html`
        <form data-form="cadastro" novalidate>
          ${erroCaixa(mensagem)}
          ${campo("nome", "Seu nome", "text", { autocomplete: "name", valor: valores.nome })}
          ${campo("email", "E-mail", "email", { autocomplete: "email", valor: valores.email })}
          ${campo("senha", "Senha", "password", {
            autocomplete: "new-password", dica: "Pelo menos 10 caracteres."
          })}
          ${campo("workspace", "Nome do espaço de trabalho", "text", {
            valor: valores.workspace, dica: "Ex.: Consultório Camila Ferraz, Clínica Bem Viver."
          })}

          <label class="auth__campo" for="tipo_workspace">
            <span>Tipo</span>
            <select id="tipo_workspace" name="tipo_workspace">
              <option value="solo">Profissional autônomo</option>
              <option value="office">Consultório</option>
              <option value="clinic">Clínica</option>
            </select>
          </label>

          <label class="auth__campo" for="profissao">
            <span>Profissão</span>
            <select id="profissao" name="profissao" data-profissao>
              <option value="">Selecione…</option>
              ${html.juntar(opcoes)}
            </select>
            <small>Define os termos do sistema e se pedimos registro profissional.</small>
          </label>

          <div data-conselho hidden></div>

          <button class="btn btn--accent btn--block" type="submit" data-enviar>Criar conta e entrar</button>
        </form>`,
      html`
        <div class="auth__rodape">
          <button class="btn btn--quiet btn--sm" type="button" data-ir="login">Já tenho conta</button>
        </div>`
    ));
  }

  /* Conselho e registro só aparecem quando a profissão exige — quem
     decide é o catálogo do servidor, não um `if` escrito aqui. */
  function atualizarCamposDaProfissao() {
    var select = VC.dom.el("[data-profissao]", alvo);
    var caixa = VC.dom.el("[data-conselho]", alvo);
    if (!select || !caixa) return;

    var escolhida = profissoes.filter(function (p) { return p.slug === select.value; })[0];
    if (!escolhida || !escolhida.exige_conselho) {
      caixa.hidden = true;
      VC.safe.render(caixa, html.vazio);
      return;
    }
    caixa.hidden = false;
    VC.safe.render(caixa, html`
      ${campo("registro", escolhida.rotulo_registro || "Registro profissional", "text", {
        dica: escolhida.rotulo_conselho
          ? "Conselho: " + escolhida.rotulo_conselho
          : ""
      })}`);
  }

  /* ---------------- esqueci a senha ---------------- */
  function renderEsqueci(mensagem, sucesso) {
    VC.safe.render(alvo, moldura(
      "Recuperar acesso",
      "Enviaremos as instruções para o seu e-mail.",
      sucesso
        ? html`<div class="auth__ok">${sucesso}</div>`
        : html`
          <form data-form="esqueci" novalidate>
            ${erroCaixa(mensagem)}
            ${campo("email", "E-mail", "email", { autocomplete: "email" })}
            <button class="btn btn--accent btn--block" type="submit" data-enviar>Enviar instruções</button>
          </form>`,
      html`<div class="auth__rodape">
        <button class="btn btn--quiet btn--sm" type="button" data-ir="login">Voltar para o login</button>
      </div>`
    ));
  }

  /* ---------------- escolha de workspace ---------------- */
  function renderWorkspaces(mensagem) {
    var lista = VC.session.workspaces().map(function (w) {
      return html`
        <button class="auth__workspace" type="button" data-workspace="${w.tenantId}">
          <span class="auth__workspace-nome">${w.nome}</span>
          <span class="auth__workspace-papel">${w.papelNome || w.papel}</span>
        </button>`;
    });

    VC.safe.render(alvo, moldura(
      "Escolha o espaço de trabalho",
      "Você participa de mais de uma conta. Os dados de cada uma são separados.",
      html`
        ${erroCaixa(mensagem)}
        <div class="auth__workspaces">${html.juntar(lista)}</div>`,
      html`<div class="auth__rodape">
        <button class="btn btn--quiet btn--sm" type="button" data-acao="sair-auth">Sair</button>
      </div>`
    ));
  }

  /* ---------------- convite ----------------
     Esta tela existe antes de qualquer sessão: quem foi convidado
     pode ainda não ter conta nenhuma. A autenticação aqui é o token
     do link, e o servidor responde a mesma coisa para link errado,
     vencido, revogado ou já usado — distinguir só ajudaria quem
     estivesse testando links.

     O que a tela mostra é o mínimo: o nome da conta e o papel. Não
     mostra quem mais está lá dentro nem o e-mail de quem convidou. */
  function renderConvite(mensagem) {
    var c = convite && convite.dados;
    if (!c) {
      VC.safe.render(alvo, moldura(
        "Convite indisponível",
        "Este link não vale mais.",
        html`<div class="auth__erro" role="alert">
          O convite pode ter expirado, sido revogado ou já usado.
          Peça um novo para quem administra a conta.
        </div>`,
        html`<div class="auth__rodape">
          <button class="btn btn--quiet btn--sm" type="button" data-ir="login">Ir para o login</button>
        </div>`
      ));
      return;
    }

    var campos = c.jaTemConta
      ? html`${campo("senha", "Sua senha", "password", { autocomplete: "current-password" })}`
      : html`
        ${campo("nome", "Seu nome completo", "text", { autocomplete: "name" })}
        ${campo("senha", "Crie uma senha", "password", {
          autocomplete: "new-password", dica: "Mínimo de 10 caracteres" })}`;

    VC.safe.render(alvo, moldura(
      "Convite para " + c.workspace,
      c.jaTemConta
        ? "Você já tem conta. Confirme a senha para entrar nesta clínica."
        : "Crie sua senha para entrar nesta clínica.",
      html`
        <form data-form="convite" novalidate>
          ${erroCaixa(mensagem)}
          <div class="auth__convite">
            <div><b>${c.email}</b></div>
            <div>Você entra como <b>${c.papelRotulo}</b></div>
            ${c.mensagem ? html`<div class="auth__convite-msg">“${c.mensagem}”</div>` : html.vazio}
          </div>
          ${campos}
          <button class="btn btn--accent btn--block" type="submit" data-enviar>Aceitar convite</button>
        </form>`,
      html`<div class="auth__rodape">
        <button class="btn btn--quiet btn--sm" type="button" data-ir="login">Entrar em outra conta</button>
      </div>`
    ));
  }

  /* ---------------- confirmar e-mail ----------------
     Vem de um link do e-mail, antes de qualquer sessão. Uma resposta só
     para link errado, vencido ou já usado: distinguir ajudaria apenas
     quem está testando links. */
  function renderVerificar(estado) {
    if (estado === "ok") {
      VC.safe.render(alvo, moldura(
        "E-mail confirmado",
        "Pronto — seu endereço está confirmado.",
        html`<div class="auth__ok">Você já pode entrar normalmente.</div>`,
        html`<div class="auth__rodape">
          <button class="btn btn--accent btn--block" type="button" data-ir="login">Entrar</button>
        </div>`
      ));
      return;
    }
    if (estado === "erro") {
      VC.safe.render(alvo, moldura(
        "Link indisponível",
        "Este link não vale mais.",
        html`<div class="auth__erro" role="alert">
          Ele pode ter expirado ou já ter sido usado. Entre na sua conta e peça um novo
          link de confirmação.
        </div>`,
        html`<div class="auth__rodape">
          <button class="btn btn--quiet btn--sm" type="button" data-ir="login">Ir para o login</button>
        </div>`
      ));
      return;
    }
    VC.safe.render(alvo, moldura("Confirmando seu e-mail", "Um instante…", html.vazio));
  }

  /* ---------------- redefinir senha ---------------- */
  function renderRedefinir(mensagem, sucesso) {
    if (sucesso) {
      VC.safe.render(alvo, moldura(
        "Senha redefinida",
        "Sua senha nova já vale.",
        html`<div class="auth__ok">Por segurança, todas as outras sessões foram encerradas.</div>`,
        html`<div class="auth__rodape">
          <button class="btn btn--accent btn--block" type="button" data-ir="login">Entrar</button>
        </div>`
      ));
      return;
    }
    VC.safe.render(alvo, moldura(
      "Criar nova senha",
      "Escolha uma senha que você não use em outro lugar.",
      html`
        <form data-form="redefinir" novalidate>
          ${erroCaixa(mensagem)}
          ${campo("senha", "Nova senha", "password", {
            autocomplete: "new-password", dica: "Mínimo de 10 caracteres" })}
          <button class="btn btn--accent btn--block" type="submit" data-enviar>Redefinir</button>
        </form>`,
      html`<div class="auth__rodape">
        <button class="btn btn--quiet btn--sm" type="button" data-ir="login">Voltar para o login</button>
      </div>`
    ));
  }

  /* ---------------- envio ---------------- */
  function bloquear(form, travar) {
    ocupado = travar;
    var botao = VC.dom.el("[data-enviar]", form);
    if (botao) {
      botao.disabled = travar;
      VC.safe.texto(botao, travar ? "Um instante…" : botao.getAttribute("data-rotulo") || botao.textContent);
    }
  }

  function valores(form) {
    var dados = {};
    VC.dom.els("input, select", form).forEach(function (campoEl) {
      dados[campoEl.name] = campoEl.value.trim();
    });
    return dados;
  }

  function mensagemDe(e) {
    if (e && e.status === 0) return "Não conseguimos falar com o servidor. Verifique se a API está rodando.";
    if (e && e.status === 429) return "Muitas tentativas seguidas. Aguarde um instante e tente de novo.";
    return (e && e.message) || "Não foi possível concluir. Tente novamente.";
  }

  function depoisDeEntrar() {
    /* Libera a trava de envio: o login terminou. Sem isto, o clique
       seguinte (escolher o workspace) seria engolido. */
    ocupado = false;
    if (!VC.session.temWorkspace()) { tela = "workspaces"; renderWorkspaces(); return; }
    if (aoEntrar) aoEntrar();
  }

  function enviar(form) {
    var tipo = form.getAttribute("data-form");
    var dados = valores(form);
    bloquear(form, true);

    var acao;
    if (tipo === "login") {
      acao = VC.session.entrar(dados.email, dados.senha).then(depoisDeEntrar);
    } else if (tipo === "cadastro") {
      acao = VC.session.cadastrar({
        nome: dados.nome,
        email: dados.email,
        senha: dados.senha,
        workspace: dados.workspace,
        tipo_workspace: dados.tipo_workspace || "solo",
        profissao: dados.profissao || null,
        registro: dados.registro || null
      }).then(depoisDeEntrar);
    } else if (tipo === "redefinir") {
      acao = VC.api.post("/auth/password/reset", {
        token: tokenDeLink, senha: dados.senha
      }).then(function () {
        ocupado = false;
        global.location.hash = "#/";
        renderRedefinir(null, true);
      });
    } else if (tipo === "convite") {
      acao = VC.services.equipe.aceitar(convite.token, {
        nome: dados.nome, senha: dados.senha
      }).then(function () {
        /* O servidor já abriu a sessão e deixou a pessoa dentro da
           conta que convidou. Recarregar a sessão é o que traz
           permissões e termos certos. */
        convite = null;
        global.location.hash = "#/";
        return VC.session.carregar().then(depoisDeEntrar);
      });
    } else {
      acao = VC.api.post("/auth/password/forgot", { email: dados.email }).then(function (r) {
        ocupado = false;
        renderEsqueci(null, r && r.mensagem);
      });
    }

    acao.catch(function (e) {
      bloquear(form, false);
      var msg = mensagemDe(e);
      if (tipo === "login") renderLogin(msg);
      else if (tipo === "cadastro") renderCadastro(msg, dados);
      else if (tipo === "convite") renderConvite(msg);
      else if (tipo === "redefinir") renderRedefinir(msg);
      else renderEsqueci(msg);
    });
  }

  /* ---------------- eventos ---------------- */
  function ligarEventos() {
    VC.dom.on(alvo, "submit", "form", function (e, form) {
      e.preventDefault();
      if (!ocupado) enviar(form);
    });

    VC.dom.on(alvo, "click", "[data-ir]", function (e, botao) {
      e.preventDefault();
      mostrar(botao.getAttribute("data-ir"));
    });

    VC.dom.on(alvo, "change", "[data-profissao]", function () {
      atualizarCamposDaProfissao();
    });

    VC.dom.on(alvo, "click", "[data-workspace]", function (e, botao) {
      e.preventDefault();
      if (ocupado) return;
      ocupado = true;
      VC.session.trocarTenant(botao.getAttribute("data-workspace")).then(function () {
        ocupado = false;
        if (aoEntrar) aoEntrar();
      }, function (erro) {
        ocupado = false;
        /* 404 aqui significa "não existe para você" — mesma resposta
           que o servidor dá para workspace de outra pessoa. */
        renderWorkspaces(erro && erro.status === 404
          ? "Este espaço de trabalho não está disponível para a sua conta."
          : mensagemDe(erro));
      });
    });

    VC.dom.on(alvo, "click", '[data-acao="sair-auth"]', function (e) {
      e.preventDefault();
      VC.session.encerrar();
    });
  }

  /* ---------------- ciclo ---------------- */
  function carregarProfissoes() {
    if (profissoes.length) return Promise.resolve(profissoes);
    return VC.api.get("/professions").then(function (lista) {
      profissoes = lista || [];
      return profissoes;
    }, function () { return []; });
  }

  function mostrar(qual) {
    tela = qual || "login";
    document.body.setAttribute("data-auth", "on");

    if (tela === "cadastro") {
      carregarProfissoes().then(function () {
        renderCadastro();
        atualizarCamposDaProfissao();
      });
      return;
    }
    if (tela === "convite") return renderConvite();
    if (tela === "esqueci") return renderEsqueci();
    if (tela === "workspaces") return renderWorkspaces();
    renderLogin();
  }

  function iniciar(opcoes) {
    alvo = VC.dom.el("[data-auth-outlet]");
    aoEntrar = opcoes.aoEntrar;
    ligarEventos();

    if (opcoes.tela === "verificar" && opcoes.token) {
      document.body.setAttribute("data-auth", "on");
      tela = "verificar";
      renderVerificar("carregando");
      VC.api.post("/auth/email/verify", { token: opcoes.token }).then(function () {
        global.location.hash = "#/";
        renderVerificar("ok");
      }, function () {
        global.location.hash = "#/";
        renderVerificar("erro");
      });
      return;
    }

    if (opcoes.tela === "redefinir" && opcoes.token) {
      document.body.setAttribute("data-auth", "on");
      tela = "redefinir";
      tokenDeLink = opcoes.token;
      renderRedefinir();
      return;
    }

    if (opcoes.tela === "convite" && opcoes.token) {
      convite = { token: opcoes.token, dados: null };
      document.body.setAttribute("data-auth", "on");
      VC.services.equipe.verConvite(opcoes.token).then(function (dados) {
        convite.dados = dados;
        tela = "convite";
        renderConvite();
      }, function () {
        /* Link inválido, vencido, revogado ou já usado: a mesma tela
           para todos os casos. */
        convite = { token: opcoes.token, dados: null };
        tela = "convite";
        renderConvite();
      });
      return;
    }

    mostrar(opcoes.tela || "login");
  }

  function esconder() {
    document.body.removeAttribute("data-auth");
    if (alvo) VC.safe.render(alvo, html.vazio);
  }

  VC.auth = { iniciar: iniciar, mostrar: mostrar, esconder: esconder };
})(window);
