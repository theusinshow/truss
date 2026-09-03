# Arquitetura tecnica - Truss Agent

Atualizado em: 2026-09-02

Estado: arquitetura implementada e validada ate F6.2.

## Visao geral

```text
Next.js 16 / React 19
        |
        | HTTP local
        v
FastAPI / Python
   |         |             |
   |         |             +--> AI Provider abstrato (opt-in, crops localizados)
   |         +--> arquivos locais (PDF, geometria, render, artefatos)
   +--> SQLite (metadados, snapshots, auditoria, feedback, operacoes)

Python batch worker (sem porta, concorrencia 1)
        |
        +--> SQLite queue -> journal unitario -> pipelines
```

Ha um processo de frontend, uma API local e um worker Python local sem porta de rede. Nao existe
tenancy, conta de usuario, broker ou banco remoto. O backend e a autoridade para persistencia e
coordenadas; o frontend nao escreve diretamente em SQLite ou no filesystem.

## Componentes

### `apps/web`

Next.js App Router com shell React orientado ao viewer. Responsabilidades:

- selecionar projeto, revisao, documento e folha;
- renderizar PDF/imagem e overlays a partir de coordenadas canonicas;
- navegar por Sheet Map, findings, assistente e aprendizado;
- coletar feedback humano;
- apresentar estado operacional e diagnosticos sem expor caminhos locais;
- solicitar retomada somente quando o backend marca a operacao como segura.

O frontend usa Geist para interface e JetBrains Mono somente para codigos, coordenadas e
metadados. O sistema visual e CAD tecnico escuro, com vermelho como acento funcional.

### `apps/api/truss_api`

FastAPI organiza o dominio em modulos:

- `projects`: projetos e revisoes;
- `documents`: validacao, armazenamento, folhas, texto e render;
- `sheetmap`: extracao vetorial, geometria, regioes, views, escopos e elementos;
- `rules` e `audit`: rule packs, avaliacoes, findings e feedback;
- `vision` e `ai`: candidatos localizados, crops, provider, cache e custo;
- `assistant`: conversa vinculada ao contexto da folha;
- `preferences`, `learning` e `calibration`: aprendizado explicito e corpus;
- `db`: conexao, schema e migrations numeradas;
- `recovery`: erros publicos, diagnostico, escrita atomica, journal, backup e restore.
- `batch`: fila duravel, fases, claims atomicos, cancelamento, retomada e worker local.

Rotas chamam orquestradores; orquestradores combinam dominio e repositories; repositories
concentram SQL. Artefatos em disco sao referenciados por caminhos relativos a `data_dir`.

## Modelo central

```text
project
  -> revision (imutavel)
       -> document (PDF original por hash)
            -> sheet (pagina e coordenadas)
                 -> sheet_map snapshot
                      -> scopes / regions / views / elements
                 -> audit_run
                      -> rule_evaluations
                      -> findings
                           -> feedback/status humano

preferences / learning decisions / calibration decisions
  -> evidencias e snapshots explicitos

processing_operations
  -> processing_operation_events append-only

document
  -> document_source_events append-only (SOURCE_UNAVAILABLE / SOURCE_RESTORED)

batch_run
  -> batch_items por folha e fase
  -> batch_run_events append-only
```

Uma revisao nao e sobrescrita por nova exportacao. Um Sheet Map com pipeline/entrada diferente e
novo snapshot. Audit runs preservam versao, cobertura e avaliacoes. Findings conhecidos usam
chave de deduplicacao, mas seu status humano nao e resetado por reexecucao.

## Coordenadas

O sistema canonico e o espaco da pagina PDF em pontos:

```text
bbox = (x0, y0, x1, y1)
origem e rotacao = metadados da pagina PDF
```

Texto, view, elemento, finding, evidencia e crop relevante carregam bbox nesse sistema. Pixels
existem apenas na saida de render. Zoom e overlay aplicam uma transformacao derivada de largura,
altura, rotacao e escala; nao gravam bbox somente em pixels.

## Armazenamento local

Layout padrao:

```text
data/
  db/truss.sqlite
  db/recovery/pre-migration-*.sqlite
  originals/<project>/<revision>/<sha256>-<nome>.pdf
  geometry/<project>/<revision>/...
  renders/...
  cache/...
  calibration/analyses/...
  calibration/runs/...
  calibration/exports/...
  knowledge-inbox/...
backups/
```

Classificacao:

- critica: SQLite e PDFs originais referenciados;
- duravel: knowledge inbox, geometria/extracoes e runs de calibracao;
- reconstruivel: renders, cache, previews e exports;
- temporaria: arquivos `.partial` e stagings reconhecidos;
- externa ao runtime: codigo, `.env`, segredos, logs e rule packs versionados.

PDF nao e armazenado no SQLite. Caminhos persistidos sao relativos ao `data_dir`. Novos
originais usam SHA-256 completo no nome. Novas geometrias reduzidas sao enderecadas por conteudo;
caminhos legados continuam legiveis.

`document_source_events` registra, em sequencia imutavel, uma fonte historica ausente do ambiente
ou sua restauracao posterior. `SOURCE_UNAVAILABLE` so pode ser declarado quando o arquivo nao
existe; `SOURCE_RESTORED` exige os bytes e o SHA-256 historico exato. A API e o viewer nunca
oferecem render para uma fonte cujo ultimo evento seja indisponivel.

## Escrita atomica

Arquivos relevantes seguem:

```text
criar temporario no mesmo diretorio
-> escrever e fsync quando suportado
-> validar formato/hash
-> os.replace para destino final
```

Falha remove apenas o temporario pertencente a operacao. `ENOSPC`, permissao/read-only e I/O sao
traduzidos em codigos publicos. Arquivo `.partial` nunca e considerado artefato valido.

## SQLite e migrations

O SQLite usa foreign keys por conexao. Migrations SQL numeradas sao append-only e registradas em
`schema_migrations`. Versoes historicas `001` a `009` nao possuem hash retroativo; migrations a
partir de `010` registram SHA-256 do SQL.

Antes de migration pendente em banco existente:

1. `integrity_check` e `foreign_key_check`;
2. sequencia aplicada deve ser prefixo conhecido;
3. snapshot verificado em `data/db/recovery` pela API de backup do SQLite;
4. migration e registro executam na mesma transacao;
5. integridade e verificada novamente.

Falha e fail-closed. Snapshot nunca e copiado automaticamente sobre o banco ativo.

## Pipelines e cache

### Importacao

```text
validar PDF
-> armazenar original por hash
-> registrar document/sheets/text blocks em transacao
-> responder 202 no fluxo em lote
-> worker constroi Sheet Maps e auditorias
```

### Sheet Map

Extrai texto e vetor, detecta regioes/carimbo, classifica a folha, detecta escopos/views/elementos
e calcula snapshot hash. Entrada identica e mesma versao reutilizam o snapshot existente.

### Auditoria deterministica

Carrega Sheet Map, registro entre folhas e rule packs aplicaveis. A chave inclui hashes/versoes
relevantes. Avaliacoes distinguem pass, fail, unknown, not applicable e skipped. Somente fail gera
finding; cobertura completa permanece no run.

### Visao

Detectores locais selecionam candidatos e bboxes. O backend renderiza crop com padding limitado,
aplica budget/call limit e usa o AI Provider. Crop, configuracao, modelo e prompt compoem o cache.
O PDF completo nao e reenviado a cada pergunta.

### Calibracao

Runner isolado mede corpus por manifesto e hashes. `delivered_reference` nao equivale a ground
truth perfeito. Propostas e decisoes nao alteram rules automaticamente.

## Journal e retomada F6.1

`processing_operations` guarda estado atual e `processing_operation_events` guarda eventos
append-only. Tipos iniciais: importacao de documento, Sheet Map, auditoria deterministica e
auditoria visual.

Estados:

```text
pending -> running -> completed
                  -> failed
                  -> interrupted
                  -> manual_retry_required
```

Importacao usa checkpoints `validated`, `original_stored`, `document_registered`,
`sheet_maps_completed`, `completed`. Identidade semantica e compare-and-swap impedem execucao
concorrente duplicada. No startup, `running` remanescente vira interrompida. Nada e retomado sem
acao do usuario.

Somente operacao deterministica/cacheada pode ser retomada. Chamada visual interrompida vira
`manual_retry_required`, pois repetir pode gerar custo externo.

O journal nao e fila: a F6.2 adiciona uma camada separada que somente agenda e agrega operacoes
unitarias. Resultados e identidades cacheadas continuam pertencendo ao journal e aos pipelines.

## Lote e observabilidade F6.2

`batch_runs`, `batch_items` e `batch_run_events` persistem configuracao congelada, unidade por
folha/fase e historico append-only. O fluxo possui barreira global de Sheet Map antes da auditoria
deterministica. Registry parcial declara cobertura incompleta e regras cross-sheet retornam
`UNKNOWN`; a folha sem Sheet Map fica `skipped_dependency`.

O worker usa processo separado, abre o PDF por operacao e reivindica um item por compare-and-swap
com `run_token`. Concorrencia deterministica e visual permanecem fixas em 1; o SQLite mantem o
journal mode anterior e `busy_timeout=5000`. Startup transforma item sem dono em falha e lote
`interrupted`; retomada e sempre explicita. Falha local tipada permite no maximo uma repeticao
automatica. Chamada visual nunca e repetida sem nova confirmacao.

Cancelamento grava `cancel_requested`, deixa a etapa atomica corrente publicar com seguranca e
marca o restante como `cancelled`. A web consulta a cada 1 s em primeiro plano e 5 s em background,
para no estado terminal e mantem o viewer navegavel. Progresso e contagens sao derivados dos itens,
nunca de timer ou contador duplicado.

## Comparacao grafica F7.1

`truss_api.comparisons` executa a comparacao no backend local. O matcher recebe snapshots das
folhas e aplica, nesta ordem, pareamento manual ativo, `sheet_code` canonico exato e unico e mesmo
hash/indice para replay de conteudo. Numero da pagina e nome de arquivo servem somente para
apresentacao e ordenacao, nunca para afirmar identidade.

O detector raster usa PyMuPDF em tons de cinza e escala reduzida. Pixels acima do limiar sao
agregados em tiles e componentes conexos; cada componente volta ao sistema canonico de pontos PDF
como `base_bbox` e `target_bbox`. Mudanca de dimensao ou rotacao produz uma regiao de pagina
inteira e impede sobreposicao/blink na web. Falha ou ausencia da fonte produz `unavailable` e nao
e convertida em igualdade.

A migration `014_revision_comparisons.sql` adiciona:

- `revision_comparisons`, run imutavel e unico por fingerprint;
- `revision_comparison_pairs`, snapshot imutavel do pareamento e estado de cada folha;
- `revision_comparison_regions`, regioes imutaveis nos dois sistemas PDF;
- `comparison_pair_overrides`, decisoes humanas com revogacao por timestamp.

O fingerprint inclui fontes, Sheet Maps, pareamentos ativos e `revision-comparison-v0.1`. Um replay
identico devolve o mesmo run; mudar ou revogar um pareamento cria outro snapshot e preserva o
anterior. A web carrega o painel sob demanda e reutiliza o endpoint existente de finding manual
somente apos acao explicita do proprietario.

Rotas aditivas:

```text
POST   /projects/{project_id}/revision-comparisons
GET    /revision-comparisons/{comparison_id}
POST   /projects/{project_id}/comparison-pairings
DELETE /comparison-pairings/{pairing_id}
```

## Deltas de camadas PDF F7.2

A F7.2 preserva o pareamento e o run imutavel da F7.1 e adiciona comparacao local de texto nativo
e primitivas vetoriais. A extracao reutiliza `extract_page` e `EXTRACTOR_VERSION`; o fingerprint
inclui essa versao e `revision-comparison-v0.2`, de modo que um replay identico reutiliza pares e
deltas sem reabrir os PDFs.

Texto e vetor passam primeiro por consumo de igualdade exata. `moved` exige conteudo ou geometria
estavel e correspondencia unica; `modified` exige correspondencia espacial mutua e unica. Uma
evidencia ambigua nunca e forçada para esses tipos: as primitivas observadas permanecem
`added`/`removed`. A classificacao descreve somente a mudanca extraida, nao significado tecnico,
conformidade ou erro de engenharia.

A migration `015_comparison_layer_deltas.sql` acrescenta estado, contagens completas, resumo e
truncamento aos pares e cria `revision_comparison_deltas`. Cada registro guarda camada, tipo,
metodo/similaridade, payload antes/depois, detalhes estruturados e bboxes base/alvo em pontos PDF.
Triggers impedem update e delete. Runs F7.1 anteriores sao lidos como `not_run`.

Cada camada persiste ate 500 deltas, depois de calcular as contagens totais. Fonte ausente, falha
de extracao e dimensao/rotacao incompativel produzem estados explicitos em vez de igualdade vazia.
Na web, os filtros `Raster`, `Texto` e `Vetor` controlam overlays independentes; a selecao de um
delta foca a bbox disponivel e abre evidencia antes/depois no painel direito.

## Backup e restore F6.1

`truss-backup-v0.1` e um ZIP local com:

- manifesto versionado;
- snapshot SQLite criado por `sqlite3.Connection.backup`;
- originais referenciados;
- geometria/extracoes;
- analyses/runs de calibracao;
- knowledge inbox.

Uma fonte ausente invalida o backup, exceto quando o ultimo evento append-only do documento a
declara `SOURCE_UNAVAILABLE`. Nesse caso, o manifesto lista a excecao separadamente e nao inclui
bytes ficticios. O verificador cruza cada declaracao com o snapshot SQLite; documentos sem essa
declaracao continuam obrigados a possuir o original e o hash correto.

Cada entrada possui caminho POSIX relativo, papel, tamanho e SHA-256. Renders, cache, exports,
previews, secrets, logs e backups anteriores ficam fora.

Verificacao recusa entrada extra/duplicada, path traversal, symlink, hash/tamanho divergente,
SQLite corrompido, migration desconhecida e original ausente. Restore extrai em staging irmao e
publica somente por rename para um destino inexistente. Nao existe force, merge ou in-place.

Comandos:

```powershell
.venv\Scripts\python -m truss_api.recovery.cli backup-create
.venv\Scripts\python -m truss_api.recovery.cli backup-verify <archive>
.venv\Scripts\python -m truss_api.recovery.cli restore <archive> --target <novo-diretorio>
.venv\Scripts\python -m truss_api.recovery.cli diagnose --deep
.venv\Scripts\python -m truss_api.recovery.cli resume <operation-id>
.venv\Scripts\python -m truss_api.recovery.cli source-unavailable <document-id> --reason-code <codigo> --note <nota>
.venv\Scripts\python -m truss_api.recovery.cli source-restored <document-id>
```

O archive nao e criptografado e deve ser tratado como sensivel.

## Erros e saude

Falhas operacionais usam envelope:

```json
{
  "detail": {
    "code": "PDF_UNREADABLE",
    "message": "O arquivo nao pode ser aberto como PDF.",
    "action": "Exporte o PDF novamente e importe a nova copia.",
    "retryable": false,
    "operation_id": null
  }
}
```

`/health` e barato, nao cria layout e nao expoe paths. `/diagnostics` agrega checks nomeados;
`deep=true` verifica hashes de originais. Stack traces e detalhes sensiveis permanecem somente no
ambiente local de desenvolvimento/log.

## Privacidade e AI Provider

Provider e uma abstracao configuravel. Default local nao implica chamada externa. Chaves ficam
em ambiente e nunca em banco, export, manifesto ou resposta. Toda operacao externa deve carregar
versao/modelo e respeitar limites. Retentativa potencialmente cobrada exige acao explicita.

## Verificacao

O repositorio possui testes Python de dominio/API e Vitest para frontend. Alteracoes de
persistencia, coordenadas, findings, cache, preferencias, calibracao ou recuperacao exigem
fixtures isoladas em `tmp_path`. Restore nunca usa o `data` real como alvo de teste.

Gate final de milestone:

- suites API e web;
- lint, typecheck e build Next;
- recovery drill em diretorios descartaveis;
- verificacao manual do viewer, diagnostico e retomada;
- README, DECISIONS e roadmap atualizados.
