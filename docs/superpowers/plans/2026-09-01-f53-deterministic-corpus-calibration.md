# F5.3 - Calibracao deterministica pelo acervo aprovado

Data: 2026-09-01

Status: aprovada, implementada e validada em 2026-09-02

Escopo: medir o pipeline e os rule packs sobre o acervo local aprovado, produzir propostas
auditaveis de calibracao e exportar feedback humano sem fine-tuning, sem alterar regras
automaticamente e sem confundir projeto entregue com ground truth tecnico integral

## Contexto confirmado

- `docs/00-PROJECT-CONTEXT.md` e `docs/06-TECH-ARCHITECTURE.md` continuam ausentes. Sua
  reconstituicao pertence a F6.1; este plano usa `README.md`, `docs/DECISIONS.md`,
  `docs/14-ROADMAP.md`, o codigo e os artefatos atuais como fontes disponiveis.
- existem 12 PDFs locais confirmados pelo proprietario em
  `data/knowledge-inbox/approved/` e um projeto-base `human_verified`;
- o corpus historicamente medido soma 13 PDFs e 259 paginas;
- os 12 PDFs locais ja possuem drafts v4 e catalogo por hash em
  `data/knowledge-inbox/.truss/`;
- `approved` significa versao final entregue e representativa do padrao do proprietario, mas pode
  conter pequenos erros. Portanto, nao equivale a `confirmed_zero`;
- somente `calibration/juliano-corbellini-r05.yml` possui ground truth humano verificado amplo;
- `truss_api.calibration` ja oferece catalogo por hash, intake seguro e runners descartaveis para
  ruido, elementos, continuidade, secoes e visao;
- F5.2 ja persiste preferencias e decisoes de aprendizado com snapshots, mas seu contrato de
  evidencia referencia findings do banco de trabalho e nao deve ser deformado para representar
  paginas do corpus ainda nao importadas.

## Resultado pretendido

O proprietario executa deliberadamente uma medicao local e recebe um run imutavel, identificado
pelos hashes do corpus, pipeline, rule packs, politica e preferencias. O resultado mostra:

- frequencias observadas por tipo de prancha, escopo tecnico, view, elemento e resultado de regra;
- findings brutos, findings suprimidos por preferencias e findings efetivamente exibidos;
- cobertura e lacunas sem apresentar ausencia de deteccao como conformidade;
- propostas de calibracao com amostras, contraexemplos e localizadores em pontos PDF;
- uma decisao humana separada para cada proposta;
- um export portavel de dataset que nao inclui PDF, render, segredo nem memoria explicita.

Aprovar uma proposta a deixa `ready_for_implementation`. Nenhum YAML, regra, confianca,
severidade, finding, preferencia ou Sheet Map e alterado automaticamente na F5.3.

## Decisoes arquiteturais propostas

Estas decisoes fazem parte do gate e precisam da aprovacao do proprietario antes da
implementacao:

1. adicionar persistencia pequena em SQLite para runs, propostas, evidencias e decisoes;
2. guardar o artefato completo de cada run no disco local, referenciado pelo banco;
3. executar a medicao por CLI explicita, nao por request HTTP longo; fila e progresso pertencem a
   F6;
4. estender `Aprendizado local` com uma terceira aba `Calibracao`, sem criar dashboard separado;
5. exibir crops locais de amostras e contraexemplos, sempre derivados de bbox PDF canonica;
6. exportar dataset estruturado em JSON sem caminhos absolutos nem binarios;
7. manter a promocao de uma proposta aprovada para rule pack como mudanca de codigo posterior,
   com diff, testes e aprovacao explicita.

## Fontes e niveis de autoridade

Os dados devem carregar `source_kind` e nunca ser misturados silenciosamente:

| Fonte | Significado permitido | Significado proibido |
|---|---|---|
| `delivered_reference` | PDF final representativo do padrao pessoal | folha perfeita ou zero findings |
| `human_verified_ground_truth` | atributo, bbox ou finding confirmado no escopo declarado | generalizacao fora do escopo revisado |
| `finding_feedback` | confirmacao, rejeicao justificada ou achado manual | regra global pronta |
| `learning_decision` | decisao F5.2 e snapshot que a sustentou | alteracao automatica de rule pack |
| `rule_evaluation` | resultado deterministico de uma versao conhecida | verdade tecnica independente |

`memories` nao entram no corpus, na mineracao ou no export. Memoria explicita continua sendo
contexto do assistente; dataset continua sendo evidencia de calibracao reproduzivel.

## Identidade e cache por conteudo

### Manifesto do corpus

O runner constroi `corpus-manifest-v0.1` com uma entrada por PDF:

```text
document_sha256
page_count
source_kind
ground_truth_sha256 | null
classification_confirmation_sha256 | null
```

O nome do arquivo aparece apenas como rotulo humano. Hash e pagina sao a identidade tecnica.

### Chave da analise bruta

```text
SHA256(
  corpus_manifest_hash
  + sheetmap_pipeline_version
  + audit_pipeline_version
  + rule_pack_digest
  + calibration_policy_version
)
```

A politica recebe a versao `corpus-calibration-policy-v0.1`. O artefato bruto e reutilizado quando
somente preferencias mudam.

### Chave do run apresentado

```text
SHA256(analysis_key + active_preference_digest)
```

Um run completo com a mesma chave e artefatos validos e reutilizado. Alterar PDF, ground truth,
pipeline, rule pack ou politica invalida a analise bruta. Alterar apenas preferencias preserva a
analise e recalcula supressoes, metricas efetivas e propostas. Nenhum resultado anterior e
sobrescrito.

## Execucao isolada

Comando proposto:

```powershell
.venv\Scripts\python -m truss_api.calibration.runner measure-approved
```

Fluxo:

1. descobrir o projeto-base verificado e `data/knowledge-inbox/approved/`;
2. validar hashes, duplicidades, quantidade de paginas e fontes de autoridade;
3. criar um diretorio temporario fora do banco de trabalho;
4. importar cada PDF como revisao isolada usando o importer de producao;
5. reutilizar a analise bruta se `analysis_key` e artefato forem validos;
6. quando necessario, construir Sheet Maps com a versao atual;
7. executar auditoria deterministica em todas as folhas e coletar snapshots, views, elementos,
   avaliacoes e findings brutos;
8. aplicar somente em leitura o snapshot das preferencias ativas do banco de trabalho;
9. gerar metricas, propostas, evidencias e export;
10. gravar o artefato por escrita atomica e registrar o run concluido em uma transacao;
11. descartar todo banco, render e geometria temporarios.

O runner nao altera PDFs do acervo, findings do banco de trabalho, ground truths ou rule packs.
Falha antes da publicacao nao cria run parcial.

## Persistencia proposta

Migration `009_calibration_runs.sql`:

### `calibration_runs`

- `id` UUID;
- `analysis_key` e `run_key` unico;
- hashes do manifesto, pipeline, rules, politica e preferencias;
- contagens de documentos, paginas, Sheet Maps, avaliacoes e findings;
- `artifact_path` relativo a `data/calibration/runs/`;
- `created_at`;
- nenhuma atualizacao ou exclusao pela API.

### `calibration_proposals`

- `id` UUID e `stable_key` deterministica;
- `run_id` imutavel;
- `proposal_kind`: `rule_noise`, `checklist_candidate` ou `rule_retention`;
- `sheet_type`, `technical_scope` e `rule_id` opcionais;
- titulo, racional e `proposal_payload_json` versionado;
- `policy_version` e `created_at`;
- unicidade por `(run_id, stable_key)`;
- propostas de runs anteriores permanecem consultaveis.

### `calibration_proposal_evidence`

- `proposal_id`;
- `evidence_kind`: `sample`, `counterexample` ou `feedback`;
- `document_sha256`, `page_index`, `sheet_code` opcional;
- bbox `x0/y0/x1/y1` em pontos PDF, opcional apenas quando a evidencia e de folha inteira;
- `source_finding_id` opcional para evidencia do banco de trabalho;
- descricao curta e payload estruturado versionado;
- identidade composta impede duplicidade da mesma evidencia.

### `calibration_proposal_decisions`

- decisao append-only `approved` ou `dismissed`;
- justificativa obrigatoria;
- `stable_key`, `proposal_id` de origem, `created_at` e `revoked_at`;
- no maximo uma decisao ativa por `stable_key`, mesmo quando um run novo atualiza as evidencias;
- revogacao reabre a proposta e preserva o historico.

Nenhuma dessas tabelas contem PDF, render, crop ou caminho absoluto.

## Artefato do run

Arquivos locais:

```text
data/calibration/analyses/{analysis_key}/raw.json
data/calibration/runs/{run_key}/report.json
```

Contrato `calibration-report-v0.1`:

- manifesto do corpus e versoes;
- contagens por documento e pagina;
- distribuicoes por `sheet_type`, `technical_scope`, `view_kind` e `element_kind`;
- resultados por `rule_id`, `outcome`, severidade e escopo;
- findings brutos, suprimidos e efetivos, sempre separados;
- paginas sem view, sem tipo verificavel ou sem rule pack;
- propostas e referencias de evidencias;
- tempos e tamanhos de artefatos;
- lista explicita de metricas nao computaveis e o motivo.

O report nao afirma recall ou precisao quando nao existe conjunto positivo humano. Em material
apenas entregue, findings sao `candidate_noise`, nunca falsos positivos confirmados.

## Politica deterministica de propostas

### `rule_noise`

Criada quando uma regra produz findings brutos em ao menos 2 documentos entregues ou quando existe
rejeicao humana justificada para a mesma regra. Inclui:

- amostras dos findings;
- folhas comparaveis onde a regra passou como contraexemplo;
- contagem bruta, suprimida e efetiva;
- feedback F5.2 relacionado;
- nenhuma sugestao automatica de severidade ou threshold.

### `checklist_candidate`

Criada somente a partir de `draft_rule` aprovado na F5.2 ou de assinatura manual que ja atingiu a
politica F5.2. O corpus adiciona contexto e contraexemplos, mas nao inventa `check`, `target`,
severidade ou tipo de finding. O payload declara `rule_spec_status: needs_design`.

### `rule_retention`

Criada a partir de `retain_rule` aprovado na F5.2 e enriquecida com resultados da regra no corpus.
Serve para impedir que reducao de ruido remova silenciosamente uma verificacao repetidamente
confirmada.

Chaves incluem tipo de proposta, tipo de prancha/escopo, regra ou assinatura F5.2 e versao da
politica. Amostras e contraexemplos sao escolhidos por ordenacao deterministica de hash/pagina,
com limite explicito por proposta; contagens completas permanecem no report.

Se o corpus real nao produzir nenhuma proposta pronta, o run continua valido e registra zero com
as razoes. Fixtures sinteticas exercitam todos os tipos sem fabricar evidencia no corpus real.

## Metricas de reducao sem perda silenciosa

Para cada regra e tipo de prancha:

```text
raw_findings
suppressed_findings
effective_findings = raw_findings - suppressed_findings
PASS / FAIL / UNKNOWN / NOT_APPLICABLE
confirmed / rejected / pending feedback
```

Uma preferencia demonstra reducao quando `effective_findings` cai e `raw_findings` permanece
preservado. A medicao falha se aplicar uma preferencia alterar avaliacoes, apagar findings brutos
ou reduzir o numero de paginas processadas.

Comparacao entre runs so e rotulada como regressao/melhoria quando corpus e politica sao
compativeis. Mudanca de pipeline ou rule pack aparece como variavel explicita, nao como melhoria
automaticamente atribuida ao aprendizado.

## Export portavel do dataset

Comando proposto:

```powershell
.venv\Scripts\python -m truss_api.calibration.runner export-feedback --run-id <id>
```

Saida em `data/calibration/exports/{timestamp}-{run_id}/`:

- `manifest.json`: schema, hashes, versoes e contagens;
- `feedback.ndjson`: findings confirmados/rejeitados/manuais e justificativas;
- `decisions.ndjson`: preferencias, decisoes F5.2 e decisoes F5.3;
- `evidence.ndjson`: localizadores, labels e proveniencia;
- `metrics.json`: metricas brutas e efetivas do run.

O export exclui:

- PDF, imagem, crop, geometria completa e texto integral da prancha;
- segredos, eventos de uso, conversas e memorias;
- caminhos absolutos e IDs sem proveniencia;
- inferencias nao aprovadas apresentadas como labels humanas.

## API e interface propostas

Rotas somente para resultados concluidos:

- `GET /calibration/runs`;
- `GET /calibration/runs/{id}`;
- `GET /calibration/proposals` com filtros por run, estado, tipo e regra;
- `GET /calibration/proposals/{id}`;
- `POST /calibration/proposals/{id}/decisions`;
- `DELETE /calibration/proposal-decisions/{id}`;
- `GET /calibration/evidence/{id}/preview` para crop local derivado sob demanda;
- `POST /calibration/runs/{run_id}/exports` cria explicitamente o pacote estruturado e retorna seu
  caminho relativo local.

A API nao inicia medicao longa na F5.3.

Na aba `Calibracao` de `Aprendizado local`:

- selecionar run e comparar bruto/suprimido/efetivo;
- filtrar propostas pendentes, aprovadas, descartadas e reabertas;
- ler racional, versoes, amostras e contraexemplos;
- abrir crop com bbox e, quando o hash ja existir na biblioteca, abrir a folha no viewer; o
  preview resolve somente hashes presentes no manifesto contra raizes locais permitidas, nunca um
  caminho recebido do cliente;
- aprovar/descartar com justificativa e revogar a decisao;
- exportar o dataset do run;
- estados de loading, vazio, erro e artefato ausente;
- nenhum botao `Aplicar regra` ou edicao automatica de YAML.

O visual continua CAD tecnico e denso, reaproveitando a central F5.2. Preview e localizacao
servem a decisao; nao ha grafico decorativo nem dashboard SaaS.

## Sequencia de implementacao

1. adicionar fixtures e testes dos contratos de manifesto, cache e autoridade;
2. implementar manifesto e runner descartavel sobre o pipeline de producao;
3. produzir report versionado e metricas brutas/suprimidas/efetivas;
4. adicionar migration e repositories de runs/propostas/decisoes;
5. implementar geradores deterministicos com amostras e contraexemplos;
6. implementar export portavel com lista de exclusao testada;
7. expor API de leitura, decisao, preview e export;
8. estender a central F5.2 com a aba de calibracao;
9. rodar a medicao real dos 13 PDFs em ambiente descartavel;
10. revisar manualmente um run, uma proposta e sua revogacao;
11. atualizar README, DECISIONS, calibration/README e roadmap somente apos os gates verdes.

Testes devem ser executados apos cada bloco; nao acumular todas as mudancas antes da primeira
validacao.

## Testes obrigatorios

### API e dominio

- manifesto e `run_key` estaveis independentemente da ordem dos arquivos;
- PDF, ground truth, pipeline, rules, politica ou preferencia alterados invalidam o cache;
- replay identico reutiliza o run sem reprocessar PDFs;
- todo PDF e toda pagina aparecem exatamente uma vez;
- `approved` nunca gera `confirmed_zero` implicito;
- banco e PDFs de trabalho permanecem byte a byte inalterados pela medicao;
- falha no meio do processamento nao publica run parcial;
- metricas preservam findings brutos e avaliacoes ao aplicar preferencias;
- propostas nao duplicam amostras e respeitam documento/folha/escopo;
- selecao de amostras e contraexemplos e deterministica;
- `checklist_candidate` exige sinal F5.2 aprovado;
- decisao duplicada e idempotente ou conflito claro;
- revogacao preserva historico;
- nenhuma decisao altera rule pack, finding, Sheet Map ou preferencia;
- preview usa bbox em pontos PDF e limita dimensoes;
- export nao contem PDF, imagem, memoria, conversa, segredo ou caminho absoluto;
- migration e idempotente e preserva F5.1/F5.2.

### Web

- filtros, selecao de run e estados de loading/vazio/erro;
- separacao visual entre bruto, suprimido e efetivo;
- amostras e contraexemplos identificados sem ambiguidade;
- aprovacao, descarte e revogacao exigem justificativa;
- preview e navegacao para documento ja importado;
- artefato ausente produz diagnostico, nao tela quebrada;
- viewer e abas F5.2 permanecem sem regressao;
- teclado, foco, contraste e `prefers-reduced-motion` preservados.

### Medicao real

- 13 PDFs e 259 paginas processados ou divergencia explicada por manifesto;
- zero paginas omitidas, inclusive paginas sem views;
- distribuicoes e lacunas registradas por fonte de autoridade;
- toda proposta real possui amostra e, quando existir, contraexemplo;
- nenhum numero e apresentado como recall/precisao sem ground truth positivo;
- replay identico reutiliza o artefato por conteudo.

## Criterios de aceite

- [x] corpus aprovado possui manifesto versionado e identidade por hash;
- [x] medicao usa banco temporario e nao altera acervo nem estado de trabalho;
- [x] run e imutavel, reproduzivel e cacheado por todas as entradas relevantes;
- [x] todas as paginas aparecem nas metricas, inclusive sem view ou regra;
- [x] frequencias existem por tipo, escopo, view, elemento, regra e outcome;
- [x] findings brutos, suprimidos e efetivos nunca sao colapsados;
- [x] reducao por preferencia e demonstrada sem apagar cobertura bruta;
- [x] `approved` e `human_verified` permanecem semanticamente distintos;
- [x] propostas possuem politica, versoes, racional, amostras e contraexemplos;
- [x] proposta nunca altera regra ou preferencia automaticamente;
- [x] aprovacao e revogacao sao explicitas, justificadas e auditaveis;
- [x] proposta aprovada fica apenas pronta para implementacao posterior;
- [x] export portavel separa feedback, decisoes, evidencia e metricas;
- [x] memoria explicita, conversas, binarios, segredos e caminhos absolutos ficam fora do export;
- [x] central permite inspecionar e decidir sem virar dashboard generico;
- [x] suites completas, lint, typecheck e build ficam verdes;
- [x] medicao real e fluxo manual principal sao documentados;
- [x] nenhuma implementacao da F6 ou alteracao automatica de rule pack entra no milestone.

## Fora do escopo

- fine-tuning, embeddings, clustering semantico ou IA externa;
- considerar todo projeto entregue tecnicamente perfeito;
- gerar regra executavel a partir de linguagem natural;
- editar ou ativar YAML automaticamente;
- importar permanentemente todo o corpus para o banco de trabalho;
- fila, cancelamento, progresso em tempo real e retomada, pertencentes a F6;
- backup/restauracao e lote de 85 folhas, pertencentes a F6;
- comparacao grafica entre revisoes, candidata a F7;
- multiusuario, autenticacao, SaaS ou envio do corpus para nuvem.

## Gate de aprovacao

Aprovacao explicita recebida antes da implementacao. O milestone foi encerrado somente depois da
medicao real, replay de cache, suites completas, build e verificacao manual da terceira aba.
