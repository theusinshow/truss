# Medicao F3.3 - secoes explicitas de pilares

Data: 2026-09-01  
Pipeline: `sheetmap-v0.8` + `audit-v0.5` + `formas_geral@1.3.0`  
Execucao: importacao, Sheet Map, registry e auditoria em banco descartavel por PDF

## Resultado agregado

O projeto-base e os 12 PDFs aprovados somam 259 paginas. O extrator reconheceu 1.850 spans
autonomos `a x b` no corpus. Depois do contrato espacial aprovado na Task 1, 353 ficaram associadas
a uma ocorrencia de pilar dentro da mesma view e 3 permaneceram ambiguas por dimensoes concorrentes.

- 353 associacoes, todas com proveniencia `adjacent-label`;
- zero associacoes `table-row`: a gramatica de linha de tabela nao entrou neste slice;
- 351 pares `view_id + code` resolvidos e 4 ambiguos;
- 10 pares de niveis seguros herdados da F3.2;
- 19 `PASS`, 18 `FAIL`, 41 `UNKNOWN` e 184 `NOT_APPLICABLE`;
- 18 pontos de atencao, todos `ATTENTION_POINT` de severidade `MEDIUM`;
- 156,59 MiB de artefatos temporarios produzidos pelos 13 processamentos;
- 1.209,25 segundos de tempo acumulado por documento (execucao paralela em quatro lotes).

Os 18 `FAIL` reproduzem exatamente as 18 mudancas preliminares revisadas na Task 1: 7 no
projeto-base e 11 no R02. Nenhum candidato novo apareceu e nenhum dos revisados sumiu. Nenhuma
regra, extrator, allowlist ou gabarito foi alterado para suprimir candidatos.

## Resultado por documento

| documento | pag. | cand. | assoc. | ambig. | resolv. | ambig. view+cod | pares | PASS | FAIL | UNKNOWN | N/A |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Projeto Estrutural Juliano Corbellini R05 | 29 | 548 | 54 | 0 | 54 | 0 | 6 | 13 | 7 | 30 | 7 |
| Prj estrutural Lagoa 01 | 1 | 42 | 20 | 0 | 20 | 0 | 0 | 0 | 0 | 0 | 0 |
| Proj EEE Sao Jose Almeida | 72 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 36 |
| Proj est Valcir R01 | 8 | 106 | 10 | 0 | 8 | 1 | 0 | 0 | 0 | 0 | 10 |
| Proj Estrutural EEEs Inimutaba geral | 44 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 22 |
| Proj Estrutural ETE1 Inimutaba | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 |
| Proj Estrutural ETE2 Inimutaba | 9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 |
| Proj Estrutural R02 | 5 | 144 | 40 | 0 | 40 | 0 | 1 | 1 | 11 | 2 | 12 |
| Rancho Queimado estrutural/madeira | 30 | 875 | 216 | 3 | 216 | 3 | 2 | 5 | 0 | 9 | 69 |
| Guarita Country Club MMD R01 | 8 | 135 | 13 | 0 | 13 | 0 | 0 | 0 | 0 | 0 | 7 |
| EST-0010 a EST-0240 Profunda | 26 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 9 |
| EST-0880 a EST-0960 | 9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 4 |
| EST-1040 a EST-1140 | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 4 |
| **Total** | **259** | **1.850** | **353** | **3** | **351** | **4** | **10** | **19** | **18** | **41** | **184** |

## Pontos de atencao para revisao humana

Nenhum deles afirma erro estrutural. Todos dizem que a notacao mudou entre dois niveis pareados e
pedem verificacao.

| documento | codigo | transicao | niveis | confianca |
|---|---|---|---|---:|
| projeto-base | P27 | `20x40 -> 20x20` | 680 -> 780 | 0,850 |
| projeto-base | P16 | `20x40 -> 14x30` | -04 -> 338 | 0,584 |
| projeto-base | P19 | `20x40 -> 14x40` | -04 -> 338 | 0,584 |
| projeto-base | P25 | `20x60 -> 14x60` | -04 -> 338 | 0,584 |
| projeto-base | P28 | `20x35 -> 14x30` | -04 -> 338 | 0,584 |
| projeto-base | P29 | `20x40 -> 14x40` | -04 -> 338 | 0,584 |
| projeto-base | P34 | `20x40 -> 14x40` | -04 -> 338 | 0,584 |
| R02 | P2, P5, P6, P7, P8, P9, P10, P11, P12, P13, P14 | `20x30 -> 14x30` | -0.05 -> 2.75 | 0,850 |

Nenhuma das secoes traz unidade explicita no span. O finding registra `unidade: ausente` e a tela
mostra `UNIDADE NAO DECLARADA`; nada e convertido nem lido como centimetro por convencao.

## Diferenca para a varredura exploratoria

A revisao da Task 1 contou 478 associacoes univocas com um script proprio sobre os spans brutos. O
pipeline associou 353. A diferenca nao e perda de contrato: o pipeline so associa a uma ocorrencia
de pilar que ja esteja ligada a uma view reconhecida, entao codigos fora de view segmentada nao
recebem secao. Rancho Queimado bate exatamente (216); projeto-base cai de 119 para 54, Guarita de
62 para 13 e Valcir de 18 para 10 pelo mesmo motivo.

Isso mantem a promessa do slice: secao e atributo coordenado de uma ocorrencia observada dentro de
uma view, nunca um texto solto promovido a dado estrutural.

## Leitura dos resultados nao positivos

`NOT_APPLICABLE` domina porque a maioria das folhas nao tem secao associada ou nao tem par seguro
de niveis - inclusive as sete folhas do corpus sem texto nativo utilizavel. `UNKNOWN` concentra os
casos em que uma das pontas nao e univoca: 30 no projeto-base e 9 no Rancho Queimado, onde as tres
ocorrencias de `P30` com `19x30` e `19x40` concorrentes permanecem ambiguas, como previsto na
revisao.

Limite consciente registrado: um pilar observado sem nenhuma secao associada na folha de origem nao
gera avaliacao. A regra so se pronuncia sobre codigos que tem secao em pelo menos uma ponta, do
mesmo modo que a F3.2 so avalia pilares com lifecycle explicito. Isso evita transformar a ausencia
normal de notacao em um volume de `UNKNOWN` sem informacao.

## Verificacao manual no viewer

O projeto-base foi importado num `data_dir` descartavel e aberto no viewer; o acervo real do
proprietario nao foi tocado.

A folha `EST-0080-B` (8/29) apresentou o achado alterado e as transicoes iguais na mesma auditoria:

- alterado: `ELEMENTO P27 / 20X40 -> 20X20`, `ATTENTION`, `MEDIUM`, `85%`, `NIVEL 680 -> 780`,
  `FOLHA EST-0080-B -> EST-0090-B`, `UNIDADE NAO DECLARADA`, aviso de hipotese pendente,
  `REGIAO / 740,1202 -> 760,1213 PT` e `REGISTRY / 768F15A201F79E2D1D01E057`;
- iguais: seis `PASS` na mesma folha, entre eles `P27` com `20x40 -> 20x40` em outro par de views,
  `P16`, `P28` e `P37` com `14x30 -> 14x30`. Nenhum gerou achado, como esperado.

A evidencia bruta abriu no disclosure `Ver evidencia completa (+4)`, mostrando as duas pontas com
folha, view, nivel, secao, assinatura, ordem impressa e bbox em pontos PDF, alem de proveniencia,
pareamento e `registry_hash`. O bloco nao anima e o reset global de `prefers-reduced-motion` do
design system continua valendo.

## Conclusao

A medicao de release confirma o contrato aprovado no gate: os 18 candidatos revisados sao
exatamente os 18 pontos de atencao produzidos, os casos duvidosos permanecem `UNKNOWN` e nenhuma
unidade foi inferida. O gabarito continua em
`calibration/human-review/f3-pillar-sections-ground-truth.yml` e a revisao humana em
`calibration/human-review/f3-pillar-sections-review.md`.
