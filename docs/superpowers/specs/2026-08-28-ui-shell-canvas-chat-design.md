# Shell do viewer, gestos do canvas e chat - Design

Data: 2026-08-28
Status: aprovado
Escopo: reorganizacao da UI do viewer de prancha - layout, navegacao e experiencia de chat

## Problema

Tres queixas do proprietario, verificadas na aplicacao rodando:

1. **Desorganizacao.** Achados e chat dividem a coluna direita de 390px, espremendo os dois.
2. **Nao consegue mover a prancha.** Arrastar com o botao esquerdo faz marquee de selecao;
   pan exige botao do meio ou Espaco+arrasto (`sheet-viewer.tsx:1057`).
3. **Nao da para saber se o chat esta respondendo.**

A terceira queixa tem causa nao obvia. O `truss-chat.tsx` **ja possui** streaming, botao de
parar, copiar, regenerar, editar mensagem, feedback, conversas, itens de contexto e trilha de
atividade em etapas - e todos ja sao passados pelo `sheet-viewer.tsx`. O que falta nao e
funcionalidade.

A causa real e estrutural: **a pagina inteira rola como um documento unico**. O chat nao tem
scroll proprio, entao cresce e empurra a pagina. O indicador de "gerando" e o composer ficam
fora da tela. O usuario nao ve o estado porque ele esta abaixo da dobra, nao porque nao existe.

Isso torna o layout a correcao de base: sem altura travada, nenhuma das outras melhorias
aparece.

## Decisoes de produto

Tomadas com o proprietario durante o brainstorming:

| Questao | Decisao |
|---|---|
| Onde ficam os achados | gaveta inferior colapsavel; coluna direita fica so para o chat |
| Modelo de interacao no canvas | padrao de visualizador PDF: arrastar move, roda da zoom |
| Escopo do trabalho no chat | painel com scroll proprio, estados legiveis, limpar ruido e recursos novos |
| Reescrever o chat | nao; o componente existente e preservado |

## Abordagem

**App shell de altura fixa.** O viewer ocupa exatamente a altura da janela e nunca rola como
pagina. Dentro dele, regioes com scroll independente.

Alternativas descartadas:

- *Manter o scroll de pagina e so reorganizar os blocos*: nao resolve nada, porque a causa das
  tres queixas de visibilidade e o scroll unico. Seria maquiagem.
- *Reescrever o viewer*: joga fora undo/redo, selecao multipla, minimap, reguas e pan por pinca,
  que funcionam e estao testados. Custo e risco altos, ganho nulo sobre a opcao escolhida.

## Decomposicao de `sheet-viewer.tsx`

O arquivo esta com 2.301 linhas e este trabalho toca layout, gestos e chat - regioes diferentes
dele. O spec da F1 ja registrou a regra "quem mexe, separa".

| Modulo | Responsabilidade |
|---|---|
| `components/canvas/sheet-canvas.tsx` | viewport, pan/zoom, reguas, minimap, marquee |
| `components/findings/findings-drawer.tsx` | gaveta inferior, filtros, navegacao entre achados |
| `components/sheet-viewer.tsx` | orquestracao, estado e fiacao do chat |

Nao ha refatoracao alem do que for tocado.

## Secao 1: o shell

```
+----------------------------------------------+--------------+
| EST-0130-A / Proj_Estrutural...              |  CHAT        |  <- nao rola
| PLANTA DE ARMADURAS - A1        < 4/28 >     |  cabecalho   |
+----------------------------------------------+--------------+
|                                              |              |
|                                              |  historico   |
|              CANVAS                          |  rola        |
|         (nao rola - faz pan)                 |  sozinho     |
|                                              |              |
+----------------------------------------------+              |
| ^ ACHADOS (12)  < 3/12 >   [todos] [low]     +--------------+
| [LOW] falta escala na vista    v x +         | gerando... # |  <- barra de estado
| rola sozinha                                 | [composer  ] |  <- sempre visivel
+----------------------------------------------+--------------+
```

**Regras estruturais:**

- container raiz `h-[100dvh]` com `overflow-hidden` - e o que elimina o scroll de pagina;
- todo filho de flex/grid que precisa rolar recebe `min-h-0`. Sem isso o filho **estoura o pai**
  em vez de rolar dentro dele, que e exatamente o defeito atual do chat;
- o canvas usa `overflow-hidden`; o pan e o scroll dele.

**A gaveta de achados** tem tres alturas: fechada (~40px, so a barra), padrao (~200px) e
expandida (~45% da altura). Alterna por clique na barra ou pela tecla `A`. O estado persiste em
`localStorage`. Fechada, o canvas ganha o espaco - a razao de ter escolhido gaveta em vez de
faixa fixa no topo.

**A coluna do chat** mantem a largura atual (390px em `xl`, 420px em `2xl`) e empilha abaixo do
canvas em telas menores que `xl`, preservando o responsivo existente.

**Degradacao deliberada:** a altura minima de 720px do canvas e preservada. Em janelas mais
baixas que isso, travar tudo em `100dvh` espremeria o desenho a ponto de inutilizar, entao o
shell volta a permitir scroll de pagina.

## Secao 2: gestos do canvas

A mecanica de pan ja existe e funciona (`sheet-viewer.tsx:1102`). Muda o gesto que a dispara.

| Gesto | Hoje | Passa a ser |
|---|---|---|
| Arrastar com esquerdo | marquee de selecao | **mover a prancha** |
| Roda | rola vertical | **zoom no cursor** |
| Shift + arrastar | - | marquee de selecao |
| Ctrl + roda | zoom | zoom (mantem) |
| Botao do meio, Espaco + arrastar | pan | pan (mantem) |
| Clique simples num achado | seleciona | seleciona (mantem) |
| `F`, `Ctrl+0` | fit, reset | mantem |

**Distincao de origem da roda.** Mapear roda para zoom de forma ingenua quebra o trackpad, que
emite dezenas de eventos por segundo ao rolar com dois dedos. O handler decide assim:

- `ctrlKey` presente -> **zoom**. O navegador marca o gesto de pinca do trackpad desse jeito,
  entao pinca passa a dar zoom sem codigo extra;
- `deltaX != 0` -> rolagem de dois dedos -> **pan nos dois eixos**;
- so `deltaY` sem `ctrlKey` -> roda de mouse -> **zoom no cursor**.

**Compensacao pela perda do marquee no arrasto simples:** `Shift+arrastar` continua fazendo
selecao por area, e o modo *achado manual*, que ja existe na barra, troca o arrasto para desenho
enquanto ligado. A barra de status abaixo do canvas exibe o gesto ativo.

**Cursor comunica o modo:** `grab`/`grabbing` no padrao, `crosshair` com Shift ou no modo manual.
O padrao atual e `crosshair`, o que sugere selecao e contribuiu para a confusao.

**Correcao que entra junto:** hoje nao ha limite de deslocamento, entao e possivel arrastar a
prancha inteiramente para fora da tela sem saber como voltar. O pan passa a ser limitado de modo
que o retangulo da prancha sempre intersecte o viewport em pelo menos 80px nos dois eixos. O
limite se aplica ao resultado de qualquer operacao que mova o viewport - arrasto, roda e zoom -
e nao apenas ao arrasto.

## Secao 3: o chat

### Estados legiveis

Maquina de estados explicita, renderizada numa barra fixa acima do composer:

| Estado | O que aparece |
|---|---|
| `idle` | nada; so o composer |
| `enviando` | "enviando..." com pulso sutil |
| `gerando` | "gerando..." + botao parar em destaque + cursor piscando na resposta |
| `parado` | "interrompido por voce" + acao *continuar* |
| `erro` | causa especifica + acao *tentar de novo* |

O backend **ja** distingue as causas em `ai/provider.py:247` (`_openai_public_error` devolve
mensagem e codigo); o frontend hoje colapsa tudo num tom vermelho generico. "Sem chave
configurada", "cota esgotada" e "rede indisponivel" pedem reacoes diferentes do usuario - a
primeira se resolve no ambiente, a segunda nao melhora com nova tentativa.

### Limpar o ruido

Tres niveis visuais no lugar de um:

- **fala do Truss** - bolha normal, peso de leitura;
- **evento de sistema** ("1 elemento duplicado no canvas") - linha fina, monoespacada, sem bolha;
- **card de achado** - bloco estruturado, como ja e.

**Deduplicacao:** rodar auditoria varias vezes na mesma folha e legitimo, mas hoje repete o card
inteiro a cada vez. Se um achado ja foi mostrado na conversa, a nova ocorrencia vira uma linha
"achado ja listado acima" com link para ele.

### Recursos novos

**Autoscroll com ancora.** Rola sozinho enquanto o usuario esta no fim; se ele subiu para ler,
para de puxar e mostra um botao "novas mensagens". Autoscroll que ignora a posicao de leitura e
um dos comportamentos mais irritantes de uma interface de chat.

**Estado vazio com sugestoes.** Tres acoes reais para a folha ativa - auditar, explicar o achado
selecionado, listar o que falta no carimbo - usando o `onInsertPrompt` existente.

**Custo visivel.** `ai_usage_events` ja grava provider, modelo, tokens e custo, e `/usage` ja
serve o dado; nada disso aparece na tela. Entra um rodape discreto com o gasto da conversa.

**Acessibilidade.** A regiao de mensagens recebe `aria-live="polite"` para anunciar chegada e
conclusao, e o botao de parar recebe foco durante o streaming.

### Nao esta no escopo

Substituir o `truss-chat.tsx`. Ele ja tem copiar, regenerar, editar, feedback, conversas e
trilha de atividade, construidos e funcionando. O que falta e layout, estado visivel e
hierarquia.

## Verificacao

Cada item abaixo e verificado na aplicacao rodando, com o projeto real de 28 folhas carregado:

- a pagina nao rola; canvas, gaveta e chat rolam de forma independente;
- arrastar move a prancha; roda da zoom no cursor; `Shift+arrastar` seleciona;
- rolagem de dois dedos no trackpad faz pan, nao zoom;
- nao e possivel perder a prancha fora da tela;
- a gaveta abre, fecha e lembra o estado apos recarregar;
- durante uma resposta o estado "gerando" e o botao parar ficam visiveis sem rolar;
- um erro de IA mostra causa especifica e acao de retentar;
- rodar auditoria duas vezes na mesma folha nao duplica o card.

Testes automatizados cobrem apenas a logica pura extraida - clamp de pan, decisao de origem da
roda, maquina de estados do chat e deduplicacao de achados. Segue a preferencia registrada de
suites enxutas: o que quebra silenciosamente ganha teste, o resto e verificado na tela.
