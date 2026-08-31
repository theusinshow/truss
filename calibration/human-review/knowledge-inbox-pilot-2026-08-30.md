# Confirmacoes humanas - piloto do acervo

Data: 2026-08-30
Revisor: proprietario
Status: confirmacao parcial

## Significado do acervo `approved`

O proprietario confirmou que os 12 PDFs colocados em `data/knowledge-inbox/approved/` sao versoes
finais entregues e representam seu padrao de projeto. Eles podem conter pequenos erros ainda nao
identificados.

O proprietario tambem confirmou ser o autor dos projetos do acervo. Padroes recorrentes podem,
portanto, gerar propostas de preferencias pessoais. A autoria nao transforma automaticamente uma
convencao recorrente em regra tecnica geral.

Consequencias para a calibracao:

- o acervo mede principalmente o piso de ruido do Truss;
- um finding novo e candidato a falso positivo ou a pequeno erro real e precisa de revisao humana;
- a condicao `approved` nao equivale a `confirmed_zero` para findings;
- nenhum finding deve ser rejeitado ou convertido em excecao automaticamente por aparecer neste
  acervo.

## Escopo

Esta confirmacao cobre somente a identidade e a classificacao das quatro folhas abaixo. Ela nao
confirma bounding boxes, todas as views, ausencia de findings ou aprovacao tecnica integral dos
documentos.

## Classificacoes confirmadas

| Documento | Folha canonica | Classificacao confirmada |
|---|---|---|
| `Proj_Estrutural_RanchoQueimado_geral_madeira.pdf` | `EST-0290-A` | detalhamento dos apoios da cobertura de madeira |
| `Proj_Estrutural_RanchoQueimado_geral_madeira.pdf` | `EST-0300-A` | planta e cortes da cobertura de madeira |
| `XXXXX-SES-ETE-EST-1040-A a XXXXX-SES-ETE-EST-1140-A.pdf` | `EST-1040-A` | detalhamento/sugestao de armadura para estaca helice continua |
| `XXXXX-SES-ETE-EST-1040-A a XXXXX-SES-ETE-EST-1140-A.pdf` | `EST-1060-A` | detalhamento de blocos de fundacao e pilares de arranque |

## Familia de plantas e cortes

O proprietario confirmou que as folhas descritas no carimbo como `PLANTA ALTA, PLANTA BAIXA E
CORTES` ou `PLANTA ALTA, PLANTA BAIXA / CORTES` devem ser classificadas como
`planta_formas`.

No primeiro processamento do acervo, essa confirmacao cobre 29 folhas: 18 em
`Proj_EEE_São_josé_Almeida.pdf` e 11 em `Proj_Estrutural_EEEs_Inimutaba_geral.pdf`. A confirmacao
e aplicada aos rascunhos de calibracao com origem humana explicita; ela nao ativa silenciosamente
uma heuristica no classificador de producao.

## Familia de detalhamento de armaduras

O proprietario confirmou que as folhas que agrupam `DETALHAMENTO DE VIGAS`, `ARMACAO DAS LAJES`
e `DETALHAMENTO DE PILARES` sao pranchas de armaduras e devem ser classificadas como
`planta_armaduras`.

No primeiro processamento, essa confirmacao cobre quatro folhas dos documentos
`Proj_Estrutural_ETE1_Inimutaba.pdf` e `Proj_Estrutural_ETE2_Inimutaba.pdf`.

O proprietario confirmou ainda que as folhas de sugestao/detalhamento de armadura para estaca
helice continua e de detalhamento de blocos de fundacao e pilares de arranque tambem pertencem a
categoria principal `planta_armaduras`. A solucao detalhada permanece como subtipo, nao como tipo
principal da prancha. Essa confirmacao cobre as folhas equivalentes nos dois pacotes de ETE:

- `EST-0010-A` e `EST-0030-A` em `XXXX-SES-ETE-EST-0010 a EST-0240-A-PROFUNDA.pdf`;
- `EST-1040-A` e `EST-1060-A` em
  `XXXXX-SES-ETE-EST-1040-A a XXXXX-SES-ETE-EST-1140-A.pdf`.

Na inspecao das 17 folhas restantes sem categoria, o proprietario confirmou:

- 16 folhas com detalhamentos de vigas, pilares, fundacoes, radier, lajes ou piscina como
  `planta_armaduras`;
- a pagina 3 de `Proj_est_valcir_R01.pdf`, composta por cortes e perspectivas da cobertura de
  madeira, como `planta_cobertura_madeira`.

Depois da estabilizacao do intake em 2026-08-31, todas as 230 paginas possuem uma linha no
rascunho, sem lacunas. As duas paginas sem view detectada nao sao mais omitidas: pagina 30 de
`Proj_Estrutural_EEEs_Inimutaba_geral.pdf` e pagina 21 de
`XXXX-SES-ETE-EST-0010 a EST-0240-A-PROFUNDA.pdf` carregam `views: []` e
`view_detection_status: no_views_detected`. Isso marca segmentacao pendente, nao folha vazia ou
revisada, e nao significa que os demais atributos estejam confirmados.

## Pranchas mistas

A pagina 30 de `Proj_Estrutural_EEEs_Inimutaba_geral.pdf`, descrita como `FORMAS LAJES TOPO,
DET. TAMPA E DET. REFORCO NA ABERTURA`, foi confirmada pelo proprietario como uma prancha mista de
formas e armaduras. O proprietario informou que esse tipo de composicao acontece com frequencia.

Essa evidencia nao deve ser reduzida a um unico `sheet_type`. A classificacao correta precisa
preservar os dois escopos e, quando houver segmentacao confiavel, associar cada escopo as views ou
regioes correspondentes. A alteracao multiescopo foi aprovada explicitamente e implementada no
Sheet Map, nas views, nas avaliacoes de regras, nos achados e na cobertura de auditoria.

A pagina 21 de `XXXX-SES-ETE-EST-0010 a EST-0240-A-PROFUNDA.pdf` declara explicitamente `PLANTA DE
ARMADURAS` e `DETALHAMENTO VIGAS` e segue a familia de armaduras ja confirmada pelo proprietario.

## Identidade bruta e canonica

O texto nativo do carimbo contem `XXXXX-SES-ETE-EST-01040-A` e
`XXXXX-SES-ETE-EST-01060-A`. O proprietario confirmou como codigos canonicos
`EST-1040-A` e `EST-1060-A`, sem o zero adicional.

O Truss deve preservar o texto bruto como evidencia e tratar a forma canonica como normalizacao
humana confirmada. Esta confirmacao nao autoriza uma regra generica de remocao de zeros em outros
codigos de folha.

O intake v4 implementa essa separacao. No corpus regenerado, 151 folhas tiveram codigo canonico
detectado, duas mantiveram normalizacao humana confirmada, 48 possuem somente codigo bruto
pendente de confirmacao e 29 ficaram explicitamente como `not_verifiable`.

## Origem da confirmacao

O pipeline classificou as quatro folhas como `desconhecido` durante o lote piloto. As
classificacoes acima foram propostas ao proprietario e confirmadas explicitamente na conversa.
