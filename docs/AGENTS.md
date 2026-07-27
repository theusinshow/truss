# AGENTS.md — Truss Agent

## Missão do repositório

Construir o Truss Agent como aplicativo pessoal de revisão gráfica de projetos estruturais. Não transformar o projeto em SaaS, chatbot genérico ou sistema multiusuário sem decisão explícita do proprietário.

## Como trabalhar

Antes de alterar arquitetura relevante:

1. leia `README.md`;
2. leia `docs/00-PROJECT-CONTEXT.md`;
3. leia `docs/06-TECH-ARCHITECTURE.md`;
4. leia `docs/14-ROADMAP.md`;
5. identifique o milestone atual;
6. implemente somente o necessário para satisfazer os critérios de aceite daquele milestone;
7. rode testes antes de avançar.

## Autonomia permitida

O agente pode:

- criar arquivos e pastas coerentes com a arquitetura;
- refatorar internamente sem mudar contratos públicos;
- criar e melhorar testes;
- instalar dependências justificadas;
- executar migrações locais;
- rodar serviços locais;
- criar utilitários de desenvolvimento;
- corrigir bugs encontrados durante o milestone;
- usar subagentes quando isso reduzir risco ou acelerar tarefas independentes.

Um agente principal deve continuar responsável pela integração final.

## Decisões que não podem ser alteradas sem aprovação

Não alterar sozinho:

- Next.js como frontend;
- FastAPI/Python como backend local de análise e registro;
- SQLite como banco inicial;
- armazenamento dos PDFs e renders no disco local;
- abstração de AI Provider;
- revisão imutável;
- sistema de achados com localização gráfica;
- protocolo de auditoria;
- classificação de achados;
- separação entre memória explícita e dataset;
- foco em PDF na V0.1;
- escopo pessoal/local do produto;
- design system principal;
- estrutura central de dados.

Mudanças arquiteturais grandes devem seguir:

```text
analisar → explicar → propor → aguardar aprovação
```

## Princípios técnicos obrigatórios

### 1. PDF é a fonte principal

Não tratar o produto como chat-first. O viewer e os achados sobre a prancha são a experiência principal.

### 2. Não depender apenas de visão do LLM

Sempre que possível, combinar:

- render visual;
- texto nativo + coordenadas;
- informação vetorial;
- regras determinísticas;
- análise multimodal.

Aquilo que puder ser verificado deterministicamente não deve depender exclusivamente do modelo.

### 3. Coordenadas são dados de primeira classe

Toda região, texto, achado e evidência relevante deve poder ser ligada ao sistema de coordenadas da página.

### 4. Revisões são imutáveis

Nunca sobrescrever o PDF de uma revisão anterior. Uma nova exportação deve gerar nova revisão.

### 5. Feedback humano é dado de treinamento

Confirmar, rejeitar, justificar rejeição e criar achado manual devem ser persistidos.

### 6. Cache por conteúdo

Não repetir chamadas de IA para a mesma entrada quando o resultado válido já existir. Usar hash de conteúdo + versão do pipeline + versão/configuração do modelo.

### 7. Privacidade por minimização

Manter PDF original local. Enviar à API apenas o conteúdo necessário à tarefa quando possível: crops, renders e dados estruturados.

## UI/UX

O visual deve seguir `docs/05-DESIGN-SYSTEM.md` e `docs/12-UI-UX.md`.

Direção:

- CAD técnico escuro;
- identidade inspirada no design system da marca do proprietário;
- preto/grafite como base;
- vermelho como acento principal;
- Geist como tipografia de interface quando disponível;
- JetBrains Mono para dados técnicos, coordenadas, códigos e metadados;
- poucos arredondamentos;
- grids e divisórias bem definidos;
- motion refinado e funcional;
- evitar aparência de dashboard SaaS genérico;
- não adicionar 3D decorativo sem função clara.

Antes de implementar páginas importantes, usar skills de UI/UX e motion disponíveis no ambiente quando forem relevantes.

Motion deve comunicar estado: carregamento, foco, seleção, transição de painel, navegação entre achados e alteração de contexto. Respeitar `prefers-reduced-motion`.

## Regras do agente de revisão

O Truss é agressivo por padrão: deve priorizar encontrar suspeitas, mas sempre separar confiança de severidade.

Tipos de resultado:

- INCONSISTENCY
- ATTENTION_POINT
- MISSING_INFORMATION
- NOT_VERIFIABLE

Severidade:

- LOW
- MEDIUM
- HIGH
- CRITICAL

Nunca apresentar uma hipótese como erro confirmado sem evidência suficiente.

## Testes

Toda funcionalidade que altera persistência, coordenadas, achados, revisões ou cache deve possuir teste.

Não considerar milestone concluído sem:

- testes automatizados relevantes;
- verificação manual do fluxo principal;
- critérios de aceite atendidos;
- atualização da documentação quando necessário.

## Antipadrões proibidos

- prompt monolítico responsável por tudo;
- colocar PDF binário dentro do SQLite;
- usar nome do arquivo como significado técnico sem validação;
- armazenar bounding boxes apenas em pixels de render;
- esconder regras aprendidas do usuário;
- sobrescrever revisão;
- reenviar o PDF completo à API em toda pergunta;
- implementar fine-tuning na V0.1;
- criar sistema multiusuário;
- adicionar autenticação, cobrança ou landing page;
- avançar vários milestones de uma vez sem testar o anterior.
