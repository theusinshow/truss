# F6.2 - Lote e observabilidade local

Data: 2026-09-02

Status: aprovada, implementada e validada em 2026-09-02

Escopo: processar uma revisao grande de forma duravel e observavel, com fila local por folha,
barreiras corretas entre fases, cancelamento cooperativo, falhas isoladas e limites explicitos.
Nao inclui servico remoto, dashboard administrativo, distribuicao, prioridade generica ou mudanca
do foco PDF-first.

## Evidencia do estado atual

- F6.1 esta concluida no commit `9f01a5d`, com journal unitario, retomada idempotente, backup,
  restore e diagnosticos;
- a importacao atual registra o documento e constroi todos os Sheet Maps dentro da mesma requisicao;
- depois da importacao, o frontend dispara todas as auditorias por `Promise.all`, sem limite de
  concorrencia, progresso duravel ou cancelamento;
- `processing_operations` descreve operacoes unitarias e deliberadamente nao e uma fila;
- regras cross-sheet usam o registry da revisao, portanto auditorias nao podem comecar antes de a
  fase de Sheet Map atingir uma barreira conhecida;
- o PyMuPDF nao suporta processamento concorrente por threads. A documentacao oficial recomenda
  processos separados, com cada processo abrindo o proprio documento;
- o SQLite continua em journal mode tradicional. Escritas caras de PDF acontecem fora das
  transacoes, mas duas escritas SQLite ainda seriam serializadas;
- o acervo real presente em `docs/projeto_base/` contem PDFs de 29, 30 e 25 paginas: 84 paginas
  disponiveis. O proprietario aprovou formalmente medir essas 84 folhas reais e executar uma
  fixture de falha separada, sem apresenta-la como uma 85a folha real.

## Resultado pretendido

O proprietario consegue:

1. importar um PDF grande e continuar usando o viewer enquanto o processamento avanca;
2. acompanhar a fase, a folha atual e contagens reais de concluidas, pendentes, ignoradas e com
   erro;
3. pedir cancelamento sabendo que a etapa atomica atual termina antes da parada;
4. retomar um lote interrompido sem duplicar Sheet Maps, audit runs, findings ou custo externo;
5. abrir folhas ja concluidas enquanto as demais continuam em processamento;
6. localizar e repetir somente falhas deterministicamente seguras;
7. obter um resumo final auditavel e reabrir a revisao sem perda de dados.

## Decisoes propostas

### 1. Fila duravel separada do journal unitario

Adicionar uma migration aditiva `013_batch_runs.sql` com tres estruturas:

- `batch_runs`: identidade do lote, revisao, configuracao congelada, fase e estado agregado;
- `batch_items`: uma unidade por folha e fase, com ordem, tentativa, erro e vinculo opcional a
  `processing_operations`;
- `batch_run_events`: historico append-only de criacao, inicio, mudanca de fase, pedido de
  cancelamento, retomada e conclusao.

O journal da F6.1 continua sendo a autoridade da operacao unitaria. A fila apenas agenda e agrega
essas operacoes; nao duplica resultados de Sheet Map ou auditoria.

Contagens de progresso sao derivadas de `batch_items`, nao mantidas como contadores independentes.
Isso impede que uma interrupcao deixe `42/85` no lote e 41 itens realmente concluidos.

### 2. Fases com barreiras explicitas

O pipeline do lote segue:

```text
INTAKE
  -> SHEET_MAP
       -> REGISTRY_READY
            -> DETERMINISTIC_AUDIT
                 -> VISUAL_AUDIT opcional
                      -> COMPLETED | COMPLETED_WITH_ERRORS | CANCELLED
```

- `INTAKE` valida, armazena e registra documento, folhas e texto nativo;
- `SHEET_MAP` processa cada folha independentemente;
- `REGISTRY_READY` so e atingido quando todos os itens de Sheet Map chegaram a um estado terminal;
- se algum Sheet Map falhar, as demais folhas podem seguir, mas regras cross-sheet devem receber
  cobertura incompleta e retornar `UNKNOWN`, nunca inferir conformidade ou falha com registry
  parcial;
- a auditoria da folha cujo Sheet Map falhou fica `SKIPPED_DEPENDENCY`;
- repetir uma falha de Sheet Map recalcula o fingerprint do registry e invalida apenas auditorias
  dependentes;
- `VISUAL_AUDIT` nao faz parte do modo padrao e exige opt-in explicito do proprietario.

Para viabilizar a unidade por folha, extrair `build_sheet_map_for_sheet(sheet_id, settings)` do
builder atual. `build_sheet_map_for_document` permanece como wrapper compativel para fluxos e
testes existentes.

### 3. Estados e cancelamento seguro

Estados do lote:

```text
queued -> running -> completed
                  -> completed_with_errors
                  -> cancel_requested -> cancelled
                  -> interrupted
```

Estados do item:

```text
queued -> running -> completed
                  -> failed
                  -> skipped_dependency
                  -> cancelled
                  -> manual_retry_required
```

Cancelamento e cooperativo:

- `POST /batch-runs/{id}/cancel` grava `cancel_requested` e um evento;
- nenhum item novo e reivindicado depois do pedido;
- a operacao atomica em curso termina e publica ou falha normalmente;
- itens ainda em fila viram `cancelled`;
- chamada externa ja enviada nao e abortada nem repetida; o resultado que chegar e persistido;
- a UI usa a frase `Parando apos a etapa atual`, sem prometer parada instantanea.

Nao matar processo no meio de escrita e parte do contrato. Arquivos `.partial` continuam nunca
sendo tratados como artefatos validos.

### 4. Worker local em processo separado

Adicionar um worker Python local sem porta de rede:

```powershell
.venv\Scripts\python -m truss_api.batch.worker
```

O `npm run dev` passa a iniciar web, API e worker. A API cria/consulta/cancela lotes; o worker
reivindica itens por compare-and-swap no SQLite e executa uma folha por vez em processo separado
do servidor HTTP.

Decisao conservadora para o primeiro gate:

- concorrencia deterministica padrao e maxima: `1` folha;
- concorrencia visual maxima: `1` chamada;
- nenhum uso de threads para PyMuPDF;
- `PRAGMA busy_timeout` explicito nas conexoes;
- manter o journal mode atual durante o primeiro drill, sem introduzir WAL junto com a fila.

O limite `1` e intencional: a meta da F6 e confiabilidade de ponta a ponta, nao benchmark. Depois
do lote real, elevar para dois processos pode receber um plano proprio com medicao de CPU, memoria,
tempo e contencao. O SQLite admite leitores concorrentes, mas continua serializando escritores;
alterar para WAL nao elimina esse limite e ampliaria o escopo de backup/recovery.

Cada claim recebe um `run_token`. Somente o worker que possui esse token pode publicar o estado
terminal. No startup, item `running` sem worker ativo aparece como `interrupted`; nao e
reivindicado silenciosamente. Retomada explicita cria novo token e reutiliza as identidades/cache
da F6.1.

### 5. API aditiva e polling local

Rotas propostas:

```text
POST /projects/{project_id}/revisions/{revision_id}/batch-imports
POST /revisions/{revision_id}/batch-runs
GET  /revisions/{revision_id}/batch-runs?active=true
GET  /batch-runs/{batch_id}
GET  /batch-runs/{batch_id}/items?status=&phase=&limit=&offset=
POST /batch-runs/{batch_id}/cancel
POST /batch-runs/{batch_id}/resume
POST /batch-runs/{batch_id}/retry-failures
```

- `batch-imports` recebe o PDF, conclui somente o intake seguro e responde `202` com documento e
  lote;
- o endpoint sincrono atual permanece compativel para testes e ferramentas existentes;
- `batch-runs` permite reprocessar folhas ja importadas quando pipeline/regra mudar;
- somente um lote ativo por revisao e modo pode existir;
- endpoints de mutacao usam compare-and-swap e retornam `409` para transicoes invalidas;
- respostas nunca incluem caminho absoluto, segredo ou PDF binario;
- a web consulta o lote ativo a cada 1 segundo enquanto a aba esta visivel e reduz a frequencia
  quando fica em background. WebSocket/SSE nao entra na V0.1.

### 6. Custo e chamadas externas

O modo padrao do lote e `local_deterministic`, sem chamadas externas.

Uma opcao separada `include_visual=true` exige confirmacao que mostre:

- provider e modelo;
- teto de chamadas restante da revisao;
- budget restante em USD;
- numero maximo de candidatos;
- aviso de que cancelamento nao desfaz chamada ja enviada.

A configuracao e congelada no `batch_run`. O worker reutiliza os limites e o cache existentes da
F4; nao cria outra contabilidade. Itens visuais interrompidos ficam `manual_retry_required` e nunca
recebem retry automatico. Cancelar o lote impede novas chamadas.

### 7. Integracao PDF-first

O progresso aparece no contexto da revisao ativa, entre o cabecalho do projeto e o viewer:

- faixa compacta com fase (`Mapeando folhas`, `Auditando`, `Triagem visual`), `<progress>` nativo e
  contagem `37 de 85`;
- estados distintos por texto e icone: executando, concluido, com erros, interrompido e parando;
- detalhes expansivos inline, sem modal e sem dashboard, mostrando apenas folha atual, falhas e
  itens ignorados;
- folha concluida fica navegavel imediatamente;
- `Parar apos a etapa atual`, `Continuar` e `Repetir falhas seguras` sao acoes explicitas;
- erros oferecem salto direto para a folha quando existe Sheet Map/render;
- atualizacoes relevantes usam `aria-live="polite"`; o progresso possui nome acessivel;
- motion fica entre 120 e 180 ms e comunica somente mudanca de estado; reduced motion remove a
  transicao;
- `OperationalStatus` continua reservado a saude e operacoes interrompidas. Progresso normal nao
  vira alerta global.

A direcao segue `apps/web/PRODUCT.md` e `docs/05-DESIGN-SYSTEM.md`. O arquivo
`docs/12-UI-UX.md`, citado pelo `AGENTS.md`, nao existe neste clone; a implementacao nao deve
inventar seu conteudo. Reconstituir esse documento exige fonte ou aprovacao separada.

## Contrato de falhas isoladas

Uma folha defeituosa nao derruba o processo do worker nem apaga resultados das demais:

- erro de PDF/Sheet Map fica ligado a folha e encerra somente aquele item;
- erro transiente tipado pode receber uma unica tentativa automatica, com backoff curto;
- erro de conteudo, hash, migration, fonte ausente ou estado invalido nunca recebe retry automatico;
- falha de banco/integridade pausa o lote inteiro e degrada `/health`;
- falha visual nunca repete chamada;
- resumo final separa `completed`, `failed`, `skipped_dependency`, `cancelled` e
  `manual_retry_required`;
- um lote com qualquer falha termina `completed_with_errors`, nunca `completed`.

## Persistencia proposta

Campos essenciais de `batch_runs`:

```text
id, project_id, revision_id, mode, status, phase
config_json, input_fingerprint, pipeline_version
cancel_requested_at, created_at, started_at, completed_at, updated_at
```

Campos essenciais de `batch_items`:

```text
id, batch_run_id, sheet_id, phase, sequence, status
operation_id, attempt_count, run_token
error_code, error_message, created_at, started_at, completed_at, updated_at
```

Restricoes:

- unique por `batch_run_id + sheet_id + phase`;
- foreign keys sem cascade destrutivo para revisao, folha e operacao;
- checks de status/fase;
- eventos com `sequence` unica por lote e triggers append-only;
- indice de claim por `status + phase + sequence`;
- indice de consulta por `revision_id + created_at`;
- nenhuma bbox, finding ou PDF e duplicado na fila.

## Sequencia de implementacao proposta

1. testes de estado e migration para lotes, itens, eventos e transicoes invalidas;
2. repository de fila com claim atomico, run token, cancelamento e agregados derivados;
3. extrair builder de Sheet Map por folha preservando o wrapper atual;
4. adicionar cobertura da revisao ao registry e `UNKNOWN` explicito quando incompleta;
5. worker local de concorrencia 1 e retomada depois de interrupcao;
6. endpoint de batch import e endpoints de consulta/controle;
7. substituir o `Promise.all` irrestrito do frontend pelo lote duravel;
8. integrar faixa de progresso contextual e detalhes de falha no viewer;
9. adicionar opt-in visual com snapshot de budget e nenhuma repeticao automatica;
10. testes de crash, cancelamento em cada barreira, retry, cache e concorrencia de claims;
11. teste das 84 folhas reais em copia descartavel, medindo tempo, pico de memoria, contagens e
    hashes, seguido por uma fixture separada de falha isolada;
12. verificacao manual de importacao, navegacao durante processamento, feedback e reabertura;
13. backup/restore de um lote em andamento e de um lote concluido;
14. atualizar arquitetura, decisoes, README e roadmap somente depois do gate.

## Testes obrigatorios

### Fila e persistencia

- migration preserva todo estado F6.1;
- segundo lote ativo equivalente recebe conflito e nao duplica itens;
- dois workers nao reivindicam o mesmo item;
- contagens agregadas sempre correspondem aos itens;
- eventos sao sequenciais e append-only;
- reinicio transforma trabalho sem dono em interrompido, sem autoexecucao;
- retomada reutiliza snapshot, audit run e findings quando a identidade nao mudou.

### Barreiras e cobertura

- nenhuma auditoria inicia enquanto existe Sheet Map nao terminal;
- falha de uma folha nao gera cross-sheet `PASS` ou `FAIL` com registry parcial;
- folha dependente fica `SKIPPED_DEPENDENCY`;
- retry bem-sucedido recompõe registry e invalida somente resultados dependentes;
- folhas independentes preservam resultados concluidos.

### Cancelamento e retry

- cancelamento antes do claim nao inicia trabalho;
- cancelamento durante Sheet Map termina a etapa atomica e para antes da proxima;
- cancelamento durante chamada visual nao dispara nova chamada;
- retry automatico ocorre no maximo uma vez e somente para codigos permitidos;
- retry manual de falhas seguras nao repete itens concluidos;
- operacao visual interrompida exige nova confirmacao.

### Web

- progresso real, fase e contagens aparecem na revisao ativa;
- polling para ao atingir estado terminal e reduz em aba oculta;
- controles possuem foco, labels, disabled/loading/error e alvo minimo;
- `aria-live` nao anuncia cada tick redundante;
- reduced motion remove transicoes nao essenciais;
- viewer permanece navegavel durante o lote;
- falha oferece folha/evidencia sem abrir dashboard separado.

### Gate real

- processar as 84 folhas estruturais reais disponiveis em ambiente descartavel;
- executar separadamente uma fixture que falhe de forma controlada e verificar o isolamento;
- registrar hashes e contagens antes/depois;
- interromper e retomar ao menos uma vez;
- pedir cancelamento em um run separado e confirmar parada cooperativa;
- confirmar zero duplicatas de documento, Sheet Map, audit run e finding;
- confirmar que feedback humano persiste apos reabertura;
- criar backup, verificar e restaurar o estado final;
- registrar tempo total, pico de memoria, quantidade de retries, falhas e itens em cache.

## Decisao sobre o corpus

Em 2026-09-02, o proprietario escolheu alterar formalmente o criterio historico de 85 folhas. O
gate usa as 84 paginas estruturais reais atualmente disponiveis e, em execucao separada, uma
fixture defeituosa para comprovar isolamento, diagnostico e resumo de erro.

A fixture nao conta como folha real, nao entra em metricas de qualidade do acervo e nao pode ser
usada para inflar cobertura. Ela testa somente o comportamento operacional diante de falha.

Os dois PDFs nao rastreados em `docs/projeto_base/` permanecem fora do Git. A fila pode usa-los
localmente no drill sem versionar os documentos.

## Criterios de aceite

- [x] uma revisao grande e processada sem bloquear o servidor HTTP;
- [x] progresso e resumo derivam de estado duravel por folha;
- [x] a barreira de Sheet Map protege a corretude cross-sheet;
- [x] cancelamento e cooperativo, honesto e nao corrompe artefatos;
- [x] falha de uma folha fica isolada e explicada;
- [x] retomada nao duplica dados nem chamadas externas;
- [x] concorrencia e custo possuem limites explicitos;
- [x] o viewer continua sendo a superficie principal;
- [x] o gate de 84 folhas reais mais a fixture separada, feedback, reabertura e recovery passa;
- [x] suites, lint, typecheck, build e verificacao manual ficam verdes;
- [x] documentacao registra metricas e decisoes finais.

## Fora do escopo

- fila distribuida, Redis, Celery, broker ou servico cloud;
- prioridade arbitraria, agendamento, recorrencia ou multiusuario;
- WebSocket/SSE antes de polling demonstrar insuficiencia;
- paralelismo por threads com PyMuPDF;
- mais de um worker no primeiro gate;
- WAL sem medicao e plano de recovery especifico;
- cancelamento forcado no meio de escrita ou chamada externa;
- progresso inventado por timer;
- processamento visual automatico por padrao;
- comparacao entre revisoes, F7, SaaS, autenticacao ou cobranca.

## Riscos e mitigacoes

| Risco | Mitigacao proposta |
|---|---|
| auditoria usa registry parcial | barreira de fase e cobertura `UNKNOWN` explicita |
| fila duplica journal F6.1 | fila agenda; operacao unitaria continua autoridade idempotente |
| PyMuPDF falha em threads | worker em processo separado, concorrencia 1 |
| SQLite fica ocupado | transacoes curtas, `busy_timeout`, um worker e teste de contencao |
| cancelamento promete demais | estado `cancel_requested` e copy `Parando apos a etapa atual` |
| restart duplica trabalho | run token, CAS e retomada explicita |
| visual excede custo | opt-in, snapshot de limites, cache e uma chamada por vez |
| UI vira dashboard | progresso inline na revisao e viewer sempre acessivel |
| gate usa corpus artificial | exigir a 85a folha real ou decisao formal do proprietario |

## Fontes tecnicas verificadas

- PyMuPDF FAQ: https://pymupdf.readthedocs.io/en/latest/faq/index.html
- PyMuPDF multiprocessing: https://pymupdf.readthedocs.io/en/latest/recipes-multiprocessing.html
- SQLite WAL: https://www.sqlite.org/wal.html

## Gate de aprovacao

Aprovado explicitamente pelo proprietario antes da implementacao:

- tabelas duraveis de lote separadas do journal F6.1;
- worker Python local sem porta, iniciado junto ao ambiente de desenvolvimento;
- concorrencia inicial fixa em uma folha e uma chamada visual;
- polling HTTP em vez de WebSocket/SSE;
- cancelamento cooperativo, nunca terminacao forcada;
- modo visual somente por opt-in com limites congelados;
- demais decisoes arquiteturais desta proposta. O tratamento do corpus usa 84 paginas reais mais
  uma fixture separada de falha isolada.
