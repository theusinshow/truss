# Medicao F3 - elementos de pilares e cruzamento entre folhas

Data: 2026-08-31  
Pipeline: `sheetmap-v0.6` + `audit-v0.3`  
Escopo: projeto-base versionado e 12 PDFs locais do acervo `approved`

## Metodo

Cada PDF foi importado como uma revisao isolada em banco SQLite temporario. A medicao executou o
mesmo fluxo do produto: importacao, extracao rica, Sheet Map, persistencia de elementos, registry
derivado, auditoria e findings. Nenhum PDF e nenhum banco de trabalho foi alterado.

O corpus aprovado mede piso de ruido. `approved` nao significa ausencia confirmada de defeitos;
qualquer finding seria apenas candidato a falso positivo ou pequeno erro real, pendente de revisao
humana.

## Resultado agregado

| metrica | resultado |
|---|---:|
| PDFs | 13 |
| paginas | 259 |
| ocorrencias de pilares | 2.558 |
| ocorrencias com associacao espacial ambigua | 537 |
| `PASS` cross-sheet | 190 |
| `UNKNOWN` | 37 |
| `NOT_APPLICABLE` | 85 |
| `FAIL` / candidatos a finding | **0** |
| artefatos de geometria e extracao | 164.196.071 bytes (~156,6 MiB) |

Seis PDFs, incluindo o projeto-base, expuseram codigos `P...` utilizaveis. Sete PDFs possuem texto
nativo, mas os identificadores de pilares nao aparecem em codificacao reconhecivel; nesses casos a
regra retorna `NOT_APPLICABLE`, nunca conformidade ou erro inventado.

## Resultado por documento

| documento | paginas | pilares | ambiguos | outcomes F3 | findings |
|---|---:|---:|---:|---|---:|
| Projeto Estrutural Juliano Corbellini R05 | 29 | 769 | 277 | 55 PASS, 3 N/A | 0 |
| Prj estrutural Lagoa 01 | 1 | 126 | 0 | sem folha de formas aplicavel | 0 |
| EEE Sao Jose Almeida | 72 | 0 | 0 | 36 N/A | 0 |
| Valcir R01 | 8 | 144 | 55 | 9 UNKNOWN, 1 N/A | 0 |
| EEEs Inimutaba geral | 44 | 0 | 0 | 22 N/A | 0 |
| ETE1 Inimutaba | 7 | 0 | 0 | 2 N/A | 0 |
| ETE2 Inimutaba | 9 | 0 | 0 | 2 N/A | 0 |
| Estrutural R02 | 5 | 228 | 0 | 14 UNKNOWN | 0 |
| Rancho Queimado madeira | 30 | 1.026 | 82 | 135 PASS, 2 N/A | 0 |
| Guarita Country Club | 8 | 265 | 123 | 14 UNKNOWN | 0 |
| ETE profunda 0010-0240 | 26 | 0 | 0 | 9 N/A | 0 |
| ETE 0880-0960 | 9 | 0 | 0 | 4 N/A | 0 |
| ETE 1040-1140 | 11 | 0 | 0 | 4 N/A | 0 |

## Falso positivo evitado durante a medicao

A primeira rodada no projeto-base produziu 26 candidatos. Duas causas foram encontradas:

1. codigos em envelopes de armaduras sobrepostos ficavam sem `view_id`, embora permanecessem na
   mesma folha de um detalhamento de pilares reconhecido;
2. as quatro folhas `DETALHAMENTO FUNDACOES E PILARES DE ARRANQUE` eram classificadas como
   `locacao` por causa do texto `REVISAO LOCACAO PILARES` no carimbo.

A regra passou a usar a evidencia mais especifica: o titulo explicito da view identifica o alvo, e
os codigos da mesma folha contam como ocorrencias do alvo mesmo quando o envelope nao permite
escolher uma unica view. A segunda rodada caiu para 21 candidatos; depois de incluir os
detalhamentos de fundacoes/pilares de arranque, a terceira rodada chegou a zero.

Nenhuma regra foi silenciada, nenhum codigo foi colocado em allowlist e nenhum finding foi
rejeitado automaticamente. Na fixture defeituosa independente, `P1` aparece nos dois lados e
`P2` somente na forma: o resultado permanece 1 PASS + 1 FAIL e um finding localizado para `P2`.

## Desempenho e limites

O projeto-base levou 32,6 s para 29 paginas. O lote sequencial equivalente soma aproximadamente
16 minutos; em grupos paralelos, o maior documento (72 paginas) levou 249 s. O custo dominante e
a extracao vetorial e escrita dos artefatos, nao a consulta do registry.

Isso e aceitavel como medicao offline, mas ainda nao caracteriza experiencia de lote pronta para
uso diario. Progresso, retomada e otimizacao de lote continuam pertencendo a F6.

Limites atuais:

- somente pilares `P...` em texto nativo;
- nenhuma alegacao quando o codigo nao e recuperavel;
- nenhuma continuidade entre niveis;
- nenhum pareamento semantico entre cada planta e seu pavimento de detalhamento;
- envelopes agrupadores continuam precisando de subviews para rastreabilidade mais fina.

