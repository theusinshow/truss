# F5.1 - Preferencias explicitas de regras

Data: 2026-09-01

Status: concluido e validado em 2026-09-01

Escopo: transformar rejeicoes rastreaveis em supressoes explicitas, visiveis e revogaveis por tipo de prancha

## Resultado pretendido

Uma rejeicao continua sendo apenas feedback sobre um finding. Quando o finding automatico possui
`rule_id` e tipo de prancha verificavel, o Truss oferece uma proposta separada. Somente a aprovacao
do proprietario cria a preferencia. Auditorias seguintes preservam o finding bruto, mas o viewer o
recolhe como silenciado por padrao.

## Contrato aprovado

- rejeitar nunca cria preferencia automaticamente;
- o primeiro slice aceita somente `scope: sheet_type` e `action: suppress`;
- a preferencia usa a chave estavel `(sheet_type, rule_id)`;
- achado manual, regra ausente ou folha nao classificada nao pode generalizar;
- supressao nao altera nem apaga findings ou audit runs;
- findings suprimidos continuam consultaveis com origem, bbox, evidencia e feedback;
- revogacao grava `revoked_at`, sem apagar a decisao anterior;
- uma preferencia ativa vale para todas as folhas do mesmo tipo no ambiente local;
- nenhuma IA ou chamada de rede participa do aprendizado.

## Pipeline

```text
finding automatico rejeitado + justificativa
  -> proposta inline
  -> aprovacao explicita
  -> rule_preferences(sheet_type, rule_id, suppress)
  -> anotacao derivada dos findings
  -> silenciados recolhidos no viewer
  -> revogacao explicita restaura exibicao
```

## Criterios de aceite

- [x] migration cria `rule_preferences` sem alterar findings historicos;
- [x] rejeicao isolada permanece visivel e nao cria preferencia;
- [x] somente finding automatico rejeitado, com `rule_id`, e elegivel;
- [x] preferencia ativa se aplica a outra folha do mesmo tipo;
- [x] audit run em cache reflete a preferencia atual;
- [x] supressao e derivada e nao apaga o finding;
- [x] revogacao preserva historico e restaura o finding;
- [x] viewer mostra proposta, silenciados e acao de reativacao;
- [x] fluxo manual, testes completos, lint, typecheck e build ficam verdes;
- [x] documentacao registra limites e decisoes.

## Fora do escopo

- ativar preferencia automaticamente por contagem de rejeicoes;
- escopos `global` ou `project`;
- downgrade de severidade;
- promover achado manual a regra;
- minerar acervo aprovado;
- perguntas proativas do Truss;
- implementar F5.2 ou F6.

## Evidencia de fechamento

- fluxo manual em banco temporario: proposta, supressao, contador, auditoria e revogacao;
- API: `223 passed, 1 skipped`;
- web: `8` arquivos e `42` testes aprovados;
- ESLint, TypeScript, build Next.js e `git diff --check` aprovados;
- migration `007` aplicada ao banco local, preservando findings e audit runs existentes.
