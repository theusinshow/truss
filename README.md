# Truss Agent

Aplicativo pessoal de revisao grafica de projetos estruturais.

O Truss Agent nasce como um laboratorio de uso diario para revisao de pranchas estruturais em PDF, com foco inicial em formas, locacao, cortes, detalhamentos, legibilidade, cotas, titulos, escalas, tabelas e coerencia grafica. O objetivo e funcionar como um segundo desenhista tecnico: ele analisa, marca regioes suspeitas, permite confirmar ou rejeitar achados, faz perguntas para aprender padroes e mantem historico por projeto e revisao.

Este repositorio deve ser implementado de forma incremental, seguindo `AGENTS.md` e os documentos em `docs/`.

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
