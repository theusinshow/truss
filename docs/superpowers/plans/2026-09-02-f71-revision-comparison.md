# F7.1 - Comparacao grafica entre revisoes

Data: 2026-09-02

Status: implementada e validada em fixture isolada; gate real pendente

Escopo: comparar duas revisoes imutaveis do mesmo projeto, parear folhas com evidencia explicita,
detectar alteracoes graficas localmente e apresenta-las no viewer sem transformar diferenca em
erro confirmado. Nao inclui IA, comparacao semantica de engenharia, alteracao automatica de
findings ou inferencia de identidade pelo nome do arquivo/numero da pagina.

## Evidencia do estado atual

- F6.2 esta concluida e validada;
- revisoes, documentos, folhas e Sheet Maps ja sao imutaveis e carregam coordenadas em pontos PDF;
- renders sao derivados locais e reconstruiveis;
- o viewer atual ja possui pan, zoom, fit e criacao de finding manual;
- as revisoes antigas de Rancho Queimado estao declaradas `SOURCE_UNAVAILABLE`;
- `REV-005` e `REV-006` possuem fontes, mas representam conjuntos graficos diferentes e nao sao
  um par confiavel antes/depois;
- o gate automatizado pode usar fixtures sinteticas, mas o fechamento do milestone exige um par
  real de revisoes relacionadas fornecido pelo proprietario.

## Resultado pretendido

O proprietario consegue:

1. escolher revisao-base e revisao-alvo do mesmo projeto;
2. entender como cada folha foi pareada e corrigir manualmente uma identidade inconclusiva;
3. navegar por folhas identicas, alteradas, adicionadas, removidas, ambiguas ou indisponiveis;
4. inspecionar antes/depois lado a lado, sobrepostos ou em alternancia com pan e zoom sincronizados;
5. selecionar uma regiao alterada em coordenadas PDF dos dois lados;
6. promover uma alteracao a finding manual na revisao-alvo;
7. reabrir a mesma comparacao sem recalcular o diff quando as entradas nao mudaram.

## Contratos aprovados

### Pareamento honesto

Ordem de autoridade:

1. pareamento manual ativo e auditavel;
2. `sheet_code` canonico exato e unico nos dois lados;
3. mesmo hash de documento e mesmo indice de pagina, apenas para replay do mesmo conteudo;
4. sem evidencia suficiente, estado `ambiguous`.

Numero da pagina, nome do arquivo, tipo global da folha ou proximidade textual nunca bastam
isoladamente para afirmar identidade. Codigo presente em somente um lado produz `added` ou
`removed`; folha sem codigo e sem decisao humana permanece ambigua.

### Comparacao deterministica local

- rasterizar as duas paginas em escala reduzida e tons de cinza apenas no backend local;
- comparar no sistema canonico da pagina, sem pedir coordenadas a modelo externo;
- agrupar pixels alterados em regioes e converter os limites novamente para pontos PDF;
- uma mudanca de formato/rotacao e uma alteracao verificavel de pagina e gera regiao de pagina
  inteira, sem fingir registro geometrico;
- fonte ausente produz `unavailable`, nao `identical` nem `changed`;
- `changed` descreve diferenca grafica, nao falha tecnica.

### Imutabilidade e cache

Cada run guarda revisoes, fingerprint das fontes/Sheet Maps/pareamentos, versao do pipeline,
contagens e pares derivados. Pares e regioes pertencem ao run e nao sao reescritos. Uma alteracao
de pareamento cria outro fingerprint e outro run; o historico anterior permanece legivel.

Pareamentos humanos preservam linhas revogadas. Revogar nao apaga a decisao anterior.

### Interface PDF-first

- modo `Comparar revisoes` no cabecalho do projeto, ao lado das ferramentas existentes;
- faixa de selecao base/alvo e resumo de cobertura, sem dashboard separado;
- lista tecnica compacta de folhas e canvas como superficie dominante;
- modos `Lado a lado`, `Sobrepor` e `Alternar`;
- vermelho marca regioes alteradas; estados usam texto e nao dependem somente de cor;
- transicoes de 120-180 ms comunicam troca de modo/folha; reduced motion remove alternancia
  animada;
- criacao de finding ocorre inline, com descricao e severidade explicitas.

## Persistencia aditiva

Migration `014_revision_comparisons.sql`:

- `revision_comparisons`: run imutavel e cacheado por `input_fingerprint`;
- `revision_comparison_pairs`: snapshot do pareamento e do resultado por folha;
- `revision_comparison_regions`: bboxes base/alvo em pontos PDF;
- `comparison_pair_overrides`: decisoes humanas preservadas com `revoked_at`.

Nenhum PDF, render ou bbox historica e sobrescrito.

## API aditiva

```text
POST   /projects/{project_id}/revision-comparisons
GET    /revision-comparisons/{comparison_id}
POST   /projects/{project_id}/comparison-pairings
DELETE /comparison-pairings/{pairing_id}
```

Criar uma comparacao identica reutiliza o run existente. Parear/revogar valida projeto, revisoes
e folhas antes de escrever.

## Criterios de aceite

- run recusado quando revisoes sao iguais ou pertencem a projetos diferentes;
- identidade automatica usa somente evidencia aprovada;
- fixture identica resulta em `identical` e zero regioes;
- fixture com alteracao localizada resulta em `changed` e bbox valida em pontos PDF;
- adicao/remocao, ambiguidade, fonte indisponivel, formato diferente e pareamento manual possuem
  testes;
- replay identico reutiliza o mesmo run sem duplicar pares/regioes;
- UI permite os tres modos, navegacao por estado, pareamento manual e promocao para finding;
- suites API/web, lint, typecheck e build passam;
- verificacao manual cobre o fluxo principal e reduced motion;
- documentacao registra limites e evidencia do gate.

## Sequencia de implementacao

1. migration, modelos e testes de persistencia/validacao;
2. matcher deterministico e fingerprint;
3. detector raster local e conversao de coordenadas;
4. rotas e cache imutavel;
5. cliente TypeScript e componente de comparacao;
6. testes de interface e verificacao no navegador;
7. gate real quando houver um par antes/depois confiavel.

## Evidencia de implementacao

- migration, repository, matcher, diff raster, orquestrador e quatro rotas aditivas implementados;
- cobertura de cache, imutabilidade, bboxes PDF, ambiguidade, adicao/remocao, fontes ausentes,
  mudanca de formato, validacao de projeto e pareamento manual;
- painel comparativo carregado sob demanda e verificado nos modos lado a lado, sobreposicao e
  alternancia, com promocao explicita de uma regiao para finding;
- fixture isolada `R01 -> R02`: uma folha `EST-0010-A`, uma regiao alterada,
  `changed_ratio=0.00115`, bbox `220,220 -> 356,260 pt`;
- suites API/web, lint, typecheck e build aprovados na data do gate;
- o gate real continua bloqueado somente pela ausencia de duas exportacoes relacionadas no acervo,
  nao por falha da implementacao.
