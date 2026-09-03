# F7.2 - Deltas explicaveis por camada PDF

Data: 2026-09-03

Status: concluida e validada com fixture isolada

## Objetivo

Enriquecer os pares confiaveis da F7.1 com diferencas deterministicas de texto nativo e
primitivas vetoriais. Cada delta deve preservar evidencia antes/depois e bboxes em pontos PDF,
sem transformar mudanca grafica em erro de engenharia.

## Direcao visual aprovada

- manter integralmente a paleta grafite/vermelho e Geist + JetBrains Mono existentes;
- usar a direcao A do mock: filtros `Raster`, `Texto` e `Vetor` na toolbar atual;
- manter os PDFs como superficie dominante;
- mostrar a evidencia do delta selecionado no painel direito;
- preservar densidade tecnica compacta, divisorias de 1 px e raio de 4 px;
- nao copiar o shell ficticio do mock nem introduzir assets raster na interface.

## Contratos

### Unidade e imutabilidade

O `revision_comparison` continua sendo o run imutavel. Pares novos carregam status e contagens
das camadas. Deltas pertencem ao par, nao sao atualizados e nao sao apagados. Comparacoes F7.1
anteriores continuam legiveis como `not_run`.

### Extracao e cache

- abrir localmente somente as paginas ja pareadas;
- usar `extract_page` e `EXTRACTOR_VERSION` existentes para texto e vetores;
- incluir a versao do extrator e `revision-comparison-v0.2` no fingerprint;
- replay identico reutiliza o run e nao reabre os PDFs;
- fonte ausente ou falha de extracao produz estado explicito, nunca delta vazio equivalente a
  igualdade.

### Classificacao deterministica

Tipos de delta:

- `added`: existe somente na revisao-alvo;
- `removed`: existe somente na revisao-base;
- `modified`: ocupa a mesma regiao verificavel, mas conteudo ou propriedades mudaram;
- `moved`: conteudo/propriedades permanecem iguais e a bbox mudou.

Correspondencias `modified` e `moved` devem ser conservadoras e mutuamente unicas. Casos sem
evidencia suficiente permanecem como adicao/remocao de primitivas observadas. Isso descreve a
extracao, nao uma intencao tecnica.

### Limites honestos

- camadas so sao comparadas quando fontes existem e dimensoes/rotacao sao compativeis;
- cada camada persiste no maximo 500 deltas para proteger uso local;
- contagens completas sao calculadas antes do limite;
- truncamento aparece no contrato e na UI;
- nenhuma IA, OCR, alinhamento geometrico avancado ou regra de engenharia entra nesta fase.

## Persistencia aditiva

Migration `015_comparison_layer_deltas.sql`:

- adiciona `delta_status`, `delta_counts_json`, `delta_truncated` e `delta_summary` aos pares;
- cria `revision_comparison_deltas` com camada, tipo, evidencia de match, valores antes/depois,
  detalhes estruturados e bboxes base/alvo em pontos PDF;
- impede update/delete dos deltas por trigger.

## API

As rotas F7.1 permanecem. `RevisionComparison` passa a devolver, em cada par:

- `delta_status`;
- `delta_counts` totais por camada/tipo;
- `delta_truncated`;
- `delta_summary`;
- `deltas` persistidos.

## Interface

- filtros independentes `Raster`, `Texto` e `Vetor`, ativos por padrao;
- selecionar uma regiao raster ou delta foca a bbox correspondente nos canvases;
- o painel direito mostra camada, tipo, valor antes/depois, metodo e coordenadas;
- estados vazio, indisponivel, nao comparavel e truncado usam texto explicito;
- reduced motion continua removendo alternancia automatica, sem esconder controles manuais.

## Criterios de aceite

- texto e vetor cobrem igualdade, adicao, remocao, modificacao e deslocamento em fixtures;
- bboxes permanecem dentro das paginas e em pontos PDF;
- correspondencia ambigua nao e promovida silenciosamente a modificacao/deslocamento;
- fontes ausentes e geometrias diferentes nao resultam em igualdade por ausencia de deltas;
- limite preserva contagem total e sinaliza truncamento;
- replay reutiliza run/deltas sem duplicacao;
- registros novos e historicos F7.1 sao legiveis pela API;
- UI filtra camadas, foca delta e mostra evidencia antes/depois;
- testes API/web, lint, typecheck e build passam;
- verificacao manual cobre desktop, viewport estreito, estados e fluxo principal;
- README, contexto, arquitetura, decisoes e roadmap sao atualizados no fechamento.

## Sequencia

1. migration e modelos;
2. matcher textual/vetorial e testes unitarios;
3. integracao no orquestrador, cache e repository;
4. contrato TypeScript e toolbar/evidencia;
5. testes, build e verificacao visual;
6. documentacao, commit e push.

## Resultado

Implementacao concluida conforme os contratos aprovados. A fixture `R01 -> R02`, `EST-0010-A`,
produziu 3 deltas de texto e 7 vetoriais, com bboxes em pontos PDF e evidencia antes/depois. O
replay reutilizou o run imutavel; limites, fontes ausentes, geometria incompativel, duplicidade
ambigua e leitura de runs F7.1 receberam cobertura automatizada.

A verificacao visual confirmou a composicao desktop, os filtros e o painel de evidencia. Em 900 px
foi identificada compressao vertical; o shell comparativo passou a usar rolagem interna abaixo do
breakpoint desktop e foi verificado novamente. O gate permanece explicitamente sintetico porque o
acervo nao possui duas exportacoes reais relacionadas.
