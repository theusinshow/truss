# Truss Agent

Aplicativo pessoal de revisao grafica de projetos estruturais.

O Truss Agent nasce como um laboratorio de uso diario para revisao de pranchas estruturais em PDF, com foco inicial em formas, locacao, cortes, detalhamentos, legibilidade, cotas, titulos, escalas, tabelas e coerencia grafica. O objetivo e funcionar como um segundo desenhista tecnico: ele analisa, marca regioes suspeitas, permite confirmar ou rejeitar achados, faz perguntas para aprender padroes e mantem historico por projeto e revisao.

Este repositorio deve ser implementado de forma incremental, seguindo `AGENTS.md` e os documentos em `docs/`.
O estado das fases e a sequencia aprovada de continuidade ficam em [`docs/14-ROADMAP.md`](docs/14-ROADMAP.md).

## Principio central

O PDF e o protagonista. O chat e uma ferramenta complementar.

Fluxo principal:

```text
Projeto
  |
Revisao imutavel
  |
PDF
  |
Extracao visual + textual + vetorial
  |
Sheet Map
  |
Auditoria
  |
Achados localizados no canvas
  |
Validacao humana
  |
Memoria + dataset
```

## Stack alvo

- Web: Next.js + TypeScript
- UI: Tailwind CSS + componentes acessiveis
- Motion: biblioteca de motion para React, usada com proposito e respeitando reduced motion
- Backend local: FastAPI + Python
- PDF: PyMuPDF como base de parsing/renderizacao
- Banco: SQLite
- Arquivos pesados: disco local
- IA: provider abstrato; primeira implementacao com OpenAI

## V0.1 concluida quando

E possivel criar um projeto, importar um PDF estrutural real com uma ou varias pranchas, separar e interpretar as folhas, abrir uma prancha no viewer, executar auditoria grafica agressiva, visualizar achados diretamente sobre a regiao correspondente, navegar entre eles, confirmar/rejeitar cada apontamento, adicionar achado manual, responder perguntas do Truss e manter todo o estado salvo localmente.

## M0 - Bootstrap

O M0 cria apenas a base executavel do produto:

- monorepo npm para o frontend;
- frontend Next.js com shell tecnico inicial;
- backend FastAPI local com health check;
- estrutura local de armazenamento em `data/`;
- testes minimos de web e API;
- scripts de execucao local.

M0 nao implementa importacao de PDF, viewer, auditoria, IA, persistencia completa ou fluxo de projeto.

## M1 - Projects + SQLite

M1 adiciona a primeira persistencia local:

- banco SQLite em `data/db/truss.sqlite`;
- tabelas `projects` e `revisions`;
- revisoes imutaveis com codigo unico por projeto;
- API local para listar/criar projetos, consultar projeto e criar revisoes;
- tela inicial conectada ao backend para gerenciar projetos e revisoes.

As rotas FastAPI recebem `Settings` por dependencia para permitir testes com banco temporario sem tocar no estado local real.

## M2/M3 - PDF import + viewer inicial

O fluxo visual inicial permite:

- importar PDF real para uma revisao imutavel;
- calcular hash SHA-256 do conteudo;
- copiar o arquivo para `data/originals/{project}/{revision}/`;
- registrar `documents` e `sheets` no SQLite;
- extrair quantidade de paginas, dimensoes em pontos PDF e rotacao;
- renderizar folha sob demanda para PNG em `data/renders/`;
- visualizar folhas no frontend com navegacao, zoom, fit e pan por arrasto.

O contrato de coordenadas inicial usa pontos PDF (`pt`) como sistema canonico. Pixels de render sao derivados e nao substituem as coordenadas da pagina.

## M4/M9 - Parsing, auditoria inicial e feedback

O pipeline agora persiste:

- blocos de texto nativo por folha em `text_blocks`;
- bounding boxes textuais em coordenadas PDF;
- execucoes de auditoria em `audit_runs`;
- achados estruturados em `findings`;
- status `pending`, `confirmed` e `rejected`;
- motivo de rejeicao;
- achados manuais com origem `human`.

A auditoria V0.1 inicial e deterministica e agressiva, usando regras simples sobre texto nativo: ausencia de texto, escala nao encontrada e titulo tecnico nao reconhecido. A arquitetura preserva a fronteira para regras mais fortes e analise multimodal/IA sem transformar o produto em um prompt monolitico.

O Sheet Map tambem suporta pranchas de conteudo misto. `sheet_type` permanece como contrato
legado, enquanto escopos tecnicos como `formas` e `armaduras` podem coexistir na folha e ser
associados individualmente as views. O motor aplica cada rule pack somente ao seu escopo; quando
a associacao nao e confiavel, o resultado e nao verificavel em vez de assumir uma classificacao.

A identidade da prancha separa evidencia de interpretacao: `sheet_code_raw` preserva o texto lido
no carimbo e `sheet_code` so contem a forma canonica verificavel. O intake de calibracao representa
todas as paginas, inclusive quando nenhuma view foi segmentada.

## F3 - Elementos e cruzamento entre folhas

O primeiro slice de F3 extrai ocorrencias de pilares (`P1`, `P 12`, `P-12A`) do texto nativo,
preservando codigo bruto, forma canonica, bbox em pontos PDF, confianca e proveniencia. As
ocorrencias pertencem ao snapshot imutavel do Sheet Map; o registry da revisao e derivado por
consulta e nunca duplicado em uma tabela materializada.

A regra cross-sheet procura pilares presentes em views de formas e nao localizados em folhas com
detalhamento explicito de pilares. Sem alvo observavel, sem codigos extraiveis ou com origem
ambigua, o resultado e `UNKNOWN`/`NOT_APPLICABLE`, nao um erro inventado. O cache inclui o
fingerprint do registry, portanto anexar ou reprocessar outra folha invalida resultados dependentes.

Medido em 13 PDFs aprovados (259 paginas): 2.558 ocorrencias, 190 comparacoes conformes e zero
candidatos a finding. A fixture defeituosa independente gera exatamente um finding localizado para
`P2`.

O segundo slice de F3 reconhece somente estados de ciclo de vida explicitamente associados ao
codigo (`MORRE`, `NASCE` e `PASSA`) e deriva pares de niveis sem inventar unidade de engenharia.
Pares entre folhas exigem paginas consecutivas, ao menos tres codigos compartilhados e overlap de
0,50; um pilar sem estado nunca e presumido como `PASSA`. Medido no mesmo corpus: 78 marcacoes,
41 associadas com seguranca, 30 niveis, 10 pares, 20 `PASS`, 25 `UNKNOWN`, zero `FAIL` e zero
candidatos a finding. Vigas, lajes e continuidade sem declaracao explicita permanecem fora deste
slice.

## M10/M6 - Provider local, chat, memoria e custo

A aplicacao possui uma primeira abstracao de AI Provider:

- interface `AIProvider`;
- provider local deterministico `local/deterministic-context-v0.1`;
- provider OpenAI opcional via Responses API;
- chat contextual por folha sem chamada externa;
- persistencia de mensagens em `chat_messages`;
- memorias explicitas em `memories`, com criacao, listagem e exclusao;
- eventos de uso em `ai_usage_events`;
- cache de auditoria em `cache_entries`.

Por padrao, `TRUSS_AI_PROVIDER=local` evita qualquer chamada externa. Para usar OpenAI, configure explicitamente `TRUSS_AI_PROVIDER=openai` depois de criar uma chave nova. Tambem existe `TRUSS_AI_PROVIDER=auto`, que usa OpenAI quando existe chave no ambiente e cai para o provider local quando nao existe. O provider local registra custo estimado zero. Segredos nunca devem ser salvos em SQLite, JSON, localStorage ou logs.

### Configuracao de IA

Use uma destas variaveis no ambiente do backend:

```powershell
setx OPENAI_API_KEY "sua_chave_nova"
```

ou:

```powershell
setx TRUSS_OPENAI_API_KEY "sua_chave_nova"
```

Configuracoes opcionais:

```powershell
setx TRUSS_AI_PROVIDER "auto"
setx TRUSS_OPENAI_MODEL "gpt-5.6-sol"
setx TRUSS_OPENAI_ORG_ID "org_..."
setx TRUSS_OPENAI_PROJECT_ID "proj_..."
setx TRUSS_OPENAI_REASONING_EFFORT "low"
setx TRUSS_OPENAI_MAX_OUTPUT_TOKENS "900"
```

Depois de usar `setx`, feche e reabra o terminal antes de iniciar a API. Para habilitar OpenAI diretamente, use `TRUSS_AI_PROVIDER=openai`. Para forcar execucao sem chamadas externas, use `TRUSS_AI_PROVIDER=local`. Quando houver mais de uma organizacao ou projeto na conta, configure tambem `TRUSS_OPENAI_ORG_ID` e `TRUSS_OPENAI_PROJECT_ID` para evitar que o backend use uma chave/projeto sem quota.

## F4.1 - Triagem visual de legibilidade por crops

A analise visual e uma acao explicita no viewer e permanece desabilitada por padrao. O Truss
seleciona candidatos por texto nativo e geometria, recorta somente a regiao suspeita e envia ao
provider a imagem PNG do crop. O PDF completo e o render completo da prancha nao fazem parte da
entrada multimodal.

O modelo classifica apenas `PASS`, `ATTENTION` ou `NOT_VERIFIABLE` em schema estrito. Ele nao
recebe autoridade para criar coordenadas: todo achado continua ligado a bbox canonica em pontos
PDF produzida antes da chamada. Resultados visuais aparecem como hipotese pendente
`ATTENTION_POINT/MEDIUM`, com origem `VISAO / CROP` e rastreabilidade de crop, provider, modelo e
prompt.

Para habilitar com OpenAI e um limite operacional por revisao:

```powershell
setx TRUSS_AI_PROVIDER "openai"
setx TRUSS_VISION_ENABLED "true"
setx TRUSS_VISION_BUDGET_USD_PER_REVISION "0.25"
setx TRUSS_VISION_MAX_CALLS_PER_REVISION "30"
setx TRUSS_VISION_MAX_CANDIDATES_PER_SHEET "8"
setx TRUSS_VISION_COST_RESERVE_USD_PER_CALL "0.05"
```

O cache visual usa o hash do crop, pipeline, prompt, modelo, reasoning e detalhe da imagem. A
reserva conservadora e o teto de chamadas sao verificados antes de cada chamada nova; respostas
ja em cache nao consomem novamente a API. O provider local informa indisponibilidade em vez de
simular visao.

O smoke test autorizado com provider real avaliou 3 crops por USD 0.019245 estimados e o replay
identico nao gerou nova chamada. A medicao completa fica em
`calibration/human-review/f4-visual-legibility-measurement-2026-09-01.md`.

## F5.1 - Preferencias explicitas de regras

O primeiro aprendizado do Truss e deliberadamente humano e reversivel. Rejeitar um finding nao
altera nenhuma regra. Quando o achado automatico possui `rule_id` e tipo de prancha verificavel, o
viewer oferece uma segunda acao: silenciar aquela regra em todas as folhas locais do mesmo tipo.

A aprovacao cria uma linha em `rule_preferences`; findings e audit runs permanecem intactos. Os
resultados afetados aparecem no filtro `Silenciados`, preservando bbox, evidencia e justificativa.
Reativar a regra grava a revogacao e faz os findings voltarem ao fluxo normal. Achados manuais,
regras sem rastreabilidade e folhas nao classificadas nunca geram preferencia.

## F5.2 - Central de preferencias e propostas

A central `Aprendizado local` torna preferencias ativas e revogadas inspecionaveis, com regra,
tipo de prancha, justificativa, datas e localizador exato do finding no PDF. A navegacao volta ao
viewer, troca projeto/revisao/folha quando necessario e foca a bbox persistida em pontos PDF.

Propostas sao derivadas deterministicamente dos feedbacks por `learning-policy-v0.1`: rejeicoes
ou confirmacoes de uma regra automatica usam chave por tipo de prancha e `rule_id`; achados
manuais exigem assinatura textual normalizada exata. Os limiares exigem folhas distintas e, para
regras automaticas, razao minima de 75%. Abrir a central nao grava dados e nenhuma proposta entra
em vigor sozinha.

Somente a aprovacao explicita de `suppress_rule` cria uma preferencia, na mesma transacao da
decisao. `retain_rule` e `draft_rule` registram apenas calibracao futura. Toda decisao congela sua
lista de evidencias; revogacoes preservam o historico e restauram os findings sem reescrever
auditorias, PDFs ou Sheet Maps.

## F5.3 - Calibracao deterministica pelo acervo

A calibracao roda somente por comando explicito e processa cada PDF em armazenamento e SQLite
temporarios. O manifesto `corpus-manifest-v0.1` separa projetos entregues de ground truth humano,
usa hash de conteudo e combina as versoes de Sheet Map, auditoria, rule packs, politica e
preferencias em duas chaves: uma para a analise bruta e outra para o run derivado.

```powershell
$env:PYTHONPATH="apps/api"
.venv\Scripts\python -m truss_api.calibration.runner measure-approved
```

A medicao validada reuniu 13 PDFs/259 paginas, 259 Sheet Maps, 1.626 avaliacoes deterministicas,
721 views e 2.557 pilares. Foram observados 140 findings brutos, zero suprimidos e 140 efetivos,
com duas propostas de ruido elegiveis. O replay identico reutilizou analise e run sem reabrir os
PDFs. Projetos entregues continuam sendo referencias de ruido, nao prova de erro zero.

A terceira aba de `Aprendizado local` permite selecionar o run, comparar contagens brutas,
suprimidas e efetivas, inspecionar crops de amostras/contraexemplos e aprovar, descartar ou reabrir
uma proposta. Aprovar apenas marca `ready_for_implementation`; nenhum YAML ou rule pack e editado.
O export portavel pode ser criado pela interface ou pela CLI:

```powershell
.venv\Scripts\python -m truss_api.calibration.runner export-feedback --run-id <id>
```

O ZIP contem manifesto, feedback, decisoes, evidencias e metricas. PDFs, imagens, memorias,
conversas, segredos e caminhos absolutos ficam de fora. Artefatos permanecem locais em
`data/calibration/` e nao sao versionados.

## F6.1 - Recuperacao segura concluida

A F6.1 adicionou journal de operacoes, escrita atomica, diagnosticos tipados, snapshots seguros
de migration e o formato local `truss-backup-v0.1`. Backup e restore permanecem deliberadamente
na CLI; a interface mostra apenas falhas e operacoes que podem ser retomadas com seguranca.

```powershell
$env:PYTHONPATH="apps/api"
.venv\Scripts\python -m truss_api.recovery.cli diagnose --deep
.venv\Scripts\python -m truss_api.recovery.cli backup-create
.venv\Scripts\python -m truss_api.recovery.cli backup-verify <archive>
.venv\Scripts\python -m truss_api.recovery.cli restore <archive> --target <novo-diretorio>
.venv\Scripts\python -m truss_api.recovery.cli source-unavailable <document-id> --reason-code <codigo> --note <nota>
.venv\Scripts\python -m truss_api.recovery.cli source-restored <document-id>
```

Restore nunca sobrescreve o `data` ativo e recusa destino existente. O archive contem PDFs e nao
e criptografado.

Quatro fontes historicas que nunca vieram para este clone foram declaradas indisponiveis por
eventos append-only, sem apagar revisoes, findings ou feedback. Essa declaracao nao simula o PDF:
diagnostico e viewer exibem `SOURCE_UNAVAILABLE`, e uma restauracao futura so e aceita se os bytes
possuirem o hash historico exato. As duas versoes atuais fornecidas foram importadas como novas
revisoes imutaveis `REV-005` e `REV-006`.

O backup real `backups/truss-20260902T144559Z-b03ef121.zip` foi criado e verificado, e o drill
ponto-no-tempo confirmou que uma revisao posterior ao snapshot nao aparece no restore. O gate
final passou com 264 testes backend, 1 ignorado, 51 testes web, lint, typecheck, build e verificacao
manual das revisoes atual e historica. Use `http://localhost:3000` no desenvolvimento local; o
host `127.0.0.1` pode ser recusado pelo controle de origem dos recursos internos do Next.js dev.

## Requisitos locais

- Node.js 20 ou superior
- npm 10 ou superior
- Python 3.11 ou superior

## Instalacao

```bash
npm install
python -m venv .venv
.venv\Scripts\python -m pip install -r apps/api/requirements-dev.txt
```

## Execucao

Em dois terminais:

```bash
npm run dev:web
```

```bash
.venv\Scripts\python -m uvicorn truss_api.main:app --reload --app-dir apps/api
```

Ou, depois de instalar as dependencias Python no ambiente ativo:

```bash
npm run dev
```

Servicos padrao:

- Web: `http://localhost:3000`
- API: `http://localhost:8000`
- Health check: `http://localhost:8000/health`

## Uso rapido

Abra a web e arraste um PDF estrutural para a area principal. O Truss cria projeto e revisao automaticamente quando necessario, importa o PDF, separa as folhas e executa as verificacoes deterministicas iniciais. Os formularios manuais continuam disponiveis para quando voce quiser controlar nomes, revisoes e contexto.

## Validacao

```bash
npm run lint
npm run typecheck
npm run test:web
.venv\Scripts\python -m pytest apps/api/tests
```
