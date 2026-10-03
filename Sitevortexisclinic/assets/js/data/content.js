/* =============================================================
   Conteudos dinamicos (usados por componentes JS).
   Textos fixos das secoes ficam direto no HTML por questao de SEO.
   ============================================================= */
(function (global) {
  "use strict";

  var CONTENT = {
    /* Modal "Como instalar no celular" */
    pwaTutorial: {
      title: "Como instalar no celular",
      intro:
        "Os sistemas da Vortexis Clinic funcionam no navegador e podem ser adicionados à tela inicial, abrindo como um aplicativo.",
      platforms: [
        {
          name: "Android",
          note: "Google Chrome",
          steps: [
            "Abra o sistema no Chrome.",
            "Toque no menu de três pontos.",
            "Escolha Adicionar à tela inicial ou Instalar aplicativo.",
            "Confirme. O ícone aparece junto dos seus apps."
          ]
        },
        {
          name: "iPhone",
          note: "Safari",
          steps: [
            "Abra o sistema no Safari.",
            "Toque no botão Compartilhar.",
            "Escolha Adicionar à Tela de Início.",
            "Confirme. O ícone aparece na tela inicial."
          ]
        }
      ],
      footer: "Em breve disponibilizaremos um tutorial em vídeo nesta mesma página."
    },

    /* Linha do tempo da seção de expansão */
    roadmap: [
      { title: "Psicologia", note: "Acesso antecipado" },
      { title: "Odontologia", note: "Próxima expansão" },
      { title: "Estética", note: "Expansão posterior" },
      { title: "Fisioterapia e Nutrição", note: "No roadmap" },
      { title: "Novos módulos da plataforma", note: "Contínuo" }
    ]
  };

  global.VC = global.VC || {};
  global.VC.content = CONTENT;
})(window);
