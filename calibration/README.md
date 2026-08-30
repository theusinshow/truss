# Gabarito de calibracao

Um arquivo `.yml` por projeto, descrevendo o que se espera que o Truss identifique. E o unico
criterio objetivo de "ficou mais inteligente".

Nenhum teste referencia um gabarito pelo nome: `truss_api.calibration.catalog` varre esta pasta e
localiza o PDF de cada um. **Acrescentar um projeto e soltar dois arquivos.**

## Acrescentar um projeto

1. Coloque o PDF em `docs/projeto_base/`.
2. Gere o rascunho do gabarito:

```bash
.venv/Scripts/python -X utf8 -c "
import sys, pathlib; sys.path.insert(0,'apps/api')
from truss_api.calibration.intake import write_draft
pdf = pathlib.Path('docs/projeto_base/NOME-DO-ARQUIVO.pdf')
print(write_draft(pdf, pathlib.Path('calibration') / (pdf.stem.lower().replace(' ', '-') + '.yml')))
"
```

3. Revise o YAML. O rascunho sai com `status: draft_unverified`, todas as views com
   `human_confirmed: false` e todas as folhas com `expected_findings.status: not_provided`.
4. Quando terminar de conferir, troque `status` para `human_verified` e marque as views revisadas.

O rascunho carrega a saida do pipeline para voce **corrigir**, nao para o pipeline se medir contra
a propria saida. Enquanto o `status` for `draft_unverified`, o arquivo detecta regressao e nao
prova correcao - e os testes dizem isso em voz alta na saida.

## O PDF

O PDF e localizado por **hash de conteudo** quando o gabarito declara `document.sha256`, e so por
nome quando nao declara. A importacao sanitiza o nome do arquivo - troca espacos por hifens e
prefixa o hash - entao procurar pelo nome declarado falharia justamente no arquivo que o proprio
Truss guardou.

A busca cobre `docs/projeto_base/` (versionado) e `data/originals/` (local, fora do repositorio).
Gabarito cujo PDF nao esta presente faz o teste pular, e a suite segue verde numa maquina limpa.

## O que cada tipo de material mede

| material | o que mede |
|---|---|
| projeto aprovado | **piso de ruido**: todo achado e candidato a falso positivo |
| projeto com defeito conhecido e descrito | **cobertura e precisao** de findings |
| outro escritorio, outro carimbo | sobreajuste do parser de carimbo e do classificador |
| prancha fora de A1 | deteccao de moldura e `paper_format` |
| folha com `ESCALA INDICADA` | a regra existe e nunca foi exercida em material real |
| folha com detalhe agrupador e subviews | `parent_view_id` e `view_role` nunca foram produzidos |

O piso de ruido roda em `apps/api/tests/test_calibration_noise.py` e imprime achados por folha e
por regra. Um projeto aprovado que gera muitos achados esta denunciando a regra, nao o projeto.

## Estado atual

- `juliano-corbellini-r05.yml` - **`human_verified`**, seis folhas de formas revisadas pelo
  proprietario. PDF versionado em `docs/projeto_base/`. Piso de ruido medido: **0 achados em 29
  folhas**.
- `rancho-queimado-r01.yml` - **`legacy`**, gerado a partir da saida do proprio pipeline na F1.
  Detector de regressao, nao verdade independente. Nao tem `version`, `thresholds` nem views, entao
  nao participa da medicao de views. Seu PDF nao esta versionado.

## O que ainda nao e mensuravel

- **recall de content blocks por IoU**: nenhum gabarito tem caixa espacial, so `position_hint` em
  texto livre. Os bboxes seguem `draft_unverified` ate a conferencia visual no viewer.
- **cobertura e precisao de findings**: exigem folhas com defeito conhecido e descrito. Todo o
  material conferido ate agora e de projeto aprovado, onde o esperado e zero.
