# Sheet Map e inteligencia de auditoria - Design

Data: 2026-08-28
Status: aprovado
Escopo: continuacao do Truss Agent depois de M0-M10, com foco em inteligencia e aprendizado

## Problema

A auditoria atual nao produz sinal util. O banco local mostra 63 audit runs sobre 85 folhas
reais e 63 findings, todos com `severity: low`. Como o unico finding de severidade baixa e o
fallback "nao encontrou inconsistencias obvias", isso significa que nenhuma das tres regras
determinsticas disparou em nenhuma folha do projeto real.

A causa nao e a falta de regras. E a falta de uma camada semantica entre a extracao e a
auditoria. Hoje o pipeline e:

```
text_blocks -> 3 regras de regex -> findings
```

Regras sobre texto cru nao conseguem responder as perguntas que um desenhista tecnico faz.
Exemplo concreto medido nas pranchas do Rancho Queimado: a regra atual pergunta "existe a
palavra ESCALA na folha?" e a resposta e sempre sim, porque a folha 5 contem
`2 DETALHE 01 LAJE PRE-FABRICADA - TRELICADA` seguido de `ESCALA 1:20`. A pergunta correta e
"cada vista tem escala declarada?", e ela exige saber que uma prancha contem varias vistas.

## Evidencia coletada no material real

Medicoes feitas com PyMuPDF sobre `Proj_Estrutural_RanchoQueimado_geral.pdf` (28 paginas):

- material 100% vetorial: 26.019 drawings e 32.708 segmentos de linha na folha 1;
- texto nativo presente em todas as folhas (21.121 blocos ja extraidos no banco);
- moldura detectavel e consistente: retangulo em ~93% da area da pagina em `(71,29)`;
- carimbo estruturado no canto inferior direito, com responsavel, CPF, cidade, obra e
  codigo da prancha (`EST-0010-A`, `EST-0130-A`);
- multiplas vistas por prancha, cada uma com titulo e escala propria;
- formatos A0 (3370x2384pt) e A1 (2384x1684pt).

Consequencias diretas:

- **OCR sai do escopo.** O material e vetorial; OCR fica como contingencia futura.
- **O codigo real da prancha existe** e deve substituir o rotulo generico `Folha 01`.
- **A unidade de auditoria e a vista, nao so a folha.**

## Decisoes de produto

Tomadas com o proprietario durante o brainstorming:

| Questao | Decisao |
|---|---|
| Foco da continuacao | inteligencia e aprendizado, nao polimento |
| Capacidades desejadas | enxergar o desenho, cruzar folhas, aprender com o usuario, conhecer a norma |
| Execucao da auditoria | triagem em camadas: determinstico e vetorial em tudo, visao so em crops suspeitos |
| Fonte da verdade | checklist escrito primeiro, acervo aprovado calibrando depois |
| Exportacao / relatorio | fora de escopo; uso e na tela |
| Comparacao entre revisoes | fora de escopo agora, candidata a F7 |

## Arquitetura: a camada Sheet Map

O pipeline ganha um estagio entre extracao e auditoria:

```
PDF -> extracao (texto + vetorial) -> SHEET MAP -> auditoria em camadas -> findings
                                         ^                                     |
                                     checklist                            feedback
```

O Sheet Map e uma hierarquia de quatro niveis, integralmente em coordenadas `pt`, preservando a
decisao canonica ja registrada em `docs/DECISIONS.md`:

1. **Sheet** - identidade e tipo: codigo extraido do carimbo, tipo classificado
   (`forma`, `locacao`, `detalhe`, `quadro_aco`, `quadro_pilares`, `corte`, `capa`),
   formato e orientacao.
2. **Region** - areas funcionais achadas por analise vetorial:
   `moldura`, `carimbo`, `area_desenho`, `quadro`, `legenda`, `notas`.
3. **View** - cada vista dentro da area de desenho, com titulo, escala declarada e bbox.
4. **Element** - conteudo da vista: `P1`, `LP1`, `L33`, `h=15`, `e=-0.50`, cotas, niveis, eixos.

### Por que essa camada e a peca-chave

Cada capacidade pedida depende dela:

| Capacidade | Sem Sheet Map | Com Sheet Map |
|---|---|---|
| Checklist / norma | regex em texto solto | "folha tipo FORMA exige CARIMBO + QUADRO_PILARES + ESCALA por vista" |
| Cruzar folhas | impossivel | query sobre elementos: "P12 esta na forma, ausente no quadro" |
| Enxergar | render inteiro para o modelo | crop da regiao suspeita, barato e localizado |
| Aprender | feedback em texto cru | feedback com chave estavel `(sheet_type, rule_id, element_kind)` |

O Sheet Map ja aparece no fluxo do `README.md` original do projeto e nunca foi construido.
Esta e a recuperacao de uma peca prevista, nao a introducao de um conceito novo.

### Integracao com o codigo existente

A mudanca e aditiva:

- `inspect_pdf()` em `apps/api/truss_api/documents/importer.py` ganha extracao de geometria;
- o Sheet Map vive num modulo novo `apps/api/truss_api/sheetmap/`;
- `audit/orchestrator.py` passa a ler o Sheet Map em vez de `text_blocks` cru;
- `findings`, o viewer, o canvas e o loop de feedback nao mudam de contrato: ja falam bbox em `pt`.

### Decisoes tecnicas

- **A construcao do Sheet Map e determinstica e acontece no import.** Geometria e texto nativo
  bastam para os quatro niveis. O modelo entra depois, apenas onde a estrutura nao decide sozinha.
  Isso respeita o principio 2 do `AGENTS.md`.
- **Normalizacao de texto vira infraestrutura de primeira classe** (acentos, caixa, encoding).
  A regra atual em `audit/orchestrator.py` tenta cobrir acentuacao listando as duas grafias de
  "locacao" na mao, dentro da tupla `title_terms`. Isso nao escala e falha em qualquer termo novo.

## Como este documento se relaciona com os planos de implementacao

Este spec descreve o **programa inteiro**, das seis fases. Ele nao e um plano de implementacao.

Cada fase recebe seu proprio ciclo de plano, implementacao e verificacao. O plano imediato cobre
**apenas a F1**; as fases seguintes sao planejadas quando a anterior fechar seu criterio de aceite,
porque o resultado de cada fase informa o desenho da proxima. Isso segue a regra do `AGENTS.md`
de nao avancar varios milestones de uma vez.

## Fases

Seis fases sequenciais. O `AGENTS.md` proibe avancar varios milestones sem testar o anterior;
cada fase tem criterio de aceite e so libera a seguinte quando fecha.

| Fase | Entrega | Capacidade | Criterio de aceite |
|---|---|---|---|
| F1 | Sheet Map base: extracao vetorial, regioes, carimbo, tipo de folha, migrations e gabarito de calibracao | fundacao | 85 folhas classificadas, codigo real no viewer, >=90% de acerto de tipo |
| F2 | Vistas com escala propria e checklist versionado por tipo de prancha | norma / oficio | findings reais e localizados cobrindo >=60% do gabarito |
| F3 | Elementos, consulta de registry por revisao e regras entre folhas | cruzar folhas | detecta elemento presente numa folha e ausente no quadro correspondente |
| F4 | Visao multimodal por triagem em crops | enxergar | pega itens do gabarito que nenhuma regra pegou, dentro do teto de custo |
| F5 | Feedback vira regra, perguntas do Truss, calibracao pelo acervo | aprender | apontamento rejeitado nao retorna; falso-positivo cai entre revisoes |
| F6 | Solidez para uso diario | - | revisao de 85 folhas do inicio ao fim sem falha |

### Gabarito de calibracao

Entregue junto com F1 e usado por todas as fases seguintes. O proprietario revisa 4 ou 5 pranchas
reais e registra o que ele proprio apontaria. Isso vira o gabarito contra o qual se mede precisao
e cobertura.

Sem esse gabarito nao ha como afirmar que a auditoria melhorou, nem como detectar regressao.

### Notas por fase

**F1.** Extrai geometria, detecta moldura, carimbo e quadros, parseia o carimbo, classifica o tipo
e normaliza texto. Resolve tambem o armazenamento de geometria e introduz migrations.

**F2.** E onde o ganho fica visivel. Checklist declarativo versionado no repositorio
(`checklists/forma.yml`, `locacao.yml`, ...), legivel e editavel pelo proprietario, avaliado por um
motor de regras sobre o Sheet Map. F1 e F2 sao deliberadamente as fases mais curtas.

**F3.** Cruzamento entre folhas, possivel apenas depois que elementos existem. Registry por revisao
imutavel.

**F4.** Crop de regiao suspeita, nunca a prancha inteira. Reaproveita `cache_entries`, ja existente,
com chave `hash(crop) + versao_pipeline + modelo`, cumprindo a regra de cache do `AGENTS.md`.
Teto de gasto por revisao configuravel.

**F5.** Primeiro o feedback ajustando o checklist explicito, depois a ingestao do acervo aprovado.

**F6.** Lote com progresso, backup do banco, tratamento de erro, e reconstituicao dos documentos
que o `AGENTS.md` referencia e nao existem (`00-PROJECT-CONTEXT`, `06-TECH-ARCHITECTURE`,
`07-PDF-PROCESSING`, `08-AI-ARCHITECTURE`, `09-DATA-MODEL`, `14-ROADMAP`).

## Modelo de dados

### Migrations

`db/schema.py` usa hoje `CREATE TABLE IF NOT EXISTS` mais um `_ensure_column()` manual alimentado
pelos dicts `CHAT_MESSAGE_COLUMNS` e `CHAT_MESSAGE_CONTEXT_COLUMNS`. Isso ja e fragil para duas
tabelas e nao sustenta sete novas.

F1 substitui por migrations numeradas em `db/migrations/NNN_*.sql` mais uma tabela
`schema_migrations`. O schema atual vira a migration `001` como baseline.

### Tabelas novas

Seguem a convencao existente: PK `TEXT` uuid, timestamps `TEXT` ISO, FK `ON DELETE RESTRICT`.

```
sheet_maps          um por folha por versao de pipeline
  id, sheet_id, pipeline_version, status, geometry_path,
  sheet_code, sheet_type, paper_format, orientation,
  title_block_json, built_at
  UNIQUE (sheet_id, pipeline_version)

sheet_regions
  id, sheet_map_id, region_kind, x0, y0, x1, y1, confidence

sheet_views
  id, sheet_map_id, region_id, title, declared_scale, view_kind, x0, y0, x1, y1

sheet_elements
  id, sheet_map_id, view_id, element_kind, code, attributes_json, x0, y0, x1, y1

rule_preferences
  id, scope, sheet_type, rule_id, action, reason, created_at
  scope:  'global' | 'project' | 'sheet_type'
  action: 'suppress' | 'downgrade' | 'keep'
  sheet_type e obrigatorio quando scope = 'sheet_type', nulo nos demais
```

O `UNIQUE (sheet_id, pipeline_version)` permite reconstruir o Sheet Map com uma versao nova de
pipeline sem destruir a anterior, preservando os findings ja validados que apontam para ela.

### Colunas novas em `findings`

`rule_id`, `view_id`, `source_layer` (`deterministic` | `vector` | `vision`) e `element_code`.

Sao elas que dao ao feedback uma chave estavel para generalizar. Sem `rule_id`, rejeitar um
apontamento nao ensina nada, que e a limitacao atual.

### Decisoes de armazenamento

- **Geometria bruta fora do banco.** `sheet_maps.geometry_path` aponta para
  `data/geometry/{project}/{revision}/{sheet}.json`. Mesma logica que ja mantem PDF e render em
  disco, e evita cerca de 2,8 milhoes de linhas em SQLite.
- **Sem tabela de registry.** O cruzamento do F3 e uma query sobre `sheet_elements` agrupada por
  revisao e `code`. Tabela separada seria estado duplicado.
- **O checklist nao vive no banco.** Fica em arquivos versionados junto do codigo que os avalia.
  A regra e codigo; a excecao aprendida e dado, e vai para `rule_preferences`.
- **O gabarito fica fora do banco:** `calibration/rancho-queimado-r01.yml`, referenciando folhas
  pelo hash do PDF. O teste de calibracao pula sozinho quando o PDF nao esta na maquina, de modo
  que a suite nao depende de material de cliente.

## Loop de aprendizado

Restricao vinda do `AGENTS.md`: "esconder regras aprendidas do usuario" e antipadrao proibido.
Isso descarta aprendizado silencioso e define a arquitetura.

### Sinais

| Sinal | Vira |
|---|---|
| Rejeitar com motivo | candidato a supressao de `(rule_id, sheet_type)` |
| Confirmar | calibracao de confianca da regra |
| Achado manual repetido | proposta de regra nova |
| Acervo aprovado | proposta de item de checklist |

Tres desses quatro sinais ja sao produzidos hoje e nao sao aproveitados.

### Principios

- **O Truss propoe, o usuario decide.** Nada entra em vigor sozinho. O sistema acumula evidencia
  e, ao atingir limiar, pergunta. A resposta vira linha explicita e revogavel em
  `rule_preferences`, com tela listando tudo que esta ativo.
- **Supressao nunca apaga.** Apontamento suprimido vai para uma lista recolhida de silenciados na
  folha, com contador, e continua auditavel. A supressao e sempre escopada a um tipo de prancha.
- **Achado manual repetido e o sinal mais rico.** E o unico que ensina algo que o sistema nao
  sabia; os outros tres apenas ajustam o que ele ja faz. O Truss propoe promover o padrao a regra
  e escreve o rascunho para revisao.
- **A calibracao pelo acervo e determinstica.** Ingere projetos aprovados, monta o Sheet Map de
  cada um e mede frequencia por tipo de folha. Presenca em alta frequencia vira candidato a regra;
  presenca em baixa frequencia nao vira nada.

### Fora de escopo

Fine-tuning, proibido na V0.1 pelo `AGENTS.md` e injustificado pelo volume de dados. O feedback e
armazenado em formato exportavel e separado das memorias explicitas, como a documentacao exige.

## Testes e verificacao

Cinco camadas, nenhuma dependendo de rede ou de material de cliente:

1. **Unitario sobre PDFs sinteticos.** Funcoes do Sheet Map testadas contra pranchas minimas
   geradas em codigo com PyMuPDF.
2. **Fixture de projeto sintetico.** PDF de tres folhas (forma, locacao, quadro) commitado,
   cobrindo o pipeline ponta a ponta.
3. **Golden files de findings.** O conjunto de `(rule_id, bbox)` sobre a fixture e estavel; pega
   regressao silenciosa em mudancas de checklist.
4. **Suite de calibracao.** Gabarito contra o projeto real, pulada quando o PDF nao esta presente,
   imprimindo precisao e cobertura. E o portao de cada fase, junto com uma passada manual.
5. **Provider falso para visao.** F4 nunca chama rede em teste; o `Protocol AIProvider` de
   `ai/provider.py` recebe um duble. Inclui teste de teto de custo em lote.

As suites atuais (33 pytest, 12 vitest) devem permanecer verdes.

## Divida estrutural a tratar durante as fases

`apps/web/components/sheet-viewer.tsx` tem 2.262 linhas, e as fases 2, 3 e 5 adicionam UI nele:
tipo de prancha, vistas, resultado do checklist, lista de silenciados e propostas de regra.

Nao ha refatoracao ampla no plano. A abordagem e **decomposicao pontual na fase que primeiro toca
cada parte**: extrair o canvas (viewport, minimapa, reguas), o painel de achados e o painel de chat
em modulos proprios conforme forem sendo modificados.

## Fora de escopo

- exportacao e relatorio (uso e na tela);
- OCR (material vetorial);
- fine-tuning;
- comparacao entre revisoes, candidata a F7;
- qualquer item da lista de antipadroes do `AGENTS.md`.
