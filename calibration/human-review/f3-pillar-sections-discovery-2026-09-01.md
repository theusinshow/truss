# Descoberta F3.3 - secoes explicitas de pilares

Data: 2026-09-01  
Estado: levantamento exploratorio; nao e gabarito humano nem metrica de release

## Objetivo

Medir como secoes de pilares aparecem no texto nativo antes de propor qualquer extrator ou regra.
O levantamento usou o projeto-base e os 12 PDFs aprovados, sem alterar os arquivos, o banco
principal ou a memoria explicita.

## Forma da evidencia

Nos seis documentos com texto utilizavel, nenhum codigo de pilar e sua secao apareceu no mesmo
span/linha logica do PDF. A forma recorrente e espacial: um span `P1` fica ao lado de outro span
`40x40 cm` ou `40x40`. Isso ocorre tanto em etiquetas de planta quanto em tabelas de pilares.

Uma regex isolada nao estabelece pertencimento. Vigas usam a mesma notacao (`V300 20x60`) e
dimensoes de lajes, blocos e tabelas podem estar proximas. A futura associacao precisa considerar
bbox, view, distancia ao codigo e concorrencia de outros elementos.

## Varredura nativa

O numero abaixo conta spans brutos, inclusive repeticoes do mesmo pilar em planta e tabela. O
limite de 3 pt foi usado somente para observar o corpus; ele ainda nao e limiar aprovado.

| documento | spans `Pxx` | spans `axb` | candidato ate 3 pt | candidato ate 10 pt | multiplas dimensoes ate 10 pt |
|---|---:|---:|---:|---:|---:|
| Projeto Estrutural Juliano Corbellini R05 | 701 | 624 | 123 | 123 | 7 |
| Prj estrutural Lagoa 01 | 84 | 42 | 21 | 21 | 0 |
| Proj est Valcir R01 | 144 | 121 | 18 | 18 | 0 |
| Proj Estrutural R02 | 200 | 164 | 42 | 42 | 0 |
| Rancho Queimado estrutural/madeira | 922 | 1.157 | 219 | 228 | 14 |
| Guarita Country Club MMD R01 | 265 | 172 | 62 | 62 | 2 |
| sete PDFs sem codigos/secoes em texto nativo utilizavel | 0 | 0 | 0 | 0 | 0 |
| **Total** | **2.316** | **2.280** | **485** | **494** | **23** |

Exemplos observados incluem `40x40`, `20x50`, `14x40`, `27x57`, `19x30`, `15x30` e
`19x19`. Alguns spans carregam `cm`; outros dependem de um cabecalho de tabela `(cm)` ou nao
declaram unidade localmente. Nenhuma unidade pode ser completada por convencao.

## Transicoes preliminares em pares F3.2

Uma associacao exploratoria ligou a ocorrencia ao unico span `axb` a ate 3 pt. Casos com dois
candidatos praticamente equidistantes foram descartados. Os numeros servem para escolher o
gabarito; nao autorizam a regra.

| documento | niveis | iguais | alteradas | sem duas secoes univocas |
|---|---|---:|---:|---:|
| projeto-base | `338 -> 680` | 5 | 0 | 10 |
| projeto-base | `680 -> 780` | 1 | 1 | 6 |
| projeto-base | `780 -> 940` | 4 | 0 | 0 |
| projeto-base | `-350 -> -167` | 0 | 0 | 1 |
| projeto-base | `-650 -> -350` | 1 | 0 | 3 |
| projeto-base | `-04 -> 338` | 1 | 6 | 20 |
| Proj Estrutural R02 | `-0.05 -> 2.75` | 1 | 11 | 2 |
| Rancho Queimado | `4.30 -> 5.80` | 5 | 0 | 1 |
| Rancho Queimado | `-1.36 -> 3.30` | 0 | 0 | 23 |
| **Total** |  | **18** | **18** | **66** |

Mudancas preliminares no projeto-base:

- `P27: 20x40 -> 20x20` entre `680` e `780`;
- `P16: 20x40 -> 14x30` entre `-04` e `338`;
- `P19: 20x40 -> 14x40`;
- `P25: 20x60 -> 14x60`;
- `P28: 20x35 -> 14x30`;
- `P29: 20x40 -> 14x40`;
- `P34: 20x40 -> 14x40`.

No R02, onze pilares passam majoritariamente de `20x30` para `14x30`; `P3` permanece `19x19`.
No Rancho Queimado, cinco comparacoes resolvidas permanecem iguais. Todos os 18 casos alterados
precisam de revisao humana antes de virar expectativa de calibracao.

## Consequencias para o plano

- mudanca de secao e comum e pode ser intencional; nao e erro confirmado;
- ausencia de secao nao significa ausencia do pilar;
- codigo observado nos dois niveis permite comparar evidencia sem classifica-lo como `PASSA`;
- a ordem `14x30` versus `30x14` deve ser preservada, mas nao prova mudanca de tamanho;
- tabela e etiqueta de planta podem reforcar uma secao quando concordam e criar ambiguidade quando
  divergem;
- os sete PDFs sem texto nativo permanecem `NOT_APPLICABLE`, sem OCR ou visao neste slice.

O proximo artefato humano deve revisar amostras positivas e negativas, medir distancia e direcao
entre bboxes e identificar quando uma dimensao pertence a viga, pilar, tabela ou outro elemento.
