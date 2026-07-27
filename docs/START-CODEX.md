# START CODEX — Primeiro prompt

Cole o texto abaixo no Codex a partir da raiz do repositório do Truss Agent.

```text
Estamos iniciando o Truss Agent, um aplicativo pessoal de revisão gráfica de projetos estruturais em PDF.

A documentação de arquitetura e produto já está definida e é a fonte de verdade deste projeto.

Antes de escrever qualquer código:

1. Leia AGENTS.md integralmente.
2. Leia README.md.
3. Leia todos os arquivos em docs/.
4. Dê atenção especial a:
   - docs/00-PROJECT-CONTEXT.md
   - docs/02-MVP-SCOPE.md
   - docs/04-DRAWING-REVIEW-PROTOCOL.md
   - docs/05-DESIGN-SYSTEM.md
   - docs/06-TECH-ARCHITECTURE.md
   - docs/07-PDF-PROCESSING.md
   - docs/08-AI-ARCHITECTURE.md
   - docs/09-DATA-MODEL.md
   - docs/14-ROADMAP.md
5. Verifique quais skills estão disponíveis no ambiente. Use skills relevantes de UI/UX, design systems, motion, acessibilidade, Next.js, Python/FastAPI e testes quando elas realmente ajudarem.

Não implemente o produto inteiro.

O milestone inicial é exclusivamente M0 — Bootstrap, conforme docs/14-ROADMAP.md.

Antes de implementar M0, responda com um plano objetivo contendo:
- arquitetura inicial que será criada;
- estrutura de diretórios;
- dependências propostas e justificativa;
- estratégia para iniciar web + backend localmente;
- testes previstos;
- critérios de aceite do M0;
- qualquer decisão que entre em conflito ou não esteja coberta pela documentação.

Não altere decisões arquiteturais definidas no AGENTS.md sem aprovação.

Depois do plano, aguarde minha aprovação antes de implementar.
```

## Depois que o plano for aprovado

```text
Plano aprovado. Implemente somente o M0.

Siga AGENTS.md e docs/14-ROADMAP.md.
Execute os testes e valide todos os critérios de aceite.
No final informe:
1. o que foi criado;
2. como executar;
3. testes executados;
4. critérios de aceite atendidos;
5. limitações/dívidas técnicas;
6. arquivos principais.

Não avance para M1.
```
