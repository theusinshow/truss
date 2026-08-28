# Decisoes humanas normalizadas — Formas v1

Status: **confirmado pelo proprietario em 2026-08-28**

Fonte humana: `forms-ground-truth-questionnaire.md`, complementada por confirmacao direta do
proprietario. Este documento normaliza as decisoes; nao substitui os bboxes do ground truth, que
ainda precisam ser gerados em pontos PDF e conferidos no viewer.

## Documento de referencia

- Arquivo local: `Projeto Estrutural_Juliano Corbellini_R05.pdf`
- SHA-256: `147b730c0189a78e9e83a7301b717612db0550d7fa6a8fbdb7a2924ef77fae4c`
- Paginas: 29
- O PDF e material local e nao deve ser versionado.

## Politica confirmada

### Certeza e tipo de finding

- Incapacidade real de concluir pelo material disponivel: `NOT_VERIFIABLE`.
- Evidencia existente, mas fraca ou ambigua: `ATTENTION_POINT`.
- Severidade mede impacto; confianca mede certeza.
- A agressividade desejada e equilibrada: procurar problemas sem aceitar ruido excessivo.

### Views, titulos e escalas

- Toda view tecnica precisa estar coberta por um titulo proprio ou por um titulo agrupador
  inequivocamente associado.
- Subviews internas de um detalhamento agrupado nao precisam repetir o titulo completo.
- Toda view tecnica precisa ter escala numerica propria, escala compartilhada pelo grupo ou uma
  declaracao valida de `ESCALA INDICADA`.
- `ESCALA INDICADA` e valida em composicoes com subviews em escalas diferentes, como vista de
  viga em 1:50 e secao em 1:25.
- Perspectivas e representacoes auxiliares podem usar `ESCALA REPRESENTATIVA` ou nao possuir
  escala numerica.
- Perspectivas nao precisam possuir nivel.
- Duplicidade de identificador de view na mesma folha gera `ATTENTION_POINT`, salvo quando a
  semantica de agrupamento demonstrar equivalencia intencional.

### Niveis

- Preferencia explicita do proprietario: toda planta de formas deve declarar nivel no titulo.
- A regra geral pode reconhecer casos simples em que base/topo seriam compreensiveis sem nivel,
  mas o rule pack pessoal deve exigir nivel sempre.
- Valores do projeto de referencia foram confirmados com a seguinte normalizacao:

| Texto no PDF | Valor normalizado |
|---|---:|
| `-650` | `-6.50 m` |
| `-350` | `-3.50 m` |
| `-167` | `-1.67 m` |
| `-04` | `-0.04 m` |
| `338` | `3.38 m` |
| `680` | `6.80 m` |
| `780` | `7.80 m` |
| `940` | `9.40 m` |

O texto bruto deve ser preservado junto do valor normalizado.

### Content regions e subviews

- Tabelas de pilares, vigas, lajes e materiais sao content regions, nao views.
- Tabelas proximas de uma planta podem pertencer ao contexto daquela view.
- Um detalhe pode representar varios tipos, como `01/02/03/04`, numa unica view principal.
- `VISTA H`, `VISTA B` e `SECAO` podem ser subviews internas do detalhamento de um pilar; nem
  todo pilar deve virar view de primeiro nivel.
- Agrupamentos como `P21=P38` e `P28=P37` representam detalhamentos equivalentes e nao sao
  duplicidades.

### Semantica estrutural que nao deve gerar falso positivo

- Niveis locais e elevacoes de lajes nao contradizem automaticamente o nivel geral da planta.
- `MORRE`, `NASCE` e mudanca de secao sao indicacoes intencionais.
- Em fase posterior, `PASSA` deve ser conferido contra o proximo nivel, e `MORRE` deve ser
  conferido como ausente no nivel seguinte.
- Uma perspectiva auxiliar sem titulo, escala numerica ou nivel nao deve ser tratada
  automaticamente como view tecnica incompleta.

### Coerencia

- Carimbo classificado como planta de formas com conteudo dominante de outro tipo:
  `INCONSISTENCY`, severidade `MEDIUM`.
- Elemento desenhado e ausente de tabela gera finding somente quando a tabela representar um
  conjunto completo aplicavel.
- Divergencia entre planta e tabela gera `ATTENTION_POINT` inicialmente.
- Nenhuma das duas fontes e considerada correta automaticamente; o finding apresenta o conflito.
- Chamada de corte ou detalhe sem destino gera finding somente depois de procurar em toda a
  revisao.
- View sem chamada de origem gera `ATTENTION_POINT`, quando a chamada for esperada.

## Folhas verificadas

### Referencias aprovadas sem findings esperados nesta primeira calibracao

- `EST-0050-B` — detalhamento de fundacoes e pilares de arranque (4/4).
- `EST-0060-B` — tres plantas de formas e uma perspectiva auxiliar.
- `EST-0070-B` — planta de formas, detalhe de laje e perspectiva auxiliar.
- `EST-0080-B` — duas plantas de formas, detalhe agrupado e perspectiva auxiliar.
- `EST-0090-B` — duas plantas de formas, detalhe e duas perspectivas auxiliares.

As listas vazias de findings dessas folhas foram confirmadas como **zero findings esperados para
o escopo da primeira calibracao de views**. Isso nao declara que as folhas sao perfeitas para
todas as regras futuras.

### Referencia com ressalva pendente

- `EST-0260-A` — detalhamento de pilares da cobertura.

O conteudo e valido para calibrar agrupamentos e subviews. A ressalva tecnica ainda nao foi
descrita e, portanto, a folha nao deve ser usada como exemplo negativo integral ate essa
informacao ser registrada.

## Estado para conversao em ground truth

Ja pode ser tratado como humanamente confirmado:

- identidade e revisao das seis folhas;
- tipos e titulos das views descritas no questionario;
- escalas e niveis declarados;
- normalizacao dos niveis;
- regras negativas acima;
- zero findings esperados no escopo de views para `EST-0050-B` a `EST-0090-B`.

Ainda requer trabalho:

- gerar bboxes em pontos PDF;
- conferir overlays dos bboxes no viewer;
- registrar a ressalva de `EST-0260-A`;
- revisar `EST-0100-B`, `EST-0110-B` e `EST-0120-B` para ampliar a diversidade de plantas de
  formas.

