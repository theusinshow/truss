# F3.3 - Secoes explicitas de pilares entre niveis

Data: 2026-09-01  
Status: proposta aguardando aprovacao  
Escopo: terceiro slice de F3, limitado a secoes textuais `a x b` associadas a pilares observados

## Resultado pretendido

Ao revisar duas forms views ja pareadas pela F3.2, o Truss deve mostrar quando o mesmo codigo de
pilar possui secoes explicitamente observadas diferentes. A mudanca e um ponto de atencao para
revisao humana, nao uma inconsistencia estrutural confirmada.

O slice nao tenta decidir se a reducao e correta, dimensionar o pilar ou provar que faltou uma
indicacao grafica. Ele localiza as duas evidencias, preserva os textos brutos e separa secao igual,
alterada e nao verificavel.

## Base preservada

- PDF e Sheet Map continuam como fontes principais;
- bboxes permanecem em pontos PDF;
- revisoes e snapshots continuam imutaveis;
- o registry permanece derivado por revisao;
- os pares de niveis continuam sendo exclusivamente os gates seguros da F3.2;
- nenhuma unidade e inventada ou convertida;
- achado automatico permanece hipotese pendente;
- nao ha mudanca de Next.js, FastAPI, SQLite, armazenamento local ou estrutura central de dados.

O levantamento que fundamenta esta proposta esta em
`calibration/human-review/f3-pillar-sections-discovery-2026-09-01.md`.

## Evidencia observada

Nos 13 PDFs / 259 paginas, seis documentos possuem codigos e secoes em texto nativo utilizavel.
Foram observados 2.316 spans de codigo e 2.280 spans `a x b`, mas nenhum codigo e secao apareceu
no mesmo span/linha logica. A associacao e espacial.

Uma leitura exploratoria a ate 3 pt encontrou 485 candidatos; 23 ocorrencias tinham mais de uma
dimensao a ate 10 pt. Nos pares seguros atuais, 18 comparacoes ficaram iguais, 18 alteradas e 66
sem duas secoes univocas. Os 18 casos alterados ainda nao sao gabarito humano.

Exemplos:

- projeto-base, `P27: 20x40 -> 20x20`, nivel `680 -> 780`;
- projeto-base, seis reducoes entre `-04 -> 338`;
- R02, onze mudancas principalmente de `20x30 -> 14x30`;
- Rancho Queimado, cinco secoes resolvidas sem mudanca.

Isso demonstra valor para uma verificacao, mas tambem demonstra que `secao mudou = erro` seria uma
regra incorreta.

## Decisoes propostas

### 1. Secao e atributo coordenado da ocorrencia

Nao sera criada tabela nem coluna. Quando houver associacao segura, a ocorrencia de pilar recebe
em `attributes_json`:

```text
section_raw: texto integral preservado
section_a_raw: primeiro valor textual
section_b_raw: segundo valor textual
section_signature: par numerico sem unidade, ordenado apenas para comparar tamanho
section_ordered_signature: par na ordem impressa
section_unit_raw: unidade explicita local ou null
section_provenance: adjacent-label | table-row
section_confidence: 0..1
section_bbox_pt: bbox do texto da secao em pontos PDF
```

`section_signature` nao afirma unidade. Ela so permite comparar duas notacoes coerentes dentro do
mesmo par de views. `section_raw` e `section_ordered_signature` impedem perder a orientacao
impressa.

### 2. A associacao e espacial e precisa de gabarito

O extrator candidato `native-text/pillar-section-v1` aceita inicialmente apenas dois numeros
positivos separados por `x`, `X` ou `×`. Notacoes com `/`, tres numeros, diametro, armadura ou
tokens residuais nao entram.

A secao so pode ser ligada ao pilar quando:

1. codigo e dimensao pertencem a mesma pagina e a mesma view;
2. a distancia e direcao entre bboxes atendem um limiar medido;
3. existe um unico codigo estrutural compativel mais proximo;
4. um codigo de viga ou outro elemento nao disputa a dimensao;
5. repeticoes do mesmo codigo na view concordam ou ficam explicitamente ambiguas.

O valor de distancia nao sera fixado pelos 3 pt exploratorios. A Task 1 cria gabarito positivo e
negativo e mede um limiar. Se nao houver separacao segura, o release fica restrito a linhas de
tabela verificaveis ou a associacoes confirmadas pelo usuario.

### 3. Unidade e ordem nao sao completadas

`20x40 cm` preserva `cm`. Um `20x40` sem unidade local continua sem unidade. Um cabecalho `(cm)`
so pode fornecer contexto se a linha/coluna da tabela for detectada de forma deterministica.

Nao existe conversao para metros ou centimetros. Duas secoes so sao comparadas quando a familia de
notacao e o contexto de unidade sao compativeis. `14x30` e `30x14` possuem o mesmo tamanho de
secao para este slice, mas a inversao de orientacao fica registrada e nao e verificada.

### 4. A regra informa mudanca, nao condena o projeto

Nova regra proposta: `cross_sheet.pillar_section_transition`.

| evidencia | resultado |
|---|---|
| mesmo codigo observado nos dois niveis e mesma assinatura | `PASS` |
| mesmo codigo observado nos dois niveis e assinatura diferente | `FAIL` tecnico que gera `ATTENTION_POINT` |
| secao ausente, ambigua ou unidade incompativel em qualquer ponta | `UNKNOWN` |
| folha sem secoes associadas ou sem par seguro | `NOT_APPLICABLE` |

O `FAIL` do motor significa que a condicao de atencao foi satisfeita; nao significa erro de
engenharia. O finding tera severidade `MEDIUM`, confianca derivada das duas associacoes e texto como:

> P27 foi observado com secao 20x40 no nivel 680 e 20x20 no nivel 780. Verifique a transicao de
> secao indicada no projeto.

O finding e localizado na secao/codigo da origem e inclui ambas as bboxes, niveis, views, folhas,
textos brutos, proveniencias e `registry_hash`.

### 5. Observar o mesmo codigo nao inventa `PASSA`

A comparacao usa duas ocorrencias concretas do mesmo codigo. Ela nao grava lifecycle, nao trata
pilar sem etiqueta como `PASSA` e nao conclui nada quando o codigo ou a secao de uma ponta nao e
observavel. Contradicoes `MORRE`/`NASCE` continuam pertencendo exclusivamente a regra F3.2.

### 6. Duplicatas podem reforcar ou bloquear

Planta e tabela podem repetir o mesmo pilar dentro da mesma view:

- todas as secoes univocas iguais aumentam a confianca;
- secoes divergentes geram `UNKNOWN` para a transicao e uma ambiguidade rastreavel no registry;
- uma ocorrencia fora da view nao completa a secao de outra view;
- snapshots historicos nao entram no agrupamento atual.

### 7. Cache, versoes e viewer

Os novos atributos entram no hash do snapshot e no fingerprint do registry. A proposta reserva
`sheetmap-v0.8` e `audit-v0.5`; nenhuma versao sobe antes de o gate humano ser aprovado.

O viewer existente ganha, no maximo:

- `Elemento P27 / 20x40 -> 20x20` em mono;
- niveis e folhas das duas pontas;
- aviso de hipotese;
- evidencia bruta e unidade declarada/ausente.

Nao sera criada uma pagina de dashboard nem navegacao automatica para o alvo neste slice.

## Implementacao proposta

### Task 1 - Gabarito espacial de secoes

Criar um exportador somente leitura e revisar no viewer:

- todos os 18 candidatos de mudanca preliminar;
- pelo menos 20 associacoes iguais;
- pelo menos 20 negativos proximos a vigas, lajes, blocos ou outra linha de tabela;
- todos os 23 casos com multiplas dimensoes a ate 10 pt;
- exemplos de etiqueta de planta, tabela com `cm`, tabela com cabecalho `(cm)` e unidade ausente.

Saidas:

- `calibration/human-review/f3-pillar-sections-ground-truth.yml`;
- `calibration/human-review/f3-pillar-sections-review.md`.

Gate: nenhuma associacao automatica entra no Sheet Map antes de positivos e negativos separarem
um contrato espacial reproduzivel. Se nao separarem, voltar ao proprietario com o recorte seguro.

### Task 2 - Extrator coordenado

Adicionar funcoes puras para reconhecer tokens de secao e associar bbox a uma ocorrencia de pilar.
Casos obrigatorios:

- `P1` vizinho de `40x40 cm`;
- `P1(MORRE)` vizinho de `20x50`;
- `V300 20x60` nao associado ao pilar proximo;
- `B8/30/100`, `1/2`, datas e escalas rejeitados;
- duas dimensoes concorrentes produzem ambiguidade;
- duplicatas concordantes e divergentes;
- coordenadas preservadas em pontos PDF.

Arquivos principais:

- `apps/api/truss_api/sheetmap/elements/pillars.py`;
- novo `apps/api/truss_api/sheetmap/elements/sections.py`;
- `apps/api/tests/test_element_extraction.py`;
- novo `apps/api/tests/test_pillar_section_extraction.py`.

### Task 3 - Registry de secoes por view

Enriquecer as ocorrencias derivadas sem tabela materializada. Resolver uma secao por
`view_id + code` como unica, reforcada ou ambigua.

Testar isolamento por documento, revisao, snapshot e view; unidade incompativel; ordem invertida;
duplicatas; fingerprint; e ausencia de associacao cruzada entre plantas da mesma folha.

### Task 4 - Regra de transicao

Adicionar a regra ao pack geral de formas e cobrir:

- secao igual: `PASS`;
- secao diferente: finding `ATTENTION_POINT/MEDIUM`;
- ordem invertida: mesmo tamanho, orientacao nao verificada;
- secao ausente/ambigua/unidade incompativel: `UNKNOWN`;
- sem par ou sem secoes: `NOT_APPLICABLE`;
- `MORRE`, `NASCE` e pilar ausente continuam sob F3.2;
- estruturas independentes nunca sao comparadas.

### Task 5 - Cache e persistencia

O dedupe inclui regra, codigo, view/level de origem e assinaturas. Alterar secao no snapshot alvo
invalida o cache sem apagar findings ou feedback historicos.

### Task 6 - Viewer

Aplicar a skill de UI/UX antes da alteracao. Mostrar a transicao de forma compacta, preservar o
foco na bbox fonte, permitir evidencia longa e manter reduced motion.

### Task 7 - Medicao real

Reprocessar os 13 PDFs em bancos descartaveis e registrar:

- secoes candidatas, associadas e ambiguas por documento;
- proveniencia `adjacent-label` versus `table-row`;
- `PASS`, `FAIL`, `UNKNOWN` e `NOT_APPLICABLE`;
- todos os pontos de atencao para revisao humana;
- tempo e tamanho dos artefatos.

Nenhum candidato aprovado/rejeitado sera usado como allowlist ou supressao automatica.

## Criterios de aceite

- [ ] o gabarito separa associacoes de pilar, viga, tabela e outros elementos;
- [ ] nenhum limiar espacial e escolhido sem medicao positiva e negativa;
- [ ] texto, ordem, unidade e bbox brutos sao preservados;
- [ ] unidade ausente nunca e completada por convencao;
- [ ] `14x30` e `30x14` preservam ordem e nao viram mudanca de tamanho neste slice;
- [ ] duplicatas divergentes produzem `UNKNOWN`;
- [ ] somente ocorrencias concretas nas duas pontas sao comparadas;
- [ ] nenhum pilar e classificado como `PASSA` por exclusao;
- [ ] mudanca gera `ATTENTION_POINT/MEDIUM`, nunca erro estrutural confirmado;
- [ ] findings possuem codigo, secoes, niveis, views, bboxes, proveniencia e `registry_hash`;
- [ ] cache invalida com nova secao sem apagar feedback historico;
- [ ] os 18 candidatos preliminares sao revisados antes da medicao de release;
- [ ] testes API/web, lint e typecheck ficam verdes;
- [ ] pelo menos uma transicao real igual e uma alterada sao verificadas no viewer.

## Fora do escopo

- calcular ou validar capacidade resistente;
- afirmar que reducao/aumento de secao esta correto ou errado;
- verificar orientacao geometrica do pilar;
- inferir unidade;
- OCR ou visao multimodal;
- reconhecer contorno vetorial do pilar;
- detectar mudanca sem texto `a x b`;
- comparar revisoes diferentes;
- continuidade de vigas, lajes, blocos ou estacas;
- criar tabela materializada de secoes;
- implementar F4, F5 ou F6.

## Gate de aprovacao

A implementacao depende da aprovacao explicita destas restricoes:

1. mudanca de secao gera `ATTENTION_POINT` de severidade `MEDIUM`, nao inconsistencia confirmada;
2. ausencia ou ambiguidade de secao gera `UNKNOWN`, nunca mudanca presumida;
3. `14x30` e `30x14` sao o mesmo tamanho neste slice; orientacao fica fora do escopo;
4. associacao espacial so entra se o gabarito separar positivos e negativos com seguranca;
5. nenhum valor sem unidade sera convertido ou exibido como centimetro por convencao.

Se o gabarito exigir identidade estrutural nova, normalizacao de unidade ou mudanca na estrutura
central de dados, o fluxo volta a:

```text
analisar -> explicar -> propor -> aguardar aprovacao
```
