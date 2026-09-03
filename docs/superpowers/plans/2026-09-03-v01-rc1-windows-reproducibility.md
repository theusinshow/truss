# V0.1-RC1 - Robustez Windows e gate reproduzivel

Status: aprovado pelo proprietario e concluido em 2026-09-03.

## Objetivo

Fechar fragilidades operacionais reveladas quando os tres PDFs de referencia passaram a estar
versionados, sem alterar arquitetura, schema, APIs publicas ou comportamento do produto.

## Escopo aprovado

1. reduzir o comprimento de nomes fisicos e temporarios usados por importacao e recovery;
2. preservar nome original, hash integral, revisoes e caminhos historicos;
3. impedir que a configuracao privada de provider altere expectativas de testes locais;
4. executar testes, verificacoes estaticas, build e o gate deterministico de 84 folhas;
5. registrar a evidencia sem alegar validacao real de comparacao entre revisoes distintas.

## Criterios de aceite

- importacao com nome longo conserva o metadado e publica o PDF atomico;
- restore usa staging curto no mesmo volume e nunca sobrescreve o destino;
- suite de API passa no Windows sem comando temporario manual;
- web tests, lint, typecheck e build passam;
- os tres PDFs versionados produzem 84 Sheet Maps e 84 auditorias;
- replay nao duplica Sheet Maps, auditorias ou findings;
- cancelamento, feedback, backup/restore e fixture de falha preservam seus invariantes.

## Resultado

Todos os criterios foram atendidos. Evidencia consolidada em
`docs/v01-rc1-gate-2026-09-03.json`.

A verificacao manual carregou a home, um projeto real, o render da prancha, achados e chat com a
API conectada e sem overlay de erro. O unico aviso do Chrome foi associado ao atributo
`cz-shortcut-listen` injetado por extensao externa antes da hidratacao.
