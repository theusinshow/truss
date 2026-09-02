# Roadmap do Truss Agent

Atualizado em: 2026-09-02

Este documento e o mapa de continuidade do produto. Cada fase deve receber plano proprio,
implementacao, testes automatizados e verificacao manual antes da fase seguinte. Registrar uma
fase aqui nao autoriza mudanca arquitetural nem o avanco de varios milestones em conjunto.

## Estado atual

| Fase | Estado | Evidencia principal | Pendencia para encerrar o programa da fase |
|---|---|---|---|
| F1 - Sheet Map base | implementada | migrations, geometria vetorial, regioes, carimbo e classificacao | preservar a calibracao no acervo real |
| F2 - Vistas e checklist | implementada | vistas com escala e regras deterministicas localizadas | ampliar ground truth positivo para medir precisao e cobertura |
| F3 - Cruzamento entre folhas | concluida e validada | registry por revisao, continuidade e secoes de pilares | nenhuma no escopo aprovado |
| F4 - Visao por crops | concluida e validada | triagem multimodal, cache por conteudo e teto de custo | nenhuma no escopo aprovado |
| F5 - Aprendizado explicito | concluida e validada | F5.1: preferencias; F5.2: propostas; F5.3: corpus versionado, runs imutaveis e export auditavel | nenhuma no escopo aprovado |
| F6 - Solidez diaria | em andamento | F6.1 concluida: recovery verificavel, fontes historicas explicitas e drill real | F6.2: 84 folhas reais + fixture de falha isolada do inicio ao fim |

## Sequencia de continuidade

### F5.2 - Central de preferencias e propostas

Status: concluida e validada em 2026-09-01.

Objetivo: tornar todas as decisoes aprendidas inspecionaveis sem transformar o produto em um
painel administrativo generico.

- listar preferencias ativas e revogadas com regra, tipo de prancha, motivo e achado de origem;
- permitir filtrar, localizar a evidencia no PDF e revogar a decisao;
- acumular confirmacoes, rejeicoes e achados manuais por chaves estaveis;
- somente propor uma decisao ao atingir evidencia definida; nunca ativar automaticamente;
- testar persistencia, escopo, duplicidade, revogacao e regressao do viewer.

Criterio de aceite: o proprietario consegue explicar, localizar e desfazer qualquer comportamento
aprendido, e nenhuma preferencia nasce sem aprovacao explicita.

### F5.3 - Calibracao deterministica pelo acervo aprovado

Status: concluida e validada em 2026-09-02.

Objetivo: usar projetos aprovados para medir e propor melhorias do checklist sem fine-tuning.

- definir o contrato de acervo aprovado e sua separacao de memoria explicita e dataset;
- reconstruir Sheet Maps com pipeline versionado e medir frequencias por tipo de prancha;
- produzir propostas de item de checklist, com amostras e contraexemplos;
- revisar e aprovar cada proposta antes de alterar regras versionadas;
- exportar os sinais de feedback em formato auditavel e portavel;
- medir queda de falso-positivo entre revisoes sem esconder findings brutos.

Criterio de aceite: um apontamento rejeitado e aprovado como preferencia nao volta por padrao, e
as metricas demonstram reducao de falso-positivo sem perda silenciosa de cobertura.

Resultado real: o manifesto reuniu 13 PDFs e 259 paginas; o pipeline produziu 1.626 avaliacoes,
140 findings brutos, zero suprimidos e 140 efetivos na ausencia de preferencias ativas. As
frequencias registraram 259 Sheet Maps, 721 views e 2.557 elementos de pilar. Duas propostas de
ruido atingiram a politica `corpus-calibration-policy-v0.1`, sem alterar rule packs. O replay
identico reutilizou `analysis_key` e `run_key` sem reprocessar PDFs.

### F6.1 - Recuperacao e operacao segura

Objetivo: proteger o uso local cotidiano.

Status: concluida e validada em 2026-09-02.

- backup e restauracao verificavel do SQLite e dos arquivos locais;
- reconstituicao dos documentos arquiteturais ainda ausentes;
- diagnostico claro para PDF corrompido, falha de render, disco e migracao;
- retomada idempotente de processamento interrompido;
- teste de recuperacao sem sobrescrever revisoes ou PDFs anteriores.

Resultado real: o clone recebido continha metadados de quatro PDFs historicos sem os respectivos
bytes. Com aprovacao do proprietario, as ausencias foram registradas como `SOURCE_UNAVAILABLE` em
eventos append-only; revisoes, findings e feedback foram preservados. As duas fontes atuais foram
importadas como `REV-005` e `REV-006`, sem substituir o historico. O backup real foi verificado e o
drill em duas restauracoes confirmou integridade, hashes e isolamento ponto-no-tempo. Diagnostico
e viewer continuam mostrando a indisponibilidade historica de forma explicita.

### F6.2 - Lote e observabilidade local

Objetivo: processar uma revisao real grande com progresso e falhas isoladas.

- fila local de folhas com estados, progresso e cancelamento seguro;
- limites de concorrencia, custo e chamadas por revisao;
- retry apenas para operacoes seguras e cacheadas;
- resumo final com folhas concluidas, ignoradas e com erro;
- passada completa nas 84 folhas reais disponiveis e execucao separada de uma fixture de falha.

Criterio de aceite da F6: as 84 folhas estruturais reais disponiveis percorrem importacao,
Sheet Map, auditoria, feedback e reabertura sem perda de dados; uma fixture separada comprova o
isolamento e a explicacao de falha sem ser contabilizada como folha real.

## Depois da V0.1

F7 permanece apenas candidata: comparacao grafica entre revisoes imutaveis. Ela exige analise,
proposta e aprovacao explicita antes de entrar em planejamento. SaaS, multiusuario, autenticacao,
cobranca, 3D decorativo e fine-tuning continuam fora do escopo.

## Proximo passo

A proposta arquitetural da F6.2 esta em
[`docs/superpowers/plans/2026-09-02-f62-batch-observability.md`](superpowers/plans/2026-09-02-f62-batch-observability.md).
Como esse passo introduz novos contratos operacionais, a implementacao aguarda aprovacao
explicita; nenhum worker ou fila foi antecipado pela F6.1. O proprietario aprovou usar as 84
paginas reais atualmente disponiveis e uma fixture separada de falha isolada no gate final.
