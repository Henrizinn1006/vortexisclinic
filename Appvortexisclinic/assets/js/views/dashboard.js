/* =============================================================
   INÍCIO — o dia do profissional em uma tela

   Esta view não calcula nada: todos os números chegam prontos de
   VC.services.dashboard, que por sua vez usa VC.domain.metrics.
   Aqui só existe apresentação.

   Conteúdo clínico não aparece: só operação (horário, presença,
   valores), com nome abreviado e sujeito ao modo discreto.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var html = VC.safe.html;
  var ui = VC.ui, fmt = VC.fmt, t = VC.terms.t;

  function saudacao() {
    var h = new Date().getHours();
    if (h < 12) return "Bom dia";
    if (h < 18) return "Boa tarde";
    return "Boa noite";
  }

  function esqueleto() {
    return html`
      <div class="page-head">
        <div class="page-head__title">
          <div class="skel skel--title" style="width:220px;height:22px"></div>
          <div class="skel skel--line skel--w40"></div>
        </div>
      </div>
      ${ui.skeletonStats(4)}
      <div class="cols-main" style="margin-top:var(--sp-5)">
        <div class="card"><div class="card__body">${ui.skeletonLinhas(5)}</div></div>
        <div class="card"><div class="card__body">${ui.skeletonLinhas(3)}</div></div>
      </div>`;
  }

  /* ---------- Blocos ---------- */
  function indicadores(d) {
    var f = d.financeiro;
    var dia = d.resumoDia;
    var podeFinanceiro = VC.session.pode("finance.read");

    return html`
      <div class="grid grid--4">
        ${ui.stat({
          rotulo: t("appointment.many") + " hoje",
          valor: dia.total,
          dica: dia.restantes ? dia.restantes + " ainda por vir" : "Agenda do dia concluída",
          href: "#/agenda"
        })}
        ${ui.stat({
          rotulo: t("client.many") + " ativos",
          valor: d.pacientes.ativos,
          dica: d.pacientes.inativos + " inativos",
          href: "#/pacientes"
        })}
        ${podeFinanceiro ? ui.stat({
          rotulo: "Recebido no mês",
          valor: fmt.moeda(f.recebido),
          dica: f.meta ? fmt.porcento(f.percentualMeta) + " da meta de " + fmt.moeda(f.meta) : "",
          tendencia: f.variacaoMesAnterior,
          tom: "ok",
          href: "#/financeiro"
        }) : html.vazio}
        ${podeFinanceiro ? ui.stat({
          rotulo: "A receber",
          valor: fmt.moeda(f.pendente),
          dica: d.pendencias.length + " " + t("appointment.many", true) + " em aberto",
          tom: d.pendencias.length ? "warn" : "",
          href: "#/pendencias"
        }) : html.vazio}
      </div>`;
  }

  function agendaDeHoje(d) {
    var lista = VC.domain.metrics.ativos(d.hoje);
    var dia = d.resumoDia;
    var corpo = lista.length
      ? html`<div class="slot-list">${html.juntar(lista.map(function (a) { return ui.linhaAtendimento(a); }))}</div>`
      : ui.vazio({
          titulo: "Nenhum " + t("appointment.one", true) + " hoje",
          texto: "Aproveite para revisar pendências ou registrar o que ficou pendente de sessões anteriores.",
          acao: { href: "#/agenda", rotulo: "Abrir agenda" }
        });

    return html`
      <div class="card">
        <div class="card__head">
          <h3>Hoje · ${fmt.dataLonga(new Date())}</h3>
          <a class="btn btn--quiet btn--sm" href="#/agenda">Ver agenda</a>
        </div>
        <div class="card__body" style="padding-top:var(--sp-2)">${corpo}</div>
        ${lista.length ? html`<div class="card__foot">
          Realizados: <b>${dia.realizados}</b> · Faltas: <b>${dia.faltas}</b> · Previsto no dia: <b>${fmt.moeda(dia.previsto)}</b>
        </div>` : html.vazio}
      </div>`;
  }

  function proximos(d) {
    var lista = d.proximos.filter(function (a) { return !fmt.mesmoDia(a.inicio, new Date()); }).slice(0, 4);
    var corpo = lista.length
      ? html`<div class="slot-list">${html.juntar(lista.map(function (a) {
          return ui.linhaAtendimento(a, { mostrarDia: true });
        }))}</div>`
      : ui.vazio({ titulo: "Sem " + t("appointment.many", true) + " futuros", texto: "Os próximos agendamentos aparecem aqui." });

    return html`
      <div class="card">
        <div class="card__head">
          <h3>Próximos ${t("appointment.many", true)}</h3>
          <a class="btn btn--quiet btn--sm" href="#/atendimentos">Ver todos</a>
        </div>
        <div class="card__body" style="padding-top:var(--sp-2)">${corpo}</div>
      </div>`;
  }

  function miniNumero(rotulo, valor, tom) {
    return html`
      <div style="border:1px solid var(--border);border-radius:var(--r-sm);padding:var(--sp-3)">
        <div class="stat__label">${rotulo}</div>
        <div style="font-size:var(--fs-lg);font-weight:800;${tom === "danger" ? "color:var(--danger)" : ""}">${valor}</div>
      </div>`;
  }

  function semana(d) {
    var s = d.semana;
    var itens = s.dias.map(function (dia) {
      return {
        rotulo: fmt.diaSemana(dia.data),
        valor: dia.total,
        destaque: dia.hoje,
        titulo: fmt.diaMes(dia.data) + ": " + dia.total
      };
    });

    return html`
      <div class="card">
        <div class="card__head">
          <h3>Resumo da semana</h3>
          <span class="muted" style="font-size:var(--fs-xs)">${fmt.diaMes(s.inicio)} – ${fmt.diaMes(s.fim)}</span>
        </div>
        <div class="card__body">
          ${ui.barras(itens, { descricao: "Atendimentos por dia na semana" })}
          <div class="grid" style="grid-template-columns:repeat(3,minmax(0,1fr));margin-top:var(--sp-4);gap:var(--sp-2)">
            ${miniNumero("Agendados", s.agendados)}
            ${miniNumero("Realizados", s.realizados)}
            ${miniNumero("Faltas", s.faltas, s.faltas ? "danger" : "")}
          </div>
          ${s.presenca !== null ? html`
            <div style="margin-top:var(--sp-4)">
              <div class="row row--between" style="margin-bottom:6px">
                <span class="muted" style="font-size:var(--fs-xs)">Presença na semana</span>
                <b style="font-size:var(--fs-sm)">${fmt.porcento(s.presenca)}</b>
              </div>
              <div class="meter meter--ok"><i style="width:${s.presenca}%"></i></div>
            </div>` : html.vazio}
        </div>
      </div>`;
  }

  function pendencias(d) {
    if (!VC.session.pode("finance.read")) return html.vazio;
    var lista = d.pendencias.slice(0, 4);
    var total = VC.domain.metrics.totalEmAberto(d.pendencias);

    var corpo = lista.length
      ? html`<div class="slot-list">${html.juntar(lista.map(function (a) {
          return html`
            <div class="slot" style="grid-template-columns:1fr auto">
              <div class="slot__who">
                ${ui.avatar(a.paciente.nome, "sm")}
                <div class="grow">
                  <div class="name">${ui.nomeCliente(a.paciente.nome)}</div>
                  <div class="meta">${fmt.diaMes(a.inicio)} · ${a.diasEmAberto} dias em aberto</div>
                </div>
              </div>
              <div class="slot__side"><b class="tabular">${fmt.moeda(a.valor)}</b></div>
            </div>`;
        }))}</div>`
      : ui.vazio({ titulo: "Nada em aberto", texto: "Todos os atendimentos realizados estão pagos." });

    return html`
      <div class="card">
        <div class="card__head">
          <h3>Pagamentos pendentes</h3>
          ${d.pendencias.length ? html`<a class="btn btn--quiet btn--sm" href="#/pendencias">Ver todas</a>` : html.vazio}
        </div>
        <div class="card__body" style="padding-top:var(--sp-2)">${corpo}</div>
        ${total ? html`<div class="card__foot">Total em aberto: <b>${fmt.moeda(total)}</b></div>` : html.vazio}
      </div>`;
  }

  function atalhos() {
    return html`
      <div class="card"><div class="card__body stack" style="gap:var(--sp-2)">
        <h3 style="font-size:var(--fs-base);margin-bottom:var(--sp-1)">Atalhos</h3>
        <button class="btn btn--accent btn--block" type="button" data-acao="novo-paciente">${t("client.new")}</button>
        <button class="btn btn--ghost btn--block" type="button" data-acao="novo-atendimento">${t("appointment.new")}</button>
        ${VC.session.pode("clinical_records.write")
          ? html`<a class="btn btn--quiet btn--block" href="#/anotacoes">${t("record.new")}</a>`
          : html.vazio}
      </div></div>`;
  }

  function avisoPrivacidade() {
    return html`
      <div class="notice" style="margin-top:var(--sp-5)">
        <div><b>Privacidade:</b> esta tela mostra apenas informação administrativa — horário, presença e valores.
        ${t("record.many")} ficam na área protegida do ${t("client.one", true)}, com permissão própria, e o
        <b>modo discreto</b> (no topo) borra os nomes quando alguém puder ver sua tela.</div>
      </div>`;
  }

  /* ---------- Ciclo da view ---------- */
  function render() { return esqueleto(); }

  function mount(params, alvo) {
    VC.shell.definirTitulo("Início", fmt.dataLonga(new Date()));

    VC.services.dashboard.carregar().then(function (d) {
      var prof = VC.session.atual();
      var diaSemana = new Intl.DateTimeFormat("pt-BR", { weekday: "long" }).format(new Date());

      VC.safe.render(alvo, html`
        <div class="page-head">
          <div class="page-head__title">
            <h1>${saudacao()}, ${prof.nome.split(" ")[0]}</h1>
            <p>${fmt.capitalizar(diaSemana)}, ${fmt.dataLonga(new Date())}</p>
          </div>
          <div class="page-head__actions">
            <button class="btn btn--ghost" type="button" data-acao="novo-paciente">${t("client.new")}</button>
            <button class="btn btn--accent" type="button" data-acao="novo-atendimento">${t("appointment.new")}</button>
          </div>
        </div>

        ${indicadores(d)}

        <div class="cols-main" style="margin-top:var(--sp-5)">
          <div class="stack">${agendaDeHoje(d)}${proximos(d)}</div>
          <div class="stack">${semana(d)}${pendencias(d)}${atalhos()}</div>
        </div>

        ${avisoPrivacidade()}`);

      VC.shell.atualizarContadores();
    }).catch(function (e) {
      VC.safe.render(alvo, ui.vazio({
        titulo: "Não foi possível carregar o painel",
        texto: e && e.code === "nao_encontrado"
          ? "Esta conta não está mais disponível para o seu usuário."
          : "Recarregue a página. Se persistir, avise o suporte."
      }));
      VC.toast.erro("Falha ao carregar", e && e.message);
    });
  }

  VC.views = VC.views || {};
  VC.views.dashboard = { render: render, mount: mount };
})(window);
