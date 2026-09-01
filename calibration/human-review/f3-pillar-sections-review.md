# Revisao humana F3.3 - secoes de pilares

Data: 2026-09-01  
Resultado: gate espacial aprovado para o recorte conservador

## Escopo revisado

O corpus permaneceu somente leitura. Foram geradas pranchas de contato descartaveis diretamente
dos PDFs, com codigo em vermelho, candidato de secao em verde e concorrentes em laranja. Todas as
caixas e distancias foram medidas em pontos PDF.

A revisao cobriu:

- 20 associacoes positivas estratificadas em cinco documentos;
- 21 negativos de vigas ou pecas de madeira;
- 3 rotulos de secao plausiveis, mas deliberadamente nao suportados por terem texto residual;
- todos os 23 casos com mais de uma dimensao bruta a ate 10 pt;
- as duas evidencias de cada uma das 18 mudancas preliminares.

Os exemplos e expectativas reproduziveis estao em
`calibration/human-review/f3-pillar-sections-ground-truth.yml`.

## Contrato aprovado

Uma secao candidata precisa ser um span autonomo composto somente por dois numeros separados por
`x`, `X` ou `×`, com `cm` opcional. Ambos os valores devem estar entre 8 e 300. Texto residual,
como `V14 19x30`, `TERCA 8x16` ou `20x50 e=-0.07`, nao e parcialmente aproveitado.

A associacao exige:

1. mesma pagina e mesma view;
2. distancia entre bboxes de no maximo 2,0 pt;
3. um unico pilar estrutural mais proximo do span;
4. margem minima de 0,5 pt para o segundo pilar;
5. uma unica assinatura de secao ligada a ocorrencia.

Repeticoes concordantes podem reforcar a secao da view. Duas assinaturas distintas tornam o
`view_id + code` ambiguo. A assinatura para comparacao e o par numerico sem ordem, mas a ordem
impressa, o texto, a unidade e a bbox permanecem preservados.

## Medicao e separacao

Os candidatos positivos observados ficaram abaixo de 1,70 pt; a distribuicao exploratoria teve
p95 de 1,55 pt e p99 de 1,59 pt. O limite de 2,0 pt deixa uma pequena folga para variacao do PDF
sem ampliar para os concorrentes distantes.

Distancia sozinha nao separa os elementos: `TERCA 8x16`, `CAIBRO 8x16` e `V14 19x30` aparecem a
0,0-0,11 pt de alguns codigos. A separacao segura vem primeiro do span autonomo; a distancia e a
unicidade resolvem pertencimento entre os tokens restantes.

Na varredura dos seis documentos com texto nativo, o contrato encontrou 478 associacoes univocas:

| documento | univocas |
|---|---:|
| projeto-base | 119 |
| Lagoa | 21 |
| Valcir | 18 |
| R02 | 42 |
| Rancho Queimado | 216 |
| Guarita | 62 |

As tres ocorrencias de `P30` no Rancho Queimado, paginas 6, 29 e 30, possuem `19x30` e `19x40`
como spans autonomos concorrentes. As tres ficam ambiguas. Nos outros 20 casos multiplos, aceitar
somente o span autonomo selecionou a secao visualmente correta e bloqueou a etiqueta de viga,
madeira ou o texto residual.

## Transicoes revisadas

O pipeline descartavel da F3.2 foi reexecutado no projeto-base e no R02. O contrato reproduziu
exatamente as 18 mudancas preliminares: 7 no projeto-base e 11 no R02. Codigo, secao e geometria
foram conferidos nas duas pontas de cada par.

Essas confirmacoes significam apenas que a notacao mudou entre duas views pareadas. Nao significam
erro estrutural. A regra F3.3 deve produzir `ATTENTION_POINT` de severidade `MEDIUM`, e ausencia,
unidade incompativel ou ambiguidade deve produzir `UNKNOWN`.

## Limites conscientes

- `20x50 e=-0.07` pode conter uma secao real, mas fica sem associacao nesta versao;
- unidade ausente continua `null`, sem assumir centimetros;
- `14x30` e `30x14` comparam como o mesmo tamanho, preservando a ordem bruta;
- nao ha OCR, inferencia geometrica do contorno ou validacao de capacidade;
- o limiar e valido para este recorte de texto nativo e deve ser recalibrado antes de ampliar a
  gramatica.

## Conclusao do gate

O contrato separa positivos e negativos de modo reproduzivel e conserva os casos duvidosos como
ambiguos ou ausentes. A implementacao de `native-text/pillar-section-v1` pode prosseguir sem mudar
a estrutura central de dados.
