# Gabarito de calibracao

Cada arquivo `.yml` descreve o que se espera que o Truss identifique num projeto real. E o unico
criterio objetivo de "ficou mais inteligente".

Os PDFs de referencia nao ficam no repositorio: sao material de cliente. O teste em
`apps/api/tests/test_calibration.py` procura o arquivo em `data/originals/` pelo nome e **pula
automaticamente** quando ele nao esta presente, de modo que a suite continua verde numa maquina
limpa.

## Status atual deste gabarito

> **Atencao:** `rancho-queimado-r01.yml` foi gerado a partir da saida do proprio pipeline na F1.
> Isso o torna um **detector de regressao**, nao uma verdade independente: ele prova que o
> comportamento nao mudou, nao que ele esta certo.
>
> Para virar gabarito de verdade, as 28 linhas precisam ser conferidas manualmente contra as
> pranchas. A conferencia por amostragem feita durante a F1 (paginas 0, 2, 5, 12, 20) bateu em
> todas, mas as 23 restantes seguem sem revisao humana.

## Evolucao

Na F1 o gabarito cobre codigo da prancha e tipo. A partir da F2 ganha os findings esperados por
folha, e ai passa a medir precisao e cobertura da auditoria - que e o numero que realmente
interessa.
