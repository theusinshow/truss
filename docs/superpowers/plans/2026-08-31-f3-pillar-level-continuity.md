# F3.2 - Continuidade explicita de pilares entre niveis

Data: 2026-08-31  
Status: concluido e validado em 2026-09-01
Escopo: segundo slice de F3, limitado a estados explicitos de pilares em plantas de formas

## Resultado pretendido

Ao auditar uma planta de formas, o Truss deve reconhecer quando um pilar esta explicitamente
marcado como `MORRE`, `NASCE` ou `PASSA`, localizar o nivel estrutural anterior ou seguinte da
mesma sequencia de plantas e apontar uma contradicao somente quando as duas pontas da comparacao
forem observaveis.

O slice fecha uma verificacao mais estreita que "todo pilar continua corretamente". No corpus
medido, `MORRE` e `NASCE` aparecem junto dos codigos, mas `PASSA` aparece como legenda grafica e
nao como texto individual. Um pilar sem etiqueta nunca sera classificado como `PASSA` por
exclusao. A ausencia de evidencia vira `UNKNOWN` ou `NOT_APPLICABLE`, nao conformidade inventada.

## Base aprovada

Este plano preserva as decisoes ja vigentes:

- PDF e Sheet Map continuam como fonte principal;
- coordenadas permanecem em pontos PDF;
- `sheet_elements` armazena ocorrencias por snapshot imutavel;
- o registry continua derivado, sem tabela materializada;
- revisoes nao sao comparadas nem sobrescritas;
- regras deterministicas precedem visao;
- severidade mede impacto e confianca mede certeza;
- todo finding automatico permanece hipotese pendente de validacao humana.

Nao ha mudanca de Next.js, FastAPI, SQLite, escopo local/pessoal, estrutura central de dados ou
design system.

## Evidencia que orienta o recorte

A politica humana confirmada declara:

- `MORRE`, `NASCE` e mudanca de secao sao indicacoes intencionais;
- um pilar `PASSA` deve ser conferido no proximo nivel;
- um pilar `MORRE` deve estar ausente no proximo nivel.

Uma leitura de texto nativo do projeto-base e dos 12 PDFs locais encontrou marcacoes inline:

| documento | `MORRE` ligado ao codigo | `NASCE` ligado ao codigo | `PASSA` ligado ao codigo |
|---|---:|---:|---:|
| Projeto Estrutural Juliano Corbellini R05 | 37 | 7 | 0 |
| Proj_est_valcir_R01 | 8 | 4 | 0 |
| Rancho Queimado estrutural/madeira | 113 | 0 | 0 |

O material tambem contem marcadores `(MORRE)` separados em spans vizinhos e legendas como
`Pilar que passa`. A legenda prova que a simbologia existe, mas nao identifica sozinha qual codigo
usa cada simbolo. Associar a legenda global a todo pilar seria um falso positivo sistemico.

## Decisoes propostas

### 1. Estado de ciclo de vida e atributo da ocorrencia

Nao sera criada coluna nem tabela nova. O extrator `native-text/pillar-code-v2` adiciona em
`sheet_elements.attributes_json` apenas quando houver evidencia associada ao codigo:

```text
lifecycle_state: morre | nasce | passa
lifecycle_raw: texto preservado do PDF
lifecycle_provenance: inline | adjacent-span
lifecycle_confidence: 0..1
```

Sao aceitos inicialmente:

- `P5(MORRE)`;
- `P1 (NASCE)`;
- `P12(PASSA)`, caso apareca em outro documento;
- codigo e marcador em spans adjacentes, na mesma linha e dentro de distancia tipografica segura.

`Pilar que morre`, `Pilar que nasce` e `Pilar que passa` isolados sao legendas. Eles nao recebem
`element_code` e nao alteram ocorrencias proximas sem uma associacao grafica especifica.

### 2. Ordem de nivel e derivada sem inventar unidade de engenharia

`sheet_views.level_raw` continua preservado e `sheet_views.level` continua nulo quando nao existe
normalizacao humana confirmada. A F3.2 pode calcular uma chave ordinal temporaria para comparar
dois textos numericos, mas nao grava nem exibe uma cota convertida para metros.

O comparador `numeric-relative-level-v1` so aceita uma familia coerente de notacao dentro do grupo:

- sinal opcional;
- digitos;
- no maximo um separador decimal;
- nenhuma unidade ou token residual ambiguo;
- valores distintos e ordenaveis.

Assim, `-650 < -350 < -04 < 338` pode definir ordem relativa sem afirmar que `-650` significa
`-6,50 m`. Mistura de convencoes, nivel repetido ou texto simbolico sem tabela confirmada produz
`UNKNOWN`.

### 3. Uma sequencia estrutural nunca e toda a revisao por padrao

Ordenar globalmente todas as views da revisao e proibido. O acervo contem PDFs com varias
estruturas independentes e codigos de pilar reutilizados.

O `form_level_registry` continua sendo uma consulta derivada. Ele agrupa views candidatas apenas
quando houver evidencia suficiente de que pertencem a mesma sequencia:

1. mesmo documento e escopo tecnico `formas`;
2. view do tipo `plan`, com `level_raw` numerico e associacao confiavel;
3. assinatura de contexto compativel no titulo;
4. sobreposicao significativa de codigos de pilares entre views vizinhas;
5. um unico nivel anterior/seguinte possivel.

Os limiares de sobreposicao nao serao escolhidos por intuicao. A Task 1 mede o corpus e registra
um valor que separa pares reais de estruturas independentes. Se essa separacao nao existir, o
primeiro release fica limitado a pares na mesma folha e a implementacao para antes de ampliar o
pareamento entre folhas.

### 4. A regra avalia somente declaracoes explicitas

Nova regra: `cross_sheet.pillar_lifecycle_continuity`.

| estado na origem | alvo observado | resultado |
|---|---|---|
| `MORRE` | codigo ausente no proximo nivel | `PASS` |
| `MORRE` | codigo presente no proximo nivel | `FAIL` |
| `NASCE` | codigo ausente no nivel anterior | `PASS` |
| `NASCE` | codigo presente no nivel anterior | `FAIL` |
| `PASSA` explicito | codigo presente no proximo nivel | `PASS` |
| `PASSA` explicito | codigo ausente no proximo nivel | `FAIL` |
| qualquer estado | par de nivel ambiguo ou alvo sem extracao confiavel | `UNKNOWN` |
| pilar sem estado explicito | nao avaliado por esta regra | `NOT_APPLICABLE` agregado |

Um `FAIL` gera `INCONSISTENCY`, severidade `HIGH`, localizado na declaracao de origem. A descricao
permanece hipotetica, por exemplo:

> P5 esta marcado como MORRE no nivel -350, mas tambem foi localizado no proximo nivel observado,
> 338.

O finding inclui codigo, estado bruto, niveis brutos, views/folhas dos dois lados, bboxes das
ocorrencias encontradas, versao do extrator, versao da regra e `registry_hash`.

### 5. Ausencia no alvo exige cobertura do alvo

Para concluir que um `PASSA` nao apareceu ou que um `MORRE` realmente desapareceu, a view alvo
precisa ter:

- bbox e escopo confiaveis;
- pelo menos um conjunto observavel de codigos de pilares;
- associacao de elementos suficiente para distinguir a view de outras plantas na folha;
- snapshot corrente dentro do mesmo registry usado pela auditoria.

Elemento alvo sem `view_id`, view vazia ou planta mista ambigua nao sustentam ausencia. O resultado
e `UNKNOWN`.

### 6. Cache e imutabilidade continuam no contrato atual

O novo estado entra no hash do snapshot por `attributes_json`. O `registry_hash` ja incorpora o
hash de cada snapshot corrente, portanto a mudanca de lifecycle, nivel, view ou ocorrencia invalida
o audit run dependente.

O pipeline do Sheet Map sobe para `sheetmap-v0.7` e o da auditoria para `audit-v0.4`. Snapshots e
findings anteriores permanecem legiveis e imutaveis.

### 7. O viewer ganha rastreabilidade, nao uma nova pagina

O finding existente mostra:

- `Elemento P5 / MORRE` em texto tecnico;
- `Origem / nivel -350`;
- `Alvo / nivel 338`;
- folha e view pesquisadas;
- aviso de hipotese pendente.

O foco inicial continua na bbox de origem. Navegacao direta para a ocorrencia alvo pode ser
planejada depois; neste slice, a evidencia textual identifica a folha e a bbox alvo sem criar um
dashboard de continuidade.

## Implementacao em tarefas

### Task 1 - Gabarito de pares de niveis e piso de ruido

Criar um exportador somente leitura que liste, por forms view:

- documento, folha, view e titulo;
- `level_raw`;
- codigos associados;
- estados inline/adjacentes candidatos;
- pares anterior/seguinte sugeridos e motivo da sugestao.

Revisar primeiro `EST-0060-B` a `EST-0090-B` do projeto-base. Registrar pelo menos:

- dois pares reais de niveis;
- um caso sem nivel comparavel;
- um caso de estrutura independente que nao pode ser pareada;
- um `MORRE`, um `NASCE` e um pilar sem estado explicito.

Saida principal:

- `calibration/human-review/f3-pillar-continuity-ground-truth.yml`;
- `calibration/human-review/f3-pillar-continuity-review.md`.

Gate: nenhum pareamento entre folhas e implementado antes de o gabarito separar pares reais de
falsos pares. Se o corpus nao sustentar essa separacao, parar e pedir aprovacao para restringir a
mesma folha ou adicionar uma identidade estrutural explicita.

### Task 2 - Extrator de lifecycle

Evoluir o extrator de pilares sem perder os casos F3.1. O mesmo elemento deve carregar codigo e
estado quando ambos pertencem a mesma expressao textual.

Casos obrigatorios:

- `P5(MORRE)`, `P1 (NASCE)`, `P12(PASSA)`;
- codigo e marcador em spans adjacentes na mesma linha;
- marcador em outra linha nao associado;
- legenda `Pilar que passa` nao associada a nenhum codigo;
- dois codigos proximos de um marcador ficam ambiguos;
- `P21=P38` continua produzindo os dois codigos sem lifecycle inventado.

Arquivos principais:

- `apps/api/truss_api/sheetmap/elements/pillars.py`;
- `apps/api/truss_api/sheetmap/elements/models.py`;
- `apps/api/tests/test_element_extraction.py`.

### Task 3 - Registry de niveis derivado

Enriquecer as views do registry com `document_id`, `level_raw`, `level`, bbox e proveniencia.
Criar funcoes puras para:

- parse ordinal do nivel bruto;
- assinatura de contexto;
- conjunto de pilares por view;
- score de sobreposicao;
- pareamento anterior/seguinte com resultado confiavel ou ambiguo.

Nenhuma tabela `form_level_registry` sera criada.

Testes obrigatorios:

- isolamento entre documentos, revisoes e estruturas;
- ordem numerica relativa sem conversao de unidade;
- nivel duplicado ou notacao incoerente vira ambiguo;
- duas sequencias com codigos reutilizados nao sao unidas;
- fingerprint muda quando lifecycle ou nivel muda;
- snapshot historico nao entra no par atual.

Arquivos principais:

- `apps/api/truss_api/sheetmap/elements/registry.py`;
- novo `apps/api/truss_api/sheetmap/elements/levels.py`;
- `apps/api/tests/test_element_registry.py`;
- novo `apps/api/tests/test_pillar_level_registry.py`.

### Task 4 - Regra de continuidade

Adicionar `pillar_lifecycle_continuity` ao motor e ao pack geral de formas. Uma avaliacao e criada
por codigo com estado explicito; codigos repetidos na mesma view sao deduplicados sem perder as
evidencias.

Fixtures obrigatorias de tres niveis:

- `P1(PASSA)` presente no seguinte: `PASS`;
- `P1(PASSA)` ausente com alvo coberto: `FAIL`;
- `P2(MORRE)` ausente no seguinte: `PASS`;
- `P2(MORRE)` presente no seguinte: `FAIL`;
- `P3(NASCE)` ausente no anterior: `PASS`;
- `P3(NASCE)` presente no anterior: `FAIL`;
- alvo vazio, escopo ambiguo ou nivel nao pareavel: `UNKNOWN`;
- pilar sem estado: nenhum finding;
- estrutura independente com mesmo `P1`: nenhum cruzamento.

Arquivos principais:

- `apps/api/truss_api/rules/packs/formas_geral.v1.yml`;
- `apps/api/truss_api/rules/engine.py`;
- novo `apps/api/tests/test_pillar_continuity_rules.py`.

### Task 5 - Orquestracao, cache e persistencia de findings

Reutilizar `element_code`, `view_id`, bbox e `registry_hash`. O dedupe inclui regra, codigo, estado
e view de origem para que duas declaracoes legitimas em niveis diferentes nao colidam.

Testar:

- reexecucao identica usa cache e nao duplica feedback;
- novo snapshot do nivel alvo invalida o run da origem;
- finding confirmado/rejeitado antigo nao e sobrescrito;
- remover a contradicao em novo snapshot impede novo finding, sem apagar o historico.

Arquivos principais:

- `apps/api/truss_api/audit/orchestrator.py`;
- `apps/api/truss_api/audit/repository.py`;
- `apps/api/tests/test_audit.py`;
- `apps/api/tests/test_findings_traceability.py`.

### Task 6 - Apresentacao no viewer

Antes de alterar o componente, aplicar a skill de UI/UX do ambiente. Manter a linguagem CAD
escura, mono para nivel/codigo e reduced motion. Nao criar nova pagina.

Testar:

- label tecnico com codigo e estado;
- niveis brutos de origem/alvo;
- aviso de hipotese em finding pendente;
- evidencia longa nao rompe o drawer;
- foco continua na bbox PDF da ocorrencia fonte.

Arquivos principais:

- `apps/web/lib/projects-api.ts`;
- `apps/web/components/sheet-viewer.tsx`;
- `apps/web/tests/finding-presentation.test.ts`.

### Task 7 - Medicao real e documentacao

Reprocessar projeto-base e os 12 PDFs locais aprovados em bancos descartaveis. Registrar:

- estados por tipo e por documento;
- marcadores ambiguos ou nao associados;
- views com nivel bruto e views pareaveis;
- pares dentro da mesma folha e entre folhas;
- `PASS`, `FAIL`, `UNKNOWN` e `NOT_APPLICABLE`;
- candidatos a finding para revisao humana;
- tempo e tamanho adicional do snapshot.

Nenhum candidato do acervo aprovado sera rejeitado automaticamente. Cada `FAIL` deve ser aberto no
viewer antes de alterar regra, extrator ou gabarito.

## Criterios de aceite

- [x] estados inline preservam texto bruto, codigo, bbox, confianca e proveniencia;
- [x] legenda global nao e associada silenciosamente a um pilar;
- [x] pilar sem estado explicito nunca e tratado como `PASSA`;
- [x] `level_raw` permanece intacto e nenhuma unidade e inventada;
- [x] registry nao mistura documentos, revisoes, snapshots historicos ou estruturas ambiguas;
- [x] `MORRE`, `NASCE` e `PASSA` explicitos cobrem os seis outcomes sinteticos esperados;
- [x] ausencia no alvo so produz `FAIL` quando o alvo esta observavel;
- [x] falta de nivel, par ambiguo ou alvo vazio produz `UNKNOWN`;
- [x] findings possuem codigo, estado, nivel origem/alvo, views, bboxes e `registry_hash`;
- [x] alterar o nivel alvo invalida o cache sem apagar feedback historico;
- [x] viewer comunica contradicao como hipotese e focaliza a origem;
- [x] gabarito e medicao real ficam versionados e separados da memoria explicita;
- [x] lint, typecheck, testes web e testes API integralmente verdes;
- [x] fluxo sintetico principal e pelo menos um par real sao verificados manualmente no viewer.

## Fora do escopo

- classificar pilar sem etiqueta como `PASSA`;
- reconhecer simbologia vetorial de passa/morre/nasce pela legenda;
- mudanca de secao ou dimensao do pilar;
- continuidade de vigas, lajes, blocos ou estacas;
- comparar revisoes diferentes;
- OCR ou visao multimodal;
- criar tabela materializada de niveis;
- exigir identidade estrutural pelo nome do arquivo;
- navegar automaticamente para a folha alvo;
- implementar F4, F5 ou F6.

## Ordem e gate de aprovacao

Este documento e uma proposta. A implementacao so comeca depois de aprovadas estas duas
restricoes:

1. a primeira F3.2 verifica somente lifecycle explicitamente associado ao codigo;
2. pareamento entre folhas so entra se o gabarito da Task 1 provar separacao segura entre
   sequencias estruturais; caso contrario, o agente volta para decisao do proprietario.

Qualquer necessidade de adicionar `stack_id`, normalizar niveis sem fonte humana ou classificar
simbolo vetorial volta ao fluxo:

```text
analisar -> explicar -> propor -> aguardar aprovacao
```
