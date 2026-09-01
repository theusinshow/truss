# Revisao F3.2 - continuidade explicita de pilares

Data: 2026-08-31  
Pipeline medido: `sheetmap-v0.7` + `audit-v0.4`  
Fonte: projeto-base com views e niveis ja confirmados pelo proprietario

## Gate de pareamento

O projeto-base possui oito forms views com nivel numerico bruto entre `EST-0060-B` e
`EST-0090-B`. O registry derivado reconheceu seis pares seguros:

| origem | alvo | metodo | evidencia |
|---|---|---|---|
| `-650 / EST-0060-B` | `-350 / EST-0060-B` | mesma folha | ordem de nivel |
| `-350 / EST-0060-B` | `-167 / EST-0060-B` | mesma folha | ordem de nivel; alvo sem cobertura de codigos |
| `-04 / EST-0070-B` | `338 / EST-0080-B` | folhas consecutivas | 11 codigos compartilhados |
| `338 / EST-0080-B` | `680 / EST-0080-B` | mesma folha | 13 codigos compartilhados |
| `680 / EST-0080-B` | `780 / EST-0090-B` | folhas consecutivas | P27, P39, P40 e P41 |
| `780 / EST-0090-B` | `940 / EST-0090-B` | mesma folha | conjunto P27/P39/P40/P41 completo |

O limite entre `-167` e `-04` nao foi automatizado. A view `-167` nao possui pilares associados
com confianca suficiente, logo nao sustenta pareamento entre folhas nem afirmacao de ausencia.

O gate foi considerado satisfeito com a seguinte restricao: dentro da mesma folha vale a ordem
numerica relativa; entre folhas, somente bordas de paginas consecutivas com pelo menos tres
codigos compartilhados e overlap coefficient de 0,50. O algoritmo nunca ordena toda a revisao.
Isso isola PDFs do acervo que carregam varias estruturas independentes e reutilizam cotas/codigos.

## Gate de lifecycle

O texto nativo contem 37 expressoes `MORRE` e 7 `NASCE` ligadas ao codigo quando quebras de linha
sao ignoradas. O contrato seguro associou somente os 22 casos na mesma linha: 19 `MORRE` e 3
`NASCE`.

Os 22 casos restantes possuem codigo e marcador em linhas diferentes. Eles permanecem sem estado
porque a proximidade vertical, sozinha, pode escolher o marcador de outro pilar. Tambem nao existe
nenhum `Pxx(PASSA)` textual no corpus; `Pilar que passa` aparece apenas na legenda.

Resultado da regra no projeto-base:

- 18 `PASS`;
- 1 `UNKNOWN`;
- 0 `FAIL`;
- 5 folhas `NOT_APPLICABLE` por nao possuirem lifecycle explicito.

O `UNKNOWN` e intencional: a declaracao possui estado, mas nao existe par/target coberto suficiente
para concluir. Nenhum caso foi transformado em conformidade por falta de dados.

## Decisao operacional

O primeiro release da F3.2 pode seguir com estados inline/mesma linha e os seis pares acima. Nao
esta autorizado:

- tratar pilar sem etiqueta como `PASSA`;
- ligar marcador de outra linha por distancia;
- ordenar niveis de toda a revisao;
- converter nivel bruto para metros;
- suprimir findings com base no acervo aprovado.

O arquivo executavel do gabarito e
`calibration/human-review/f3-pillar-continuity-ground-truth.yml`.

