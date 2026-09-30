/* =============================================================
   PESSOAS ATENDIDAS — lista com busca e filtros + ficha individual
   O rótulo ("Paciente" ou "Cliente") vem de core/terms.js.
   A aba clínica só aparece para quem tem permissão clínica.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var html = VC.safe.html;
  var ui = VC.ui, fmt = VC.fmt, t = VC.terms.t;

  var filtros = { busca: "", status: "ativo", somenteComPendencia: false,
                  pagina: 1, tamanho: 25 };
  var pessoaAberta = null;      /* a ficha em tela, para recarregar o prontuário */

  /* ---------------- Lista ---------------- */
  function cabecalho() {
    var podeFinanceiro = VC.session.pode("finance.read");
    return html`
      <div class="page-head">
        <div class="page-head__title">
          <h1>${t("client.many")}</h1>
          <p data-total-pacientes>Carregando…</p>
        </div>
        <div class="page-head__actions">
          <button class="btn btn--accent" type="button" data-acao="novo-paciente">${t("client.new")}</button>
        </div>
      </div>

      <div class="filters">
        <div class="field grow" style="max-width:320px">
          <label for="f-busca">Buscar</label>
          <input id="f-busca" type="search" placeholder="${t("client.search")}" value="${filtros.busca}" data-filtro="busca">
        </div>
        <button class="chip" type="button" data-filtro-status="ativo" aria-pressed="${filtros.status === "ativo"}">Ativos</button>
        <button class="chip" type="button" data-filtro-status="inativo" aria-pressed="${filtros.status === "inativo"}">Inativos</button>
        <button class="chip" type="button" data-filtro-status="todos" aria-pressed="${filtros.status === "todos"}">Todos</button>
        ${podeFinanceiro ? html`
          <span style="width:1px;height:22px;background:var(--border)"></span>
          <button class="chip" type="button" data-filtro-pendencia aria-pressed="${filtros.somenteComPendencia}">Com pendência</button>`
          : html.vazio}
      </div>
      <div class="card" data-lista><div class="card__body">${ui.skeletonLinhas(6)}</div></div>
      <div data-paginacao></div>`;
  }

  function linha(p, podeFinanceiro) {
    var r = p.resumo;
    return html`
      <tr>
        <td class="cell-first">
          <a class="row" href="#/pacientes/${p.id}" style="gap:var(--sp-3)">
            ${ui.avatar(p.nome, "sm")}
            <span>
              <span class="cell-main">${ui.nomeCliente(p.nome, true)}</span>
              <span class="cell-sub" style="display:block">${fmt.capitalizar(p.frequencia)} · ${ui.rotuloDe(ui.MODALIDADE, p.modalidadePadrao)}</span>
            </span>
          </a>
        </td>
        <td data-label="Situação">${p.status === "ativo"
          ? html`<span class="badge badge--ok">Ativo</span>`
          : html`<span class="badge badge--neutral">Inativo</span>`}</td>
        <td data-label="Último">${r.ultimo
          ? html`<span class="tabular">${fmt.diaMes(r.ultimo)}</span>`
          : html`<span class="soft">—</span>`}</td>
        <td data-label="Próximo">${r.proximo
          ? html`<span class="tabular">${fmt.dataRelativa(r.proximo)} · ${fmt.hora(r.proximo)}</span>`
          : html`<span class="soft">Sem agenda</span>`}</td>
        <td data-label="Presença">${r.presenca === null
          ? html`<span class="soft">—</span>`
          : html`<span class="tabular">${fmt.porcento(r.presenca)}</span>`}</td>
        ${podeFinanceiro ? html`<td data-label="Em aberto" class="num">${r.valorEmAberto
          ? html`<b style="color:var(--warn)">${fmt.moeda(r.valorEmAberto)}</b>`
          : html`<span class="soft">—</span>`}</td>` : html.vazio}
        <td data-label="" class="num"><a class="btn btn--ghost btn--sm" href="#/pacientes/${p.id}">Abrir</a></td>
      </tr>`;
  }

  function pintarLista(lista) {
    var alvo = VC.dom.el("[data-lista]");
    if (!alvo) return;
    var podeFinanceiro = VC.session.pode("finance.read");

    if (!lista.length) {
      VC.safe.render(alvo, html`<div class="card__body">${ui.vazio({
        titulo: "Nenhum resultado",
        texto: filtros.busca
          ? "Nada corresponde a “" + filtros.busca + "”. Revise a busca ou troque o filtro de situação."
          : "Cadastre o primeiro registro para começar a marcar atendimentos.",
        acao: { href: "#/pacientes", rotulo: t("client.new") }
      })}</div>`);
      return;
    }

    var colunas = [
      { rotulo: t("client.one") }, { rotulo: "Situação" }, { rotulo: "Último" },
      { rotulo: "Próximo" }, { rotulo: "Presença" }
    ];
    if (podeFinanceiro) colunas.push({ rotulo: "Em aberto", num: true });
    colunas.push({ rotulo: "" });

    VC.safe.render(alvo, ui.tabela(colunas, lista.map(function (p) { return linha(p, podeFinanceiro); })));
  }

  /* Paginação: só aparece quando existe mais de uma página. Barra de
     navegação em lista de 6 pessoas é ruído. */
  function pintarPaginacao(total) {
    var alvo = VC.dom.el("[data-paginacao]");
    if (!alvo) return;
    var paginas = Math.max(1, Math.ceil(total / filtros.tamanho));
    if (paginas <= 1) { VC.safe.render(alvo, html.vazio); return; }

    var primeiro = (filtros.pagina - 1) * filtros.tamanho + 1;
    var ultimo = Math.min(filtros.pagina * filtros.tamanho, total);

    VC.safe.render(alvo, html`
      <div class="row" style="justify-content:space-between;align-items:center;
                  margin-top:var(--sp-3);gap:var(--sp-3);flex-wrap:wrap">
        <span class="cell-sub">${primeiro}–${ultimo} de ${total}</span>
        <span class="row" style="gap:var(--sp-2)">
          <button class="btn btn--ghost btn--sm" type="button" data-pagina="${filtros.pagina - 1}"
                  ${filtros.pagina <= 1 ? html.estatico("disabled") : html.vazio}>Anterior</button>
          <span class="cell-sub tabular">${filtros.pagina} / ${paginas}</span>
          <button class="btn btn--ghost btn--sm" type="button" data-pagina="${filtros.pagina + 1}"
                  ${filtros.pagina >= paginas ? html.estatico("disabled") : html.vazio}>Próxima</button>
        </span>
      </div>`);
  }

  function carregar() {
    VC.services.pacientes.listar({
      busca: filtros.busca, status: filtros.status,
      somenteComPendencia: filtros.somenteComPendencia,
      limite: filtros.tamanho, pagina: filtros.pagina
    }).then(function (r) {
      var lista = r.lista;
      pintarLista(lista);
      pintarPaginacao(r.total);
      var comPendencia = lista.filter(function (p) { return p.resumo.valorEmAberto > 0; }).length;
      VC.safe.texto(VC.dom.el("[data-total-pacientes]"),
        r.total + " " + t("client.many", true) + " nesta visão" +
        (comPendencia ? " · " + comPendencia + " com pendência nesta página" : ""));
    }).catch(function () {
      VC.safe.render(VC.dom.el("[data-lista]"), html`<div class="card__body">${ui.vazio({
        titulo: "Não foi possível carregar", texto: "Tente novamente em instantes."
      })}</div>`);
    });
  }

  function render() { return cabecalho(); }

  function mount(params, alvo) {
    VC.shell.definirTitulo(t("client.many"), "Cadastro e acompanhamento");

    var busca = new URLSearchParams(global.location.hash.split("?")[1] || "").get("busca");
    if (busca) {
      filtros.busca = busca;
      var campo = VC.dom.el('[data-filtro="busca"]');
      if (campo) campo.value = busca;
    }

    var timer = null;
    VC.dom.on(alvo, "input", '[data-filtro="busca"]', function (e, campo) {
      clearTimeout(timer);
      timer = setTimeout(function () { filtros.busca = campo.value.trim(); filtros.pagina = 1; carregar(); }, 220);
    });
    VC.dom.on(alvo, "click", "[data-filtro-status]", function (e, botao) {
      filtros.status = botao.getAttribute("data-filtro-status");
      filtros.pagina = 1;
      VC.dom.els("[data-filtro-status]", alvo).forEach(function (b) {
        b.setAttribute("aria-pressed", String(b === botao));
      });
      carregar();
    });
    VC.dom.on(alvo, "click", "[data-pagina]", function (e, botao) {
      var alvoPagina = parseInt(botao.getAttribute("data-pagina"), 10);
      if (!alvoPagina || alvoPagina < 1 || botao.disabled) return;
      filtros.pagina = alvoPagina;
      carregar();
      global.scrollTo({ top: 0, behavior: "smooth" });
    });

    VC.dom.on(alvo, "click", "[data-filtro-pendencia]", function (e, botao) {
      filtros.somenteComPendencia = !filtros.somenteComPendencia;
      filtros.pagina = 1;
      botao.setAttribute("aria-pressed", String(filtros.somenteComPendencia));
      carregar();
    });

    carregar();
  }

  /* ---------------- Ficha ---------------- */
  /* Recorrências ativas: o molde que gerou várias das sessões abaixo.
     Fica aqui, e não na agenda, porque é uma combinação com a pessoa
     ("toda terça às 9") — não um evento do calendário. */
  function pintarSeries(lista) {
    var caixa = VC.dom.el("[data-series]");
    if (!caixa) return;
    var ativas = lista.filter(function (s) { return s.ativa; });
    if (!ativas.length) { VC.safe.render(caixa, html.vazio); return; }

    VC.safe.render(caixa, html`
      <div class="card" style="margin-bottom:var(--sp-4)">
        <div class="card__body">
          <div class="cell-sub" style="margin-bottom:var(--sp-2)">Recorrência</div>
          ${html.juntar(ativas.map(function (s) {
            return html`
              <div class="row" style="justify-content:space-between;align-items:center;gap:var(--sp-3)">
                <div>
                  <div class="cell-main">${fmt.capitalizar(s.frequenciaRotulo)} ·
                    ${fmt.diaSemana(s.inicio)} às ${fmt.hora(s.inicio)}</div>
                  <div class="cell-sub">${s.ocorrencias} sessões${
                    s.valor ? " · " + fmt.moeda(s.valor) : ""}</div>
                </div>
                ${VC.session.pode("appointments.cancel") ? html`
                  <button class="btn btn--ghost btn--sm" type="button" data-acao="encerrar-serie"
                          data-serie="${s.id}"
                          data-rotulo="${s.frequenciaRotulo}">Encerrar</button>` : html.vazio}
              </div>`;
          }))}
        </div>
      </div>`);
  }

  function carregarSeries(p) {
    if (!VC.session.pode("appointments.read")) return;
    VC.services.agenda.seriesDoPaciente(p.id).then(pintarSeries, function () {});
  }

  function abaHistorico(p) {
    if (!p.historico.length) {
      return ui.vazio({ titulo: "Sem registros", texto: "Os atendimentos aparecem aqui assim que forem criados." });
    }
    var podeFinanceiro = VC.session.pode("finance.read");
    var colunas = [{ rotulo: "Data" }, { rotulo: "Horário" }, { rotulo: "Modalidade" }, { rotulo: "Situação" }];
    if (podeFinanceiro) colunas.push({ rotulo: "Pagamento" }, { rotulo: "Valor", num: true });

    var linhas = p.historico.slice(0, 20).map(function (a) {
      return html`
        <tr>
          <td class="cell-first"><span class="cell-main tabular">${fmt.diaMes(a.inicio)}</span></td>
          <td data-label="Horário" class="tabular">${fmt.hora(a.inicio)} · ${fmt.duracao(a.duracaoMin)}</td>
          <td data-label="Modalidade">${ui.badgeModalidade(a.modalidade)}</td>
          <td data-label="Situação">${ui.badgeAtendimento(a.status)}</td>
          ${podeFinanceiro ? html`
            <td data-label="Pagamento">${ui.badgePagamento(a.pagamento)}</td>
            <td data-label="Valor" class="num tabular">${fmt.moeda(a.valor)}</td>` : html.vazio}
        </tr>`;
    });
    return ui.tabela(colunas, linhas);
  }

  function campo(rotulo, valor) {
    return html`
      <div>
        <div class="stat__label">${rotulo}</div>
        <div style="font-size:var(--fs-base);font-weight:600;margin-top:2px">${valor}</div>
      </div>`;
  }

  /* ---------------- Prontuário ----------------
     A aba lista metadado. O texto de cada registro só é buscado
     quando alguém pede para ler — e essa chamada é o que o servidor
     grava na trilha de acesso. Abrir a aba não é ler o prontuário. */
  function badgeDaNota(n) {
    if (n.conteudoApagadoEm) return html`<span class="badge badge--neutral">conteúdo apagado</span>`;
    return n.assinada
      ? html`<span class="badge badge--ok">assinada</span>`
      : html`<span class="badge badge--warn">rascunho</span>`;
  }

  function cartaoDeNota(n) {
    var podeEditar = n.souOAutor && !n.conteudoApagadoEm;
    return html`
      <div class="card" style="margin-bottom:var(--sp-3)">
        <div class="card__body">
          <div class="row" style="justify-content:space-between;align-items:flex-start;gap:var(--sp-3)">
            <div>
              <div class="cell-main">${n.tipoRotulo} · ${fmt.dataLonga(n.ocorridoEm)}</div>
              <div class="cell-sub">${n.autor || "—"} · versão ${n.versaoAtual}${
                n.assinada && n.assinadaEm ? " · assinada em " + fmt.diaMes(n.assinadaEm) : ""}</div>
            </div>
            <div class="row" style="gap:var(--sp-2)">
              ${badgeDaNota(n)}
              ${n.conteudoApagadoEm ? html.vazio : html`
                <button class="btn btn--ghost btn--sm" type="button"
                        data-ler-registro="${n.id}">Ler</button>`}
              ${podeEditar ? html`
                <button class="btn btn--ghost btn--sm" type="button" data-acao="editar-registro"
                        data-nota="${n.id}" data-assinada="${n.assinada}">Editar</button>` : html.vazio}
              ${podeEditar && !n.assinada ? html`
                <button class="btn btn--ghost btn--sm" type="button" data-acao="assinar-registro"
                        data-nota="${n.id}">Assinar</button>` : html.vazio}
            </div>
          </div>
          <div data-conteudo-de="${n.id}" hidden></div>
        </div>
      </div>`;
  }

  function pintarProntuario(notas) {
    var alvo = VC.dom.el("[data-prontuario]");
    if (!alvo) return;
    if (!notas.length) {
      VC.safe.render(alvo, ui.vazio({
        titulo: "Nenhum registro",
        texto: VC.session.pode("clinical_records.write")
          ? "O primeiro registro pode ser criado pelo botão acima."
          : "Não há registros que você possa acessar."
      }));
      return;
    }
    VC.safe.render(alvo, html.juntar(notas.map(cartaoDeNota)));
  }

  function carregarProntuario(p) {
    VC.services.prontuario.listar(p.id).then(pintarProntuario, function () {
      VC.safe.render(VC.dom.el("[data-prontuario]"), ui.vazio({
        titulo: "Não foi possível carregar",
        texto: "Tente novamente em instantes."
      }));
    });
  }

  function abaClinica(p) {
    var podeEscrever = VC.session.pode("clinical_records.write");
    var podeAuditar = VC.session.pode("audit.read");
    return html`
      <div class="notice">
        <div><b>Área protegida.</b> ${t("record.many")} são dados de saúde. O acesso é do
        profissional responsável — não do papel administrativo — e cada leitura de conteúdo
        fica registrada na trilha desta pessoa.</div>
      </div>
      <div class="row" style="justify-content:space-between;margin:var(--sp-4) 0 var(--sp-3)">
        <b>Registros</b>
        <span class="row" style="gap:var(--sp-2)">
          ${podeAuditar ? html`
            <button class="btn btn--ghost btn--sm" type="button" data-acao="trilha-clinica"
                    data-paciente="${p.id}" data-nome="${p.nome}">Quem acessou</button>` : html.vazio}
          ${podeEscrever ? html`
            <button class="btn btn--accent btn--sm" type="button" data-acao="novo-registro"
                    data-paciente="${p.id}" data-nome="${p.nome}">Novo registro</button>` : html.vazio}
        </span>
      </div>
      <div data-prontuario>${ui.skeletonLinhas(3)}</div>`;
  }

  /* ---------------- Privacidade da pessoa ----------------
     Consentimento com versão e data, pacote de portabilidade, pedido do
     titular e anonimização. O que não dá para desfazer está escrito como
     não dando para desfazer. */
  function pintarConsentimentos(lista) {
    var alvo = VC.dom.el("[data-consentimentos]");
    if (!alvo) return;
    if (!lista.length) {
      VC.safe.render(alvo, ui.vazio({
        titulo: "Nenhum consentimento registrado",
        texto: "Registre o aceite com a versão do texto apresentado — sem versão, “aceitou” não diz nada depois."
      }));
      return;
    }
    VC.safe.render(alvo, html`<div class="slot-list">${html.juntar(lista.map(function (c) {
      return html`
        <div class="slot" style="grid-template-columns:1fr auto">
          <div>
            <div class="name">${c.tipoRotulo} <span class="soft">v${c.versao}</span></div>
            <div class="meta">aceito em ${fmt.dataLonga(c.aceitoEm)}${
              c.revogadoEm ? " · revogado em " + fmt.dataLonga(c.revogadoEm) : ""}</div>
          </div>
          <div class="slot__side">${c.vigente
            ? html`
              <span class="badge badge--ok">vigente</span>
              ${VC.session.pode("patients.write") ? html`
                <button class="btn btn--quiet btn--sm" type="button"
                        data-acao="revogar-consentimento"
                        data-consentimento="${c.id}">Revogar</button>` : html.vazio}`
            : html`<span class="badge badge--neutral">revogado</span>`}</div>
        </div>`;
    }))}</div>`);
  }

  function carregarPrivacidade(p) {
    VC.services.privacidade.consentimentos(p.id).then(pintarConsentimentos, function () {});
  }

  function abaPrivacidade(p) {
    var podePedido = VC.session.pode("data_requests.manage");
    return html`
      <div class="row" style="justify-content:space-between;margin-bottom:var(--sp-4);gap:var(--sp-2);flex-wrap:wrap">
        <b>Consentimentos</b>
        <span class="row" style="gap:var(--sp-2);flex-wrap:wrap">
          ${VC.session.pode("patients.write") ? html`
            <button class="btn btn--ghost btn--sm" type="button" data-acao="registrar-consentimento"
                    data-paciente="${p.id}" data-nome="${p.nome}">Registrar aceite</button>`
            : html.vazio}
          <button class="btn btn--ghost btn--sm" type="button" data-acao="baixar-pacote"
                  data-paciente="${p.id}" data-nome="${p.nome}">Baixar dados (JSON)</button>
          ${podePedido ? html`
            <button class="btn btn--ghost btn--sm" type="button" data-acao="abrir-pedido"
                    data-paciente="${p.id}" data-nome="${p.nome}">Registrar pedido</button>`
            : html.vazio}
        </span>
      </div>
      <div data-consentimentos>${ui.skeletonLinhas(2)}</div>

      ${p.anonimizadoEm ? html`
        <div class="notice" style="margin-top:var(--sp-5)">
          <div><b>Cadastro anonimizado.</b> O que identificava esta pessoa foi removido; a
          série de atendimentos continua, sem titular identificável.</div>
        </div>`
        : podePedido ? html`
        <div class="notice" style="margin-top:var(--sp-5)">
          <div><b>Anonimizar</b> remove nome, contato e nascimento <b>para sempre</b>, mantendo
          a série de atendimentos e os valores. É o caminho para um pedido de exclusão que
          esbarra na guarda obrigatória do prontuário.</div>
        </div>
        <div class="row" style="justify-content:flex-end;margin-top:var(--sp-3)">
          <button class="btn btn--ghost btn--sm" type="button" data-acao="anonimizar"
                  data-paciente="${p.id}" data-nome="${p.nome}">Anonimizar cadastro</button>
        </div>` : html.vazio}`;
  }

  function conteudoAba(aba, p) {
    if (aba === "historico") return abaHistorico(p);

    if (aba === "cadastro") {
      return html`
        <div class="grid grid--2">
          ${campo("Nome completo", ui.nomeCliente(p.nome, true))}
          ${campo("Situação", p.status === "ativo"
            ? html`<span class="badge badge--ok">Ativo</span>`
            : html`<span class="badge badge--neutral">Inativo</span>`)}
          ${campo("Telefone", html`<span class="private">${p.telefone}</span>`)}
          ${campo("E-mail", html`<span class="private">${p.email}</span>`)}
          ${campo("Nascimento", fmt.dataLonga(p.nascimento))}
          ${VC.session.pode("finance.read") ? campo("Valor da sessão", fmt.moeda(p.valorSessao)) : html.vazio}
        </div>
        <div class="notice" style="margin-top:var(--sp-4)">Edição de cadastro entra com o formulário e a validação, na etapa da API.</div>`;
    }

    if (aba === "financeiro") {
      var abertos = p.historico.filter(function (a) {
        return a.pagamento === "pendente" && new Date(a.inicio) < new Date();
      });
      var pago = VC.domain.metrics.soma(p.historico.filter(function (a) { return a.pagamento === "pago"; }));
      return html`
        <div class="grid grid--3" style="margin-bottom:var(--sp-4)">
          ${ui.stat({ rotulo: "Em aberto", valor: fmt.moeda(p.resumo.valorEmAberto), tom: "warn" })}
          ${ui.stat({ rotulo: "Pago no total", valor: fmt.moeda(pago), tom: "ok" })}
          ${ui.stat({ rotulo: "Valor da sessão", valor: fmt.moeda(p.valorSessao) })}
        </div>
        ${abertos.length ? html`<div class="slot-list">${html.juntar(abertos.map(function (a) {
          return html`
            <div class="slot" style="grid-template-columns:70px 1fr auto">
              <div class="slot__time"><b>${fmt.diaMes(a.inicio)}</b><span>${fmt.hora(a.inicio)}</span></div>
              <div class="slot__who"><div class="grow">
                <div class="name">${ui.rotuloDe(ui.STATUS_ATENDIMENTO, a.status)}</div>
                <div class="meta">${ui.rotuloDe(ui.MODALIDADE, a.modalidade)}</div>
              </div></div>
              <div class="slot__side">
                <b class="tabular">${fmt.moeda(a.valor)}</b>
                ${VC.session.pode("finance.write")
                  ? html`<button class="btn btn--ghost btn--sm" type="button" data-acao="marcar-pago"
                          data-atendimento="${a.id}" data-valor="${a.valor}"
                          data-nome="${p.nome}">Marcar pago</button>`
                  : html.vazio}
              </div>
            </div>`;
        }))}</div>` : ui.vazio({ titulo: "Nada em aberto", texto: "Todos os atendimentos estão quitados." })}`;
    }

    if (aba === "clinico") return abaClinica(p);
    if (aba === "privacidade") return abaPrivacidade(p);

    return abaDocumentos(p);
  }

  /* ---------------- Documentos ----------------
     Recibo é administrativo e declaração é clínica — e isso muda quem
     consegue abrir. A lista já vem filtrada pelo servidor; aqui a tela
     só deixa de oferecer o que não adianta pedir. */
  function cartaoDeDocumento(d) {
    return html`
      <div class="slot" style="grid-template-columns:1fr auto">
        <div>
          <div class="name">${d.tipoRotulo}${d.eClinico
            ? html` <span class="badge badge--info">clínico</span>`
            : html` <span class="badge badge--neutral">administrativo</span>`}</div>
          <div class="meta">${d.titulo} · ${fmt.dataLonga(d.criadoEm)} ·
            ${Math.max(1, Math.round(d.tamanho / 1024))} KB</div>
        </div>
        <div class="slot__side">${d.conteudoApagadoEm
          ? html`<span class="soft">apagado a pedido</span>`
          : html`<button class="btn btn--ghost btn--sm" type="button" data-acao="baixar-documento"
                   data-documento="${d.id}" data-nome="${d.nomeArquivo}">Baixar</button>`}
        </div>
      </div>`;
  }

  function pintarDocumentos(lista) {
    var alvo = VC.dom.el("[data-documentos]");
    if (!alvo) return;
    if (!lista.length) {
      VC.safe.render(alvo, ui.vazio({
        titulo: "Nenhum documento",
        texto: "Recibo, declaração de comparecimento e cópia do prontuário são emitidos pelos botões acima."
      }));
      return;
    }
    VC.safe.render(alvo, html`<div class="slot-list">${
      html.juntar(lista.map(cartaoDeDocumento))}</div>`);
  }

  function carregarDocumentos(p) {
    VC.services.documentos.listar(p.id).then(pintarDocumentos, function () {
      VC.safe.render(VC.dom.el("[data-documentos]"), ui.vazio({
        titulo: "Não foi possível carregar", texto: "Tente novamente em instantes."
      }));
    });
  }

  function abaDocumentos(p) {
    var podeRecibo = VC.session.pode("finance.write");
    var podeClinico = VC.session.pode("documents.write");
    var podeExportarProntuario = VC.session.pode("clinical_records.read");

    return html`
      <div class="row" style="justify-content:space-between;margin-bottom:var(--sp-4);gap:var(--sp-2);flex-wrap:wrap">
        <b>Documentos</b>
        <span class="row" style="gap:var(--sp-2);flex-wrap:wrap">
          ${podeRecibo ? html`
            <button class="btn btn--ghost btn--sm" type="button" data-acao="emitir-recibo"
                    data-paciente="${p.id}" data-nome="${p.nome}">Recibo</button>` : html.vazio}
          ${podeClinico ? html`
            <button class="btn btn--ghost btn--sm" type="button" data-acao="emitir-declaracao"
                    data-paciente="${p.id}" data-nome="${p.nome}">Declaração</button>
            <button class="btn btn--ghost btn--sm" type="button" data-acao="anexar-documento"
                    data-paciente="${p.id}">Anexar arquivo</button>` : html.vazio}
          ${podeExportarProntuario ? html`
            <button class="btn btn--ghost btn--sm" type="button" data-acao="exportar-prontuario"
                    data-paciente="${p.id}" data-nome="${p.nome}">Exportar prontuário</button>`
            : html.vazio}
        </span>
      </div>
      <div class="notice" style="margin-bottom:var(--sp-4)">
        <div>Todo arquivo vai <b>cifrado</b> para o disco do servidor. Declaração de
        comparecimento atesta que a pessoa esteve — e nada sobre o que foi tratado.</div>
      </div>
      <div data-documentos>${ui.skeletonLinhas(3)}</div>`;
  }

  function abasDisponiveis() {
    var abas = [
      { id: "historico", rotulo: "Histórico" },
      { id: "cadastro", rotulo: "Dados cadastrais" }
    ];
    if (VC.session.pode("finance.read")) abas.push({ id: "financeiro", rotulo: "Financeiro" });
    if (VC.session.pode("clinical_records.read")) abas.push({ id: "clinico", rotulo: t("record.many") });
    if (VC.session.pode("documents.read")) abas.push({ id: "documentos", rotulo: "Documentos" });
    if (VC.session.pode("data_requests.manage") || VC.session.pode("patients.write")) {
      abas.push({ id: "privacidade", rotulo: "Privacidade" });
    }
    return abas;
  }

  function fichaHTML(p) {
    var r = p.resumo;
    var abas = abasDisponiveis().map(function (a, i) {
      return html`<button class="tab" role="tab" aria-selected="${i === 0}" data-aba="${a.id}">${a.rotulo}</button>`;
    });

    return html`
      <div class="page-head">
        <div class="page-head__title">
          <a class="btn btn--quiet btn--sm" href="#/pacientes" style="margin-bottom:var(--sp-2)">← ${t("client.many")}</a>
          <div class="row" style="gap:var(--sp-4)">
            ${ui.avatar(p.nome, "lg")}
            <div>
              <h1>${ui.nomeCliente(p.nome, true)}</h1>
              <p>${fmt.capitalizar(p.frequencia)} · ${ui.rotuloDe(ui.MODALIDADE, p.modalidadePadrao)}${p.desde ? " · desde " + fmt.dataLonga(p.desde) : ""}</p>
            </div>
          </div>
        </div>
        <div class="page-head__actions">
          <button class="btn btn--ghost" type="button" data-acao="editar-paciente"
                  data-paciente="${p.id}">Editar cadastro</button>
          <button class="btn btn--accent" type="button" data-acao="novo-atendimento"
                  data-paciente="${p.id}">${t("appointment.new")}</button>
        </div>
      </div>

      <div class="grid grid--4">
        ${ui.stat({ rotulo: t("appointment.many"), valor: r.realizados, dica: "realizados no total" })}
        ${ui.stat({ rotulo: "Presença", valor: r.presenca === null ? "—" : fmt.porcento(r.presenca), dica: r.faltas + " falta(s)" })}
        ${ui.stat({ rotulo: "Próximo", valor: r.proximo ? fmt.dataRelativa(r.proximo) : "—",
                    dica: r.proximo ? fmt.hora(r.proximo) : "sem agendamento" })}
        ${VC.session.pode("finance.read")
          ? ui.stat({ rotulo: "Em aberto", valor: fmt.moeda(r.valorEmAberto), tom: r.valorEmAberto ? "warn" : "",
                      dica: (r.quantidadeEmAberto || 0) + " atendimento(s)" })
          : html.vazio}
      </div>

      <div class="tabs" role="tablist" style="margin-top:var(--sp-5)">${html.juntar(abas)}</div>
      <div data-series></div>
      <div class="card" data-painel-aba><div class="card__body">${abaHistorico(p)}</div></div>`;
  }

  function renderFicha() {
    return html`<div class="card"><div class="card__body">${ui.skeletonLinhas(5)}</div></div>`;
  }

  function mountFicha(params, alvo) {
    pessoaAberta = null;
    VC.services.pacientes.obter(params.id).then(function (p) {
      pessoaAberta = p;
      VC.shell.definirTitulo(fmt.nomeCurto(p.nome), "Ficha do " + t("client.one", true));
      VC.safe.render(alvo, fichaHTML(p));
      carregarSeries(p);

      VC.dom.on(alvo, "click", "[data-aba]", function (e, botao) {
        var aba = botao.getAttribute("data-aba");
        VC.dom.els("[data-aba]", alvo).forEach(function (b) { b.setAttribute("aria-selected", String(b === botao)); });
        VC.safe.render(VC.dom.el("[data-painel-aba]", alvo), html`<div class="card__body">${conteudoAba(aba, p)}</div>`);
        if (aba === "clinico") carregarProntuario(p);
        if (aba === "documentos") carregarDocumentos(p);
        if (aba === "privacidade") carregarPrivacidade(p);
      });

      /* Ler o conteúdo é uma chamada própria — e um evento próprio na
         trilha. Por isso o texto só aparece depois deste clique. */
      VC.dom.on(alvo, "click", "[data-ler-registro]", function (e, botao) {
        var id = botao.getAttribute("data-ler-registro");
        var caixa = VC.dom.el('[data-conteudo-de="' + id + '"]', alvo);
        if (!caixa) return;
        if (!caixa.hidden) {
          caixa.hidden = true;
          VC.safe.texto(botao, "Ler");
          return;
        }
        caixa.hidden = false;
        VC.safe.render(caixa, html`<p class="soft" style="margin-top:var(--sp-3)">Abrindo…</p>`);
        VC.services.prontuario.conteudo(id).then(function (c) {
          VC.safe.texto(botao, "Ocultar");
          VC.safe.render(caixa, html`
            <div class="registro" style="margin-top:var(--sp-3)">
              <div class="registro__texto">${c.conteudo}</div>
              <div class="cell-sub" style="margin-top:var(--sp-2)">
                versão ${c.versao} · escrita em ${fmt.dataLonga(c.criadoEm)} · leitura registrada
              </div>
            </div>`);
        }, function (erro) {
          VC.safe.render(caixa, html`
            <div class="campo__erro" role="alert" style="margin-top:var(--sp-3)">
              ${VC.form.mensagemDe(erro)}
            </div>`);
        });
      });
    }).catch(function (e) {
      /* Registro de outro tenant responde igual a registro inexistente. */
      VC.shell.definirTitulo("Não encontrado");
      VC.safe.render(alvo, ui.vazio({
        titulo: "Registro não encontrado",
        texto: "Ele pode ter sido removido, ou não pertence a esta conta.",
        acao: { href: "#/pacientes", rotulo: "Voltar para a lista" }
      }));
    });
  }

  VC.views = VC.views || {};
  VC.views.pacientes = { render: render, mount: mount };
  VC.views.pacienteFicha = {
    render: renderFicha,
    mount: mountFicha,
    /* Recarrega só a lista de registros, sem trocar de aba: depois de
       criar ou assinar, a pessoa continua onde estava. */
    recarregarProntuario: function () {
      if (pessoaAberta && VC.dom.el("[data-prontuario]")) carregarProntuario(pessoaAberta);
    }
  };
})(window);
