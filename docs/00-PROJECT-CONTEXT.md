# Contexto do projeto - Truss Agent

Atualizado em: 2026-09-03

Status do produto: V0.1 local concluida ate F7.2. A comparacao grafica combina regioes raster com
deltas deterministas de texto nativo e vetor. As F7.1 e F7.2 foram validadas com fixtures
isoladas; nao existe alegacao de validacao sobre um par real relacionado.

## Missao

O Truss Agent e um aplicativo pessoal de revisao grafica de projetos estruturais. Ele funciona
como um segundo desenhista tecnico: organiza o PDF, constroi um mapa auditavel da prancha,
encontra suspeitas e permite ao proprietario confirmar, rejeitar ou complementar cada achado sem
perder o vinculo com a evidencia grafica.

O produto nao e um chatbot generico, um SaaS ou um sistema de gestao multiusuario. A superficie
principal e o PDF. Conversa, memoria, calibracao e metadados existem para apoiar a revisao sobre a
prancha.

## Usuario e ambiente

O unico usuario da V0.1 e o proprietario, engenheiro/projetista estrutural. O uso e local, em
desktop, durante a revisao diaria de projetos reais. O ambiente precisa continuar funcional sem
servicos de autenticacao, cobranca, sincronizacao em nuvem ou infraestrutura multiusuario.

Dados de projeto, PDFs originais, renders, geometria e SQLite permanecem no computador local.
Quando uma analise multimodal externa e deliberadamente habilitada, somente crops e contexto
estruturado necessarios devem ser enviados.

## Problema que o produto resolve

A revisao de um conjunto estrutural exige relacionar informacao espalhada entre plantas,
detalhes, cortes, carimbos e revisoes. Erros e omissoes podem ser pequenos graficamente e grandes
tecnicamente. Uma ferramenta apenas conversacional perde localizacao; uma ferramenta apenas
visual perde texto, vetor, regra e rastreabilidade.

O Truss combina:

- PDF renderizado como superficie de inspecao;
- texto nativo e bounding boxes em coordenadas PDF;
- primitivas vetoriais e regioes detectadas;
- Sheet Map versionado por folha;
- regras deterministicas por escopo tecnico;
- analise multimodal localizada quando habilitada;
- feedback humano explicito e auditavel;
- calibracao sobre corpus local com fontes de autoridade separadas.

## Principios de produto

### PDF primeiro

O viewer e os achados posicionados na prancha sao a experiencia principal. Chat e paineis nunca
devem deslocar o PDF do centro da tarefa.

### Evidencia antes de certeza

O Truss e agressivo em procurar suspeitas, mas nao transforma hipotese em erro confirmado.
Confianca mede a forca da evidencia; severidade mede o impacto potencial. Sao dimensoes
independentes.

### Coordenadas como dado

Bounding boxes canonicas usam pontos PDF, nunca somente pixels de render. Render, crop, zoom e
overlay sao transformacoes dessa fonte canonica.

### Revisoes imutaveis

Uma nova exportacao gera nova revisao. PDF, Sheet Map e auditoria historicos nao sao
sobrescritos. Derivados podem ser recriados, mas o dado que explica uma decisao permanece.

Quando os bytes de uma fonte historica nao existem no ambiente recebido, a ausencia e registrada
explicitamente em eventos append-only. Ela nao apaga a revisao nem e tratada como PDF valido. Uma
fonte declarada restaurada precisa corresponder ao hash historico exato.

### Humano decide

Confirmacao, rejeicao justificada, achado manual, preferencia e decisao de calibracao sao dados
persistidos. O sistema pode propor uma mudanca; nao altera rule pack ou preferencia
silenciosamente.

### Cache por conteudo

Resultados validos sao reutilizados por hash de entrada, versao de pipeline, regra, provider e
configuracao relevante. Alterar uma entrada invalida somente o nivel afetado.

### Privacidade por minimizacao

O PDF original permanece local. Segredos, caminhos absolutos, conversas e memoria explicita nao
entram em exports de calibracao ou backups de runtime quando nao pertencem ao dado duravel.

## Fluxo principal da V0.1

1. criar ou abrir projeto local;
2. registrar uma revisao imutavel;
3. importar um ou mais PDFs;
4. extrair folhas, texto, geometria e Sheet Maps;
5. navegar pelo PDF e executar auditoria deterministica;
6. opcionalmente executar analise visual localizada dentro de limites de custo;
7. inspecionar cada finding sobre a evidencia;
8. confirmar, rejeitar com justificativa ou criar finding manual;
9. revisar preferencias e propostas de aprendizado/calibracao;
10. fechar e reabrir o trabalho sem perda de estado;
11. criar backup verificavel e recuperar para novo diretorio quando necessario.

## Linguagem de resultados

Tipos conceituais:

- `INCONSISTENCY`: informacoes observadas entram em conflito;
- `ATTENTION_POINT`: ha risco ou situacao que merece revisao;
- `MISSING_INFORMATION`: informacao esperada nao foi localizada;
- `NOT_VERIFIABLE`: o material disponivel nao sustenta verificacao.

Severidades: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.

Na API atual, os valores equivalentes sao serializados em minusculas. Um resultado limpo,
desconhecido, nao aplicavel, ignorado ou sem cobertura nao pode ser apresentado como conformidade.

## Fontes de verdade

Ordem para resolver duvidas de produto e arquitetura:

1. `AGENTS.md` e aprovacao explicita do proprietario;
2. `docs/DECISIONS.md` e `docs/14-ROADMAP.md`;
3. este documento e `docs/06-TECH-ARCHITECTURE.md`;
4. README e planos aprovados;
5. testes automatizados e codigo implementado;
6. specs historicas, usadas como contexto, nao como autorizacao automatica.

Divergencias devem ser registradas. Mudanca arquitetural relevante segue
`analisar -> explicar -> propor -> aguardar aprovacao`.

## Marcos

- F1: Sheet Map base, migrations, geometria, regioes, carimbo e classificacao;
- F2: views de formas, escopos tecnicos, rule packs e rastreabilidade;
- F3: elementos, registro entre folhas, continuidade e secoes de pilares;
- F4: provider multimodal localizado, crops, cache, custo e limites;
- F5: preferencias explicitas, propostas auditaveis e calibracao deterministica do corpus;
- F6.1: recuperacao e operacao local segura, concluida;
- F6.2: fila e worker locais, lote de 84 folhas reais, fixture separada de falha, progresso,
  cancelamento cooperativo e recovery, concluidos e validados.
- F7.1: comparacao grafica deterministica entre revisoes, runs e regioes imutaveis, pareamento
  auditavel e interface PDF-first; concluida por aceite explicito, com gate real dispensado.
- F7.2: deltas deterministas de texto nativo e primitivas vetoriais, evidencia antes/depois,
  limites honestos e filtros por camada; concluida com gate sintetico e sem classificacao de erro.

O acervo recebido nao possui duas exportacoes reais relacionadas que possam sustentar o gate
visual antes/depois das F7.1/F7.2. `REV-005` e `REV-006` sao conjuntos distintos e nao devem ser
pareados por nome de arquivo ou numero da pagina. A dispensa do gate nao altera esse limite nem
constitui evidencia de validacao real.

## Fora do escopo

- SaaS, multiusuario, autenticacao e cobranca;
- fine-tuning na V0.1;
- PDF binario dentro do SQLite;
- armazenamento principal remoto;
- nome de arquivo como significado tecnico sem validacao;
- prompt monolitico responsavel por toda a revisao;
- 3D decorativo;
- alteracao automatica de regra a partir de proposta;
- comparacao semantica de engenharia ou classificacao automatica de diferenca como erro;

## Definicao de concluido

Um milestone so termina com criterios de aceite atendidos, testes automatizados relevantes,
verificacao manual do fluxo principal e documentacao atualizada. Persistencia, coordenadas,
findings, revisoes, cache, preferencias, calibracao e recuperacao exigem testes especificos.
