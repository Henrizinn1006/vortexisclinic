# Vortexis Clinic — Site institucional

Site institucional da plataforma **Vortexis Clinic** (uma solução VORTEXIS).
HTML, CSS e JavaScript puros — sem build, sem dependências, sem framework.

> Estado atual: **Psicologia em acesso antecipado.** O site apresenta o que o
> sistema já faz e leva ao pedido de acesso por e-mail. Login, planos e preços
> ficam desligados por flag até o painel estar no ar (ver "Para publicar").

---

## Como abrir

- **Rápido:** dê dois cliques em `index.html`.
- **Recomendado (simula o servidor real):** rode um servidor local na pasta:
  ```bash
  npx serve .
  # ou
  python -m http.server 5500
  ```

---

## Estrutura

```
Sitevortexisclinic/
├── index.html                    # Home (todas as seções)
├── psicologia/index.html         # Página da vertical (casca, conteúdo vem dos dados)
├── odontologia/index.html
├── estetica/index.html
├── fisioterapia/index.html
├── nutricao/index.html
├── politica-de-privacidade/index.html
├── termos-de-uso/index.html
├── 404.html  •  .htaccess         # página de erro e config do Apache (Hostinger)
├── robots.txt  •  sitemap.xml
└── assets/
    ├── images/                   # marca (ver abaixo) + os PNGs originais
    ├── css/
    │   ├── motion.css            # TODO o movimento do site (animações e hovers)
    │   ├── tokens.css            # Cores, tipografia, espaçamento + TEMAS POR PRODUTO
    │   ├── base.css              # Reset, tipografia base, container, grid, utilitários
    │   ├── components.css        # Botões, badges, cards, card de produto, logo
    │   ├── layout.css            # Header, menu mobile, footer
    │   ├── sections.css          # Seções da home + mockups (janela do app, dispositivos)
    │   └── product-page.css      # Página de vertical e páginas legais
    └── js/
        ├── config/site.config.js # Marca, domínios, contatos, menu, FLAGS de fase
        ├── data/products.js      # CATÁLOGO DE SOLUÇÕES (fonte única da verdade)
        ├── data/content.js       # Tutorial PWA e roadmap
        ├── components/           # logo, header, footer, product-card, pwa-modal, motion, icons
        ├── pages/home.js         # Monta a grade de soluções e o roadmap
        ├── pages/product.js      # Monta a página de uma vertical a partir do slug
        └── main.js               # Bootstrap: header, footer, contatos, animações
```

Regra do projeto: **nenhum componente usa cor crua**. Tudo vem das variáveis de
`tokens.css`. Use `--accent*` sempre que a cor precisar mudar por produto.

---

## Marca

Os arquivos ficam em `assets/images/` e são usados **apenas** por
`assets/js/components/logo.js` — trocar a logo do site inteiro é mexer em um
arquivo só.

| Arquivo | Onde aparece |
|---|---|
| `simbolo.png` | vórtice do header (fundo claro) |
| `simbolo-claro.png` | mesmo vórtice clareado, para o rodapé escuro |
| `marca-texto.png` | lettering azul, fundos claros |
| `marca-texto-branco.png` | lettering branco, fundos escuros |
| `marca-completa.png` / `-branco.png` | lockup vertical (compartilhamento, apresentações) |
| `favicon.png`, `icone-192.png`, `icone-512.png` | aba do navegador e ícone de app (PWA) |
| `vortexiscliniclogo.png`, `logosemfundoV.C.png` | originais enviados, mantidos como referência |

As versões clareada e branca foram geradas a partir do PNG sem fundo. Se a logo
mudar, basta regerar esses arquivos com os mesmos nomes.

---

## Como adicionar um novo sistema (ex.: Fonoaudiologia)

1. **Dados** — em `assets/js/data/products.js`, copie um objeto e ajuste:

```js
{
  slug: "fonoaudiologia",
  name: "Fonoaudiologia",
  fullName: "Vortexis Clinic — Fonoaudiologia",
  status: "coming-soon",        // available | in-development | coming-soon | planned
  theme: "fonoaudiologia",      // opcional; sem isso usa o verde da marca
  icon: "activity",
  order: 6,
  short: "Gestão para fonoaudiólogos e clínicas.",
  description: "...",
  features: ["Pacientes", "Agenda", "Sessões"],
  highlights: [{ title: "...", text: "..." }],
  audience: "..."
}
```

2. **Página** — crie a pasta `fonoaudiologia/` e copie o `index.html` de outra
   vertical, trocando apenas `data-product`, `data-theme`, `<title>`, a
   descrição e o `canonical`. O conteúdo da página é montado a partir dos dados.

3. **Cor (opcional)** — em `assets/css/tokens.css`, adicione:

```css
[data-theme="fonoaudiologia"] {
  --accent: #0e9aa7; --accent-dark: #0a7b86;
  --accent-light: #b6e6ea; --accent-soft: #eaf7f8;
}
```

4. **Sitemap** — acrescente a URL em `sitemap.xml`.

Pronto: home, rodapé, menus e páginas "outras soluções" passam a mostrar o novo
sistema automaticamente. **A home não precisa ser mexida.**

---

## Chaves de configuração (`assets/js/config/site.config.js`)

| Campo | Para quê |
|---|---|
| `contact.email` / `contact.whatsapp` | Preenchem a seção de contato, o rodapé e os CTAs. WhatsApp só no formato `5511999999999`. |
| `social` | Lista vazia hoje; ao preencher, os ícones aparecem no rodapé. |
| `features.auth` | `false` = "Entrar" desativado e botão "Quero testar". Vire `true` só quando `app.vortexisclinic.com.br` abrir de verdade (API em VPS). |
| `features.plans` | Reservado para a seção de planos. Fica `false` enquanto os preços não existirem. |
| `earlyAccessSubject` | Assunto do e-mail aberto pelos botões "Quero testar". |
| `features.productPages` | Liga/desliga os links das páginas de vertical. |
| `prettyUrls` | `false` usa `/psicologia/index.html` (funciona até abrindo o arquivo local). Ao publicar em servidor com URL limpa, vire `true` e os links viram `/psicologia/`. |

---

## Decisões desta fase

- Conteúdo textual das seções fica **estático no HTML** (melhor para SEO); só o
  catálogo de produtos, header e footer são montados por JS, para não duplicar
  código a cada novo sistema.
- Psicologia está como `early-access`. Quando o acesso abrir para todos, troque
  para `available` — o rótulo e o botão mudam sozinhos.
- **Só se descreve o que o sistema já faz.** As seções de segurança (home e
  `security` em `products.js`) e as páginas jurídicas foram escritas a partir do
  código da API. Não acrescente promessa que o código não cumpre — inclusive
  prazo de retenção, que é decisão do profissional e não pode ser inventado.
- Privacidade e Termos têm texto completo, mas continuam com `noindex` e aviso de
  revisão jurídica. Os dados ainda não definidos (razão social, CNPJ,
  encarregado, fornecedores, foro) aparecem **destacados em amarelo** de
  propósito (`.legal__todo`), para não passarem despercebidos.
- Sem WhatsApp configurado, o cartão de WhatsApp some em vez de mostrar canal
  morto.
- **Sem ícones decorativos.** A hierarquia é feita com tipografia, numeração
  (`01`, `02`…) e réguas de acento. Só sobraram ícones funcionais: o "fechar" do
  modal e as marcas de redes sociais no rodapé (`assets/js/components/icons.js`).
- **Movimento** concentrado em `assets/css/motion.css` + `assets/js/components/motion.js`:
  entrada do topo em cascata, revelação em scroll com atraso escalonado, título
  em máscara por linha, contadores, gráfico e agenda do mockup animando,
  inclinação 3D do mockup no mouse, brilho dos cards seguindo o cursor, barra de
  progresso de leitura, linha do roadmap preenchendo, aurora no topo e no CTA,
  botões com brilho e seta, menu mobile em cascata.
  Tudo desliga sozinho com "reduzir movimento" ligado no sistema, e sem JS a
  página continua completa e estática.
- Nada é carregado de fora além da fonte Inter.

---

## Para publicar (Hostinger)

1. Envie o conteúdo desta pasta para `public_html/`, **incluindo o `.htaccess`**
   (arquivo oculto — no gerenciador de arquivos, ative "mostrar ocultos").
   Ele força HTTPS, tira o `www`, define cabeçalhos de segurança, cache e a
   página `404.html`.
2. Ative o SSL do domínio no hPanel antes; sem ele o redirecionamento para
   HTTPS dá erro.
3. Antes de indexar Privacidade e Termos: preencha os trechos em amarelo, passe
   pela revisão jurídica, remova o `<meta name="robots" content="noindex">` das
   duas páginas e os `Disallow` do `robots.txt`.
4. Quando o painel estiver no ar: `features.auth: true` em `site.config.js`.

## Ainda não implementado

Seção de planos (depende de preço) • login a partir do site (depende do deploy
da API) • WhatsApp e redes sociais (dependem dos canais oficiais).
