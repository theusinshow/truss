# Truss Web Design Contract

Atualizado em: 2026-09-03

## Hierarquia do produto

O Truss e uma mesa tecnica de revisao, nao um dashboard. A ordem visual obrigatoria e:

1. PDF e marcacoes no canvas;
2. achados da prancha ativa;
3. estado da revisao por IA e navegacao entre pranchas;
4. contexto do projeto e da revisao;
5. chat, aprendizado, comparacao e ferramentas manuais.

Existe uma unica acao primaria no workspace: `Revisar projeto com IA`. Acoes de aprendizado e
comparacao ficam em `Mais ferramentas`; chat e ferramentas da prancha permanecem recolhidos ate
serem solicitados.

## Composicao do workspace

- shell grafite/preto com divisorias retas e vermelho apenas como acento funcional;
- biblioteca local persistente a esquerda;
- cabecalho compacto do projeto, sem cards ornamentais;
- PDF central sempre aberto em Fit View ao trocar de prancha;
- painel de achados a direita;
- rail compacto de pranchas somente quando a largura comportar tres colunas; em larguras menores,
  setas e contador preservam a navegacao sem comprimir o PDF;
- nenhuma rolagem horizontal da pagina nas larguras suportadas.

## Achados e overlays

- resultados da revisao integral por IA sao a camada primaria depois que ela existe;
- achados humanos continuam sempre visiveis;
- regras deterministicas e resultados legados ficam disponiveis em `Filtros > Regras locais`,
  mas nao competem com a revisao IA por padrao;
- bbox localizada recebe contorno e preenchimento discreto;
- escopo `view` ou `sheet`, ou bbox muito ampla, recebe marcador triangular de tamanho constante
  na tela e nunca um retangulo vermelho cobrindo a prancha;
- origem, tipo, severidade, confianca e estado continuam textuais, nao apenas cromaticos;
- filtros por estado/severidade e silenciados ficam recolhidos por padrao.

## Tipografia, espacamento e controles

- Geist para interface quando disponivel;
- JetBrains Mono somente para codigos, coordenadas, metadados e estados;
- grid base de 4 px, divisorias de 1 px, poucos arredondamentos;
- alvos interativos principais com pelo menos 38 px;
- controles icon-only exigem nome acessivel e tooltip quando a funcao nao for obvia;
- texto tecnico deve permanecer legivel sem ampliar a densidade do chrome da aplicacao.

## Estado e movimento

Motion comunica somente carregamento, varredura IA, selecao/foco, transicao de painel e troca de
contexto. Todas as transicoes respeitam `prefers-reduced-motion`. Estado nao verificado,
inconclusivo, falho e concluido usam rotulos explicitos; cor so reforca o significado.

## Breakpoints de verificacao

- desktop amplo: rail de pranchas + PDF + achados;
- desktop compacto de referencia: 1249 x 1187, PDF + achados sem overflow horizontal;
- viewport estreito: PDF permanece a superficie principal e paineis secundarios deixam de
  competir por largura.
