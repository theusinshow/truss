# F4.1 - Triagem visual de legibilidade por crops

Data: 2026-09-01

Status: concluido e validado em 2026-09-01

Escopo: texto pequeno, sobreposto ou visualmente ilegivel em regioes candidatas determinadas por geometria

## Resultado pretendido

Ao executar a analise visual de uma folha, o Truss deve usar texto e geometria nativos para selecionar poucas regioes suspeitas, renderizar somente crops locais e pedir ao provider multimodal uma classificacao estruturada de legibilidade. Um resultado positivo gera `ATTENTION_POINT/MEDIUM` pendente de validacao humana e localizado na bbox PDF que originou o crop.

## Contrato aprovado

- o PDF e o Sheet Map continuam como fontes principais;
- o modelo nunca recebe o PDF inteiro neste slice;
- candidatos sao gerados deterministicamente por tamanho e sobreposicao de spans;
- pixels do crop sao derivados de uma bbox canonica em pontos PDF;
- o modelo escolhe somente entre `PASS`, `ATTENTION` e `NOT_VERIFIABLE`;
- o modelo nao cria nem corrige coordenadas;
- toda resposta segue JSON Schema estrito e preserva provider, modelo, prompt e hash do crop;
- cache usa hash do crop, versao do pipeline, prompt, modelo e configuracao visual;
- chamadas e custo possuem teto por revisao;
- visao externa fica desabilitada por padrao;
- testes usam provider falso e nunca chamam rede.

## Pipeline

```text
spans + views + geometria
  -> candidatos deterministas
  -> bbox PDF com padding
  -> crop PNG enderecado por conteudo
  -> cache / budget gate
  -> Vision AI Provider com Structured Outputs
  -> finding localizado e pendente
```

## Tasks

### Task 1 - Gabarito e candidatos

Criar fixture positiva e negativa para texto pequeno, sobreposto e legivel. O candidato deve carregar id estavel, tipo, textos brutos, bbox PDF, view e escopo tecnico quando observaveis.

### Task 2 - Render de crop

Renderizar com PyMuPDF, padding em pontos, clip nos limites da pagina, detalhe configuravel e caminho local por hash. Nenhum crop entra no SQLite.

### Task 3 - Provider multimodal

Estender a abstracao de AI Provider com operacao de crop. O provider OpenAI usa Responses API, `input_image`, `store: false`, detalhe explicito, reasoning explicito e JSON Schema estrito. O provider local informa indisponibilidade sem inventar analise.

### Task 4 - Cache e teto de custo

Reusar `cache_entries` no namespace `vision` e `ai_usage_events` na operacao `vision.legibility`. Impedir nova chamada quando a mesma entrada ja estiver em cache ou quando a reserva conservadora exceder o limite da revisao.

### Task 5 - Auditoria e persistencia

Adicionar uma execucao de auditoria `vision` separada da deterministica. Findings usam `source_layer: vision`, `rule_id: vision.text_legibility`, evidencia rastreavel e dedupe estavel, preservando feedback historico.

### Task 6 - Viewer

Adicionar uma acao explicita de analise visual ao toolbar. Durante a execucao, motion comunica varredura; findings visuais exibem a origem `VISAO / CROP`, hipotese pendente e evidencia completa.

### Task 7 - Medicao

Executar fixture e corpus sem rede para medir quantidade de candidatos, distribuicao por tipo, crops e limites. Medicao paga sobre material real depende de comando explicito do proprietario.

Concluida com autorizacao explicita: 3 crops reais, 3 resultados `ATTENTION`, custo estimado de
USD 0.019245 e replay integral pelo cache sem nova chamada. A amostra valida o contrato; nao e uma
estimativa estatistica de precisao.

## Criterios de aceite

- [x] nenhum PDF completo e enviado ao provider;
- [x] toda entrada visual nasce de bbox PDF reproduzivel;
- [x] candidatos deterministas possuem testes positivos e negativos;
- [x] schema nao permite coordenadas inventadas pelo modelo;
- [x] cache impede repeticao da mesma chamada;
- [x] teto de chamadas e custo bloqueia antes da chamada;
- [x] provider local nao simula visao;
- [x] provider falso cobre fluxo sem rede;
- [x] finding visual e `ATTENTION_POINT/MEDIUM` pendente;
- [x] viewer distingue origem visual e preserva reduced motion;
- [x] testes API/web, lint e typecheck ficam verdes;
- [x] documentacao registra medicao e limites.

## Fora do escopo

- OCR de pagina inteira;
- enviar PDF completo ou render inteiro ao modelo;
- validar dimensionamento estrutural;
- transformar baixa legibilidade em erro confirmado;
- detectar falta de cotas ou detalhamentos sem gabarito proprio;
- simbolos sem legenda;
- fine-tuning;
- implementar F5 ou F6.
