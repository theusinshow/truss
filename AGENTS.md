# AGENTS.md - Truss Agent

## Missao do repositorio

Construir o Truss Agent como aplicativo pessoal de revisao grafica de projetos estruturais. Nao transformar o projeto em SaaS, chatbot generico ou sistema multiusuario sem decisao explicita do proprietario.

## Como trabalhar

Antes de alterar arquitetura relevante:

1. leia `README.md`;
2. leia `docs/00-PROJECT-CONTEXT.md`;
3. leia `docs/06-TECH-ARCHITECTURE.md`;
4. leia `docs/14-ROADMAP.md`;
5. identifique o milestone atual;
6. implemente somente o necessario para satisfazer os criterios de aceite daquele milestone;
7. rode testes antes de avancar.

## Autonomia permitida

O agente pode:

- criar arquivos e pastas coerentes com a arquitetura;
- refatorar internamente sem mudar contratos publicos;
- criar e melhorar testes;
- instalar dependencias justificadas;
- executar migracoes locais;
- rodar servicos locais;
- criar utilitarios de desenvolvimento;
- corrigir bugs encontrados durante o milestone;
- usar subagentes quando isso reduzir risco ou acelerar tarefas independentes.

Um agente principal deve continuar responsavel pela integracao final.

## Decisoes que nao podem ser alteradas sem aprovacao

Nao alterar sozinho:

- Next.js como frontend;
- FastAPI/Python como backend local de analise e registro;
- SQLite como banco inicial;
- armazenamento dos PDFs e renders no disco local;
- abstracao de AI Provider;
- revisao imutavel;
- sistema de achados com localizacao grafica;
- protocolo de auditoria;
- classificacao de achados;
- separacao entre memoria explicita e dataset;
- foco em PDF na V0.1;
- escopo pessoal/local do produto;
- design system principal;
- estrutura central de dados.

Mudancas arquiteturais grandes devem seguir:

```text
analisar -> explicar -> propor -> aguardar aprovacao
```

## Principios tecnicos obrigatorios

### 1. PDF e a fonte principal

Nao tratar o produto como chat-first. O viewer e os achados sobre a prancha sao a experiencia principal.

### 2. Nao depender apenas de visao do LLM

Sempre que possivel, combinar:

- render visual;
- texto nativo + coordenadas;
- informacao vetorial;
- regras deterministicas;
- analise multimodal.

Aquilo que puder ser verificado deterministicamente nao deve depender exclusivamente do modelo.

### 3. Coordenadas sao dados de primeira classe

Toda regiao, texto, achado e evidencia relevante deve poder ser ligada ao sistema de coordenadas da pagina.

### 4. Revisoes sao imutaveis

Nunca sobrescrever o PDF de uma revisao anterior. Uma nova exportacao deve gerar nova revisao.

### 5. Feedback humano e dado de treinamento

Confirmar, rejeitar, justificar rejeicao e criar achado manual devem ser persistidos.

### 6. Cache por conteudo

Nao repetir chamadas de IA para a mesma entrada quando o resultado valido ja existir. Usar hash de conteudo + versao do pipeline + versao/configuracao do modelo.

### 7. Privacidade por minimizacao

Manter PDF original local. Enviar a API apenas o conteudo necessario a tarefa quando possivel: crops, renders e dados estruturados.

## UI/UX

O visual deve seguir `docs/05-DESIGN-SYSTEM.md` e `docs/12-UI-UX.md`.

Direcao:

- CAD tecnico escuro;
- identidade inspirada no design system da marca do proprietario;
- preto/grafite como base;
- vermelho como acento principal;
- Geist como tipografia de interface quando disponivel;
- JetBrains Mono para dados tecnicos, coordenadas, codigos e metadados;
- poucos arredondamentos;
- grids e divisorias bem definidos;
- motion refinado e funcional;
- evitar aparencia de dashboard SaaS generico;
- nao adicionar 3D decorativo sem funcao clara.

Antes de implementar paginas importantes, usar skills de UI/UX e motion disponiveis no ambiente quando forem relevantes.

Motion deve comunicar estado: carregamento, foco, selecao, transicao de painel, navegacao entre achados e alteracao de contexto. Respeitar `prefers-reduced-motion`.

## Regras do agente de revisao

O Truss e agressivo por padrao: deve priorizar encontrar suspeitas, mas sempre separar confianca de severidade.

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

Nunca apresentar uma hipotese como erro confirmado sem evidencia suficiente.

## Testes

Toda funcionalidade que altera persistencia, coordenadas, achados, revisoes ou cache deve possuir teste.

Nao considerar milestone concluido sem:

- testes automatizados relevantes;
- verificacao manual do fluxo principal;
- criterios de aceite atendidos;
- atualizacao da documentacao quando necessario.

## Antipadroes proibidos

- prompt monolitico responsavel por tudo;
- colocar PDF binario dentro do SQLite;
- usar nome do arquivo como significado tecnico sem validacao;
- armazenar bounding boxes apenas em pixels de render;
- esconder regras aprendidas do usuario;
- sobrescrever revisao;
- reenviar o PDF completo a API em toda pergunta;
- implementar fine-tuning na V0.1;
- criar sistema multiusuario;
- adicionar autenticacao, cobranca ou landing page;
- avancar varios milestones de uma vez sem testar o anterior.
