# Revisao humana — Plantas de formas

Status: **aguardando preenchimento pelo proprietario**

Este formulario registra o que um desenhista tecnico espera encontrar em plantas de formas.
Ele nao e uma regra ativa do Truss e nao deve ser tratado como ground truth enquanto nao estiver
preenchido e confirmado pelo proprietario.

## Como preencher

- Marque uma opcao trocando `[ ]` por `[x]`.
- Escreva respostas nos campos `Resposta:`.
- Quando uma regra depender do escritorio ou do projeto, marque-a como **preferencia pessoal**.
- Quando nao for possivel concluir apenas pelo PDF, use **nao verificavel**.
- Nao e necessario informar coordenadas. Descreva a posicao como `superior esquerdo`, `centro`,
`inferior direito` etc.; o pipeline convertera a regiao validada para pontos PDF.

## 1. Criterio geral

### 1.1 O que representa um projeto aprovado?

- [ ] Aprovado significa apenas que a prancha foi emitida.
- [x] Aprovado significa que eu revisei tecnicamente a prancha e aceito usa-la como referencia.
- [ ] Outro criterio.

Resposta:

### 1.2 Nivel de agressividade desejado

- [ ] Apontar qualquer suspeita plausivel, aceitando mais falsos positivos.
- [x] Equilibrar suspeitas e falsos positivos.
- [ ] Mostrar apenas problemas com evidencia forte.

Resposta:

### 1.3 Quando o Truss nao consegue concluir

- [x] Criar `NOT_VERIFIABLE`.
- [x] Criar `ATTENTION_POINT`.
- [ ] Nao criar finding; mostrar somente na cobertura da auditoria.
- [ ] Depende da verificacao.

Resposta:

## 2. Titulos, escalas e niveis

### 2.1 Titulo por vista

Toda planta, corte ou detalhe deve possuir titulo proprio?

- [x] Sim, sempre.
- [ ] Sim, exceto vistas auxiliares obvias.
- [ ] Nao.
- [ ] Depende do tipo de vista.

Excecoes e observacoes: AS vezes pode ocorres de por exemplo, um dealhamento de madeira ser apenas um titulo "" detalhamento de MADEIRA "" e dentro desse detalhamento ter varias vistas de det 1, 2 ,3 

### 2.2 Escala por vista

Toda view deve possuir escala propria?

- [x] Sim, sempre.
- [x] Pode compartilhar escala com um grupo de views.
- [x] `ESCALA INDICADA` e suficiente.
- [ ] Depende do tipo de view.

Quando `ESCALA INDICADA` e aceitavel?

Resposta: Quando no mesmo detalhe tem dois tipos de escal, exemplo no detalhamento de vigas, temos a viga em vista na 1:50 e a seçao ada viga na 1:25

### 2.3 Nivel da planta

Uma planta de formas deve declarar explicitamente seu nivel?

- [x] Sim, no titulo da view.
- [ ] Sim, mas pode aparecer em outra regiao claramente associada.
- [ ] Nao e obrigatorio.

Formato esperado e tolerancias: Quando tem uma planta base e topo, geralmente eu nao vejo necessiade de botar o nivel mas quando tem mais de 3 pavimentos, ou algum pavimento intermediario, é obrgatorio ter nivel, acho melhor padronizar para sempre ter.

Resposta:

### 2.4 Numeracao das views

- [x] Toda view deve ser numerada.
- [ ] Somente detalhes e cortes precisam de numero/letra.
- [ ] Numeracao e opcional.

Duplicidade de numero na mesma folha deve gerar:

- [ ] `INCONSISTENCY`.
- [x] `ATTENTION_POINT`.
- [ ] Nenhum finding.

## 3. Conteudo esperado em plantas de formas

Para cada item, marque uma classificacao:

- **O** — obrigatorio;
- **C** — condicional;
- **P** — preferencia pessoal;
- **N** — nao obrigatorio.


| Item                              | O    | C    | P    | N    | Condicao ou justificativa |
| --------------------------------- | ----: | ----: | ----: | ----: | ------------------------- |
| Carimbo legivel                   | [ x] | [ ]  | [ ]  | [ ]  |                           |
| Codigo da prancha                 | [ x] | [ ]  | [ ]  | [ ]  |                           |
| Categoria/tipo da prancha         | [ ]  | [ ]  | [ x] | [ ]  |                           |
| Titulo de cada planta             | [x ] | [ ]  | [ ]  | [ ]  |                           |
| Escala de cada planta             | [ ]  | [ ]  | [ ]  | [ x] |                           |
| Nivel de cada planta              | [ ]  | [ ]  | [ x] | [ ]  |                           |
| Eixos identificados               | [ x] | [ ]  | [ ]  | [ ]  |                           |
| Cotas gerais                      | [x ] | [ ]  | [ ]  | [ ]  |                           |
| Cotas parciais                    | [ x] | [ ]  | [ ]  | [ ]  |                           |
| Pilares identificados             | [x ] | [ ]  | [ ]  | [ ]  |                           |
| Vigas identificadas               | [ x] | [ ]  | [ ]  | [ ]  |                           |
| Lajes identificadas               | [ x] | [ ]  | [ ]  | [ ]  |                           |
| Espessura/altura das lajes        | [x ] | [ ]  | [ ]  | [ ]  |                           |
| Elevacoes/rebaixos                | [x ] | [ ]  | [ ]  | [ ]  |                           |
| Aberturas, vazios e descidas      | [x ] | [ ]  | [ ]  | [ ]  |                           |
| Indicacoes de cortes              | [ x] | [ ]  | [ ]  | [ ]  |                           |
| Detalhes construtivos necessarios | [ ]  | [ x] | [ ]  | [ ]  |                           |
| Tabela de pilares                 | [x ] | [ ]  | [ ]  | [ ]  |                           |
| Tabela de vigas                   | [x ] | [ ]  | [ ]  | [ ]  |                           |
| Tabela de lajes                   | [x ] | [ ]  | [ ]  | [ ]  |                           |
| Caracteristicas dos materiais     | [x ] | [ ]  | [ ]  | [ ]  |                           |
| Legendas de simbolos              | [x ] | [ ]  | [ ]  | [ ]  |                           |


Outros itens importantes:

Resposta:

## 4. Regras de coerencia

### 4.1 Planta versus carimbo

Se o carimbo disser `PLANTA DE FORMAS`, mas o conteudo dominante for outro:

- [x] `INCONSISTENCY`.
- [ ] `ATTENTION_POINT`.
- [ ] `NOT_VERIFIABLE`.

Severidade esperada: [ ] LOW [x] MEDIUM [ ] HIGH [ ] CRITICAL

### 4.2 Planta versus tabelas

Um elemento desenhado e ausente na tabela deve gerar finding?

- [x] Sim, sempre.
- [x] Somente quando a tabela se declarar completa.
- [ ] Nao.

Um atributo diferente entre planta e tabela deve gerar:

- [ ] `INCONSISTENCY`.
- [x] `ATTENTION_POINT`.
- [ ] `NOT_VERIFIABLE`.

Qual fonte deve ser considerada correta?

- [x] Nenhuma automaticamente; mostrar o conflito.
- [ ] A planta.
- [ ] A tabela.
- [ ] Depende do atributo.

Resposta:

### 4.3 Chamadas de corte e detalhe

Uma chamada sem vista correspondente deve gerar finding?

- [ ] Sim, mesmo que o destino possa estar em outra folha.
- [x] Sim, somente depois de procurar em toda a revisao.
- [ ] Nao.

Uma view sem chamada de origem deve gerar finding?

- [ ] Sim.
- [x] Apenas ponto de atencao.
- [ ] Nao.

### 4.4 Elementos “morre”, “passa” e mudanca de secao

Quais indicacoes sao obrigatorias e como devem ser verificadas?

Resposta: Da forma que achar melhor em 5 anos de experiencia, isso da muito pouco problema, geralmente vem bruto do software, seria bom ser confirmasse que o pilar que passa ta presente no proximo nivel e o pilar que morre morre anquela nivel e nao aprece no proximo

## 5. Severidade versus confianca

Use exemplos do seu criterio profissional.

### LOW

Problemas tipicos: Pranhca muito vazia, texto muito grande,  

Resposta:

### MEDIUM

Problemas tipicos: Texrto muito pequenos, sobreposiçao de texto, texrto inilegivel, legibilidade de texto ruim, 

Resposta:

### HIGH

Problemas tipicos: Falta de detalhamento ( ter terro, 1 andar e cobertura ter apenas detalhamento de vigas e coberutra, problema de cotas fora de escala, falta de cotas, 

Resposta:

### CRITICAL

Problemas tipicos: Prancha faltanta, tudo que tem no high também, endere;co errado de projeto, selo errado, selo cortado, etcc=

Resposta:

Quando uma suspeita de alto impacto, mas baixa certeza, deve aparecer?

Resposta:

## 6. Legibilidade e representacao

Marque o que deve gerar finding:


| Situacao                             | INCONSISTENCY | ATTENTION_POINT | NOT_VERIFIABLE | Nao apontar |
| ------------------------------------ | -------------: | ---------------: | --------------: | -----------: |
| Texto sobreposto                     | [ ]           | [x]             | [ ]            | [ ]         |
| Texto pequeno/ilegivel               | [ ]           | [x]             | [ ]            | [ ]         |
| Cota cruzando outros elementos       | [x]           | [ ]             | [ ]            | [ ]         |
| Contraste insuficiente               | []            | [x]             | [ ]            | [ ]         |
| Simbolo sem legenda                  | [x]           | [ ]             | [ ]            | [ ]         |
| View muito proxima do carimbo        | []            | [x]             | [ ]            | [ ]         |
| Informacao fora da moldura           | [x]           | [ ]             | [ ]            | [ ]         |
| Excesso de informacao sem hierarquia | [x]           | [ ]             | [ ]            | [ ]         |


Outros problemas de representacao:

Resposta:

## 7. Revisao folha por folha

Preencha uma tabela para cada folha. Adicione ou remova linhas conforme necessario.

Tipos de view sugeridos: `plan`, `section`, `detail`.

### EST-0050-A


| #   | Tipo | Titulo esperado | Escala                                             | Nivel  | Posicao aproximada | Correta?           |          |
| ---: | ----: | --------------- | -------------------------------------------------- | ------ | ------------------ | ------------------ | -------- |
| 1   | #    | Tipo            | Título esperado                                    | Escala | Nível              | Posição aproximada | Correta? |
| 2   | 1    | detail          | DETALHAMENTO FUNDAÇÕES E PILARES DE ARRANQUE (4/4) | 1:25   | vários             | folha inteira      | [x]      |
| 3   |      |                 |                                                    |        |                    | [ ]                |          |


Findings que voce faria nesta folha:


| Tipo | Severidade | Descricao | Posicao/evidencia |
| ---- | ---------- | --------- | ----------------- |
|      |            |           |                   |


Informacoes presentes que **nao** devem gerar finding:

Resposta:

Folha tecnicamente aprovada como referencia? [ ] Sim [ ] Nao [ ] Com ressalvas

Ressalvas:

### EST-0060-A


| #   | Tipo | Titulo esperado      | Escala                                         | Nivel                 | Posicao aproximada | Correta?                 |          |
| ---: | ----: | -------------------- | ---------------------------------------------- | --------------------- | ------------------ | ------------------------ | -------- |
| 1   | #    | Tipo                 | Título esperado                                | Escala                | Nível              | Posição aproximada       | Correta? |
| 2   | 1    | plan                 | PLANTA DE FORMAS - FUNDAÇÃO INFERIOR           | 1:50                  | -650               | superior esquerda        | [x]      |
| 3   | 2    | plan                 | PLANTA DE FORMAS - INTERMEDIÁRIA FUNDO PISCINA | 1:50                  | -350               | superior/centro          | [x]      |
| 4   | 3    | plan                 | PLANTA DE FORMAS - FUNDO PISCINA               | 1:50                  | -167               | direita                  | [x]      |
|     | 4    | detail / perspective | PERSPECTIVA                                    | escala representativa | —                  | inferior esquerda/centro | [x]      |


Findings que voce faria nesta folha:


| Tipo | Severidade | Descricao | Posicao/evidencia |
| ---- | ---------- | --------- | ----------------- |
|      |            |           |                   |


Informacoes presentes que **nao** devem gerar finding:**Informações presentes que não devem gerar finding:** `ESCALA REPRESENTATIVA` na perspectiva **não deve disparar “escala inválida/ausente”**. A perspectiva também não precisa possuir nível próprio. Tabelas de vigas, pilares, lajes e materiais próximas das plantas fazem parte do contexto da respectiva view e não devem virar views independentes.

Resposta:

Folha tecnicamente aprovada como referencia? [x ] Sim [ ] Nao [ ] Com ressalvas

Ressalvas:

### EST-0070-A


| #   | Tipo | Titulo esperado      | Escala                                       | Nivel                 | Posicao aproximada | Correta?                   |          |
| ---: | ----: | -------------------- | -------------------------------------------- | --------------------- | ------------------ | -------------------------- | -------- |
| 1   | #    | Tipo                 | Título esperado                              | Escala                | Nível              | Posição aproximada         | Correta? |
| 2   | 1    | plan                 | PLANTA DE FORMAS - TÉRREO                    | 1:50                  | -04                | superior/esquerda e centro | [x]      |
| 3   | 2    | detail               | DETALHE 01/02 LAJE PRÉ-FABRICADA - TRELIÇADA | 1:20                  | —                  | direita/centro             | [x]      |
|     | 3    | detail / perspective | PERSPECTIVA                                  | escala representativa | —                  | inferior direita           | [x]      |


Findings que voce faria nesta folha:


| Tipo | Severidade | Descricao | Posicao/evidencia |
| ---- | ---------- | --------- | ----------------- |
|      |            |           |                   |


Informacoes presentes que **nao** devem gerar finding:**Informações presentes que não devem gerar finding:** lajes aparecem com níveis locais/elevações diferentes (`e=-0.50`, `e=-0.07` etc.); isso não contradiz automaticamente o nível geral da planta. Elementos `MORRE`, `NASCE` e alterações de seção são semântica estrutural intencional. O detalhe da laje não precisa possuir nível.

Resposta:

Folha tecnicamente aprovada como referencia? x] Sim [ ] Nao [ ] Com ressalvas

Ressalvas:

### EST-0080-A


| #   | Tipo | Titulo esperado      | Escala                                             | Nivel                 | Posicao aproximada | Correta?           |          |
| ---: | ----: | -------------------- | -------------------------------------------------- | --------------------- | ------------------ | ------------------ | -------- |
| 1   | #    | Tipo                 | Título esperado                                    | Escala                | Nível              | Posição aproximada | Correta? |
| 2   | 1    | plan                 | PLANTA DE FORMAS - 1° PAVIMENTO                    | 1:50                  | 338                | superior esquerda  | [x]      |
| 3   | 2    | plan                 | PLANTA DE FORMAS - COBERTURA                       | 1:50                  | 680                | inferior esquerda  | [x]      |
|     | 3    | detail               | DETALHE 01/02/03/04 LAJE PRÉ-FABRICADA - TRELIÇADA | 1:20                  | —                  | centro             | [x]      |
|     | 4    | detail / perspective | PERSPECTIVA                                        | escala representativa | —                  | direita            | [x]      |


Findings que voce faria nesta folha:


| Tipo | Severidade | Descricao | Posicao/evidencia |
| ---- | ---------- | --------- | ----------------- |
|      |            |           |                   |


Informacoes presentes que **nao** devem gerar finding:a perspectiva não precisa ter escala numérica nem nível. O detalhe pode representar vários tipos (`01/02/03/04`) em uma única View. As tabelas associadas à planta superior e inferior não devem ser detectadas como Views próprias.

Resposta:

Folha tecnicamente aprovada como referencia? [x] Sim [ ] Nao [ ] Com ressalvas

Ressalvas:

### EST-0090-A


| #   | Tipo | Titulo esperado | Escala                                        | Nivel  | Posicao aproximada | Correta?           |          |
| ---: | ----: | --------------- | --------------------------------------------- | ------ | ------------------ | ------------------ | -------- |
| 1   | #    | Tipo            | Título esperado                               | Escala | Nível              | Posição aproximada | Correta? |
| 2   | 1    | plan            | PLANTA DE FORMAS - INTERMEDIÁRIA RESERVATÓRIO | 1:50   | 780                | superior esquerda  | [x]      |
| 3   | 2    | plan            | PLANTA DE FORMAS - TOPO RESERVATÓRIO          | 1:50   | 940                | superior centro    | [x]      |
|     | 3    | detail          | DETALHE 01 LAJE PRÉ-FABRICADA - TRELIÇADA     | 1:20   | —                  | superior direita   | [x]      |


Findings que voce faria nesta folha:


| Tipo | Severidade | Descricao | Posicao/evidencia |
| ---- | ---------- | --------- | ----------------- |
|      |            |           |                   |


Informacoes presentes que **nao** devem gerar finding:as duas grandes perspectivas/renderizações estruturais na metade inferior **não possuem título nem escala**, mas eu não consideraria isso erro automaticamente. Elas são representações auxiliares, não vistas técnicas que necessariamente exigem escala. Essa é uma excelente regra negativa para o Truss

Resposta:

Folha tecnicamente aprovada como referencia? [x] Sim [ ] Nao [ ] Com ressalvas

Ressalvas:

### EST-0260-A


| #   | Tipo | Titulo esperado | Escala                           | Nivel  | Posicao aproximada       | Correta?           |          |
| ---: | ----: | --------------- | -------------------------------- | ------ | ------------------------ | ------------------ | -------- |
| 1   | #    | Tipo            | Título esperado                  | Escala | Nível                    | Posição aproximada | Correta? |
| 2   | 1    | detail          | DETALHAMENTO PILARES - COBERTURA | 1:25   | 338 → 680 principalmente | folha inteira      | [x]      |
| 3   |      |                 |                                  |        |                          | [ ]                |          |


Findings que voce faria nesta folha:


| Tipo | Severidade | Descricao | Posicao/evidencia |
| ---- | ---------- | --------- | ----------------- |
|      |            |           |                   |


Informacoes presentes que **nao** devem gerar finding: `P21=P38` e `P28=P37` são agrupamentos intencionais de pilares com detalhamento equivalente; não são duplicidades. `VISTA H`, `VISTA B` e `SEÇÃO` fazem parte do detalhamento de cada pilar. Nem todos os pilares precisam constituir uma `View` de primeiro nível no Sheet Map.

Resposta:

Folha tecnicamente aprovada como referencia? [ ] Sim [ ] Nao [x] Com ressalvas

Ressalvas:

## 8. Regras pessoais do proprietario

Liste convencoes que voce deseja que o Truss aplique, mas que nao devem ser apresentadas como
regra tecnica universal.


| Regra/preferencia | Escopo: global, projeto ou tipo de prancha | Motivo |
| ----------------- | ------------------------------------------ | ------ |
|                   |                                            |        |


## 9. Confirmacao humana

Nome/referencia do revisor:

Data:

- [x] Revisei as seis folhas contra o PDF.
- [x] Os titulos, escalas, niveis e views registrados representam minha leitura.
- [x] Os findings listados representam problemas que eu realmente apontaria.
- [x] As preferencias pessoais estao separadas das regras gerais.
- [x] Autorizo transformar este formulario em um gabarito estruturado e em propostas de regras.

Observacoes finais:

