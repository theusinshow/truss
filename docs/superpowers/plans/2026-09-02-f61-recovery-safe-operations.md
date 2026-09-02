# F6.1 - Recuperacao e operacao local segura

Data: 2026-09-02

Status: aprovada; fundacao implementada e validada, recovery drill real bloqueado por dados
historicos ausentes em 2026-09-02

Escopo: proteger o uso local cotidiano com backup verificavel, restauracao sem sobrescrita,
diagnosticos acionaveis, escritas atomicas e retomada idempotente de operacoes unitarias. Nao
inclui fila, lote, concorrencia ou progresso em tempo real, que permanecem na F6.2.

## Contexto confirmado

- F5.3 esta concluida e validada; o proximo milestone autorizado pelo roadmap e somente o
  planejamento da F6.1;
- `docs/00-PROJECT-CONTEXT.md` e `docs/06-TECH-ARCHITECTURE.md` estao ausentes e devem ser
  reconstituidos antes de novas alteracoes arquiteturais;
- o banco local real usa SQLite, possui migrations `001` a `009`, passou em
  `PRAGMA integrity_check` e `PRAGMA foreign_key_check` em 2026-09-02 e usa hoje
  `journal_mode=delete`;
- ha copias manuais `truss.sqlite.pre-f2*`, mas nao existe formato de backup, manifesto,
  verificacao ou fluxo de restauracao suportado;
- o `/health` atual apenas cria diretorios e retorna caminhos absolutos. Ele nao testa integridade
  do banco, arquivos referenciados, permissao de escrita, espaco ou compatibilidade de schema;
- a importacao valida o PDF antes de registra-lo, mas original, render e geometria reduzida ainda
  podem ser gravados diretamente no destino final;
- uma interrupcao entre a escrita do original, o registro no SQLite e a construcao de Sheet Maps
  pode deixar arquivo orfao ou documento parcialmente processado, sem um checkpoint explicito;
- Sheet Maps ja reutilizam snapshots por conteudo, extracoes possuem nome por hash e auditorias
  deterministicas possuem cache por entrada. Esses contratos permitem retomada sem introduzir a
  fila da F6.2;
- revisoes, PDFs, Sheet Maps, auditorias, findings, feedback, preferencias e decisoes historicas
  devem continuar imutaveis ou append-only conforme seu contrato atual.

## Resultado pretendido

O proprietario consegue:

1. diagnosticar a instalacao local e receber codigo, explicacao e acao recomendada para falhas de
   PDF, render, disco, artefato, banco ou migration;
2. criar um backup local consistente enquanto o aplicativo esta parado ou em uso normal;
3. verificar um backup sem restaura-lo;
4. restaurar um backup validado em um diretorio novo e iniciar o Truss apontando
   `TRUSS_DATA_DIR` para ele;
5. reabrir uma operacao deterministica interrompida sem duplicar documento, snapshot, auditoria,
   finding ou chamada externa;
6. recuperar o estado preservando todas as revisoes e PDFs anteriores;
7. consultar documentos de contexto e arquitetura que descrevem fielmente o produto e seus
   limites atuais.

Backup e restauracao nao aparecerao como botoes destrutivos na interface. O frontend apenas
mostrara saude, falhas e operacoes interrompidas no contexto em que forem relevantes.

## Decisoes arquiteturais propostas

Estas decisoes compoem o gate. Nenhuma delas deve ser implementada antes da aprovacao explicita:

1. adicionar uma migration aditiva `010` para um journal pequeno de operacoes e eventos;
2. tornar atomicas as escritas de originais, renders e artefatos de geometria;
3. tornar a geometria reduzida enderecada por conteudo, preservando leitura dos caminhos legados;
4. adotar um envelope unico de erro publico com codigo estavel, mensagem segura, acao e
   `operation_id` opcional;
5. manter backup, verificacao, restauracao e diagnostico profundo em CLI local explicita;
6. usar `sqlite3.Connection.backup`, nunca copia bruta do SQLite aberto;
7. incluir no backup todo dado local duravel e excluir apenas derivados reconstruiveis e segredos;
8. restaurar somente para um caminho inexistente, por staging e promocao atomica; nao oferecer
   restauracao in-place na F6.1;
9. nao alterar `.env` nem ativar automaticamente o diretorio restaurado;
10. permitir retomada automatica somente de passos deterministicos e cacheados. Operacoes de IA
    externa interrompidas exigem nova decisao humana e nunca sao repetidas silenciosamente;
11. manter o processamento sincrono atual. Fila, workers, cancelamento e lote continuam fora;
12. reconstruir os dois documentos arquiteturais a partir de fontes existentes, registrando
    divergencias em vez de inventar contratos.

## Classificacao dos dados locais

O formato `truss-backup-v0.1` separa dados por papel:

| Classe | Conteudo | Tratamento |
|---|---|---|
| critica | snapshot do SQLite e PDFs de `originals/` referenciados pelo banco | obrigatoria; ausencia invalida o backup |
| duravel | `knowledge-inbox/`, extracoes/geometrias referenciadas e artefatos de runs de calibracao | incluida e verificada |
| reconstruivel | `renders/`, `cache/`, previews e exports de calibracao | excluida; pode ser recriada |
| configuracao/codigo | `.env`, chaves, logs, repositorio, rule packs versionados e backups anteriores | excluida |

`knowledge-inbox/` entra porque contem corpus local, catalogos e material humano que nao pode ser
recriado a partir do banco. Arquivos do repositorio, inclusive ground truths versionados em Git,
nao entram no backup de runtime.

O manifesto registra exclusoes e avisos. Um arquivo referenciado pela classe critica nunca pode
ser silenciosamente rebaixado a aviso.

## Formato e identidade do backup

Comandos propostos:

```powershell
.venv\Scripts\python -m truss_api.recovery.cli backup-create
.venv\Scripts\python -m truss_api.recovery.cli backup-verify backups\truss-<timestamp>.zip
.venv\Scripts\python -m truss_api.recovery.cli restore backups\truss-<timestamp>.zip --target C:\Truss\restored-<timestamp>
.venv\Scripts\python -m truss_api.recovery.cli diagnose
.venv\Scripts\python -m truss_api.recovery.cli resume <operation-id>
```

O destino padrao de backup sera `backups/` na raiz do repositorio, fora de `data/`, ignorado pelo
Git. `TRUSS_BACKUP_DIR` ou `--output` permite escolher outro disco. O comando recusa destino
dentro de `data/` e nunca inclui o proprio diretorio de backups.

Estrutura proposta:

```text
truss-backup-v0.1.zip
  manifest.json
  db/truss.sqlite
  files/originals/...
  files/geometry/...
  files/calibration/analyses/...
  files/calibration/runs/...
  files/knowledge-inbox/...
```

`manifest.json` contem:

```text
schema = truss-backup-v0.1
backup_id
created_at
app_version
database_sha256
schema_migrations[]
logical_counts{}
files[] = {relative_path, role, size_bytes, sha256}
excluded_roles[]
warnings[]
```

Nao ha caminho absoluto, segredo, token ou conteudo de `.env`. O ZIP nao e criptografado na
F6.1 e deve ser tratado como sensivel porque contem PDFs. Criptografia, nuvem e rotacao automatica
ficam fora do escopo.

## Criacao consistente

Fluxo de `backup-create`:

1. resolver e validar `data_dir` e destino sem seguir caminho para dentro da origem;
2. verificar espaco livre a partir do inventario mais margem operacional;
3. abrir o banco e executar `quick_check`, `integrity_check` e `foreign_key_check`;
4. criar o snapshot do banco em staging com a API de backup do SQLite;
5. consultar no snapshot os caminhos duraveis referenciados e validar que permanecem sob
   `data_dir`;
6. inventariar tambem a arvore `geometry/`, pois as extracoes completas atuais sao enderecadas
   por conteudo, mas nem todas possuem referencia direta no SQLite;
7. copiar os arquivos imutaveis por streaming, calculando SHA-256 e tamanho;
8. inventariar `knowledge-inbox/`, copiar e conferir novamente metadados/hash antes de publicar;
9. abortar com diagnostico se um arquivo critico sumir ou mudar durante a copia;
10. gravar manifesto e ZIP em `<nome>.partial`, verificar o arquivo completo e promover com
   `os.replace`;
11. remover somente o staging pertencente a essa execucao.

O snapshot SQLite permite backup durante leitura e escrita normal. A consistencia com os PDFs e
garantida porque originais sao imutaveis e os caminhos sao enumerados a partir do snapshot. Se o
corpus mutavel mudar durante a copia, o backup falha de forma explicita em vez de publicar uma
mistura de versoes.

## Verificacao e restauracao

`backup-verify` nao escreve em `data/`. Ele valida:

- formato e versao do manifesto;
- ZIP sem caminhos absolutos, `..`, drive prefix, symlink ou entrada nao declarada;
- quantidade, tamanho e SHA-256 de todas as entradas;
- hash, `integrity_check` e `foreign_key_check` do snapshot SQLite;
- migrations aplicadas como prefixo conhecido e sem versao futura desconhecida;
- existencia e hash de todo PDF original referenciado;
- presenca dos artefatos duraveis declarados;
- contagens logicas registradas no manifesto.

`restore` segue o contrato fail-closed:

1. o `--target` deve nao existir; diretorio existente, mesmo vazio, e recusado;
2. o archive e verificado integralmente antes da extracao;
3. a extracao ocorre em staging irmao do destino;
4. todos os caminhos sao novamente confinados ao staging;
5. o banco restaurado e aberto em modo somente leitura e revalidado;
6. referencias criticas e hashes dos originais sao conferidos no layout final;
7. o staging e promovido para o destino em uma unica renomeacao;
8. falha remove apenas o staging da operacao e nunca toca origem, backup ou outro diretorio;
9. ao final, a CLI imprime como testar com `TRUSS_DATA_DIR`, sem editar configuracao.

Nao existe `--force`, merge, overwrite ou restore in-place na F6.1. Ativacao definitiva do
diretorio restaurado e uma escolha manual apos o smoke test.

## Escrita atomica e artefatos

Um utilitario comum de armazenamento deve:

- criar temporario no mesmo diretorio do destino;
- escrever, flushar e sincronizar o arquivo quando suportado;
- validar tamanho/hash ou abrir o formato antes da promocao;
- promover com `os.replace`;
- limpar somente seu proprio `.partial` em caso de falha;
- traduzir `ENOSPC`, permissao, filesystem read-only e erro de I/O em diagnostico tipado.

Aplicacoes obrigatorias:

- PDF original: nome enderecado pelo SHA-256 completo conhecido e validacao de conteudo antes da
  promocao;
- extracao `.json.gz`: nome por hash, gzip legivel antes da promocao;
- geometria reduzida: novo nome `<sheet-id>.<content-hash>.json`, sem sobrescrever snapshot
  anterior; caminhos antigos `<sheet-id>.json` continuam legiveis;
- render PNG: geracao em temporario, abertura/validacao e promocao; render continua derivado e
  pode ser apagado/recriado;
- artefatos de calibracao: manter o contrato atomico ja existente e inclui-los na verificacao.

Arquivos `.partial` antigos nunca sao considerados validos. O diagnostico pode lista-los e a CLI
pode limpar apenas temporarios reconhecidos depois de confirmacao explicita.

## Journal e retomada idempotente

Migration proposta: `010_processing_operations.sql`.

### `processing_operations`

```text
id
kind                       # document_import | sheet_map_build | deterministic_audit | vision_audit
project_id | null
revision_id | null
document_id | null
sheet_id | null
input_hash
pipeline_version
status                     # pending | running | completed | failed | interrupted | manual_retry_required
checkpoint
attempt_count
error_code | null
error_message | null
error_context_json | null
created_at
started_at | null
heartbeat_at | null
completed_at | null
updated_at
```

Indice unico pela identidade semantica da operacao e indices por `status`, `revision_id` e
`sheet_id`. `error_context_json` aceita apenas dados seguros e caminhos relativos.

### `processing_operation_events`

```text
id
operation_id
sequence
event_kind                  # started | checkpoint | completed | failed | interrupted | resumed
checkpoint
detail_json
created_at
```

Eventos sao append-only. A linha da operacao guarda o estado atual para consulta; eventos
preservam auditoria. O journal nao e uma fila: nao possui prioridade, worker, agendamento,
concorrencia, percentual ou cancelamento.

### Identidades e checkpoints

- importacao: `revision_id + document_sha256 + importer_version`;
- Sheet Map: `sheet_id + document_hash + extractor/pipeline_version`;
- auditoria deterministica: a chave de cache atual, incluindo Sheet Map, rule packs, preferencias
  aplicaveis e pipeline;
- visao: chave/custo atuais, mas interrupcao vira `manual_retry_required` e nunca dispara nova
  chamada automaticamente.

Checkpoints da importacao:

```text
validated -> original_stored -> document_registered -> sheet_maps_completed -> completed
```

Cada transicao so ocorre depois que arquivo ou transacao correspondente foi publicado. Na
retomada:

- original existente e valido e reutilizado por hash;
- registro de documento existente e reutilizado internamente por `revision_id + content_hash`;
- Sheet Maps existentes com a mesma `pipeline_version` sao reutilizados;
- auditoria deterministica existente e recuperada pelo cache;
- status e feedback humano nunca sao recriados, resetados ou sobrescritos;
- a API publica continua respondendo conflito para um novo upload duplicado; somente o fluxo de
  retomada pode adotar a operacao ja conhecida.

No startup, uma operacao `running` com heartbeat anterior ao encerramento conhecido e marcada
`interrupted`. O sistema nao a executa sozinho. A interface oferece `Continuar` apenas quando o
passo e deterministicamente seguro; a CLI oferece o mesmo contrato.

## Diagnosticos e erros publicos

Envelope proposto:

```json
{
  "detail": {
    "code": "PDF_UNREADABLE",
    "message": "O arquivo nao pode ser aberto como PDF.",
    "action": "Exporte o PDF novamente e tente importar a nova copia.",
    "retryable": false,
    "operation_id": null
  }
}
```

Codigos iniciais:

| Codigo | Caso | Acao principal |
|---|---|---|
| `PDF_UNREADABLE` | parser nao abre o PDF | reexportar arquivo |
| `PDF_EMPTY` | zero bytes ou zero paginas | selecionar PDF valido |
| `PDF_SOURCE_MISSING` | banco referencia original ausente | verificar backup/restaurar em novo destino |
| `RENDER_FAILED` | pagina ou imagem nao pode ser gerada | repetir derivado ou diagnosticar PDF |
| `STORAGE_NOT_WRITABLE` | permissao/read-only | corrigir permissao/destino |
| `STORAGE_FULL` | sem espaco | liberar espaco e retomar |
| `ARTIFACT_CORRUPT` | hash/formato de artefato diverge | reconstruir derivado ou restaurar duravel |
| `DATABASE_INTEGRITY_FAILED` | SQLite inconsistente | parar escrita e verificar backup |
| `DATABASE_SCHEMA_UNKNOWN` | migration futura, ausente ou gap | usar versao compativel, sem migrar |
| `DATABASE_MIGRATION_FAILED` | migration nao concluiu | manter snapshot e diagnosticar |
| `OPERATION_INTERRUPTED` | processo terminou entre checkpoints | retomar passo seguro |
| `EXTERNAL_RETRY_REQUIRES_CONFIRMATION` | chamada externa pode ter custo duplicado | decidir manualmente |
| `BACKUP_INVALID` | manifesto, hash ou banco falhou | nao restaurar |
| `RESTORE_TARGET_EXISTS` | destino ja existe | escolher novo caminho |

Erros inesperados recebem `INTERNAL_ERROR` e um identificador local, sem stack trace, segredo ou
caminho absoluto na resposta. Logs locais preservam a causa tecnica.

Compatibilidade: o frontend passa a aceitar o envelope novo e o `detail` string legado durante a
migracao. Endpoints alterados ganham testes de contrato.

## Saude e diagnostico profundo

`GET /health` permanece barato e nao destrutivo:

```text
status = ok | degraded | unavailable
database = ok | error
storage = ok | warning | error
interrupted_operations = count
```

Ele nao retorna caminhos absolutos e nao cria diretorios como efeito colateral da leitura.

`GET /diagnostics` e a CLI `diagnose` executam checks nomeados:

- layout e confinamento de caminhos;
- escrita atomica de probe em diretorio temporario proprio;
- espaco livre como bytes e nivel, sem regra opaca;
- `quick_check`, `integrity_check` e `foreign_key_check`;
- migrations disponiveis/aplicadas/pendentes/desconhecidas;
- PDFs originais referenciados, tamanho e hash;
- artefatos referenciados e temporarios abandonados;
- operacoes interrompidas, falhas e retomabilidade.

O endpoint e somente leitura e adequado ao escopo local. Checks caros de hash podem ser
solicitados por `?deep=true`; o `/health` nunca percorre todo o acervo.

## Migrations seguras

Antes de aplicar qualquer migration pendente, o startup deve:

1. verificar integridade e compatibilidade das migrations aplicadas;
2. recusar versao desconhecida, sequencia com gap ou arquivo aplicado com identidade divergente;
3. criar e verificar snapshot SQLite pre-migration em `data/db/recovery/`;
4. aplicar cada migration pendente em transacao SQLite explicita, registrando versao e hash do
   SQL na mesma transacao;
5. reexecutar integridade e foreign keys;
6. preservar o snapshot se houver falha e informar o comando de diagnostico;
7. nunca copiar o snapshot automaticamente por cima do banco ativo.

A F6.1 pode adicionar hash do SQL ao registro de migrations novas. Migrations `001` a `009`
continuam reconhecidas pela versao historica e nao sao reescritas. Alteracao retroativa de SQL
aplicado e proibida.

Snapshots pre-migration nao entram no backup padrao e nao sao removidos automaticamente neste
milestone. Uma politica de retencao exige decisao posterior.

## Reconstituicao documental

### `docs/00-PROJECT-CONTEXT.md`

Deve consolidar:

- missao pessoal/local e problema de revisao grafica;
- PDF e viewer como experiencia principal;
- usuario, fluxo principal e limites da V0.1;
- invariantes: coordenadas PDF, revisoes imutaveis, evidencia, feedback e privacidade;
- taxonomia de findings, separacao confianca/severidade e comportamento agressivo;
- memoria explicita versus dataset;
- milestones concluidos, atual e candidatos futuros;
- fontes de verdade e processo de decisao arquitetural.

### `docs/06-TECH-ARCHITECTURE.md`

Deve registrar o estado implementado e o contrato aprovado da F6.1:

- mapa Next.js -> FastAPI -> SQLite/disco -> AI Provider;
- modulos, dependencias e fronteiras entre UI, dominio, repositories e artefatos;
- modelo central e relacoes entre projeto, revisao, documento, folha, Sheet Map, auditoria,
  finding, feedback, preferencias e calibracao;
- coordenadas canonicas em pontos PDF e transformacoes de render;
- layout local classificado em duravel, reconstruivel e temporario;
- pipelines, chaves de cache, versoes e imutabilidade;
- protocolo de auditoria, minimizacao de dados e provider abstraction;
- migrations, escrita atomica, journal, backup, restore e diagnosticos;
- comandos locais, testes e limites operacionais;
- divida conhecida e fronteira F6.1/F6.2.

Fontes, em ordem: `AGENTS.md`; decisoes e roadmap; README; testes/codigo; specs historicas. Uma
divergencia e documentada em `docs/DECISIONS.md` ou marcada como divida, nunca resolvida por
suposicao silenciosa.

## Integracao com a interface

A UI nao ganha dashboard operacional. A integracao proposta e contextual:

- erro de importacao mostra titulo, acao recomendada, codigo copiavel e `Continuar` quando seguro;
- viewer distingue `PDF_SOURCE_MISSING`, `RENDER_FAILED` e derivado em reconstrucao;
- shell exibe um indicador discreto somente quando a saude esta degradada ou ha operacao
  interrompida;
- um painel compacto lista diagnostico e operacoes retomaveis, sem expor caminho absoluto;
- backup e restore permanecem documentados para CLI, sem botao web;
- foco, teclado, contraste, reduced motion e linguagem CAD tecnica permanecem intactos.

Durante a implementacao, o desenho desse painel passa por revisao com as skills de UI/UX e motion
disponiveis antes de ser considerado concluido.

## Sequencia de implementacao proposta

1. reconstituir `00-PROJECT-CONTEXT` e o estado atual de `06-TECH-ARCHITECTURE`, marcando o
   contrato F6.1 aprovado como alvo;
2. criar testes de falha e fixtures para filesystem, SQLite corrompido, migration invalida e
   interrupcoes controladas;
3. implementar tipos de diagnostico, envelope publico e checks read-only;
4. implementar o escritor atomico e migrar original, geometria/extracao e render;
5. adicionar migration `010`, repository de operacoes, eventos e deteccao de interrupcao;
6. tornar importacao, Sheet Map e auditoria deterministica retomaveis pelas identidades atuais;
7. implementar inventario, manifesto, snapshot SQLite e `backup-create`;
8. implementar `backup-verify` e testes contra archive/path traversal/corrupcao;
9. implementar restore para destino inexistente, staging e smoke test com `TRUSS_DATA_DIR`;
10. endurecer o runner de migrations com preflight e snapshot pre-migration;
11. integrar diagnosticos e retomada contextual no frontend;
12. executar recovery drill completo em copia descartavel do estado real;
13. atualizar README, DECISIONS, documentos arquiteturais e roadmap somente apos todos os gates.

Testes devem ser executados apos cada bloco. Nenhuma etapa deve usar o banco real como destino de
restore ou fixture destrutiva.

## Arquivos previstos

Criacoes principais:

- `apps/api/truss_api/recovery/{models,errors,diagnostics,backup,restore,operations,repository,cli}.py`;
- `apps/api/truss_api/db/migrations/010_processing_operations.sql`;
- `apps/api/tests/test_recovery_*.py`;
- `apps/web/lib/diagnostics-api.ts` e testes;
- componentes compactos de erro/operacao no shell existente;
- `docs/00-PROJECT-CONTEXT.md`;
- `docs/06-TECH-ARCHITECTURE.md`.

Alteracoes principais:

- storage, settings, migrations e lifecycle da API;
- importer, rendering, Sheet Map artifacts/geometry e auditoria;
- rotas de documentos, auditoria e health;
- cliente de API e workspace do frontend;
- `.gitignore`, `.env.example`, README, DECISIONS e roadmap.

Os nomes exatos de componentes podem acompanhar a estrutura existente, sem criar outro app ou
servico.

## Testes obrigatorios

### Backup e restore

- backup de banco aberto usa snapshot consistente e nao altera a origem;
- manifesto e lista de arquivos sao estaveis independentemente da ordem do filesystem;
- todo arquivo critico possui tamanho e SHA-256;
- `.env`, secrets, logs, cache, renders, exports, temporarios e backups nao entram;
- mudanca concorrente no corpus aborta publicacao;
- falta de original referenciado invalida o backup;
- ZIP truncado, hash divergente, entrada extra, path traversal e symlink sao recusados;
- verify nao escreve em `data/`;
- restore recusa alvo existente e nunca oferece force;
- falha remove apenas staging proprio;
- restore completo preserva hashes, contagens e integridade;
- banco restaurado abre com todas as migrations conhecidas;
- rebackup do destino restaurado e verificavel.

### Persistencia, arquivos e migrations

- falha antes da promocao nao publica arquivo parcial;
- `ENOSPC`, permissao e read-only produzem codigos distintos;
- original existente com o mesmo hash e reutilizado; conteudo divergente no mesmo destino falha;
- geometria nova nao sobrescreve snapshot anterior e legado continua legivel;
- render parcial nunca e servido;
- migration `010` e aditiva e preserva todas as linhas existentes;
- migration desconhecida/gap e recusada sem escrita;
- falha de migration preserva banco e snapshot pre-migration verificavel;
- integridade e foreign keys sao verificadas antes e depois.

### Retomada

- interrupcao em cada checkpoint da importacao retoma para exatamente um documento;
- revisao e PDF anteriores permanecem byte a byte inalterados;
- Sheet Map identico e reutilizado; versao nova cria snapshot novo;
- auditoria deterministica identica recupera o mesmo run pelo cache;
- findings confirmados, rejeitados e manuais preservam status e justificativa;
- evento de retomada e append-only e sequencial;
- duas solicitacoes de retomada concorrentes nao executam o mesmo passo duas vezes;
- operacao externa interrompida nunca e repetida sem confirmacao;
- upload duplicado normal continua retornando conflito claro.

### Diagnosticos e web

- PDF vazio, invalido, criptografado/ilegivel e pagina que falha ao renderizar possuem diagnostico;
- banco corrompido nao e migrado nem reportado como saudavel;
- health barato nao cria diretorio e nao expoe caminho absoluto;
- deep diagnostics encontra arquivo ausente/corrupto e temporario abandonado;
- frontend aceita envelope novo e erro string legado;
- acao recomendada, codigo e estado de retry aparecem corretamente;
- `Continuar` so aparece em operacao segura;
- viewer, achados e central de aprendizado permanecem sem regressao;
- teclado, foco, contraste e `prefers-reduced-motion` passam na verificacao manual.

### Recovery drill real

Executar somente em copia/target descartavel:

1. registrar contagens e hashes do estado real sem modifica-lo;
2. criar e verificar um backup inicial do estado real;
3. restaura-lo como origem descartavel e iniciar o Truss somente nessa copia;
4. criar e verificar um segundo backup da origem descartavel;
5. adicionar uma nova revisao na origem descartavel depois desse snapshot;
6. restaurar o segundo backup para outro caminho inexistente;
7. iniciar API e web com `TRUSS_DATA_DIR` apontando para o restore;
8. abrir projeto, revisao antiga, PDF, Sheet Map, findings e feedback;
9. confirmar que a revisao criada depois do segundo backup nao aparece no restore;
10. interromper uma importacao em checkpoint controlado e retoma-la no ambiente descartavel;
11. confirmar ausencia de duplicatas e preservacao dos hashes;
12. remover apenas as copias temporarias pelo mecanismo de teste depois de registrar o resultado.

## Criterios de aceite

- [ ] os dois documentos arquiteturais ausentes existem e refletem codigo, decisoes e roadmap;
- [ ] backup usa snapshot SQLite, manifesto versionado e hashes de todo dado duravel;
- [ ] verificacao detecta corrupcao antes de qualquer restore;
- [ ] restore so publica em destino inexistente e nunca sobrescreve `data`, revisao ou PDF;
- [ ] PDFs originais e feedback humano sobrevivem ao recovery drill;
- [ ] dados reconstruiveis excluidos reaparecem sob demanda sem perda funcional;
- [ ] escritas relevantes usam temporario, validacao e promocao atomica;
- [ ] geometrias novas sao imutaveis por conteudo e geometrias legadas continuam legiveis;
- [ ] falhas de PDF, render, disco, artefato, banco e migration possuem diagnostico acionavel;
- [ ] health nao mascara falha nem expoe caminho absoluto;
- [ ] migration insegura ou banco corrompido nao recebem escrita automatica;
- [ ] importacao, Sheet Map e auditoria deterministica interrompidos podem ser retomados sem
      duplicar estado;
- [ ] chamada externa potencialmente cobrada nunca e repetida silenciosamente;
- [ ] journal preserva eventos e nao implementa antecipadamente a fila da F6.2;
- [ ] suites completas, lint, typecheck e build ficam verdes;
- [ ] fluxo principal e recovery drill sao verificados manualmente e documentados;
- [ ] nenhuma fila, lote, worker, SaaS, autenticacao ou cloud backup entra no milestone.

## Fora do escopo

- fila de 85 folhas, workers, prioridade, concorrencia, progresso, pausa e cancelamento;
- retry automatico de AI Provider ou qualquer operacao com custo potencial;
- backup agendado, retencao, deduplicacao entre backups, incremental ou cloud;
- criptografia e gerenciamento de chaves do archive;
- restore in-place, merge de bancos, downgrade ou edicao automatica de `.env`;
- recuperacao de arquivo fonte que nunca esteve sob gestao do Truss;
- mudanca de Next.js, FastAPI, SQLite, disco local ou abstracao de AI Provider;
- comparacao grafica entre revisoes, candidata a F7;
- multiusuario, autenticacao, cobranca, SaaS ou fine-tuning.

## Riscos e mitigacoes

| Risco | Mitigacao proposta |
|---|---|
| falsa sensacao de backup seguro | verify obrigatorio no create e recovery drill real |
| ZIP contem PDFs sensiveis | destino local explicito, exclusao de secrets e aviso de arquivo nao criptografado |
| restore destrutivo | alvo inexistente, staging, sem `--force` e sem in-place |
| SQLite e arquivos fora do mesmo instante | snapshot + arquivos imutaveis + revalidacao do inventario mutavel |
| migration falha no startup | preflight, snapshot verificado e fail-closed |
| retomada duplica achados | identidades atuais, cache e transacoes; feedback nunca e regravado |
| journal vira fila prematura | schema sem worker/prioridade/agendamento/progresso/cancelamento |
| diagnostico vaza ambiente | paths relativos, mensagens publicas seguras e detalhes apenas em log local |
| geometria historica muda | novos nomes por hash e compatibilidade de leitura legada |

## Gate de aprovacao

Este documento e apenas a proposta da F6.1. A implementacao deve permanecer parada ate o
proprietario aprovar explicitamente as decisoes, em especial:

- conteudo padrao do backup;
- restore somente para destino novo;
- migration do journal de operacoes;
- CLI como unica superficie de backup/restore;
- limites entre retomada unitaria da F6.1 e fila/lote da F6.2.

## Estado da implementacao em 2026-09-02

Aprovacao explicita recebida. A fundacao foi implementada, testada e publicada. O milestone
permanece aberto somente porque o estado real nao satisfaz o contrato fail-closed do backup.

Implementado:

- `docs/00-PROJECT-CONTEXT.md` e `docs/06-TECH-ARCHITECTURE.md` reconstruidos;
- migration `010` com journal de operacoes e eventos append-only;
- deteccao de operacoes interrompidas no startup e retomada por compare-and-swap;
- importacao e auditoria deterministica retomaveis; visao nunca recebe retry automatico;
- escrita atomica para PDF original, render, extracao e geometria reduzida por conteudo;
- envelope de erro tipado, `/health` seguro e `/diagnostics` com modo profundo;
- migrations com verificacao, hash novo e snapshot pre-migration;
- `truss-backup-v0.1`, verificacao de hashes/paths/SQLite e restore para destino inexistente;
- CLI de backup, verify, restore, diagnose e resume;
- saida JSON da CLI isolada de imports de PDF nos comandos que nao usam retomada;
- identidade de operacao atomica e idempotente, incluindo rule packs deterministicas e a
  configuracao relevante da analise visual;
- aviso operacional contextual e erros acionaveis no frontend, sem dashboard e sem backup web;
- leituras de estado mutavel do frontend sem cache HTTP;
- testes de corrupcao, path traversal, alvo existente, arquivo ausente, migration falha e retomada.

Validacao final concluida:

- backend completo: `258 passed, 1 skipped`;
- frontend completo: `50 passed`;
- lint passou;
- typecheck passou;
- build Next.js 16 passou;
- drill completo de backup, verify, restore e rebackup passou em uma origem descartavel;
- verificacao manual passou em API/web descartaveis: `/health` ficou `degraded`, o projeto abriu e
  o painel exibiu uma operacao visual interrompida sem oferecer retomada automatica;
- a verificacao web deve usar o host canonico `localhost`; `127.0.0.1` pode falhar no controle de
  origem dos recursos internos do Next.js dev;
- os servidores temporarios foram encerrados e as portas de teste ficaram livres.

Recovery drill real:

- a criacao do backup foi corretamente recusada com `PDF_SOURCE_MISSING`;
- o SQLite real possui 5 documentos e 4 referencias de original ausentes;
- tres ausencias sao revisoes de `Proj_Estrutural_RanchoQueimado_geral.pdf`;
- uma ausencia e `017_26_est_geral-01.pdf`;
- os hashes esperados sao `7d2f9c32...` para as tres primeiras revisoes e `5c7d3d3d...` para a
  quarta;
- nenhum archive parcial foi publicado e o banco real nao foi alterado pelo drill;
- o snapshot pre-migration da aplicacao da migration `010` permanece ignorado em
  `data/db/recovery/`.

Trabalho restante, em ordem:

1. localizar os quatro PDFs pelos hashes/conteudo conhecido ou decidir explicitamente como
   reconciliar os registros orfaos; nao reduzir a ausencia critica a warning;
2. repetir `backup-create` e `backup-verify` sobre o estado real;
3. restaurar para dois diretorios descartaveis e concluir o recovery drill ponto-no-tempo;
4. confirmar no restore real projeto, revisao, PDF, Sheet Map, findings e feedback;
5. executar novamente backend, frontend, lint, typecheck e build se houver qualquer correcao;
6. atualizar criterios de aceite e DECISIONS somente depois do drill real verde;
7. nao iniciar F6.2 antes de encerrar estes itens.
