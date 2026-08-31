# Revisao visual de bounding boxes - lote 01

Data de preparacao: 2026-08-31
Status: concluido - 17/17 bounding boxes confirmados pelo proprietario
Sistema de coordenadas: pontos PDF

## Objetivo

Validar uma amostra transversal antes de promover qualquer `bbox_status` para
`human_verified`. O lote cobre formas, armaduras, locacao, cobertura de madeira,
fundacoes e uma prancha mista.

O primeiro render revelou 17 de 17 caixas orientadas para baixo a partir da legenda,
enquanto os desenhos correspondentes estavam acima. Nenhuma foi apresentada como
confirmada. O detector foi corrigido para `deterministic/forms-view-v2`, e as imagens
abaixo representam a segunda rodada.

## Criterio de confirmacao

Uma caixa pode ser confirmada quando contem o desenho associado, seu titulo e sua
escala, sem atribuir silenciosamente o conteudo principal de outra view. Sobreposicao
so e aceitavel quando a familia e espacialmente nao contigua e isso fica explicito
como agrupamento, nunca como caixa precisa.

| Familia | Documento / folha | Views | Pre-auditoria do agente | Confirmacao humana |
|---|---|---:|---|---|
| Formas | `Proj_Estrutural_R02.pdf`, `EST-0030-A` | 4 | duas plantas e dois cortes separados por legenda | 4/4 confirmadas pelo proprietario |
| Armaduras | `Proj_Estrutural_ETE1_Inimutaba.pdf`, `SES-ETE-EST-0060` | 4 | agrupamentos de vigas/lajes/pilares se sobrepoem; precisa de subviews | 4/4 confirmadas como envelopes agrupadores |
| Locacao | `XXXX-SES-ETE-EST-0010 a EST-0240-A-PROFUNDA.pdf`, `EST-0020-A` | 1 | planta e tabelas associadas, sem perspectivas inferiores | 1/1 confirmada pelo proprietario |
| Cobertura de madeira | `Proj_Estrutural_RanchoQueimado_geral_madeira.pdf`, `EST-0300-A` | 3 | dois cortes e envelope da planta com representacao auxiliar | 3/3 confirmadas pelo proprietario |
| Fundacoes | `XXXXX-SES-ETE-EST-1040-A a XXXXX-SES-ETE-EST-1140-A.pdf`, `EST-1060-A` | 1 | detalhe agrupador da folha | 1/1 confirmada como envelope agrupador |
| Mista | `Proj_EEE_São_josé_Almeida.pdf`, `EST-0020-A` | 4 | forma, armaduras positiva/negativa e reforco separados | 4/4 confirmadas pelo proprietario |

## Imagens locais

- [Formas](../../data/knowledge-inbox/.truss/visual-review/batch-02/01-formas-full.png)
- [Armaduras](../../data/knowledge-inbox/.truss/visual-review/batch-02/02-armaduras-full.png)
- [Locacao](../../data/knowledge-inbox/.truss/visual-review/batch-02/03-locacao-full.png)
- [Cobertura de madeira](../../data/knowledge-inbox/.truss/visual-review/batch-02/04-cobertura-madeira-full.png)
- [Fundacoes](../../data/knowledge-inbox/.truss/visual-review/batch-02/05-fundacoes-full.png)
- [Prancha mista](../../data/knowledge-inbox/.truss/visual-review/batch-02/06-mista-full.png)

Os PNGs sao artefatos locais ignorados pelo Git. Os PDFs originais nao foram
alterados.

## Confirmacoes recebidas

### `EST-0030-A` - formas

O proprietario confirmou explicitamente as quatro caixas apresentadas na imagem do lote v2:

1. planta de formas da cobertura;
2. planta de formas do terreo;
3. corte A-A;
4. corte B-B.

Somente `bbox_status` foi promovido para `human_verified`. `human_confirmed` permanece falso nos
rascunhos porque esta resposta nao confirmou titulo, escala, nivel ou os demais atributos da view.

### `EST-0020-A` - locacao

O proprietario confirmou que a caixa inclui corretamente a planta de locacao e suas tabelas,
deixando as perspectivas 3D inferiores de fora. Somente `bbox_status` foi promovido para
`human_verified`.

### `EST-1060-A` - fundacoes

O proprietario confirmou a caixa que envolve o conjunto de detalhamentos de blocos de fundacao e
pilares de arranque. Ela foi registrada com `bbox_semantics: grouping_envelope`: a confirmacao vale
para a extensao grafica do conjunto e nao afirma que cada detalhe interno ja possui uma subview
individual confirmada.

### `EST-0020-A` - prancha mista

O proprietario confirmou as quatro caixas e sua separacao espacial:

1. formas das lajes de topo (`formas`);
2. armadura positiva (`armaduras`);
3. armadura negativa (`armaduras`);
4. corte A-A do reforco na abertura (`armaduras`).

Somente os bounding boxes foram promovidos para `human_verified`; a confirmacao nao transforma os
demais atributos das views em verdade humana.

### `EST-0300-A` - cobertura de madeira

O proprietario confirmou as caixas dos cortes A-A e B-B e a caixa da planta baixa. A terceira
caixa tambem engloba a representacao 3D auxiliar a esquerda e, por isso, foi registrada como
`bbox_semantics: grouping_envelope`.

### `SES-ETE-EST-0060` - armaduras

O proprietario confirmou as quatro caixas como envelopes agrupadores: vigas do terreo, armadura
positiva das lajes, pilares da cobertura e vigas da cobertura. As caixas podem se sobrepor porque
cada familia e espacialmente nao contigua. A confirmacao nao elimina a necessidade futura de
segmentar cada desenho interno como subview.
