# F5.2 - Central de preferencias e propostas por evidencia

Data: 2026-09-01

Status: concluido e validado em 2026-09-01

Escopo: tornar preferencias, evidencias e propostas de aprendizado inspecionaveis e reversiveis,
sem ativar comportamento automaticamente e sem alterar rule packs versionados

## Resultado pretendido

O proprietario consegue abrir uma central local, listar preferencias ativas e revogadas, entender
por que cada decisao existe, localizar o finding de origem no PDF e revogar o comportamento. A
mesma superficie agrega confirmacoes, rejeicoes e achados manuais por chaves deterministicas e
mostra propostas somente quando uma politica de evidencia versionada e atendida.

`rule_preferences` continua sendo o unico dado desta fase que muda a apresentacao dos findings.
Uma proposta nunca silencia, reclassifica ou cria regra sozinha.

## Contrato proposto

- preferencias continuam locais, explicitas e revogaveis;
- F5.2 preserva o unico efeito aprovado na F5.1: `scope: sheet_type` + `action: suppress`;
- regra, tipo de prancha, motivo, datas e finding de origem ficam visiveis na central;
- toda evidencia possui localizador de projeto, revisao, documento, folha, bbox em pontos PDF e
  finding de origem;
- propostas sao derivadas dos findings existentes; abrir a central nao grava nem altera dados;
- uma decisao sobre proposta e persistida separadamente do finding e da preferencia;
- somente aprovar uma proposta de supressao cria `rule_preferences`, na mesma transacao;
- confirmar, rejeitar ou criar achado manual nunca cria preferencia automaticamente;
- propostas de manutencao de regra e de novo checklist sao apenas decisoes para calibracao; elas
  nao mudam confianca, severidade, YAML ou motor de regras na F5.2;
- nenhuma IA, embedding, similaridade semantica ou chamada de rede participa do agrupamento;
- revogar uma decisao nao apaga seu historico;
- findings, audit runs, PDFs e Sheet Maps permanecem imutaveis segundo seus contratos atuais.

## Chaves estaveis e politica de evidencia

A politica recebe a versao `learning-policy-v0.1`. Os contadores consideram no maximo uma
ocorrencia por finding persistido e exigem folhas distintas para impedir que reprocessamentos ou
varios achados sobre a mesma folha inflem a evidencia.

### Regra automatica

Chave material:

```text
auto | sheet_type | rule_id
```

Sinais validos:

- finding com `origin = ai`;
- `rule_id` presente;
- tipo de prancha classificado;
- status atual `confirmed` ou `rejected`;
- findings legados, pendentes ou sem rastreabilidade nao entram na contagem.

Propostas:

| Tipo | Limiar minimo | Efeito se aprovado |
|---|---|---|
| `suppress_rule` | 2 rejeicoes em 2 folhas e razao de rejeicao >= 75% | cria preferencia `suppress` para `(sheet_type, rule_id)` |
| `retain_rule` | 3 confirmacoes em 2 folhas e razao de confirmacao >= 75% | registra decisao para calibracao; nenhum efeito no runtime |

Uma preferencia F5.1 ainda pode ser aprovada a partir de uma unica rejeicao no viewer. O limiar
acima controla somente quando a central passa a sugerir a decisao por evidencia acumulada.

### Achado manual

Chave material:

```text
manual | sheet_type | category | type | normalized_description
```

`normalized_description` usa Unicode normalizado, caixa baixa, espacos colapsados e pontuacao
periferica removida. A chave publica recebe SHA-256 do material; a interface sempre mostra o texto
normalizado e as ocorrencias, nunca apenas o hash. Nao ha agrupamento aproximado.

Proposta `draft_rule`:

- 3 achados manuais com a mesma chave;
- pelo menos 2 folhas distintas;
- mesmo tipo de prancha classificado.

A aprovacao marca o padrao como candidato revisado para calibracao futura. Ela nao escreve em
`apps/api/truss_api/rules/packs/` e nao passa a gerar findings. A transformacao em item de checklist
pertence a F5.3 e exige revisao propria.

## Leitura derivada e persistencia de decisoes

### Evidencia derivada

`GET /learning/proposals` agrega os findings atuais e combina o resultado com decisoes ja
persistidas. A resposta informa:

- chave, tipo e versao da politica;
- regra e tipo de prancha quando aplicaveis;
- contagens por sinal, folhas, revisoes e projetos distintos;
- limiar e razao observada;
- estado `insufficient`, `pending`, `approved` ou `dismissed`;
- efeito real: `suppresses_findings` ou `calibration_only`;
- lista de evidencias localizaveis;
- decisao ativa e preferencia vinculada, quando existirem.

Grupos abaixo do limiar ficam disponiveis apenas com o filtro `Evidencia insuficiente`; eles nao
sao apresentados como proposta pronta.

### Migration proposta

Criar `008_learning_proposal_decisions.sql` com duas tabelas append-friendly:

```text
learning_proposal_decisions
  id, stable_key, proposal_kind, decision, reason,
  policy_version, created_at, revoked_at

learning_proposal_evidence
  decision_id, finding_id, signal_kind, created_at
```

Restricoes:

- `proposal_kind`: `suppress_rule` | `retain_rule` | `draft_rule`;
- `decision`: `approved` | `dismissed`;
- uma unica decisao nao revogada por `stable_key`;
- FKs `ON DELETE RESTRICT` para decisao e finding;
- cada evidencia aparece uma vez por decisao;
- a decisao preserva o conjunto exato de findings visto pelo proprietario;
- revogacao preenche `revoked_at`, nunca apaga linhas.

Nao criar tabela de sinais: findings continuam como fonte de verdade. Nao duplicar contadores no
banco: eles sao um read model derivado.

## Operacoes da API

### Preferencias

- manter `GET /rule-preferences` compativel;
- adicionar filtros opcionais `status`, `sheet_type` e `rule_id`;
- enriquecer o DTO com o localizador do finding de origem e resumo da evidencia;
- manter `DELETE /rule-preferences/{id}` como revogacao, sem exclusao fisica;
- adicionar reativacao explicita a partir da decisao/finding original, sem reutilizar uma linha
  revogada.

### Propostas

- `GET /learning/proposals`: lista agregada, filtravel e sem efeitos colaterais;
- `GET /learning/proposals/{stable_key}`: detalhe e evidencias localizaveis;
- `POST /learning/proposals/{stable_key}/decisions`: aprovar ou descartar com justificativa;
- `DELETE /learning/proposal-decisions/{id}`: revogar a decisao e reabrir a proposta;
- aprovacao de `suppress_rule` cria decisao, snapshot de evidencias e preferencia em uma unica
  transacao;
- revogar uma decisao `suppress_rule` revoga a preferencia ativa vinculada na mesma transacao;
- endpoints retornam `409` quando a chave perdeu elegibilidade, a decisao ficou obsoleta ou existe
  conflito ativo;
- todos os endpoints usam `Settings` por dependencia e bancos temporarios nos testes.

## UX proposta

A central nao sera um dashboard de metricas. Ela sera uma superficie tecnica de decisao dentro do
workspace existente:

```text
Projeto ativo  [Revisao]                         [Aprendizado local]
-------------------------------------------------------------------
Preferencias | Propostas
-------------------------------------------------------------------
lista tecnica densa        | detalhe da decisao
regra / tipo / estado      | motivo e efeito real
contagens de evidencia     | evidencias localizaveis
datas                       | [Abrir na prancha] [Revogar/Aprovar]
```

- o botao `Aprendizado local` alterna entre viewer e central preservando a folha atual;
- `Preferencias` abre por padrao nas ativas e oferece filtros `Ativas`, `Revogadas` e `Todas`;
- `Propostas` abre em `Pendentes` e permite ver `Aprovadas`, `Descartadas` e `Insuficientes`;
- listas usam linhas, divisorias e tipografia tecnica; nao usar grade de cards ou numeros hero;
- o detalhe separa `efeito no runtime` de `evidencia para calibracao`;
- `Abrir na prancha` retorna ao viewer, seleciona projeto/revisao/folha, foca a bbox canonica e
  ativa o finding correspondente;
- aprovar ou descartar exige justificativa inline e confirmacao textual do efeito;
- revogar preferencia ou decisao e uma acao explicita, com resultado imediatamente refletido no
  viewer;
- estados de loading usam skeleton; vazio explica por que ainda nao ha proposta;
- transicoes de troca de superficie e foco usam 120-180 ms e respeitam
  `prefers-reduced-motion`;
- alvos mantem 38 px, foco visivel, labels alem de cor e navegacao por teclado.

## Integracao prevista

Backend:

- `apps/api/truss_api/db/migrations/008_learning_proposal_decisions.sql`;
- novo modulo `truss_api/learning/` para politica, agregacao, modelos, repositorio e rotas;
- `truss_api/preferences/` recebe somente o enriquecimento e as operacoes transacionais comuns;
- nenhuma alteracao em rule packs, cache de auditoria ou pipeline do Sheet Map.

Frontend:

- novo `components/learning/learning-center.tsx`;
- componentes menores para lista, detalhe e evidencia, evitando ampliar `sheet-viewer.tsx`;
- `project-workspace.tsx` controla a alternancia viewer/central e a navegacao global;
- `sheet-viewer.tsx` recebe apenas um alvo externo tipado `{sheetId, findingId, nonce}` para foco;
- `projects-api.ts` recebe DTOs e clientes aditivos;
- reutilizar tokens, badges e controles existentes do Truss.

## Sequencia de implementacao apos aprovacao

1. congelar fixtures de evidencia e escrever testes de politica que falham;
2. criar migration e modelos de decisao;
3. implementar normalizacao, chaves, agregacao e limiares;
4. implementar snapshot e decisoes transacionais;
5. enriquecer preferencias com localizadores;
6. adicionar contratos TypeScript e testes de apresentacao;
7. construir central com filtros, detalhe e acoes inline;
8. integrar `Abrir na prancha` e foco externo sem mover o PDF do centro do fluxo;
9. rodar suites completas e verificar manualmente o fluxo principal;
10. atualizar README, DECISIONS e roadmap somente depois dos criterios atendidos.

## Criterios de aceite

- [x] preferencia ativa e revogada aparece com regra, tipo, motivo, datas e finding de origem;
- [x] toda preferencia pode abrir exatamente sua evidencia no PDF;
- [x] revogar restaura findings sem apagar auditoria, feedback ou historico;
- [x] agregacao nao duplica ocorrencias em reprocessamentos;
- [x] tipos de prancha diferentes nunca compartilham a mesma chave;
- [x] conflitos entre confirmacoes e rejeicoes respeitam a razao minima de 75%;
- [x] achados manuais so agrupam por assinatura deterministica exata;
- [x] grupos abaixo do limiar nao aparecem como proposta pronta;
- [x] abrir/listar propostas nao cria nenhuma linha no banco;
- [x] aprovar supressao cria preferencia somente apos acao explicita;
- [x] aprovar `retain_rule` ou `draft_rule` nao muda findings nem rule packs;
- [x] decisoes duplicadas sao idempotentes ou retornam conflito claro;
- [x] revogacao preserva o snapshot de evidencias e reabre a proposta;
- [x] API usa banco temporario e cobre escopo, duplicidade, conflito e atomicidade;
- [x] web cobre filtros, loading, vazio, erro, aprovacao, revogacao e localizacao;
- [x] viewer atual permanece sem regressao, inclusive silenciados e cache anotado;
- [x] lint, typecheck, build, pytest e vitest ficam verdes;
- [x] verificacao manual cobre rejeicao -> proposta -> aprovacao -> supressao -> localizacao ->
  revogacao -> restauracao.

## Fora do escopo

- ativacao automatica de qualquer preferencia;
- escopos `global` ou `project` para preferencias;
- `downgrade`, mudanca automatica de severidade ou confianca;
- edicao automatica de YAML ou geracao de codigo de regra;
- mineracao do acervo aprovado, pertencente a F5.3;
- similaridade semantica de achados manuais;
- exportacao de dataset, pertencente a F5.3;
- backup, fila em lote e observabilidade, pertencentes a F6;
- IA externa, fine-tuning, multiusuario ou SaaS.

## Fechamento

O proprietario aprovou a execucao com `pode seguir`. A implementacao manteve o contrato aprovado:
propostas derivadas, decisoes explicitas com snapshot, unico efeito de runtime via
`rule_preferences` e navegacao para evidencia em coordenadas PDF. A verificacao manual usou uma
copia temporaria dos dados locais; ela foi movida para a Lixeira ao final sem alterar o acervo
real.

Evidencias finais:

- API: 233 testes passaram e 1 teste de calibracao permaneceu ignorado conforme o baseline;
- web: 46 testes passaram;
- ESLint, TypeScript e build de producao passaram sem erros;
- navegador: 2 rejeicoes em 2 folhas geraram proposta pendente; a aprovacao criou a preferencia,
  abriu `EST-0050-A` no bbox correto e marcou o finding como silenciado; a revogacao restaurou o
  finding e zerou o contador de silenciados;
- console do navegador sem mensagens durante o fluxo.
