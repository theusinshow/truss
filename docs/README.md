# Truss Agent

Aplicativo pessoal de revisão gráfica de projetos estruturais.

O Truss Agent nasce como um laboratório de uso diário para revisão de pranchas estruturais em PDF, com foco inicial em formas, locação, cortes, detalhamentos, legibilidade, cotas, títulos, escalas, tabelas e coerência gráfica. O objetivo é funcionar como um segundo desenhista técnico: ele analisa, marca regiões suspeitas, permite confirmar ou rejeitar achados, faz perguntas para aprender padrões e mantém histórico por projeto e revisão.

Este repositório deve ser implementado de forma incremental, seguindo `AGENTS.md` e os documentos em `docs/`.

## Princípio central

O PDF é o protagonista. O chat é uma ferramenta complementar.

Fluxo principal:

```text
Projeto
  ↓
Revisão imutável
  ↓
PDF
  ↓
Extração visual + textual + vetorial
  ↓
Sheet Map
  ↓
Auditoria
  ↓
Achados localizados no canvas
  ↓
Validação humana
  ↓
Memória + dataset
```

## Stack alvo

- Web: Next.js + TypeScript
- UI: Tailwind CSS + componentes acessíveis
- Motion: biblioteca de motion para React, usada com propósito e respeitando reduced motion
- Backend local: FastAPI + Python
- PDF: PyMuPDF como base de parsing/renderização
- Banco: SQLite
- Arquivos pesados: disco local
- IA: provider abstrato; primeira implementação com OpenAI

## V0.1 concluída quando

É possível criar um projeto, importar um PDF estrutural real com uma ou várias pranchas, separar e interpretar as folhas, abrir uma prancha no viewer, executar auditoria gráfica agressiva, visualizar achados diretamente sobre a região correspondente, navegar entre eles, confirmar/rejeitar cada apontamento, adicionar achado manual, responder perguntas do Truss e manter todo o estado salvo localmente.

## M1 - Projects + SQLite

M1 adiciona a primeira persistência local:

- banco SQLite em `data/db/truss.sqlite`;
- tabelas `projects` e `revisions`;
- revisões imutáveis com código único por projeto;
- API local para listar/criar projetos, consultar projeto e criar revisões;
- tela inicial conectada ao backend para gerenciar projetos e revisões.

As rotas FastAPI recebem `Settings` por dependência para permitir testes com banco temporário sem tocar no estado local real.

## M2/M3 - PDF import + viewer inicial

O fluxo visual inicial permite:

- importar PDF real para uma revisão imutável;
- calcular hash SHA-256 do conteúdo;
- copiar o arquivo para `data/originals/{project}/{revision}/`;
- registrar `documents` e `sheets` no SQLite;
- extrair quantidade de páginas, dimensões em pontos PDF e rotação;
- renderizar folha sob demanda para PNG em `data/renders/`;
- visualizar folhas no frontend com navegação, zoom, fit e pan por arrasto.

O contrato de coordenadas inicial usa pontos PDF (`pt`) como sistema canônico. Pixels de render são derivados e não substituem as coordenadas da página.
