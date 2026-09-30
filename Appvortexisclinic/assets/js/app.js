/* =============================================================
   Ponto de entrada: rotas, ações globais e PWA.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var html = VC.safe.html;

  /* Envolve uma view com a checagem de permissão.
     É proteção de interface: evita abrir tela inútil e dá uma
     mensagem decente. A negativa que vale é a do servidor, que
     repete a verificação em cada requisição. */
  function protegida(view, permissao) {
    return {
      render: function (params) {
        return VC.session.pode(permissao) ? view.render(params) : VC.views.semPermissao.render(params);
      },
      mount: function (params, alvo) {
        if (!VC.session.pode(permissao)) return VC.views.semPermissao.mount(params, alvo);
        return view.mount(params, alvo);
      }
    };
  }

  /* ---------------- Rotas ---------------- */
  function registrarRotas() {
    var r = VC.router;
    var P = VC.types.PERMISSIONS;

    r.add("/", VC.views.dashboard);
    r.add("/agenda", protegida(VC.views.agenda, P.AGENDA_READ));
    r.add("/pacientes", protegida(VC.views.pacientes, P.PATIENTS_READ));
    r.add("/pacientes/:id", protegida(VC.views.pacienteFicha, P.PATIENTS_READ));
    r.add("/atendimentos", protegida(VC.views.atendimentos, P.APPOINTMENTS_READ));
    r.add("/financeiro", protegida(VC.views.financeiro, P.FINANCE_READ));
    r.add("/pendencias", protegida(VC.views.pendencias, P.FINANCE_READ));
    r.add("/anotacoes", protegida(VC.views.anotacoes, P.CLINICAL_RECORDS_READ));
    r.add("/relatorios", VC.views.relatorios);
    r.add("/configuracoes", VC.views.configuracoes);   // ler é de todo mundo; gravar, não
    r.add("/equipe", protegida(VC.views.equipe, P.MEMBERS_MANAGE));
    r.add("/privacidade", protegida(VC.views.privacidade, P.DATA_REQUESTS_MANAGE));
    r.add("/perfil", VC.views.perfil);
    r.add("/404", VC.views.naoEncontrada);

    r.antesDeEntrar(function (rota) {
      /* Quando a autenticação existir, a checagem mora aqui:
         if (!VC.session.autenticado()) return r.navegar("/entrar"); */
      VC.shell.marcarAtivo(rota.caminho.split("?")[0]);
    });

    r.aposEntrar(function () {
      global.scrollTo({ top: 0, behavior: "instant" in global ? "instant" : "auto" });
      VC.shell.fecharMenu();
      var main = VC.dom.el("[data-outlet]");
      if (main) main.setAttribute("tabindex", "-1");
    });
  }

  /* ---------------- Ações que valem em qualquer tela ---------------- */

  /* Depois de gravar, a tela atual é redesenhada com o dado novo.
     É o caminho honesto: o painel não adivinha o resultado, ele
     pergunta de novo ao servidor. */
  function recarregarTela() {
    VC.router.resolver();
    VC.shell.atualizarContadores();
  }

  function formularioDePessoa(pessoa) {
    var f = VC.form;
    var t = VC.terms.t;
    pessoa = pessoa || {};

    VC.modal.abrir({
      titulo: pessoa.id ? "Editar cadastro" : t("client.new"),
      subtitulo: "Dados administrativos. Conteúdo clínico tem área e permissão próprias.",
      corpo: html`
        ${f.erro("")}
        <div class="grid grid--2">
          ${f.campo({ nome: "nome", rotulo: "Nome completo", valor: pessoa.nome })}
          ${f.campo({ nome: "telefone", rotulo: "Telefone", valor: pessoa.telefone, obrigatorio: false })}
          ${f.campo({ nome: "email", rotulo: "E-mail", tipo: "email", valor: pessoa.email, obrigatorio: false })}
          ${f.campo({ nome: "nascimento", rotulo: "Nascimento", tipo: "date",
                      valor: pessoa.nascimento, obrigatorio: false })}
          ${f.campo({ nome: "frequencia", rotulo: "Frequência", tipo: "select",
                      valor: pessoa.frequencia || "semanal", opcoes: [
                        { valor: "semanal", rotulo: "Semanal" },
                        { valor: "quinzenal", rotulo: "Quinzenal" },
                        { valor: "mensal", rotulo: "Mensal" },
                        { valor: "irregular", rotulo: "Irregular" }
                      ] })}
          ${f.campo({ nome: "modalidade", rotulo: "Modalidade padrão", tipo: "select",
                      valor: pessoa.modalidadePadrao || "presencial", opcoes: [
                        { valor: "presencial", rotulo: "Presencial" },
                        { valor: "online", rotulo: "Online" }
                      ] })}
          ${f.campo({ nome: "valorSessao", rotulo: "Valor da sessão", tipo: "number", passo: "0.01",
                      minimo: "0", valor: pessoa.valorSessao, obrigatorio: false,
                      dica: "Usado como padrão ao agendar" })}
          ${f.campo({ nome: "desde", rotulo: "Acompanha desde", tipo: "date",
                      valor: pessoa.desde, obrigatorio: false })}
        </div>
        ${f.campo({ nome: "observacao", rotulo: "Observação administrativa", tipo: "textarea",
                    valor: pessoa.observacao, obrigatorio: false,
                    dica: "Preferência de horário, contato do responsável. Nada clínico." })}`,
      cancelar: "Cancelar",
      confirmar: pessoa.id ? "Salvar" : "Cadastrar",
      aoConfirmar: function (caixa) {
        var dados = VC.form.valores(caixa);
        if (!dados.nome || dados.nome.length < 2) {
          return VC.form.mostrarErro(caixa, "Informe o nome completo.");
        }
        VC.form.mostrarErro(caixa, "");

        var acao = pessoa.id
          ? VC.services.pacientes.atualizar(pessoa.id, dados)
          : VC.services.pacientes.criar(dados);

        acao.then(function (salvo) {
          VC.modal.fechar();
          VC.toast.ok(pessoa.id ? "Cadastro atualizado" : t("client.one") + " cadastrado", salvo.nome);
          recarregarTela();
        }, function (e) {
          VC.form.mostrarErro(caixa, VC.form.mensagemDe(e));
        });
      }
    });
  }

  function formularioDeAtendimento(pessoaId) {
    var f = VC.form;
    var t = VC.terms.t;

    /* A lista de pessoas vem da API — e já vem filtrada pela conta
       e pelo escopo de quem está logado. */
    VC.services.pacientes.listar({ status: "ativo" }).then(function (pessoas) {
      if (!pessoas.length) {
        VC.modal.abrir({
          titulo: t("appointment.new"),
          corpo: html`<div class="notice"><div>Cadastre uma pessoa antes de agendar o primeiro
            ${t("appointment.one", true)}.</div></div>`,
          cancelar: "Entendi"
        });
        return;
      }

      var agora = new Date();
      agora.setMinutes(0, 0, 0);
      agora.setHours(agora.getHours() + 1);
      var padrao = VC.fmt.paraCampoDataHora(agora);

      /* O modal já está no DOM quando `abrir` volta, então o listener
         do "repetir" é ligado logo depois. */
      global.setTimeout(function () {
        VC.dom.on(document, "change", "[data-repetir]", function (e, caixinha) {
          var bloco = VC.dom.el("[data-recorrencia]");
          if (bloco) bloco.hidden = !caixinha.checked;
        });
      }, 0);

      VC.modal.abrir({
        titulo: t("appointment.new"),
        subtitulo: "O servidor confere conflito de horário antes de gravar.",
        corpo: html`
          ${f.erro("")}
          <div class="grid grid--2">
            ${f.campo({ nome: "pacienteId", rotulo: t("client.one"), tipo: "select",
                        valor: pessoaId || pessoas[0].id,
                        opcoes: pessoas.map(function (p) {
                          return { valor: p.id, rotulo: p.nome };
                        }) })}
            ${f.campo({ nome: "inicio", rotulo: "Início", tipo: "datetime-local", valor: padrao })}
            ${f.campo({ nome: "duracaoMin", rotulo: "Duração (min)", tipo: "number",
                        valor: 50, minimo: "5" })}
            ${f.campo({ nome: "modalidade", rotulo: "Modalidade", tipo: "select",
                        valor: "presencial", opcoes: [
                          { valor: "presencial", rotulo: "Presencial" },
                          { valor: "online", rotulo: "Online" }
                        ] })}
            ${f.campo({ nome: "valor", rotulo: "Valor", tipo: "number", passo: "0.01", minimo: "0",
                        obrigatorio: false, dica: "Vazio usa o valor padrão da pessoa" })}
          </div>
          ${f.campo({ nome: "observacao", rotulo: "Observação", tipo: "textarea",
                      obrigatorio: false, linhas: 2,
                      dica: "Operacional (remarcou, chegou atrasado). Nada clínico." })}

          <label class="campo" style="flex-direction:row;align-items:center;gap:var(--sp-2);margin-top:var(--sp-3)">
            <input type="checkbox" data-repetir style="width:auto">
            <span style="margin:0">Repetir — cria a agenda das próximas sessões de uma vez</span>
          </label>
          <div data-recorrencia hidden>
            <div class="grid grid--2">
              ${f.campo({ nome: "frequencia", rotulo: "Frequência", tipo: "select",
                          valor: "weekly", opcoes: [
                            { valor: "weekly", rotulo: "Semanal" },
                            { valor: "biweekly", rotulo: "Quinzenal" },
                            { valor: "monthly", rotulo: "Mensal" }
                          ] })}
              ${f.campo({ nome: "ocorrencias", rotulo: "Quantas sessões", tipo: "number",
                          valor: 8, minimo: "1",
                          dica: "no máximo 52 — recorrência infinita vira agenda que ninguém limpa" })}
            </div>
            <div class="notice"><div>Horário já ocupado ou bloqueado é <b>pulado</b>, e você
            fica sabendo quais. As outras sessões são criadas normalmente.</div></div>
          </div>`,
        cancelar: "Cancelar",
        confirmar: "Agendar",
        aoConfirmar: function (caixa) {
          var dados = VC.form.valores(caixa);
          var inicio = VC.form.dataHora(dados.inicio);
          if (!inicio) return VC.form.mostrarErro(caixa, "Informe data e horário.");
          VC.form.mostrarErro(caixa, "");

          var repetir = VC.dom.el("[data-repetir]", caixa);
          var comum = {
            pacienteId: dados.pacienteId,
            inicio: inicio,
            duracaoMin: Number(dados.duracaoMin || 50),
            modalidade: dados.modalidade,
            valor: dados.valor,
            observacao: dados.observacao
          };

          if (repetir && repetir.checked) {
            VC.services.agenda.criarSerie(Object.assign({
              frequencia: dados.frequencia,
              ocorrencias: dados.ocorrencias
            }, comum)).then(function (r) {
              VC.modal.fechar();
              VC.toast.ok(r.criados.length + " sessões agendadas",
                          r.serie.frequenciaRotulo);
              if (r.conflitos.length) janelaDeConflitos(r);
              recarregarTela();
            }, function (e) {
              VC.form.mostrarErro(caixa, VC.form.mensagemDe(e));
            });
            return;
          }

          VC.services.atendimentos.registrar(comum).then(function (a) {
            VC.modal.fechar();
            VC.toast.ok(t("appointment.one") + " agendado",
                        a.paciente.nome + " · " + VC.fmt.dataHora(a.inicio));
            recarregarTela();
          }, function (e) {
            VC.form.mostrarErro(caixa, VC.form.mensagemDe(e));
          });
        }
      });
    }, function (e) {
      VC.toast.erro("Não foi possível abrir o formulário", VC.form.mensagemDe(e));
    });
  }

  /* ---------- Financeiro ---------- */
  function formularioDeBaixa(atendimentoId, valorSugerido, nome) {
    var f = VC.form;

    VC.modal.abrir({
      titulo: "Registrar pagamento",
      subtitulo: nome ? nome : "",
      corpo: html`
        ${f.erro("")}
        <div class="grid grid--2">
          ${f.campo({ nome: "metodo", rotulo: "Forma", tipo: "select", valor: "pix", opcoes: [
            { valor: "pix", rotulo: "Pix" },
            { valor: "card", rotulo: "Cartão" },
            { valor: "cash", rotulo: "Dinheiro" },
            { valor: "transfer", rotulo: "Transferência" },
            { valor: "other", rotulo: "Outro" }
          ] })}
          ${f.campo({ nome: "pagoEm", rotulo: "Quando entrou", tipo: "datetime-local",
                      valor: VC.fmt.paraCampoDataHora(new Date()),
                      dica: "É esta data que conta no mês" })}
          ${f.campo({ nome: "valor", rotulo: "Valor recebido", tipo: "number", passo: "0.01",
                      minimo: "0", valor: valorSugerido || "", obrigatorio: false,
                      dica: "Vazio usa o que falta. Valor menor registra pagamento parcial." })}
        </div>
        ${f.campo({ nome: "observacao", rotulo: "Observação", obrigatorio: false,
                    dica: "Ex.: pago em duas parcelas, recebido pela recepção" })}
        <div class="notice"><div>Recebeu só uma parte? Informe o valor: o atendimento
        continua em aberto pelo resto, e a cobrança não some.</div></div>`,
      cancelar: "Cancelar",
      confirmar: "Registrar",
      aoConfirmar: function (caixa) {
        var dados = VC.form.valores(caixa);
        var quando = VC.form.dataHora(dados.pagoEm);
        if (!quando) return VC.form.mostrarErro(caixa, "Informe quando o pagamento entrou.");
        VC.form.mostrarErro(caixa, "");

        VC.services.financeiro.registrarPagamento(atendimentoId, {
          metodo: dados.metodo,
          pagoEm: quando,
          valor: dados.valor,
          observacao: dados.observacao
        }).then(function (p) {
          VC.modal.fechar();
          VC.toast.ok("Pagamento registrado", VC.fmt.moeda(p.valor) + " · " + p.metodoRotulo);
          recarregarTela();
        }, function (e) {
          VC.form.mostrarErro(caixa, VC.form.mensagemDe(e));
        });
      }
    });
  }

  function confirmarComMotivo(opcoes) {
    var f = VC.form;
    VC.modal.abrir({
      titulo: opcoes.titulo,
      subtitulo: opcoes.subtitulo,
      corpo: html`
        ${f.erro("")}
        ${opcoes.aviso ? html`<div class="notice"><div>${opcoes.aviso}</div></div>` : html.vazio}
        ${f.campo({ nome: "motivo", rotulo: "Motivo", tipo: "textarea", linhas: 2,
                    obrigatorio: false, dica: "Fica registrado junto com a operação" })}`,
      cancelar: "Cancelar",
      confirmar: opcoes.confirmar,
      aoConfirmar: function (caixa) {
        var motivo = VC.form.valores(caixa).motivo;
        VC.form.mostrarErro(caixa, "");
        opcoes.acao(motivo).then(function () {
          VC.modal.fechar();
          VC.toast.ok(opcoes.sucesso, "");
          recarregarTela();
        }, function (e) {
          VC.form.mostrarErro(caixa, VC.form.mensagemDe(e));
        });
      }
    });
  }

  /* ---------------- prontuário ----------------
     Três cuidados que valem para tudo daqui para baixo:
     conteúdo clínico é texto puro (nada de HTML, nem na ida nem na
     volta); nota assinada só muda com motivo; e depois de gravar,
     recarregamos apenas a lista de registros, para a pessoa não
     perder a aba em que estava. */
  function atualizarProntuario() {
    if (VC.views.pacienteFicha && VC.views.pacienteFicha.recarregarProntuario) {
      VC.views.pacienteFicha.recarregarProntuario();
    } else {
      recarregarTela();
    }
  }

  function formularioDeRegistro(pacienteId, nome) {
    var f = VC.form;
    VC.modal.abrir({
      titulo: "Novo registro clínico",
      subtitulo: nome || "",
      corpo: html`
        ${f.erro("")}
        <div class="grid grid--2">
          ${f.campo({ nome: "tipo", rotulo: "Tipo", tipo: "select", valor: "session", opcoes: [
            { valor: "session", rotulo: "Evolução" },
            { valor: "assessment", rotulo: "Avaliação" },
            { valor: "plan", rotulo: "Plano terapêutico" },
            { valor: "note", rotulo: "Anotação" }
          ] })}
          ${f.campo({ nome: "ocorridoEm", rotulo: "Quando aconteceu", tipo: "datetime-local",
                      valor: VC.fmt.paraCampoDataHora(new Date()) })}
        </div>
        ${f.campo({ nome: "conteudo", rotulo: "Registro", tipo: "textarea", linhas: 10,
                    dica: "Texto puro. O conteúdo é cifrado antes de ir para o banco." })}`,
      cancelar: "Cancelar",
      confirmar: "Salvar registro",
      aoConfirmar: function (caixa) {
        var dados = VC.form.valores(caixa);
        if (!dados.conteudo) return VC.form.mostrarErro(caixa, "Escreva o registro.");
        var quando = VC.form.dataHora(dados.ocorridoEm);
        if (!quando) return VC.form.mostrarErro(caixa, "Informe quando aconteceu.");
        VC.form.mostrarErro(caixa, "");

        VC.services.prontuario.criar(pacienteId, {
          conteudo: dados.conteudo, tipo: dados.tipo, ocorridoEm: quando
        }).then(function (n) {
          VC.modal.fechar();
          VC.toast.ok("Registro salvo", n.tipoRotulo + " · versão " + n.versaoAtual);
          atualizarProntuario();
        }, function (e) {
          VC.form.mostrarErro(caixa, VC.form.mensagemDe(e));
        });
      }
    });
  }

  function formularioDeEdicaoDeRegistro(notaId, assinada) {
    VC.services.prontuario.conteudo(notaId).then(function (atual) {
      var f = VC.form;
      VC.modal.abrir({
        titulo: assinada ? "Adendo ao registro" : "Editar registro",
        subtitulo: "versão atual: " + atual.versao,
        corpo: html`
          ${f.erro("")}
          <div class="notice"><div>
            ${assinada
              ? html.estatico("A nota está assinada. A correção entra como <b>adendo</b>, com motivo, e a versão anterior continua no histórico.")
              : html.estatico("Salvar cria a <b>próxima versão</b>. Nada é sobrescrito.")}
          </div></div>
          ${f.campo({ nome: "conteudo", rotulo: "Registro", tipo: "textarea", linhas: 12,
                      valor: atual.conteudo })}
          ${f.campo({ nome: "motivo", rotulo: "Motivo do adendo", obrigatorio: !assinada ? false : true,
                      dica: assinada ? "Obrigatório: fica junto da versão nova"
                                     : "Opcional" })}`,
        cancelar: "Cancelar",
        confirmar: "Salvar versão",
        aoConfirmar: function (caixa) {
          var dados = VC.form.valores(caixa);
          if (!dados.conteudo) return VC.form.mostrarErro(caixa, "O registro não pode ficar vazio.");
          if (assinada && !dados.motivo) {
            return VC.form.mostrarErro(caixa, "Nota assinada só aceita adendo com motivo.");
          }
          VC.form.mostrarErro(caixa, "");

          VC.services.prontuario.salvar(notaId, {
            conteudo: dados.conteudo, motivo: dados.motivo
          }).then(function (n) {
            VC.modal.fechar();
            VC.toast.ok("Registro salvo", "versão " + n.versaoAtual);
            atualizarProntuario();
          }, function (e) {
            VC.form.mostrarErro(caixa, VC.form.mensagemDe(e));
          });
        }
      });
    }, function (e) {
      VC.toast.erro("Não foi possível abrir o registro", VC.form.mensagemDe(e));
    });
  }

  function janelaDaTrilha(pacienteId, nome) {
    VC.services.prontuario.trilha(pacienteId).then(function (linhas) {
      var corpo = !linhas.length
        ? html`<p class="soft">Nenhum acesso registrado ainda.</p>`
        : html`<div class="slot-list">${html.juntar(linhas.map(function (l) {
            return html`
              <div class="slot" style="grid-template-columns:1fr auto">
                <div>
                  <div class="name">${l.quem || "—"} · ${l.acao}</div>
                  <div class="meta">${VC.fmt.dataLonga(l.quando)} · ${VC.fmt.hora(l.quando)}${
                    l.motivo ? " · " + l.motivo : ""}</div>
                </div>
                <div class="slot__side">${l.permitido
                  ? html`<span class="badge badge--ok">permitido</span>`
                  : html`<span class="badge badge--danger">recusado</span>`}</div>
              </div>`;
          }))}</div>`;

      VC.modal.abrir({
        titulo: "Quem acessou o prontuário",
        subtitulo: nome || "",
        corpo: html`
          <div class="notice"><div>Auditoria mostra <b>quem abriu</b>, não o que estava escrito.
          Tentativas recusadas também aparecem — são elas que denunciam acesso indevido.</div></div>
          <div style="margin-top:var(--sp-4)">${corpo}</div>`,
        cancelar: "Fechar"
      });
    }, function (e) {
      VC.toast.erro("Não foi possível abrir a trilha", VC.form.mensagemDe(e));
    });
  }

  /* ---------------- equipe ----------------
     O link do convite aparece uma vez, aqui, com botão de copiar.
     Ele não volta em listagem nenhuma: o servidor guarda só o hash
     do token. Quando o envio de e-mail existir, o link vai direto
     para a pessoa e some desta tela. */
  function atualizarEquipe() {
    if (VC.views.equipe && VC.views.equipe.recarregar) VC.views.equipe.recarregar();
    else recarregarTela();
  }

  function copiar(texto, botao) {
    function avisar() {
      VC.toast.ok("Link copiado", "Cole onde a pessoa vai receber");
      if (botao) VC.safe.texto(botao, "Copiado");
    }
    if (global.navigator && navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(texto).then(avisar, function () {
        VC.toast.erro("Não foi possível copiar", "Selecione o link e copie à mão");
      });
      return;
    }
    VC.toast.erro("Cópia indisponível neste navegador", "Selecione o link e copie à mão");
  }

  function janelaDoLink(convite) {
    VC.modal.abrir({
      titulo: "Convite criado",
      subtitulo: convite.email,
      corpo: html`
        <div class="notice"><div><b>Copie agora.</b> Este link aparece uma vez só —
        o servidor guarda apenas o resumo dele. Se fechar sem copiar, é só revogar
        e convidar de novo.</div></div>
        <label class="campo" style="margin-top:var(--sp-4)">
          <span>Link do convite</span>
          <input type="text" value="${convite.link}" readonly data-link-convite
                 onclick="this.select()">
          <small>Expira em 7 dias. Vale para ${convite.email} e mais ninguém.</small>
        </label>`,
      cancelar: "Fechar",
      confirmar: "Copiar link",
      aoConfirmar: function (caixa) {
        var campo = VC.dom.el("[data-link-convite]", caixa);
        copiar(campo ? campo.value : convite.link, VC.dom.el("[data-confirmar]", caixa));
      }
    });
  }

  /* O catálogo de profissões vem da API e não muda durante a
     sessão: uma busca por vida de painel basta. */
  var profissoesConhecidas = null;

  function profissoes() {
    if (profissoesConhecidas) return Promise.resolve(profissoesConhecidas);
    return VC.api.get("/professions").then(function (lista) {
      profissoesConhecidas = lista || [];
      return profissoesConhecidas;
    }, function () { return []; });
  }

  function formularioDeConvite(lista) {
    var f = VC.form;
    var papeis = VC.views.equipe.papeis();

    VC.modal.abrir({
      titulo: "Convidar pessoa",
      subtitulo: "O acesso é definido agora — aceitar não escolhe nada",
      corpo: html`
        ${f.erro("")}
        ${f.campo({ nome: "email", rotulo: "E-mail", tipo: "email",
                    dica: "O convite vale só para este endereço" })}
        ${f.campo({ nome: "papel", rotulo: "Papel", tipo: "select", valor: "PROFESSIONAL",
                    opcoes: papeis.map(function (p) {
                      return { valor: p.valor, rotulo: p.rotulo };
                    }) })}
        ${f.campo({ nome: "escopo", rotulo: "Enxerga", tipo: "select", valor: "own", opcoes: [
          { valor: "own", rotulo: "Só as pessoas que ela atende" },
          { valor: "all", rotulo: "Toda a conta" }
        ], dica: "Vale para cadastro, agenda e financeiro — não para prontuário alheio" })}
        ${f.campo({ nome: "profissao", rotulo: "Profissão", tipo: "select", valor: "",
                    obrigatorio: false, opcoes: [{ valor: "", rotulo: "Não atende" }]
                      .concat((lista || []).map(function (p) {
                        return { valor: p.slug, rotulo: p.nome };
                      })),
                    dica: "Quem atende ganha perfil profissional e prontuário do que é seu" })}
        ${f.campo({ nome: "mensagem", rotulo: "Recado (opcional)", tipo: "textarea", linhas: 2,
                    obrigatorio: false })}`,
      cancelar: "Cancelar",
      confirmar: "Criar convite",
      aoConfirmar: function (caixa) {
        var dados = VC.form.valores(caixa);
        if (!dados.email) return VC.form.mostrarErro(caixa, "Informe o e-mail.");
        VC.form.mostrarErro(caixa, "");

        VC.services.equipe.convidar({
          email: dados.email, papel: dados.papel, escopo: dados.escopo,
          profissao: dados.profissao, mensagem: dados.mensagem
        }).then(function (convite) {
          VC.modal.fechar();
          atualizarEquipe();
          janelaDoLink(convite);
        }, function (e) {
          VC.form.mostrarErro(caixa, VC.form.mensagemDe(e));
        });
      }
    });
  }

  function formularioDeAcesso(botao) {
    var f = VC.form;
    var id = botao.getAttribute("data-membro");
    var papeis = VC.views.equipe.papeis();
    var papelAtual = botao.getAttribute("data-papel");
    var suspenso = botao.getAttribute("data-status") === "suspended";

    VC.modal.abrir({
      titulo: "Acesso de " + botao.getAttribute("data-nome"),
      corpo: html`
        ${f.erro("")}
        ${f.campo({ nome: "papel", rotulo: "Papel", tipo: "select", valor: papelAtual,
                    opcoes: papeis.map(function (p) {
                      return { valor: p.valor, rotulo: p.rotulo };
                    }) })}
        ${f.campo({ nome: "escopo", rotulo: "Enxerga", tipo: "select",
                    valor: botao.getAttribute("data-escopo"), opcoes: [
                      { valor: "own", rotulo: "Só as pessoas que ela atende" },
                      { valor: "all", rotulo: "Toda a conta" }
                    ] })}
        ${f.campo({ nome: "status", rotulo: "Situação", tipo: "select",
                    valor: suspenso ? "suspended" : "active", opcoes: [
                      { valor: "active", rotulo: "Ativo" },
                      { valor: "suspended", rotulo: "Suspenso — perde o acesso na hora" }
                    ] })}
        <div class="notice" style="margin-top:var(--sp-3)"><div>Suspender tira o acesso
        imediatamente, e o histórico do que a pessoa fez continua.</div></div>`,
      cancelar: "Cancelar",
      confirmar: "Salvar",
      aoConfirmar: function (caixa) {
        var dados = VC.form.valores(caixa);
        VC.form.mostrarErro(caixa, "");
        VC.services.equipe.alterar(id, dados).then(function () {
          VC.modal.fechar();
          VC.toast.ok("Acesso atualizado", "");
          atualizarEquipe();
        }, function (e) {
          VC.form.mostrarErro(caixa, VC.form.mensagemDe(e));
        });
      }
    });
  }

  /* ---------------- agenda: recorrência e bloqueios ---------------- */
  function janelaDeConflitos(r) {
    VC.modal.abrir({
      titulo: r.criados.length + " sessões criadas",
      subtitulo: r.conflitos.length + " horário(s) ficaram de fora",
      corpo: html`
        <div class="notice"><div>A recorrência não foi recusada por causa deles: as outras
        sessões estão marcadas. Estes horários precisam de decisão sua.</div></div>
        <div class="slot-list" style="margin-top:var(--sp-4)">${html.juntar(
          r.conflitos.map(function (c) {
            return html`
              <div class="slot" style="grid-template-columns:1fr auto">
                <div>
                  <div class="name">${VC.fmt.dataLonga(c.inicio)} · ${VC.fmt.hora(c.inicio)}</div>
                  <div class="meta">${c.motivoRotulo}${c.detalhe ? " — " + c.detalhe : ""}</div>
                </div>
              </div>`;
          }))}</div>`,
      cancelar: "Entendi"
    });
  }

  function formularioDeBloqueio() {
    var f = VC.form;
    var inicio = new Date();
    inicio.setMinutes(0, 0, 0);
    inicio.setHours(inicio.getHours() + 1);
    var fim = new Date(inicio.getTime() + 60 * 60 * 1000);
    var podeContaInteira = (VC.session.membership() || {}).escopo === "all";

    function enviar(caixa, forcar) {
      var dados = VC.form.valores(caixa);
      var de = VC.form.dataHora(dados.inicio), ate = VC.form.dataHora(dados.fim);
      if (!de || !ate) return VC.form.mostrarErro(caixa, "Informe início e fim.");
      VC.form.mostrarErro(caixa, "");

      var conta = VC.dom.el("[data-conta-inteira]", caixa);
      VC.services.agenda.bloquear({
        inicio: de, fim: ate, titulo: dados.titulo, tipo: dados.tipo,
        contaInteira: conta && conta.checked, forcar: forcar
      }).then(function (r) {
        VC.modal.fechar();
        VC.toast.ok("Horário bloqueado", r.bloqueio.titulo);
        if (r.atendimentosNoPeriodo.length) {
          VC.toast.erro(r.atendimentosNoPeriodo.length + " atendimento(s) seguem marcados",
                        "Remarque um a um — o bloqueio não cancela ninguém");
        }
        recarregarTela();
      }, function (e) {
        if (e.code === "atendimentos_no_periodo") {
          VC.form.mostrarErro(caixa, e.message + " Clique de novo para bloquear assim mesmo.");
          var botao = VC.dom.el("[data-confirmar]", caixa);
          if (botao) {
            VC.safe.texto(botao, "Bloquear mesmo assim");
            botao.setAttribute("data-forcar", "sim");
          }
          return;
        }
        VC.form.mostrarErro(caixa, VC.form.mensagemDe(e));
      });
    }

    VC.modal.abrir({
      titulo: "Bloquear horário",
      subtitulo: "Férias, feriado, almoço — nada disso vira atendimento",
      corpo: html`
        ${f.erro("")}
        ${f.campo({ nome: "titulo", rotulo: "O que é", valor: "Férias",
                    dica: "Aparece na agenda. Não é registro clínico." })}
        <div class="grid grid--2">
          ${f.campo({ nome: "inicio", rotulo: "De", tipo: "datetime-local",
                      valor: VC.fmt.paraCampoDataHora(inicio) })}
          ${f.campo({ nome: "fim", rotulo: "Até", tipo: "datetime-local",
                      valor: VC.fmt.paraCampoDataHora(fim) })}
        </div>
        ${f.campo({ nome: "tipo", rotulo: "Tipo", tipo: "select", valor: "vacation", opcoes: [
          { valor: "vacation", rotulo: "Férias" },
          { valor: "holiday", rotulo: "Feriado" },
          { valor: "break", rotulo: "Intervalo" },
          { valor: "other", rotulo: "Outro" }
        ] })}
        ${podeContaInteira ? html`
          <label class="campo" style="flex-direction:row;align-items:center;gap:var(--sp-2)">
            <input type="checkbox" data-conta-inteira style="width:auto">
            <span style="margin:0">Vale para a conta inteira (feriado)</span>
          </label>` : html.vazio}
        <div class="notice"><div>Bloqueio <b>não cancela</b> sessão marcada. Se houver alguma
        no período, você é avisado e decide.</div></div>`,
      cancelar: "Cancelar",
      confirmar: "Bloquear",
      aoConfirmar: function (caixa) {
        var botao = VC.dom.el("[data-confirmar]", caixa);
        enviar(caixa, botao && botao.getAttribute("data-forcar") === "sim");
      }
    });
  }

  /* ---------------- documentos ----------------
     O download passa por fetch com credenciais e Blob (ver core/api.js):
     o arquivo nunca vira link visitável. */
  function atualizarDocumentos() { recarregarTela(); }

  function baixarDocumento(botao) {
    var nome = botao.getAttribute("data-nome") || "documento";
    VC.services.documentos.baixar({
      id: botao.getAttribute("data-documento"), nomeArquivo: nome
    }).then(function () {
      VC.toast.ok("Download iniciado", nome);
    }, function (erro) {
      VC.toast.erro("Não foi possível baixar", VC.form.mensagemDe(erro));
    });
  }

  function formularioDeRecibo(pacienteId, nome) {
    var f = VC.form;
    var ate = new Date();
    var de = new Date(ate.getTime() - 30 * 864e5);

    VC.modal.abrir({
      titulo: "Emitir recibo",
      subtitulo: nome || "",
      corpo: html`
        ${f.erro("")}
        <div class="notice"><div>O recibo sai do que foi <b>efetivamente recebido</b> no
        período — regime de caixa, igual ao resto do financeiro.</div></div>
        <div class="grid grid--2" style="margin-top:var(--sp-4)">
          ${f.campo({ nome: "de", rotulo: "De", tipo: "date",
                      valor: de.toISOString().slice(0, 10) })}
          ${f.campo({ nome: "ate", rotulo: "Até", tipo: "date",
                      valor: ate.toISOString().slice(0, 10) })}
        </div>`,
      cancelar: "Cancelar",
      confirmar: "Emitir",
      aoConfirmar: function (caixa) {
        var dados = VC.form.valores(caixa);
        VC.form.mostrarErro(caixa, "");
        VC.services.documentos.recibo(pacienteId, {
          de: dados.de ? dados.de + "T00:00:00" : null,
          ate: dados.ate ? dados.ate + "T23:59:59" : null
        }).then(function (d) {
          VC.modal.fechar();
          VC.toast.ok("Recibo emitido", d.titulo);
          VC.services.documentos.baixar(d);
          atualizarDocumentos();
        }, function (e) {
          VC.form.mostrarErro(caixa, VC.form.mensagemDe(e));
        });
      }
    });
  }

  function formularioDeDeclaracao(pacienteId, nome) {
    var f = VC.form;
    VC.services.pacientes.obter(pacienteId).then(function (p) {
      var realizados = (p.historico || []).filter(function (a) {
        return a.status === "realizado" || a.status === "done" || a.status === "confirmado";
      });
      if (!realizados.length) {
        VC.modal.abrir({
          titulo: "Declaração de comparecimento",
          corpo: html`<div class="notice"><div>A declaração vale para atendimento
            realizado. Marque a sessão como realizada primeiro.</div></div>`,
          cancelar: "Entendi"
        });
        return;
      }

      VC.modal.abrir({
        titulo: "Declaração de comparecimento",
        subtitulo: nome || "",
        corpo: html`
          ${f.erro("")}
          <div class="notice"><div>A declaração atesta <b>que a pessoa esteve</b>, quando e
          por quanto tempo. Não carrega nada sobre o que foi tratado.</div></div>
          ${f.campo({ nome: "atendimentoId", rotulo: "Atendimento", tipo: "select",
                      valor: realizados[0].id,
                      opcoes: realizados.slice(0, 30).map(function (a) {
                        return { valor: a.id,
                                 rotulo: VC.fmt.dataLonga(a.inicio) + " · " + VC.fmt.hora(a.inicio) };
                      }) })}`,
        cancelar: "Cancelar",
        confirmar: "Emitir",
        aoConfirmar: function (caixa) {
          var dados = VC.form.valores(caixa);
          VC.form.mostrarErro(caixa, "");
          VC.services.documentos.declaracao(pacienteId, dados.atendimentoId).then(function (d) {
            VC.modal.fechar();
            VC.toast.ok("Declaração emitida", d.titulo);
            VC.services.documentos.baixar(d);
            atualizarDocumentos();
          }, function (e) {
            VC.form.mostrarErro(caixa, VC.form.mensagemDe(e));
          });
        }
      });
    }, function (e) {
      VC.toast.erro("Não foi possível abrir", VC.form.mensagemDe(e));
    });
  }

  function anexarArquivo(pacienteId) {
    var entrada = document.createElement("input");
    entrada.type = "file";
    entrada.style.display = "none";
    document.body.appendChild(entrada);
    entrada.addEventListener("change", function () {
      var arquivo = entrada.files && entrada.files[0];
      document.body.removeChild(entrada);
      if (!arquivo) return;
      VC.toast.ok("Enviando", arquivo.name);
      VC.services.documentos.anexar(pacienteId, arquivo).then(function (d) {
        VC.toast.ok("Arquivo anexado", d.titulo);
        atualizarDocumentos();
      }, function (e) {
        VC.toast.erro("Não foi possível anexar", VC.form.mensagemDe(e));
      });
    });
    entrada.click();
  }

  /* ---------------- privacidade ----------------
     Praticamente tudo daqui é irreversível. Por isso cada ação tem
     confirmação com o que vai acontecer escrito por extenso — e a
     decisão é registrada antes de ser executada. */
  function atualizarPrivacidade() {
    if (VC.views.privacidade && VC.views.privacidade.recarregar) VC.views.privacidade.recarregar();
    else recarregarTela();
  }

  function formularioDeDecisao(pedidoId) {
    var f = VC.form;
    VC.modal.abrir({
      titulo: "Registrar decisão",
      subtitulo: "Registrar não executa — executar é o passo seguinte",
      corpo: html`
        ${f.erro("")}
        <div class="grid grid--2">
          ${f.campo({ nome: "alvo", rotulo: "Sobre o quê", tipo: "select",
                      valor: "clinical", opcoes: VC.views.privacidade.ALVOS })}
          ${f.campo({ nome: "decisao", rotulo: "Decisão", tipo: "select", valor: "keep", opcoes: [
            { valor: "keep", rotulo: "Manter" },
            { valor: "erase", rotulo: "Apagar conteúdo" },
            { valor: "anonymize", rotulo: "Anonimizar cadastro" },
            { valor: "restrict", rotulo: "Restringir tratamento (arquivar)" },
            { valor: "export", rotulo: "Exportar e entregar" }
          ] })}
        </div>
        ${f.campo({ nome: "motivo", rotulo: "Motivo", tipo: "textarea", linhas: 2,
                    dica: "Obrigatório — inclusive para manter" })}
        ${f.campo({ nome: "baseLegal", rotulo: "Base legal", obrigatorio: false,
                    dica: "Ex.: guarda obrigatória de prontuário, obrigação fiscal" })}
        <div class="notice"><div>Lançamento financeiro e histórico de atendimento têm guarda
        obrigatória: para eles, a decisão correta costuma ser <b>manter</b>, com a base
        legal escrita.</div></div>`,
      cancelar: "Cancelar",
      confirmar: "Registrar decisão",
      aoConfirmar: function (caixa) {
        var dados = VC.form.valores(caixa);
        if (!dados.motivo) return VC.form.mostrarErro(caixa, "Toda decisão precisa de motivo.");
        VC.form.mostrarErro(caixa, "");
        VC.services.privacidade.decidir(pedidoId, {
          alvo: dados.alvo, decisao: dados.decisao,
          motivo: dados.motivo, baseLegal: dados.baseLegal
        }).then(function () {
          VC.modal.fechar();
          VC.toast.ok("Decisão registrada", "Ainda não foi executada");
          atualizarPrivacidade();
        }, function (e) {
          VC.form.mostrarErro(caixa, VC.form.mensagemDe(e));
        });
      }
    });
  }

  function formularioDePedido(pacienteId, nome) {
    var f = VC.form;
    VC.modal.abrir({
      titulo: "Registrar pedido do titular",
      subtitulo: nome || "",
      corpo: html`
        ${f.erro("")}
        ${f.campo({ nome: "tipo", rotulo: "O que a pessoa pediu", tipo: "select",
                    valor: "access", opcoes: [
          { valor: "access", rotulo: "Acesso aos dados" },
          { valor: "portability", rotulo: "Portabilidade" },
          { valor: "rectification", rotulo: "Correção" },
          { valor: "erasure", rotulo: "Exclusão" },
          { valor: "restriction", rotulo: "Restrição de tratamento" },
          { valor: "revoke_consent", rotulo: "Revogação de consentimento" },
          { valor: "information", rotulo: "Informação sobre o tratamento" }
        ] })}
        <div class="grid grid--2">
          ${f.campo({ nome: "solicitante", rotulo: "Quem pediu", valor: "titular",
                      dica: "titular, representante legal, responsável" })}
          ${f.campo({ nome: "prazo", rotulo: "Prazo de resposta", tipo: "date",
                      obrigatorio: false,
                      dica: "Vazio = sem prazo; o sistema não inventa um" })}
        </div>
        ${f.campo({ nome: "observacao", rotulo: "O que foi pedido, nas palavras da pessoa",
                    tipo: "textarea", linhas: 3, obrigatorio: false })}`,
      cancelar: "Cancelar",
      confirmar: "Registrar",
      aoConfirmar: function (caixa) {
        var dados = VC.form.valores(caixa);
        VC.form.mostrarErro(caixa, "");
        VC.services.privacidade.abrirPedido(pacienteId, {
          tipo: dados.tipo, solicitante: dados.solicitante,
          prazo: dados.prazo ? dados.prazo + "T12:00:00" : null,
          observacao: dados.observacao
        }).then(function () {
          VC.modal.fechar();
          VC.toast.ok("Pedido registrado", "Agora decida item a item em Privacidade");
          recarregarTela();
        }, function (e) {
          VC.form.mostrarErro(caixa, VC.form.mensagemDe(e));
        });
      }
    });
  }

  function formularioDeConsentimento(pacienteId, nome) {
    var f = VC.form;
    VC.modal.abrir({
      titulo: "Registrar consentimento",
      subtitulo: nome || "",
      corpo: html`
        ${f.erro("")}
        <div class="grid grid--2">
          ${f.campo({ nome: "tipo", rotulo: "Sobre o quê", tipo: "select",
                      valor: "clinical_treatment", opcoes: [
            { valor: "clinical_treatment", rotulo: "Atendimento clínico" },
            { valor: "privacy", rotulo: "Política de privacidade" },
            { valor: "terms", rotulo: "Termos de uso" },
            { valor: "image", rotulo: "Uso de imagem" },
            { valor: "communication", rotulo: "Contato e lembretes" }
          ] })}
          ${f.campo({ nome: "versao", rotulo: "Versão do texto", valor: "1",
                      dica: "Sem versão, “aceitou” não diz nada depois que o texto muda" })}
        </div>
        ${f.campo({ nome: "origem", rotulo: "Como foi dado", tipo: "select",
                    valor: "in_person", opcoes: [
          { valor: "in_person", rotulo: "Presencialmente" },
          { valor: "online", rotulo: "Online" },
          { valor: "imported", rotulo: "Importado de outro sistema" }
        ] })}
        ${f.campo({ nome: "observacao", rotulo: "Observação", obrigatorio: false })}`,
      cancelar: "Cancelar",
      confirmar: "Registrar",
      aoConfirmar: function (caixa) {
        var dados = VC.form.valores(caixa);
        VC.form.mostrarErro(caixa, "");
        VC.services.privacidade.registrarConsentimento(pacienteId, dados).then(function () {
          VC.modal.fechar();
          VC.toast.ok("Consentimento registrado", "");
          recarregarTela();
        }, function (e) {
          VC.form.mostrarErro(caixa, VC.form.mensagemDe(e));
        });
      }
    });
  }

  function formularioDeAvulso() {
    var f = VC.form;
    VC.services.pacientes.listar({ status: "ativo" }).then(function (pessoas) {
      if (!pessoas.length) {
        VC.toast.erro("Nenhuma pessoa cadastrada", "Cadastre antes de lançar o pagamento");
        return;
      }
      VC.modal.abrir({
        titulo: "Pagamento avulso",
        subtitulo: "Pacote, sinal, acerto — dinheiro que não vem de um atendimento",
        corpo: html`
          ${f.erro("")}
          ${f.campo({ nome: "pacienteId", rotulo: VC.terms.t("client.one"), tipo: "select",
                      valor: pessoas[0].id,
                      opcoes: pessoas.map(function (p) {
                        return { valor: p.id, rotulo: p.nome };
                      }) })}
          <div class="grid grid--2">
            ${f.campo({ nome: "valor", rotulo: "Valor recebido", tipo: "number",
                        passo: "0.01", minimo: "0.01" })}
            ${f.campo({ nome: "metodo", rotulo: "Forma", tipo: "select", valor: "pix", opcoes: [
              { valor: "pix", rotulo: "Pix" },
              { valor: "card", rotulo: "Cartão" },
              { valor: "cash", rotulo: "Dinheiro" },
              { valor: "transfer", rotulo: "Transferência" },
              { valor: "other", rotulo: "Outro" }
            ] })}
          </div>
          ${f.campo({ nome: "pagoEm", rotulo: "Quando entrou", tipo: "datetime-local",
                      valor: VC.fmt.paraCampoDataHora(new Date()) })}
          ${f.campo({ nome: "observacao", rotulo: "Observação", obrigatorio: false,
                      dica: "Ex.: pacote de 5 sessões, sinal do mês" })}`,
        cancelar: "Cancelar",
        confirmar: "Registrar",
        aoConfirmar: function (caixa) {
          var dados = VC.form.valores(caixa);
          if (!dados.valor) return VC.form.mostrarErro(caixa, "Informe o valor recebido.");
          var quando = VC.form.dataHora(dados.pagoEm);
          if (!quando) return VC.form.mostrarErro(caixa, "Informe quando o dinheiro entrou.");
          VC.form.mostrarErro(caixa, "");

          VC.services.financeiro.registrarAvulso(dados.pacienteId, {
            valor: dados.valor, metodo: dados.metodo, pagoEm: quando,
            observacao: dados.observacao
          }).then(function (p) {
            VC.modal.fechar();
            VC.toast.ok("Pagamento registrado", VC.fmt.moeda(p.valor) + " · " + p.metodoRotulo);
            recarregarTela();
          }, function (e) {
            VC.form.mostrarErro(caixa, VC.form.mensagemDe(e));
          });
        }
      });
    }, function (e) {
      VC.toast.erro("Não foi possível abrir", VC.form.mensagemDe(e));
    });
  }

  function acoesGlobais() {
    VC.dom.on(document, "click", '[data-acao="novo-paciente"]', function (e) {
      e.preventDefault();
      formularioDePessoa(null);
    });

    VC.dom.on(document, "click", '[data-acao="novo-atendimento"]', function (e, botao) {
      e.preventDefault();
      formularioDeAtendimento(botao.getAttribute("data-paciente"));
    });

    VC.dom.on(document, "click", '[data-acao="editar-paciente"]', function (e, botao) {
      e.preventDefault();
      var id = botao.getAttribute("data-paciente");
      if (!id) return;
      VC.services.pacientes.obter(id).then(formularioDePessoa, function (erro) {
        VC.toast.erro("Não foi possível abrir o cadastro", VC.form.mensagemDe(erro));
      });
    });

    /* Mudança de situação do atendimento: confirmar, realizado,
       falta, cancelar. Quem decide se a transição é possível é o
       servidor — aqui só se mostra o resultado. */
    VC.dom.on(document, "click", "[data-status-para]", function (e, botao) {
      e.preventDefault();
      var id = botao.getAttribute("data-atendimento");
      var destino = botao.getAttribute("data-status-para");
      if (!id || !destino) return;

      botao.disabled = true;
      VC.services.atendimentos.atualizarStatus(id, destino).then(function (a) {
        VC.toast.ok("Atendimento atualizado", VC.ui.rotuloDe(VC.ui.STATUS_ATENDIMENTO, a.status));
        recarregarTela();
      }, function (erro) {
        botao.disabled = false;
        VC.toast.erro("Não foi possível atualizar", VC.form.mensagemDe(erro));
      });
    });

    VC.dom.on(document, "click", '[data-acao="em-breve"]', function (e, botao) {
      e.preventDefault();
      VC.toast.info(botao.getAttribute("data-recurso") || "Recurso", "Entra em uma próxima etapa do projeto.");
    });

    /* ---------- Dinheiro ---------- */
    VC.dom.on(document, "click", '[data-acao="marcar-pago"]', function (e, botao) {
      e.preventDefault();
      var id = botao.getAttribute("data-atendimento");
      if (!id) return;
      formularioDeBaixa(id, botao.getAttribute("data-valor"), botao.getAttribute("data-nome"));
    });

    VC.dom.on(document, "click", '[data-acao="isentar"]', function (e, botao) {
      e.preventDefault();
      var id = botao.getAttribute("data-atendimento");
      if (!id) return;
      confirmarComMotivo({
        titulo: "Isentar cobrança",
        subtitulo: botao.getAttribute("data-nome") || "",
        aviso: "Isento não entra como receita nem como pendência. Dinheiro nenhum é lançado.",
        confirmar: "Isentar",
        sucesso: "Cobrança isentada",
        acao: function (motivo) { return VC.services.financeiro.isentar(id, motivo); }
      });
    });

    VC.dom.on(document, "click", '[data-acao="estornar"]', function (e, botao) {
      e.preventDefault();
      var id = botao.getAttribute("data-pagamento");
      if (!id) return;
      confirmarComMotivo({
        titulo: "Estornar pagamento",
        subtitulo: botao.getAttribute("data-nome") || "",
        aviso: "O lançamento continua no livro-caixa, marcado como estornado, e o " +
               "atendimento volta para pendente.",
        confirmar: "Estornar",
        sucesso: "Pagamento estornado",
        acao: function (motivo) { return VC.services.financeiro.estornar(id, motivo); }
      });
    });

    VC.dom.on(document, "click", '[data-acao="novo-registro"]', function (e, botao) {
      e.preventDefault();
      formularioDeRegistro(botao.getAttribute("data-paciente"), botao.getAttribute("data-nome"));
    });

    VC.dom.on(document, "click", '[data-acao="editar-registro"]', function (e, botao) {
      e.preventDefault();
      formularioDeEdicaoDeRegistro(botao.getAttribute("data-nota"),
                                   botao.getAttribute("data-assinada") === "true");
    });

    VC.dom.on(document, "click", '[data-acao="assinar-registro"]', function (e, botao) {
      e.preventDefault();
      var id = botao.getAttribute("data-nota");
      VC.modal.abrir({
        titulo: "Assinar registro",
        corpo: html`<div class="notice"><div>Depois de assinada, a nota só muda por
          <b>adendo com motivo</b> — e a versão assinada continua no histórico.</div></div>`,
        cancelar: "Cancelar",
        confirmar: "Assinar",
        aoConfirmar: function () {
          VC.services.prontuario.assinar(id).then(function () {
            VC.modal.fechar();
            VC.toast.ok("Registro assinado", "");
            atualizarProntuario();
          }, function (erro) {
            VC.toast.erro("Não foi possível assinar", VC.form.mensagemDe(erro));
          });
        }
      });
    });

    VC.dom.on(document, "click", '[data-acao="trilha-clinica"]', function (e, botao) {
      e.preventDefault();
      janelaDaTrilha(botao.getAttribute("data-paciente"), botao.getAttribute("data-nome"));
    });

    VC.dom.on(document, "click", '[data-acao="convidar"]', function (e) {
      e.preventDefault();
      profissoes().then(formularioDeConvite);
    });

    VC.dom.on(document, "click", '[data-acao="editar-membro"]', function (e, botao) {
      e.preventDefault();
      formularioDeAcesso(botao);
    });

    VC.dom.on(document, "click", '[data-acao="revogar-convite"]', function (e, botao) {
      e.preventDefault();
      var id = botao.getAttribute("data-convite");
      VC.modal.abrir({
        titulo: "Revogar convite",
        subtitulo: botao.getAttribute("data-email"),
        corpo: html`<div class="notice"><div>O link para de funcionar na hora.
          Para chamar essa pessoa de novo, crie um convite novo.</div></div>`,
        cancelar: "Cancelar",
        confirmar: "Revogar",
        aoConfirmar: function () {
          VC.services.equipe.revogar(id).then(function () {
            VC.modal.fechar();
            VC.toast.ok("Convite revogado", "");
            atualizarEquipe();
          }, function (erro) {
            VC.toast.erro("Não foi possível revogar", VC.form.mensagemDe(erro));
          });
        }
      });
    });

    VC.dom.on(document, "click", '[data-acao="bloquear-horario"]', function (e) {
      e.preventDefault();
      formularioDeBloqueio();
    });

    VC.dom.on(document, "click", '[data-acao="remover-bloqueio"]', function (e, botao) {
      e.preventDefault();
      var id = botao.getAttribute("data-bloqueio");
      VC.services.agenda.removerBloqueio(id).then(function () {
        VC.toast.ok("Bloqueio removido", "O horário volta a aceitar agendamento");
        recarregarTela();
      }, function (erro) {
        VC.toast.erro("Não foi possível remover", VC.form.mensagemDe(erro));
      });
    });

    VC.dom.on(document, "click", '[data-acao="encerrar-serie"]', function (e, botao) {
      e.preventDefault();
      var id = botao.getAttribute("data-serie");
      confirmarComMotivo({
        titulo: "Encerrar recorrência",
        subtitulo: botao.getAttribute("data-rotulo") || "",
        aviso: "As sessões futuras são canceladas. O que já aconteceu não é tocado.",
        confirmar: "Encerrar",
        sucesso: "Recorrência encerrada",
        acao: function (motivo) {
          return VC.services.agenda.encerrarSerie(id, { motivo: motivo });
        }
      });
    });

    VC.dom.on(document, "click", '[data-acao="baixar-documento"]', function (e, botao) {
      e.preventDefault();
      baixarDocumento(botao);
    });

    VC.dom.on(document, "click", '[data-acao="emitir-recibo"]', function (e, botao) {
      e.preventDefault();
      formularioDeRecibo(botao.getAttribute("data-paciente"), botao.getAttribute("data-nome"));
    });

    VC.dom.on(document, "click", '[data-acao="emitir-declaracao"]', function (e, botao) {
      e.preventDefault();
      formularioDeDeclaracao(botao.getAttribute("data-paciente"), botao.getAttribute("data-nome"));
    });

    VC.dom.on(document, "click", '[data-acao="anexar-documento"]', function (e, botao) {
      e.preventDefault();
      anexarArquivo(botao.getAttribute("data-paciente"));
    });

    VC.dom.on(document, "click", '[data-acao="exportar-prontuario"]', function (e, botao) {
      e.preventDefault();
      var id = botao.getAttribute("data-paciente");
      VC.modal.abrir({
        titulo: "Exportar prontuário",
        subtitulo: botao.getAttribute("data-nome") || "",
        corpo: html`<div class="notice"><div>Sai em PDF <b>só o que você já pode ler</b>,
          e cada registro aberto entra na trilha de acesso da pessoa.</div></div>`,
        cancelar: "Cancelar",
        confirmar: "Exportar",
        aoConfirmar: function () {
          VC.services.documentos.exportarProntuario(id).then(function (d) {
            VC.modal.fechar();
            VC.toast.ok("Prontuário exportado", d.titulo);
            VC.services.documentos.baixar(d);
          }, function (erro) {
            VC.toast.erro("Não foi possível exportar", VC.form.mensagemDe(erro));
          });
        }
      });
    });

    VC.dom.on(document, "click", '[data-acao="pagamento-avulso"]', function (e) {
      e.preventDefault();
      formularioDeAvulso();
    });

    VC.dom.on(document, "click", '[data-acao="exportar-caixa"]', function (e) {
      e.preventDefault();
      VC.services.documentos.exportarCaixa().then(function () {
        VC.toast.ok("CSV gerado", "Abre no Excel com os acentos certos");
      }, function (erro) {
        VC.toast.erro("Não foi possível exportar", VC.form.mensagemDe(erro));
      });
    });

    VC.dom.on(document, "click", '[data-acao="decidir"]', function (e, botao) {
      e.preventDefault();
      formularioDeDecisao(botao.getAttribute("data-pedido"));
    });

    VC.dom.on(document, "click", '[data-acao="aplicar-decisao"]', function (e, botao) {
      e.preventDefault();
      var pedido = botao.getAttribute("data-pedido");
      var decisao = botao.getAttribute("data-decisao");
      VC.modal.abrir({
        titulo: "Executar decisão",
        subtitulo: botao.getAttribute("data-rotulo") || "",
        corpo: html`<div class="notice"><div><b>Isto não tem volta.</b> Apagar conteúdo
          descarta a chave daquele registro — o texto não volta nem de backup. Anonimizar
          remove o que identifica, para sempre.</div></div>`,
        cancelar: "Cancelar",
        confirmar: "Executar",
        aoConfirmar: function () {
          VC.services.privacidade.aplicar(pedido, decisao).then(function () {
            VC.modal.fechar();
            VC.toast.ok("Decisão executada", "");
            atualizarPrivacidade();
          }, function (erro) {
            VC.toast.erro("Não foi possível executar", VC.form.mensagemDe(erro));
          });
        }
      });
    });

    VC.dom.on(document, "click", '[data-acao="encerrar-pedido"]', function (e, botao) {
      e.preventDefault();
      var id = botao.getAttribute("data-pedido");
      var f = VC.form;
      VC.modal.abrir({
        titulo: "Encerrar pedido",
        corpo: html`
          ${f.erro("")}
          ${f.campo({ nome: "status", rotulo: "Desfecho", tipo: "select", valor: "done", opcoes: [
            { valor: "done", rotulo: "Atendido" },
            { valor: "refused", rotulo: "Recusado" }
          ] })}
          ${f.campo({ nome: "observacao", rotulo: "O que foi respondido ao titular",
                      tipo: "textarea", linhas: 3, obrigatorio: false,
                      dica: "Obrigatório quando recusado — recusar sem explicar não é resposta" })}`,
        cancelar: "Cancelar",
        confirmar: "Encerrar",
        aoConfirmar: function (caixa) {
          var dados = VC.form.valores(caixa);
          VC.form.mostrarErro(caixa, "");
          VC.services.privacidade.encerrar(id, dados).then(function () {
            VC.modal.fechar();
            VC.toast.ok("Pedido encerrado", "");
            atualizarPrivacidade();
          }, function (erro) {
            VC.form.mostrarErro(caixa, VC.form.mensagemDe(erro));
          });
        }
      });
    });

    VC.dom.on(document, "click", '[data-acao="definir-politica"]', function (e) {
      e.preventDefault();
      var f = VC.form;
      VC.modal.abrir({
        titulo: "Política de retenção",
        subtitulo: "Prazo sem base legal não vale para apagar nada",
        corpo: html`
          ${f.erro("")}
          ${f.campo({ nome: "alvo", rotulo: "Sobre o quê", tipo: "select",
                      valor: "clinical", opcoes: VC.views.privacidade.ALVOS })}
          ${f.campo({ nome: "meses", rotulo: "Guardar por (meses)", tipo: "number",
                      minimo: "1", obrigatorio: false,
                      dica: "Vazio = sem prazo definido, que é o padrão" })}
          ${f.campo({ nome: "baseLegal", rotulo: "Base legal", obrigatorio: false,
                      dica: "De onde vem o prazo: resolução do conselho, lei, contrato" })}
          ${f.campo({ nome: "observacao", rotulo: "Observação", obrigatorio: false })}`,
        cancelar: "Cancelar",
        confirmar: "Salvar",
        aoConfirmar: function (caixa) {
          var dados = VC.form.valores(caixa);
          VC.form.mostrarErro(caixa, "");
          VC.services.privacidade.definirPolitica(dados).then(function () {
            VC.modal.fechar();
            VC.toast.ok("Política salva", "");
            atualizarPrivacidade();
          }, function (erro) {
            VC.form.mostrarErro(caixa, VC.form.mensagemDe(erro));
          });
        }
      });
    });

    VC.dom.on(document, "click", '[data-acao="registrar-consentimento"]', function (e, botao) {
      e.preventDefault();
      formularioDeConsentimento(botao.getAttribute("data-paciente"),
                                botao.getAttribute("data-nome"));
    });

    VC.dom.on(document, "click", '[data-acao="revogar-consentimento"]', function (e, botao) {
      e.preventDefault();
      VC.services.privacidade.revogarConsentimento(botao.getAttribute("data-consentimento"))
        .then(function () {
          VC.toast.ok("Consentimento revogado", "");
          recarregarTela();
        }, function (erro) {
          VC.toast.erro("Não foi possível revogar", VC.form.mensagemDe(erro));
        });
    });

    VC.dom.on(document, "click", '[data-acao="abrir-pedido"]', function (e, botao) {
      e.preventDefault();
      formularioDePedido(botao.getAttribute("data-paciente"), botao.getAttribute("data-nome"));
    });

    VC.dom.on(document, "click", '[data-acao="baixar-pacote"]', function (e, botao) {
      e.preventDefault();
      VC.services.privacidade.baixarPacote(botao.getAttribute("data-paciente"),
                                           botao.getAttribute("data-nome"))
        .then(function () { VC.toast.ok("Pacote gerado", "JSON com tudo o que a conta tem"); },
              function (erro) {
                VC.toast.erro("Não foi possível gerar", VC.form.mensagemDe(erro));
              });
    });

    VC.dom.on(document, "click", '[data-acao="anonimizar"]', function (e, botao) {
      e.preventDefault();
      var id = botao.getAttribute("data-paciente");
      confirmarComMotivo({
        titulo: "Anonimizar cadastro",
        subtitulo: botao.getAttribute("data-nome") || "",
        aviso: "Nome, contato e nascimento somem para sempre. A série de atendimentos e os " +
               "valores continuam, sem titular identificável. Isto não tem volta.",
        confirmar: "Anonimizar",
        sucesso: "Cadastro anonimizado",
        acao: function (motivo) {
          if (!motivo) return Promise.reject({ status: 422, message: "Informe o motivo." });
          return VC.services.privacidade.anonimizar(id, motivo);
        }
      });
    });

    VC.dom.on(document, "click", '[data-acao="reenviar-verificacao"]', function (e) {
      e.preventDefault();
      VC.api.post("/auth/email/verify/request", {}).then(function () {
        VC.toast.ok("Link enviado", "Confira a sua caixa de entrada");
      }, function (erro) {
        VC.toast.erro("Não foi possível enviar", VC.form.mensagemDe(erro));
      });
    });

    VC.dom.on(document, "click", '[data-acao="sair"]', function (e) {
      e.preventDefault();
      VC.session.encerrar();
    });
  }

  /* ---------------- PWA ---------------- */
  function registrarPWA() {
    if (!("serviceWorker" in navigator)) return;
    /* file:// não tem service worker: só registra quando servido por http(s) */
    if (location.protocol !== "http:" && location.protocol !== "https:") return;
    navigator.serviceWorker.register("service-worker.js").catch(function () { /* silencioso */ });
  }

  /* ---------------- Início ----------------
     Três estados possíveis, nesta ordem:

       sem sessão            -> tela de entrada, painel nem é montado
       sessão sem workspace  -> escolha da conta (quem tem mais de uma)
       sessão com workspace  -> painel

     O painel só existe depois que o servidor confirmou os dois
     primeiros. É o fail-closed da arquitetura aplicado à interface:
     nenhuma tela de dados é montada "por otimismo".
  */
  var painelMontado = false;

  function montarPainel() {
    VC.auth.esconder();

    VC.shell.montar();
    if (painelMontado) { VC.router.resolver(); return; }

    painelMontado = true;
    registrarRotas();
    acoesGlobais();
    VC.router.iniciar();
    registrarPWA();

    /* Trocar de conta redesenha o painel inteiro: outro workspace,
       outras permissões, outros termos. */
    VC.session.aoTrocarTenant(function () { montarPainel(); });
  }

  /* Três links chegam de e-mail e precisam funcionar ANTES de existir
     sessão: convite (quem foi convidado pode não ter conta), confirmação
     de e-mail e redefinição de senha. */
  var LINKS_SEM_SESSAO = [
    { tela: "convite", re: /^#\/convite\/([^/?]+)/ },
    { tela: "verificar", re: /^#\/verificar\/([^/?]+)/ },
    { tela: "redefinir", re: /^#\/redefinir\/([^/?]+)/ }
  ];

  function linkDeEmail() {
    var hash = global.location.hash || "";
    for (var i = 0; i < LINKS_SEM_SESSAO.length; i++) {
      var m = hash.match(LINKS_SEM_SESSAO[i].re);
      if (m) return { tela: LINKS_SEM_SESSAO[i].tela, token: decodeURIComponent(m[1]) };
    }
    return null;
  }

  function iniciar() {
    var link = linkDeEmail();
    if (link) {
      VC.auth.iniciar({ tela: link.tela, token: link.token, aoEntrar: montarPainel });
      return;
    }

    VC.session.carregar().then(function () {
      if (!VC.session.autenticado()) return VC.auth.iniciar({ tela: "login", aoEntrar: montarPainel });
      if (!VC.session.temWorkspace()) return VC.auth.iniciar({ tela: "workspaces", aoEntrar: montarPainel });
      montarPainel();
    }, function (e) {
      /* Servidor fora do ar: dizer isso, em vez de mostrar um painel
         vazio que parece dado zerado. */
      VC.auth.iniciar({ tela: "login", aoEntrar: montarPainel });
      if (VC.toast) VC.toast.erro("Sem conexão com o servidor", e && e.message);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar);
  else iniciar();
})(window);
