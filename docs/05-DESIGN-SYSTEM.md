# Truss Agent Design System

Fonte inicial: export do Open Design `truss-icon-system.html` e `truss-icon-system.pdf`.
Consolidacao adicional: export V0 `truss-agent.zip`, usado como referencia de badges, reguas, status bar e microinteracoes de auditoria.

## Direcao

O Truss usa uma interface de produto tecnico, escura e PDF-first. A linguagem visual deve lembrar CAD, revisao estrutural e instrumentacao local, nao SaaS generico.

- Fundo grafite com grid tecnico de 96 px.
- Bordas de 1 px e raio base de 4 px.
- Vermelho como acento funcional: selecao, foco, revisao e severidade alta.
- PDF e achados localizados sao o centro da experiencia.
- Chat e memoria sao paineis complementares.

## Tokens

```text
bg        #0e0f10
bg-elev   #141618
panel     #17191b
panel-2   #1d2022
border    #2a2e31
grid      #202426
fg        #e7eaeb
fg-2      #98a0a5
fg-tech   #79838a
red       #d93b2b
red-crit  #ff4a37
red-dim   #3a1512
amber     #dfa03c
green     #3fa860
info      #6f8ea3
sheet     #f2f0ec
radius    4px
icon-sw   1.75
```

## Iconografia

- Canvas de 24 x 24 px.
- Area viva de 20 x 20 px, margem de 2 px.
- Traco monoline de 1.75 px.
- `currentColor` sempre que possivel.
- Icone sozinho apenas no viewer, com `title`, `aria-label` ou texto assistivo.
- Fora do viewer, icone acompanha rotulo.
- Severidade e confianca nao usam a mesma metafora: severidade usa cor/forma; confianca usa barras/medidor.

## Componentes

- Shell: topbar compacta, marca triangular e metadados mono.
- Sidebar: lista tecnica de projetos/revisoes, sem cards decorativos.
- Dropzone: borda tracejada, realce vermelho durante drag, status mono.
- Viewer: canvas central com grid tecnico, toolbar icon-only, pan/zoom/fit e modo de selecao manual.
- Achados: bounding boxes em coordenadas PDF, etiqueta de severidade, lista filtravel e detalhe tecnico.
- Badges: severidade, status, tipo e confianca sao componentes separados. Severidade usa quatro barras; confianca usa medidor percentual; status usa ponto + label.
- Reguas: viewer importante deve exibir reguas superior/lateral quando houver coordenadas PDF ativas.
- Status bar: viewer deve expor cursor em pt, zoom, tamanho da folha, selecao e estado da auditoria no rodape do canvas.
- Chat: painel secundario contextual, abaixo dos achados.
- Chat Agent: composer multiline, chips de contexto, modos de acao, activity panel, command menu e cards de achados conectados ao canvas.
- Runtime: badges compactos para API local e provider de IA.
- Memoria: painel de regras explicitas, sem esconder origem humana.

## Motion

Use transicoes de 120 a 180 ms com ease-out para hover, foco, selecao e alternancia de paineis. Animacao decorativa nao deve ser adicionada.

- Auditoria em execucao pode usar giro simples no icone de reprocessar e uma varredura vermelha discreta sobre o canvas.
- Selecao manual recem desenhada pode usar pulso curto de foco na regiao.
- Motion deve comunicar estado operacional, nunca virar ornamento.
- Respeitar `prefers-reduced-motion`.

## Fluxos Inline

- Nao usar `window.prompt` para feedback humano, rejeicao ou criacao de achado.
- Criacao manual deve ser em duas etapas: selecionar regiao no canvas, preencher tipo/severidade/descricao em painel visivel.
- Rejeicao de achado deve abrir campo de justificativa no detalhe do achado, com salvar/cancelar explicitos.
- Hipoteses pendentes devem deixar claro que severidade mede impacto, nao certeza.
- Chat nao deve simular streaming, upload ou ferramentas inexistentes. Quando o backend nao suportar uma acao, a UI deve mostrar o limite operacional e preservar o caminho real disponivel.
- Context chips removiveis sao a fonte visivel do contexto enviado ao endpoint de chat. Folha e documento sao contexto base; selecao e achado podem ser removidos.

## Acessibilidade

- Foco visivel vermelho em todos os controles.
- Alvos minimos de 38 px no desktop e equivalentes maiores por layout em touch.
- Contraste alto entre texto principal e fundo.
- Texto tecnico em mono apenas para metadados, coordenadas, codigos e status.
- Nao usar cor como unico meio para status critico: manter labels como `CRITICAL`, `PENDING`, `CONFIRMED`.
