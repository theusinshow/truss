# START CODEX - Primeiro prompt

Cole o texto abaixo no Codex a partir da raiz do repositorio do Truss Agent.

```text
Estamos iniciando o Truss Agent, um aplicativo pessoal de revisao grafica de projetos estruturais em PDF.

A documentacao de arquitetura e produto ja esta definida e e a fonte de verdade deste projeto.

Antes de escrever qualquer codigo:

1. Leia AGENTS.md integralmente.
2. Leia README.md.
3. Leia todos os arquivos em docs/.
4. De atencao especial a:
   - docs/00-PROJECT-CONTEXT.md
   - docs/02-MVP-SCOPE.md
   - docs/04-DRAWING-REVIEW-PROTOCOL.md
   - docs/05-DESIGN-SYSTEM.md
   - docs/06-TECH-ARCHITECTURE.md
   - docs/07-PDF-PROCESSING.md
   - docs/08-AI-ARCHITECTURE.md
   - docs/09-DATA-MODEL.md
   - docs/14-ROADMAP.md
5. Verifique quais skills estao disponiveis no ambiente. Use skills relevantes de UI/UX, design systems, motion, acessibilidade, Next.js, Python/FastAPI e testes quando elas realmente ajudarem.

Nao implemente o produto inteiro.

O milestone inicial e exclusivamente M0 - Bootstrap, conforme docs/14-ROADMAP.md.

Antes de implementar M0, responda com um plano objetivo contendo:
- arquitetura inicial que sera criada;
- estrutura de diretorios;
- dependencias propostas e justificativa;
- estrategia para iniciar web + backend localmente;
- testes previstos;
- criterios de aceite do M0;
- qualquer decisao que entre em conflito ou nao esteja coberta pela documentacao.

Nao altere decisoes arquiteturais definidas no AGENTS.md sem aprovacao.

Depois do plano, aguarde minha aprovacao antes de implementar.
```

## Depois que o plano for aprovado

```text
Plano aprovado. Implemente somente o M0.

Siga AGENTS.md e docs/14-ROADMAP.md.
Execute os testes e valide todos os criterios de aceite.
No final informe:
1. o que foi criado;
2. como executar;
3. testes executados;
4. criterios de aceite atendidos;
5. limitacoes/dividas tecnicas;
6. arquivos principais.

Nao avance para M1.
```
