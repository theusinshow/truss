# Medicao F3.2 - continuidade explicita de pilares

Data: 2026-09-01  
Pipeline: `sheetmap-v0.7` + `audit-v0.4`  
Execucao: importacao, Sheet Map, registry e auditoria em banco descartavel por PDF

## Resultado agregado

O projeto-base e os 12 PDFs aprovados somam 259 paginas. O pipeline encontrou 78 marcacoes de
lifecycle na mesma linha do codigo: 72 `MORRE` e 6 `NASCE`. Destas, 41 ficaram associadas com
seguranca a uma forms view: 38 `MORRE` e 3 `NASCE`. Nenhum `PASSA` individual foi inventado a
partir das legendas.

- 30 forms views com nivel numerico relativo;
- 10 pares seguros: 8 na mesma folha e 2 entre folhas consecutivas;
- zero ambiguidades registradas pelo pareador;
- 20 `PASS`, 25 `UNKNOWN`, 92 `NOT_APPLICABLE` e zero `FAIL`;
- zero findings candidatos no acervo aprovado;
- 156,59 MiB de artefatos temporarios produzidos pelos 13 processamentos;
- 941,32 segundos de tempo acumulado por documento (execucao paralela em quatro lotes).

`UNKNOWN` nao e tratado como defeito do corpus: ele preserva declaracoes cujo nivel pareado ou alvo
observavel nao foi estabelecido. Nenhuma regra, extrator, allowlist ou gabarito foi alterado para
suprimir candidatos.

## Resultado por documento

| documento | pag. | lifecycle | associado | niveis | pares | PASS | UNKNOWN | N/A | FAIL |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Projeto Estrutural Juliano Corbellini R05 | 29 | 22 | 19 | 8 | 6 | 18 | 1 | 5 | 0 |
| Prj estrutural Lagoa 01 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Proj EEE Sao Jose Almeida | 72 | 0 | 0 | 0 | 0 | 0 | 0 | 36 | 0 |
| Proj est Valcir R01 | 8 | 9 | 5 | 0 | 0 | 0 | 9 | 1 | 0 |
| Proj Estrutural EEEs Inimutaba geral | 44 | 0 | 0 | 0 | 0 | 0 | 0 | 22 | 0 |
| Proj Estrutural ETE1 Inimutaba | 7 | 0 | 0 | 1 | 0 | 0 | 0 | 2 | 0 |
| Proj Estrutural ETE2 Inimutaba | 9 | 0 | 0 | 1 | 0 | 0 | 0 | 2 | 0 |
| Proj Estrutural R02 | 5 | 0 | 0 | 2 | 1 | 0 | 0 | 1 | 0 |
| Rancho Queimado estrutural/madeira | 30 | 47 | 17 | 5 | 2 | 2 | 15 | 5 | 0 |
| Guarita Country Club MMD R01 | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| EST-0010 a EST-0240 Profunda | 26 | 0 | 0 | 7 | 1 | 0 | 0 | 9 | 0 |
| EST-0880 a EST-0960 | 9 | 0 | 0 | 3 | 0 | 0 | 0 | 4 | 0 |
| EST-1040 a EST-1140 | 11 | 0 | 0 | 3 | 0 | 0 | 0 | 4 | 0 |
| **Total** | **259** | **78** | **41** | **30** | **10** | **20** | **25** | **92** | **0** |

## Leitura do gate

Os dois pares entre folhas pertencem ao projeto-base e reproduzem o gabarito humano. Os oito pares
restantes sao internos a uma folha. PDFs com varias estruturas independentes nao foram unidos por
ordenacao global. O Rancho Queimado concentra 15 `UNKNOWN`: as declaracoes foram preservadas, mas
o pipeline nao declarou ausencia/presenca sem par e alvo coberto. Valcir preservou nove estados
como `UNKNOWN` porque nenhuma forms view com nivel numerico seguro foi formada.

O gabarito que sustenta o gate permanece separado em
`calibration/human-review/f3-pillar-continuity-ground-truth.yml`; a revisao manual do projeto-base
esta em `calibration/human-review/f3-pillar-continuity-review.md`.

## Verificacao manual no viewer

O fluxo sintetico foi aberto no viewer com uma contradicao `P1(MORRE)` entre os niveis `100` e
`200`. A tela focalizou a bbox PDF da declaracao, exibiu `Elemento P1 / MORRE`, a transicao bruta,
o aviso de hipotese e as sete evidencias, incluindo folha/view alvo e `registry_hash`.

O par real entre folhas tambem foi percorrido no viewer do projeto-base. `EST-0080-B` apresentou
as forms views de niveis `338` e `680`; a folha seguinte `EST-0090-B` apresentou `780` e `940`.
Isso confirmou visualmente a borda real `680 -> 780` usada por
`adjacent-sheet-code-overlap-v1`. Ambas as folhas permaneceram sem achados de continuidade, em
acordo com os `PASS` registrados e sem converter ausencia de finding em prova adicional.
