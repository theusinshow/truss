# F3 - Elementos e cruzamento entre folhas

Data: 2026-08-31  
Status: implementado, medido e verificado  
Escopo: primeiro slice vertical de F3, limitado a pilares

## Resultado pretendido

Ao auditar uma folha de formas, o Truss deve localizar codigos de pilares em coordenadas PDF,
consultar os elementos extraidos de toda a mesma revisao e apontar, como hipotese localizada, um
pilar que aparece na forma mas nao foi localizado em nenhum detalhamento de pilares disponivel.

O primeiro slice nao tenta extrair todos os elementos estruturais. Ele prova o contrato generico
de `sheet_elements`, o registry derivado por revisao e uma regra entre folhas com evidencias dos
dois lados. Vigas, lajes, fundacoes e continuidade entre niveis ficam para slices posteriores de
F3, depois que o comportamento com pilares estiver medido.

## Base ja aprovada

O design aprovado em
`docs/superpowers/specs/2026-08-28-sheet-map-inteligencia-auditoria-design.md` ja decidiu:

- `Element` como quarto nivel do Sheet Map;
- coordenadas PDF em pontos;
- `sheet_elements` persistido por snapshot imutavel do Sheet Map;
- registry como consulta sobre `sheet_elements`, sem tabela de registry duplicada;
- regras deterministicas antes de visao;
- F3 concluida quando um elemento presente numa folha e ausente no quadro correspondente for
  detectado.

Este plano detalha a implementacao desse contrato. Nao altera Next.js, FastAPI, SQLite,
imutabilidade, classificacao de findings nem o escopo local/pessoal.

## Evidencia que orienta o recorte

O corpus local aprovado possui ocorrencias nativas abundantes de codigos `P`, `V` e `L` nos
projetos estruturais convencionais. O questionario humano tambem prioriza pilares: conferir se o
pilar que passa continua no nivel seguinte e se o que morre deixa de aparecer.

Comecar pelos tres tipos ao mesmo tempo aumentaria a ambiguidade antes de o contrato entre folhas
estar provado. Pilares oferecem o menor slice que exercita todas as partes dificeis:

- codigo bruto e canonico;
- ocorrencia com bbox;
- associacao a view e escopo tecnico;
- agrupamento por revisao;
- presenca em forma versus detalhamento;
- finding localizado e cache dependente de varias folhas.

## Decisoes propostas para aprovacao

### 1. `sheet_elements` armazena ocorrencias, nao uma entidade mestra

Cada texto `P12` lido no PDF gera uma ocorrencia ligada ao snapshot que o produziu. O mesmo pilar
pode ter varias ocorrencias em uma view e em varias folhas. O registry agrupa as ocorrencias por
`revision_id + element_kind + code` somente durante a consulta.

Campos propostos:

```text
sheet_elements
  id TEXT PK
  sheet_map_id TEXT NOT NULL
  view_id TEXT NULL
  technical_scope TEXT NULL
  element_kind TEXT NOT NULL
  code_raw TEXT NOT NULL
  code TEXT NOT NULL
  attributes_json TEXT NOT NULL
  x0, y0, x1, y1 REAL NOT NULL
  confidence REAL NOT NULL
  provenance TEXT NOT NULL
  created_at TEXT NOT NULL
```

`code_raw` preserva a evidencia (`P 12`, `P-12`); `code` guarda apenas a normalizacao mecanica
segura (`P12`). Nenhuma equivalencia semantica e inventada. `P21=P38` produz ocorrencias para os
dois codigos, preservando a expressao original nos atributos.

### 2. O primeiro extrator reconhece somente pilares em texto nativo

O extrator `native-text/pillar-code-v1` aceita variantes tipograficas delimitadas de `P` seguido
de numero e sufixo alfabetico opcional. Ele rejeita tokens embutidos em palavras, notas como
`P=10` e candidatos sem bbox valida.

Ele nao usa nome de arquivo, OCR ou visao. Texto fragmentado em spans so e unido quando os spans
pertencem a mesma linha e a distancia tipografica permite provar que formam um unico token. A bbox
e a uniao exata dos spans usados.

### 3. Associacao espacial nunca escolhe silenciosamente entre views ambiguas

Uma ocorrencia recebe `view_id` quando existe uma unica view compativel ou uma menor view
inequivoca que a contem. Em envelopes agrupadores sobrepostos, a ocorrencia fica sem view quando
nao houver desempate seguro. Em folha mista, um elemento sem view confiavel tambem fica sem
`technical_scope`.

Essa ocorrencia continua consultavel como evidencia, mas nao pode sustentar sozinha uma regra que
dependa de formas versus armaduras.

### 4. O registry continua derivado e usa somente snapshots correntes

A consulta de registry parte da revisao da folha auditada, seleciona o snapshot corrente de cada
folha e agrupa suas ocorrencias. Snapshots anteriores continuam persistidos e enderecaveis, mas
nao sao misturados ao estado corrente da revisao.

Nao sera criada tabela `element_registry`. Isso evita estado duplicado e respeita a decisao ja
aprovada.

### 5. Ausencia so vira finding quando existe um alvo correspondente observavel

A regra geral `cross_sheet.pillar_has_detail` parte de pilares associados a views de formas. Ela:

1. procura views de armaduras cujo titulo bruto identifica detalhamento de pilares;
2. agrega os pilares extraidos dessas views em todas as folhas da revisao;
3. retorna `UNKNOWN` quando nenhum alvo correspondente foi reconhecido ou a associacao de escopo
   e ambigua;
4. retorna `PASS` quando o codigo aparece no alvo;
5. retorna `FAIL` quando o alvo foi reconhecido, outros codigos foram extraidos dele e o codigo
   procurado nao foi localizado.

O finding sera uma `INCONSISTENCY` de severidade `HIGH`, mas a descricao continuara hipotetica:
"P12 foi lido na forma, mas nao foi localizado nos detalhamentos de pilares desta revisao".
Confianca e severidade permanecem separadas.

O finding aponta para a ocorrencia na forma e carrega como evidencia:

- codigo bruto e canonico;
- `sheet_map_id`, `view_id`, folha e bbox de origem;
- folhas e views de detalhamento pesquisadas;
- codigos encontrados no alvo;
- versao do extrator, da regra e fingerprint do registry.

### 6. O cache passa a incluir o estado relevante da revisao

Uma regra entre folhas nao pode reutilizar uma resposta baseada apenas no hash da folha de origem.
O registry calcula um fingerprint deterministico sobre os snapshots correntes relevantes:

```text
sha256(sorted(sheet_map_id + snapshot_hash + element_digest))
```

Esse fingerprint entra na chave de cache do audit run e e gravado no run para auditoria. Se outro
documento ou um novo snapshot alterar o registry da mesma revisao, a auditoria da folha de origem
nao usa o resultado antigo.

### 7. O fluxo continua sendo auditoria por folha

Nao sera criada uma segunda UX de "auditoria da revisao" neste slice. O endpoint atual de auditar
a folha monta o contexto da revisao quando encontra uma regra cross-sheet. O finding continua
pertencendo a folha de origem e o canvas atual consegue focalizar sua bbox.

## Implementacao em tarefas

### Task 1 - Fixture e contrato de calibracao F3

Criar uma fixture sintetica de tres folhas:

- forma com `P1` e `P2`;
- detalhamento de pilares com apenas `P1`;
- folha sem relacao com os pilares para provar isolamento.

O golden esperado contem exatamente um finding para `P2`. Uma variante com `P2` no detalhamento
deve produzir zero findings. A fixture usa texto e coordenadas realistas, com titulos abaixo dos
desenhos como no corpus medido.

Arquivos principais:

- `apps/api/tests/fixtures.py`
- `apps/api/tests/test_element_extraction.py`
- `apps/api/tests/test_cross_sheet_rules.py`

### Task 2 - Migration e modelos genericos de elemento

Criar migration numerada para `sheet_elements`, indices por mapa/codigo e as colunas
`element_code` e `registry_hash` onde a rastreabilidade exigir. A migration deve ser apenas
aditiva e preservar contagens e feedback existentes.

Adicionar `SheetElement` ao response model do Sheet Map e manter `elements: []` como default para
snapshots antigos.

Arquivos principais:

- `apps/api/truss_api/db/migrations/006_sheet_elements.sql`
- `apps/api/truss_api/sheetmap/models.py`
- `apps/api/truss_api/audit/models.py`
- `apps/api/tests/test_migrations.py`

### Task 3 - Extracao deterministica e associacao espacial

Implementar o extrator de pilares sobre os spans ricos ja produzidos, com normalizacao minima,
bbox em pontos, confianca e proveniencia. Associar a view somente quando o resultado espacial for
inequivoco.

Casos obrigatorios de teste:

- `P1`, `P 12`, `P-12A`;
- `P21=P38` preservando ambos;
- falso positivo embutido em palavra;
- falso positivo `P=10`;
- token fragmentado na mesma linha;
- token fragmentado entre linhas nao unido;
- ocorrencia em views sobrepostas fica ambigua;
- folha mista nao recebe escopo por adivinhacao.

Arquivos principais:

- `apps/api/truss_api/sheetmap/elements/models.py`
- `apps/api/truss_api/sheetmap/elements/pillars.py`
- `apps/api/truss_api/sheetmap/elements/association.py`
- `apps/api/tests/test_element_extraction.py`

### Task 4 - Snapshot e persistencia imutavel

Incluir elementos no hash do snapshot e na transacao de `save_sheet_map`. Entrada identica deve
reutilizar o snapshot; alteracao dos elementos deve criar nova versao sem apagar a anterior.

Testar leitura de snapshots antigos sem elementos e cascade apenas quando o mapa dono for
explicitamente removido em banco temporario.

Arquivos principais:

- `apps/api/truss_api/sheetmap/builder.py`
- `apps/api/truss_api/sheetmap/snapshot.py`
- `apps/api/truss_api/sheetmap/repository.py`
- `apps/api/tests/test_sheetmap_builder.py`
- `apps/api/tests/test_sheetmap_reading.py`

### Task 5 - Registry derivado por revisao

Criar uma consulta que retorna ocorrencias agrupadas por tipo e codigo usando um snapshot corrente
por folha. A consulta tambem devolve o fingerprint e a cobertura observada: folhas, views alvo,
escopos conhecidos e ocorrencias ambiguas.

Testar:

- isolamento entre revisoes e projetos;
- nenhum snapshot antigo misturado ao atual;
- varias ocorrencias do mesmo codigo agrupadas sem perda de evidencia;
- fingerprint estavel para o mesmo estado e diferente quando qualquer snapshot relevante muda.

Arquivos principais:

- `apps/api/truss_api/sheetmap/elements/registry.py`
- `apps/api/tests/test_element_registry.py`

### Task 6 - Regra cross-sheet e orquestracao

Adicionar suporte a `target: element` no motor declarativo e registrar a regra em pack geral de
formas. O orquestrador fornece o registry somente a regras que o solicitam e inclui seu fingerprint
na chave de cache.

Outcomes obrigatorios:

- alvo de pilares ausente: `UNKNOWN`, nenhum finding;
- alvo reconhecido mas sem nenhum codigo confiavel: `UNKNOWN`, nenhum finding;
- `P1` nos dois lados: `PASS`;
- `P2` somente na forma com alvo observavel: `FAIL` e um finding;
- escopo ambiguo em prancha mista: `UNKNOWN`;
- reexecucao identica: dedupe e cache;
- novo snapshot alvo com `P2`: cache invalida e o finding nao reaparece no novo run.

Arquivos principais:

- `apps/api/truss_api/rules/checklists/formas_geral.v1.yml`
- `apps/api/truss_api/rules/models.py`
- `apps/api/truss_api/rules/engine.py`
- `apps/api/truss_api/audit/orchestrator.py`
- `apps/api/truss_api/audit/repository.py`
- `apps/api/tests/test_cross_sheet_rules.py`
- `apps/api/tests/test_audit.py`

### Task 7 - Rastreabilidade no viewer sem nova pagina

Expor `element_code` no contrato web e mostrar o codigo no item do finding. O foco continua usando
a bbox do finding no canvas. A evidencia deve listar as folhas alvo pesquisadas e deixar claro que
"nao localizado" nao significa erro humano confirmado.

Antes desta task, aplicar a skill de UI/UX disponivel para revisar a alteracao no componente
existente. Nao criar dashboard de registry nem visual decorativo.

Arquivos principais:

- `apps/web/lib/projects-api.ts`
- `apps/web/components/findings/findings-drawer.tsx`
- testes web do drawer e navegacao do canvas

### Task 8 - Medicao no material real e documentacao

Reprocessar primeiro o projeto-base versionado e depois, quando presentes, os 12 PDFs locais do
acervo aprovado. Produzir relatorio de:

- elementos por kind, folha e escopo;
- ocorrencias ambiguas;
- PASS, FAIL e UNKNOWN da regra;
- findings candidatos por projeto;
- tempo e tamanho adicional do snapshot.

Todo finding no acervo aprovado permanece pendente de revisao humana. Ele nao vira excecao por o
projeto estar em `approved`.

Registrar as decisoes finais e atualizar README somente depois da medicao.

## Criterios de aceite

- [x] migration aditiva preserva projetos, revisoes, folhas, snapshots, findings e feedback;
- [x] elementos persistidos possuem codigo bruto, codigo canonico, bbox PDF valida, confianca e
      proveniencia;
- [x] snapshot identico e reutilizado e snapshot com elementos diferentes e versionado ao lado;
- [x] registry nao mistura revisoes nem snapshots historicos;
- [x] fixture com `P2` ausente produz exatamente um finding localizado de `P2`;
- [x] fixture completa produz zero findings para a regra cross-sheet;
- [x] falta de folha alvo, extracao vazia ou escopo ambiguo produz `UNKNOWN`, nunca conformidade ou
      erro confirmado;
- [x] todo finding F3 possui `rule_id`, `element_code`, `view_id`, bbox, evidencia de origem,
      alvos pesquisados e `registry_hash`;
- [x] alterar uma folha alvo invalida o cache da auditoria da folha de origem;
- [x] o viewer focaliza a ocorrencia fonte e comunica a hipotese sem confundir severidade com
      certeza;
- [x] medicao do piso de ruido do projeto-base e do acervo local registrada sem rejeicao
      automatica;
- [x] lint, typecheck, testes web e testes API integralmente verdes;
- [x] fluxo sintetico principal verificado manualmente no viewer.

## Fora do escopo deste slice

- continuidade de pilares entre niveis;
- vigas, lajes, blocos, estacas, eixos, cotas e niveis como `sheet_elements`;
- OCR ou visao para ler codigo;
- inferir completude da revisao pelo nome do arquivo;
- comparar revisoes diferentes;
- criar tabela materializada de registry;
- resolver subviews internas dos envelopes de armaduras;
- aceitar ou rejeitar findings automaticamente pelo acervo aprovado;
- nova pagina de dashboard, autenticacao, SaaS ou multiusuario.

## Ordem de execucao e gates

As tasks sao sequenciais. Tasks 1-6 fecham o contrato backend. Task 7 so inicia depois que o
finding sintetico estiver correto e rastreavel. Task 8 mede antes de declarar F3 concluida.

Qualquer necessidade de ampliar a estrutura central alem dos campos propostos volta ao fluxo:

```text
analisar -> explicar -> propor -> aguardar aprovacao
```
