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

## Validacao

```bash
npm run lint
npm run typecheck
npm run test:web
.venv\Scripts\python -m pytest apps/api/tests
```
