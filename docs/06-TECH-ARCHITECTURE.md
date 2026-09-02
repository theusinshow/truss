# Arquitetura tecnica - Truss Agent

Atualizado em: 2026-09-02

Estado: arquitetura implementada ate F5 e contratos aprovados da F6.1. F6.2 permanece fora desta
fronteira.

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
```

Ha um unico processo de frontend e um backend local. Nao existe tenancy, conta de usuario,
servico de fila ou banco remoto. O backend e a autoridade para persistencia e coordenadas; o
frontend nao escreve diretamente em SQLite ou no filesystem.

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
-> construir Sheet Maps
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

O journal nao e fila: nao possui worker, prioridade, agenda, percentual, concorrencia ou
cancelamento. Esses contratos pertencem a F6.2.

## Backup e restore F6.1

`truss-backup-v0.1` e um ZIP local com:

- manifesto versionado;
- snapshot SQLite criado por `sqlite3.Connection.backup`;
- originais referenciados;
- geometria/extracoes;
- analyses/runs de calibracao;
- knowledge inbox.

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

