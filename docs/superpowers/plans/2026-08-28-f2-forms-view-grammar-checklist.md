# F2 - Forms View Grammar & Checklist v1 - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer o Truss interpretar a composicao de plantas de formas - reconhecer as views de cada folha, associar titulo, escala e nivel a cada uma, e executar checklists deterministicos localizados com rastreabilidade completa.

**Architecture:** A extracao passa a preservar primitivas vetoriais e spans de texto em disco comprimido, enderecados por hash de conteudo. O Sheet Map vira um snapshot imutavel identificado por hash, nunca sobrescrito. Um detector deterministico segmenta views usando ancoras de escala e titulo combinadas com limites graficos. Um motor de regras declarativo avalia rule packs versionados sobre o snapshot e emite findings rastreaveis, sem fallback artificial.

**Tech Stack:** Python 3.11, FastAPI, PyMuPDF (`fitz`), SQLite, pytest, PyYAML, Next.js 15, TypeScript, Vitest.

## Decisoes arquiteturais aprovadas

Aprovadas pelo arquiteto principal em 2026-08-28:

- **C1 aprovado.** O `pipeline_version` embute o hash do snapshot
  (`sheetmap-v0.2+<hash12>`), reaproveitando a restricao `UNIQUE (sheet_id, pipeline_version)`
  como garantia de imutabilidade. Nenhuma reconstrucao de tabela. Todas as migrations sao aditivas.
- **Threshold de 90% mantido** para associacao de titulo, escala e nivel, apesar da medicao de 35%
  com a regra ingenua. O portao de medicao da Task 5 permite ajustar apenas as tolerancias
  geometricas; **reduzir o threshold e proibido**.

## Global Constraints

- Coordenadas canonicas em pontos PDF (`pt`). Pixels de render sao derivados, nunca persistidos como fonte.
- Nenhuma chamada a LLM nesta fase. Toda verificacao e deterministica. Visao multimodal esta fora de escopo.
- Nenhum teste pode usar rede ou IA real.
- Artefatos pesados vao para disco, nunca para o SQLite.
- Migrations **aditivas**. Nenhum `DROP`, nenhuma reconstrucao de tabela, nenhum dado existente removido.
- Nao apagar Sheet Maps, findings ou feedback humano existentes.
- Nao reduzir thresholds de calibracao para fazer teste passar.
- Fixtures geradas automaticamente permanecem `status: draft_unverified` ate revisao humana.
- A fase nao pode ser declarada concluida sem validacao humana das seis folhas de formas.
- Rule packs sao versionados, validados por schema, e vivem no repositorio - nao no banco.
- **Preservar alteracoes nao commitadas do frontend.** Antes de tocar em `apps/web`, rodar
  `git status --short apps/web`; se houver mudanca pendente, integrar sem sobrescrever.
- Nao usar prompt monolitico nem LLM para verificacao deterministica.

---

## Evidencia medida antes da escrita deste plano

Todas as medicoes foram feitas contra `Proj_Estrutural_RanchoQueimado_geral.pdf` e o banco local real.

| Fato | Valor medido |
|---|---|
| Folhas classificadas `planta_formas` | 7 no banco: **6 unicas** do projeto real (paginas 4, 5, 6, 7, 8, 25) + 1 de outro escritorio |
| Ancoras `ESCALA 1:x` fora do carimbo nas 6 folhas | **17** (2, 3, 2, 2, 3, 5) |
| Fonte de titulo de view vs texto de cota | **15.8 pt** contra **5.9-8.4 pt** |
| Padrao de titulo | prefixo numerico: `1 CORTE A-A`, `2 CORTE B-B`, `2 DETALHE 01 LAJE PRE-FABRICADA` |
| Rotacao / mediabox / cropbox | `rotation=0`, `mediabox == cropbox`, matriz identidade em todas as paginas amostradas |
| Primitivas vetoriais da folha 4 | 39.396 drawings, 74.576 items |
| Tamanho em JSON sem compressao | **8,55 MB** para uma folha |
| Tamanho com gzip nivel 6 | **0,60 MB** (razao 14,3x) |
| Spans de texto na folha 4 | 1.575 |

**Consequencias diretas:**

1. **Gzip e obrigatorio, nao opcional.** 85 folhas sem compressao passariam de 700 MB.
2. **A rotacao real e sempre 0.** O suporte a rotacao existe para outros PDFs e so pode ser
   verificado com fixture sintetica rotacionada - nunca com este material.
3. **A associacao titulo/escala nao e trivial.** Uma regra ingenua de "linha imediatamente acima"
   acerta **35%** (6 de 17), nao os 90% exigidos. A causa medida e tolerancia geometrica: na
   pagina 7 o titulo `1 CORTE A-A` termina a fracao de ponto do limite testado. **O detector tem
   de ser desenvolvido iterativamente contra o ground truth, com harness de medicao** - por isso
   a calibracao e a Task 1 deste plano, antes de qualquer detector.

---

## Conflitos entre a arquitetura da F2 e os contratos existentes

Levantados por inspecao do codigo. Cada um tem a resolucao adotada e a justificativa.

### C1 - `save_sheet_map` apaga o Sheet Map anterior

`apps/api/truss_api/sheetmap/repository.py:36-48` executa `DELETE FROM sheet_regions` e
`DELETE FROM sheet_maps` para o mesmo `(sheet_id, pipeline_version)` antes de inserir. Isso viola
frontalmente "nao apagar um Sheet Map/snapshot referenciado por uma auditoria".

**Resolucao:** o `pipeline_version` passa a embutir o hash do conteudo do snapshot, no formato
`sheetmap-v0.2+<hash12>`. A restricao `UNIQUE (sheet_id, pipeline_version)` que ja existe vira
exatamente a garantia desejada: multiplos snapshots por folha sao permitidos, e reprocessar a
mesma entrada colide com a linha existente e a reutiliza em vez de recriar. O `DELETE` e removido.

**Justificativa:** evita reconstruir a tabela `sheet_maps` em SQLite, o que exigiria
`PRAGMA foreign_keys=OFF` fora de transacao por causa da FK de `sheet_regions`, e seria a operacao
de maior risco de perda de dados do milestone. A restricao existente ja faz o trabalho.

### C2 - A extracao descarta as primitivas

`sheetmap/geometry.py:47` filtra por `min_area_ratio=0.0002` e guarda **apenas o bounding box** de
cada drawing. Linhas, curvas, espessura, cor e dash sao perdidos. O escopo da F2 proibe depender
desse filtro.

**Resolucao:** `extract_page_geometry` continua existindo com a mesma assinatura, para nao quebrar
o `builder`, mas passa a ser derivada de uma extracao completa nova. O artefato em disco guarda as
primitivas integrais.

### C3 - `area_desenho` e um retangulo cortado no topo do carimbo

`sheetmap/regions.py:140-152` define a zona de desenho como a moldura ate `title_block.y0`. Numa
folha A1 com carimbo estreito a direita, isso descarta toda a faixa lateral util.

**Resolucao:** a zona de desenho passa a ser calculada por subtracao de regioes: moldura menos
carimbo, menos tabelas, menos blocos de nota e legenda, representada como lista de retangulos
disjuntos em vez de um unico bbox.

### C4 - O finding de fallback

`audit/orchestrator.py:73-84` emite "Auditoria deterministica inicial nao encontrou
inconsistencias" quando nenhuma regra dispara. A F2 exige remove-lo.

**Resolucao:** a geracao para. **Os 63 findings historicos nao sao apagados** - entre eles ha 1
confirmado e 1 rejeitado, que sao feedback humano. Eles recebem `source_layer = 'legacy'` na
migration e continuam visiveis. Auditoria limpa passa a produzir zero findings e um resumo de
cobertura.

### C5 - A chave de cache e fraca demais

`audit/orchestrator.py:27` usa `f"audit:deterministic-v0.1:{sheet_id}"`. Nao considera hash do
documento, versao do extrator, versao do pipeline, rule pack nem configuracao. Trocar uma regra
nao invalida o cache.

**Resolucao:** chave composta explicita, definida na Task 8.

### C6 - `findings` nao tem rastreabilidade

A tabela nao possui `rule_id`, `rule_version`, `view_id`, `source_layer` nem `dedupe_key`.

**Resolucao:** colunas aditivas e anulaveis na migration 003. Contratos publicos preservados: os
campos novos sao adicionais no JSON de resposta e nenhum campo existente muda de nome ou tipo.

### C7 - O import ficara mais lento

`documents/routes.py` chama `build_sheet_map_for_document` sincronamente. Com primitivas
completas, sao ~0,6 MB comprimidos por folha e um custo de CPU maior por pagina.

**Resolucao:** aceito nesta fase, com medicao obrigatoria na Task 2. Se o import de 28 paginas
passar de 90 segundos, a extracao de primitivas passa a ser preguicosa - registrada como divida
tecnica e nao expandida aqui.

---

## Estrutura de modulos

```
apps/api/truss_api/sheetmap/
  primitives.py        NOVO  dataclasses de primitiva vetorial e span de texto + (de)serializacao
  artifacts.py         NOVO  escrita/leitura de artefato comprimido enderecado por hash
  geometry.py          MOD   extracao completa + metadados de pagina; derivada mantem contrato
  regions.py           MOD   novos region kinds; zona de desenho por subtracao
  title_block.py       -     inalterado
  classifier.py        -     inalterado
  views/
    __init__.py        NOVO
    models.py          NOVO  DetectedView e enums de view_kind
    anchors.py         NOVO  reconhecimento de escala, titulo, nivel e identificador
    detector.py        NOVO  segmentacao de views de planta de formas
  snapshot.py          NOVO  hash de conteudo do Sheet Map e politica de reuso
  builder.py           MOD   orquestra extracao -> regioes -> views -> snapshot
  repository.py        MOD   persiste views; remove DELETE; reutiliza snapshot por hash
  models.py            MOD   expoe views e regioes no contrato
  routes.py            MOD   endpoint de views

apps/api/truss_api/rules/
  __init__.py          NOVO
  schema.py            NOVO  validacao do schema de rule pack
  loader.py            NOVO  carga e cache de packs do disco
  engine.py            NOVO  avaliacao -> RuleEvaluation
  models.py            NOVO  RuleEvaluation, RuleOutcome
  packs/
    planta_formas.v1.yml  NOVO

apps/api/truss_api/audit/
  orchestrator.py      MOD   roda o motor de regras; sem fallback
  repository.py        MOD   persiste RuleEvaluation, dedupe, cobertura
  models.py            MOD   campos de rastreabilidade

apps/api/truss_api/db/migrations/
  003_views_rules_traceability.sql  NOVO

calibration/
  schema.md            NOVO  formato v2 documentado
  rancho-queimado-r01.yml  MOD  migrado para v2, marcado draft_unverified

apps/api/tests/
  test_extraction.py           NOVO
  test_view_detection.py       NOVO
  test_rules_engine.py         NOVO
  test_findings_traceability.py NOVO
  test_calibration.py          MOD
  factories.py                 MOD  fixtures sinteticas de planta de formas

apps/web/
  lib/projects-api.ts          MOD  tipos de view
  components/canvas/view-overlays.tsx  NOVO
  components/sheet-viewer.tsx   MOD  render dos overlays
```

---

### Task 1: Formato de calibracao v2 e harness de metricas

Vem primeiro porque o detector de views **nao pode ser escrito as cegas**: foi medido que a regra
obvia acerta 35%. O harness e o instrumento que torna o desenvolvimento do detector mensuravel.

**Files:**
- Create: `calibration/schema.md`
- Create: `apps/api/truss_api/calibration/__init__.py`
- Create: `apps/api/truss_api/calibration/model.py`
- Create: `apps/api/truss_api/calibration/metrics.py`
- Modify: `calibration/rancho-queimado-r01.yml`
- Test: `apps/api/tests/test_calibration.py`

**Interfaces:**
- Produces:
  - `CalibrationDocument` dataclass: `filename: str`, `page_count: int`, `status: str`, `thresholds: dict[str, float]`, `sheets: list[CalibrationSheet]`
  - `CalibrationSheet` dataclass: `page_index: int`, `sheet_code: str | None`, `sheet_type: str`, `content_regions: list[CalibrationRegion]`, `views: list[CalibrationView]`, `expected_findings: list[CalibrationFinding]`
  - `CalibrationView` dataclass: `view_id: str`, `view_kind: str`, `identifier: str | None`, `title: str | None`, `declared_scale: str | None`, `level: str | None`, `bbox: tuple[float, float, float, float]`, `status: str`
  - `load_calibration(path: Path) -> CalibrationDocument`
  - `iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float`
  - `match_boxes(expected, actual, min_iou: float) -> tuple[int, int, int]` devolve `(matched, missed, spurious)`
  - `recall(matched: int, missed: int) -> float`
  - `precision(matched: int, spurious: int) -> float`

- [ ] **Step 1: Escrever o teste das metricas**

Create `apps/api/tests/test_calibration_metrics.py`:

```python
from truss_api.calibration.metrics import iou, match_boxes, precision, recall


def test_iou_of_identical_boxes_is_one() -> None:
    box = (0.0, 0.0, 10.0, 10.0)
    assert iou(box, box) == 1.0


def test_iou_of_disjoint_boxes_is_zero() -> None:
    assert iou((0.0, 0.0, 10.0, 10.0), (20.0, 20.0, 30.0, 30.0)) == 0.0


def test_iou_of_half_overlap() -> None:
    value = iou((0.0, 0.0, 10.0, 10.0), (5.0, 0.0, 15.0, 10.0))
    assert abs(value - (50 / 150)) < 1e-9


def test_match_boxes_counts_matched_missed_and_spurious() -> None:
    expected = [(0.0, 0.0, 10.0, 10.0), (100.0, 100.0, 110.0, 110.0)]
    actual = [(0.0, 0.0, 10.0, 9.0), (500.0, 500.0, 510.0, 510.0)]

    matched, missed, spurious = match_boxes(expected, actual, min_iou=0.5)

    assert (matched, missed, spurious) == (1, 1, 1)


def test_match_boxes_does_not_reuse_the_same_actual_twice() -> None:
    expected = [(0.0, 0.0, 10.0, 10.0), (0.0, 0.0, 10.0, 10.0)]
    actual = [(0.0, 0.0, 10.0, 10.0)]

    assert match_boxes(expected, actual, min_iou=0.5) == (1, 1, 0)


def test_recall_and_precision_handle_empty_input() -> None:
    assert recall(0, 0) == 1.0
    assert precision(0, 0) == 1.0
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_calibration_metrics.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'truss_api.calibration'`

- [ ] **Step 3: Implementar as metricas**

Create `apps/api/truss_api/calibration/__init__.py` vazio, e
`apps/api/truss_api/calibration/metrics.py`:

```python
BBox = tuple[float, float, float, float]


def iou(a: BBox, b: BBox) -> float:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[2], b[2])
    bottom = min(a[3], b[3])

    if right <= left or bottom <= top:
        return 0.0

    intersection = (right - left) * (bottom - top)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - intersection

    return intersection / union if union > 0 else 0.0


def match_boxes(
    expected: list[BBox],
    actual: list[BBox],
    min_iou: float,
) -> tuple[int, int, int]:
    """Casamento guloso por maior IoU. Cada caixa detectada casa no maximo uma vez."""
    available = list(range(len(actual)))
    matched = 0

    for expected_box in expected:
        best_index: int | None = None
        best_score = min_iou

        for index in available:
            score = iou(expected_box, actual[index])
            if score >= best_score:
                best_score = score
                best_index = index

        if best_index is not None:
            available.remove(best_index)
            matched += 1

    return matched, len(expected) - matched, len(available)


def recall(matched: int, missed: int) -> float:
    total = matched + missed
    return 1.0 if total == 0 else matched / total


def precision(matched: int, spurious: int) -> float:
    total = matched + spurious
    return 1.0 if total == 0 else matched / total
```

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_calibration_metrics.py -v`
Expected: PASS, 6 testes.

- [ ] **Step 5: Escrever o schema do formato v2**

Create `calibration/schema.md`:

```markdown
# Formato de calibracao v2

Coordenadas sempre em pontos PDF (`pt`), origem no canto superior esquerdo da pagina,
como devolvido por PyMuPDF. Nunca em pixels de render.

```yaml
version: 2
status: draft_unverified      # draft_unverified | human_verified
verified_by: null             # preenchido na revisao humana
verified_at: null
document:
  filename: Proj_Estrutural_RanchoQueimado_geral.pdf
  page_count: 28
thresholds:
  content_block_recall: 0.85
  content_block_iou: 0.50
  view_attribute_accuracy: 0.90
  finding_coverage: 0.60
  finding_precision: 0.70
sheets:
  - page_index: 4
    sheet_code: EST-0050-A
    sheet_type: planta_formas
    status: draft_unverified   # por folha: permite verificar folha a folha
    content_regions:
      - kind: moldura          # moldura | carimbo | drawing_zone | table | note_block | legend
        bbox: [71, 29, 2356, 1656]
    views:
      - view_id: v1            # estavel dentro da folha, atribuido pelo revisor
        view_kind: plan        # plan | section | detail
        identifier: null       # o "1" de "1 CORTE A-A"
        title: PLANTA DE FORMAS - TERREO
        declared_scale: "1:50"
        level: null            # ex.: "-0.05"
        bbox: [180, 120, 1700, 1560]
    expected_findings:
      - rule_id: forms.view.scale_declared
        view_id: v1
        severity: medium
```

## Regra de status

`status: draft_unverified` significa que o conteudo foi gerado pelo pipeline e **nao** e verdade
humana. Metricas medidas contra um documento nesse estado detectam regressao, mas nao provam
correcao. Somente um revisor humano muda para `human_verified`, preenchendo `verified_by` e
`verified_at`.

Nenhuma fase pode ser declarada concluida citando metricas de um gabarito `draft_unverified`.
```

- [ ] **Step 6: Migrar o gabarito existente para v2**

Rodar o script abaixo, que **preserva** os valores de codigo e tipo ja presentes no arquivo v1 e
acrescenta a estrutura v2 vazia, marcando tudo como draft:

```bash
.venv/Scripts/python - <<'PY'
import pathlib, yaml

source = pathlib.Path("calibration/rancho-queimado-r01.yml")
old = yaml.safe_load(source.read_text(encoding="utf-8"))

document = {
    "version": 2,
    "status": "draft_unverified",
    "verified_by": None,
    "verified_at": None,
    "document": old["document"],
    "thresholds": {
        "content_block_recall": 0.85,
        "content_block_iou": 0.50,
        "view_attribute_accuracy": 0.90,
        "finding_coverage": 0.60,
        "finding_precision": 0.70,
        "sheet_type_accuracy": old.get("minimum_type_accuracy", 0.90),
        "sheet_code_coverage": old.get("minimum_code_coverage", 0.95),
    },
    "sheets": [
        {
            "page_index": sheet["page_index"],
            "sheet_code": sheet["sheet_code"],
            "sheet_type": sheet["sheet_type"],
            "status": "draft_unverified",
            "content_regions": [],
            "views": [],
            "expected_findings": [],
        }
        for sheet in old["sheets"]
    ],
}

source.write_text(
    yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
    encoding="utf-8",
)
print("migrado para v2:", len(document["sheets"]), "folhas")
PY
```

Expected: `migrado para v2: 28 folhas`

- [ ] **Step 7: Adaptar o teste de calibracao ao v2**

Substituir em `apps/api/tests/test_calibration.py` as duas ultimas assercoes por leitura dos
thresholds do novo local, e adicionar a guarda de ground truth:

```python
    thresholds = expected["thresholds"]
    assert type_accuracy >= thresholds["sheet_type_accuracy"]
    assert code_coverage >= thresholds["sheet_code_coverage"]

    if expected["status"] != "human_verified":
        print(
            "AVISO: gabarito em draft_unverified. As metricas acima detectam regressao, "
            "mas nao provam correcao."
        )
```

- [ ] **Step 8: Rodar a suite inteira**

Run: `.venv/Scripts/python -m pytest apps/api/tests -q`
Expected: PASS, sem regressao.

- [ ] **Step 9: Commit**

```bash
git add calibration/ apps/api/truss_api/calibration/ apps/api/tests/test_calibration_metrics.py apps/api/tests/test_calibration.py
git commit -m "feat: calibration format v2 with IoU metrics and draft ground truth guard"
```

**Risco de migracao:** nenhum. O arquivo de calibracao nao e lido por codigo de producao.

**Criterio de conclusao:** `calibration/rancho-queimado-r01.yml` esta em v2 com as 28 folhas
preservadas, marcado `draft_unverified`, e as metricas de IoU tem teste verde.

---

### Task 2: Extracao rica com artefato comprimido

**Files:**
- Create: `apps/api/truss_api/sheetmap/primitives.py`
- Create: `apps/api/truss_api/sheetmap/artifacts.py`
- Modify: `apps/api/truss_api/sheetmap/geometry.py`
- Test: `apps/api/tests/test_extraction.py`

**Interfaces:**
- Consumes: `Settings`
- Produces:
  - `VectorPrimitive` dataclass: `kind: str` (`"l"`, `"c"`, `"re"`, `"qu"`), `points: list[tuple[float, float]]`, `rect: tuple[float, float, float, float]`, `width: float | None`, `color: tuple[float, ...] | None`, `dashes: str | None`
  - `TextSpanRecord` dataclass: `text: str`, `bbox: tuple[float, float, float, float]`, `font: str`, `size: float`, `dir: tuple[float, float]`
  - `PageMetadata` dataclass: `width_pt: float`, `height_pt: float`, `rotation: int`, `mediabox: tuple[float, float, float, float]`, `cropbox: tuple[float, float, float, float]`, `rotation_matrix: tuple[float, ...]`
  - `PageExtraction` dataclass: `metadata: PageMetadata`, `primitives: list[VectorPrimitive]`, `spans: list[TextSpanRecord]`
  - `extract_page(page: fitz.Page) -> PageExtraction`
  - `EXTRACTOR_VERSION: str = "extract-v0.2"`
  - `artifact_hash(extraction: PageExtraction) -> str` - sha256 dos 16 primeiros bytes hex do payload canonico
  - `write_extraction(extraction, *, project_id, revision_id, sheet_id, settings) -> str` - grava `.json.gz`, devolve caminho relativo
  - `read_extraction(relative_path: str, settings: Settings) -> PageExtraction`

- [ ] **Step 1: Escrever o teste**

Create `apps/api/tests/test_extraction.py`:

```python
from pathlib import Path

import fitz
import pytest

from truss_api.core.settings import Settings
from truss_api.sheetmap.artifacts import (
    artifact_hash,
    read_extraction,
    write_extraction,
)
from truss_api.sheetmap.primitives import extract_page


def _page(rotation: int = 0) -> fitz.Page:
    document = fitz.open()
    page = document.new_page(width=1000, height=800)
    page.draw_rect(fitz.Rect(20, 10, 970, 770), color=(0, 0, 0), width=2)
    page.draw_line(fitz.Point(100, 100), fitz.Point(400, 400))
    page.insert_text((120, 200), "PLANTA DE FORMAS", fontsize=16)
    page.insert_text((120, 240), "ESCALA 1:50", fontsize=6)
    if rotation:
        page.set_rotation(rotation)
    return page


def test_extraction_keeps_line_primitives_not_just_bounding_boxes() -> None:
    extraction = extract_page(_page())

    line_primitives = [p for p in extraction.primitives if p.kind == "l"]
    assert line_primitives, "linhas devem ser preservadas, nao apenas bboxes"
    assert all(len(p.points) >= 2 for p in line_primitives)


def test_extraction_keeps_span_font_size_used_to_tell_title_from_dimension() -> None:
    extraction = extract_page(_page())

    sizes = {round(span.size) for span in extraction.spans}
    assert 16 in sizes
    assert 6 in sizes


def test_extraction_records_page_coordinate_system() -> None:
    metadata = extract_page(_page()).metadata

    assert metadata.rotation == 0
    assert metadata.mediabox == (0.0, 0.0, 1000.0, 800.0)
    assert metadata.cropbox == metadata.mediabox


def test_extraction_records_rotation_when_page_is_rotated() -> None:
    """O material real tem rotation=0 em todas as paginas; so fixture sintetica cobre isso."""
    metadata = extract_page(_page(rotation=90)).metadata

    assert metadata.rotation == 90
    assert metadata.width_pt == 800.0
    assert metadata.height_pt == 1000.0


def test_artifact_hash_is_stable_and_content_addressed() -> None:
    first = extract_page(_page())
    second = extract_page(_page())

    assert artifact_hash(first) == artifact_hash(second)
    assert len(artifact_hash(first)) == 16


def test_write_and_read_roundtrip_uses_gzip(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data")
    extraction = extract_page(_page())

    relative = write_extraction(
        extraction,
        project_id="p",
        revision_id="r",
        sheet_id="s",
        settings=settings,
    )
    restored = read_extraction(relative, settings)

    assert relative.endswith(".json.gz")
    assert (settings.data_dir / relative).exists()
    assert len(restored.primitives) == len(extraction.primitives)
    assert len(restored.spans) == len(extraction.spans)
    assert restored.metadata == extraction.metadata
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_extraction.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'truss_api.sheetmap.primitives'`

- [ ] **Step 3: Implementar as primitivas**

Create `apps/api/truss_api/sheetmap/primitives.py`:

```python
from dataclasses import dataclass, field

import fitz


EXTRACTOR_VERSION = "extract-v0.2"


@dataclass(frozen=True)
class VectorPrimitive:
    kind: str
    points: list[tuple[float, float]]
    rect: tuple[float, float, float, float]
    width: float | None = None
    color: tuple[float, ...] | None = None
    dashes: str | None = None


@dataclass(frozen=True)
class TextSpanRecord:
    text: str
    bbox: tuple[float, float, float, float]
    font: str
    size: float
    dir: tuple[float, float]


@dataclass(frozen=True)
class PageMetadata:
    width_pt: float
    height_pt: float
    rotation: int
    mediabox: tuple[float, float, float, float]
    cropbox: tuple[float, float, float, float]
    rotation_matrix: tuple[float, ...]


@dataclass(frozen=True)
class PageExtraction:
    metadata: PageMetadata
    primitives: list[VectorPrimitive] = field(default_factory=list)
    spans: list[TextSpanRecord] = field(default_factory=list)


def _rect_tuple(rect: fitz.Rect) -> tuple[float, float, float, float]:
    return (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))


def _page_metadata(page: fitz.Page) -> PageMetadata:
    rect = page.rect
    return PageMetadata(
        width_pt=float(rect.width),
        height_pt=float(rect.height),
        rotation=int(page.rotation),
        mediabox=_rect_tuple(page.mediabox),
        cropbox=_rect_tuple(page.cropbox),
        rotation_matrix=tuple(round(float(v), 6) for v in page.rotation_matrix),
    )


def _primitives(page: fitz.Page) -> list[VectorPrimitive]:
    primitives: list[VectorPrimitive] = []

    for drawing in page.get_drawings():
        bounds = _rect_tuple(drawing["rect"])
        width = drawing.get("width")
        color = drawing.get("color")
        dashes = drawing.get("dashes")

        for item in drawing["items"]:
            points = [
                (round(float(value.x), 3), round(float(value.y), 3))
                for value in item[1:]
                if hasattr(value, "x")
            ]
            primitives.append(
                VectorPrimitive(
                    kind=str(item[0]),
                    points=points,
                    rect=bounds,
                    width=float(width) if width is not None else None,
                    color=tuple(float(c) for c in color) if color else None,
                    dashes=str(dashes) if dashes else None,
                )
            )

    return primitives


def _spans(page: fitz.Page) -> list[TextSpanRecord]:
    records: list[TextSpanRecord] = []

    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            direction = line.get("dir", (1.0, 0.0))
            for span in line["spans"]:
                text = str(span["text"]).strip()
                if not text:
                    continue

                x0, y0, x1, y1 = span["bbox"]
                records.append(
                    TextSpanRecord(
                        text=text,
                        bbox=(float(x0), float(y0), float(x1), float(y1)),
                        font=str(span.get("font", "")),
                        size=round(float(span.get("size", 0.0)), 2),
                        dir=(float(direction[0]), float(direction[1])),
                    )
                )

    return records


def extract_page(page: fitz.Page) -> PageExtraction:
    return PageExtraction(
        metadata=_page_metadata(page),
        primitives=_primitives(page),
        spans=_spans(page),
    )
```

- [ ] **Step 4: Implementar o artefato comprimido**

Create `apps/api/truss_api/sheetmap/artifacts.py`:

```python
from dataclasses import asdict
import gzip
from hashlib import sha256
import json
from pathlib import Path

from truss_api.core.settings import Settings
from truss_api.sheetmap.primitives import (
    EXTRACTOR_VERSION,
    PageExtraction,
    PageMetadata,
    TextSpanRecord,
    VectorPrimitive,
)


GZIP_LEVEL = 6


def _payload(extraction: PageExtraction) -> dict[str, object]:
    return {
        "extractor_version": EXTRACTOR_VERSION,
        "metadata": asdict(extraction.metadata),
        "primitives": [asdict(primitive) for primitive in extraction.primitives],
        "spans": [asdict(span) for span in extraction.spans],
    }


def artifact_hash(extraction: PageExtraction) -> str:
    canonical = json.dumps(_payload(extraction), sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()[:16]


def extraction_relative_path(
    project_id: str,
    revision_id: str,
    sheet_id: str,
    content_hash: str,
) -> str:
    return f"geometry/{project_id}/{revision_id}/{sheet_id}.{content_hash}.json.gz"


def write_extraction(
    extraction: PageExtraction,
    *,
    project_id: str,
    revision_id: str,
    sheet_id: str,
    settings: Settings,
) -> str:
    content_hash = artifact_hash(extraction)
    relative = extraction_relative_path(project_id, revision_id, sheet_id, content_hash)
    target = settings.data_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)

    # Enderecado por conteudo: se o arquivo ja existe, ele e identico por definicao.
    if not target.exists():
        raw = json.dumps(_payload(extraction), separators=(",", ":")).encode("utf-8")
        target.write_bytes(gzip.compress(raw, GZIP_LEVEL))

    return relative


def read_extraction(relative_path: str, settings: Settings) -> PageExtraction:
    source = Path(settings.data_dir / relative_path)
    payload = json.loads(gzip.decompress(source.read_bytes()).decode("utf-8"))

    return PageExtraction(
        metadata=PageMetadata(
            width_pt=payload["metadata"]["width_pt"],
            height_pt=payload["metadata"]["height_pt"],
            rotation=payload["metadata"]["rotation"],
            mediabox=tuple(payload["metadata"]["mediabox"]),
            cropbox=tuple(payload["metadata"]["cropbox"]),
            rotation_matrix=tuple(payload["metadata"]["rotation_matrix"]),
        ),
        primitives=[
            VectorPrimitive(
                kind=item["kind"],
                points=[tuple(point) for point in item["points"]],
                rect=tuple(item["rect"]),
                width=item["width"],
                color=tuple(item["color"]) if item["color"] else None,
                dashes=item["dashes"],
            )
            for item in payload["primitives"]
        ],
        spans=[
            TextSpanRecord(
                text=item["text"],
                bbox=tuple(item["bbox"]),
                font=item["font"],
                size=item["size"],
                dir=tuple(item["dir"]),
            )
            for item in payload["spans"]
        ],
    )
```

- [ ] **Step 5: Derivar `PageGeometry` da extracao completa**

Em `apps/api/truss_api/sheetmap/geometry.py`, acrescentar ao final, preservando tudo que ja existe:

```python
from truss_api.sheetmap.primitives import PageExtraction


def geometry_from_extraction(extraction: PageExtraction) -> PageGeometry:
    """Vista reduzida usada pela deteccao de regioes. As primitivas completas
    seguem disponiveis no artefato em disco."""
    page_area = extraction.metadata.width_pt * extraction.metadata.height_pt
    minimum_area = page_area * 0.0002
    seen: set[tuple[float, float, float, float]] = set()
    rects: list[GeometryRect] = []

    for primitive in extraction.primitives:
        if primitive.rect in seen:
            continue

        seen.add(primitive.rect)
        x0, y0, x1, y1 = primitive.rect
        if (x1 - x0) * (y1 - y0) < minimum_area:
            continue

        rects.append(GeometryRect(x0=x0, y0=y0, x1=x1, y1=y1))

    return PageGeometry(
        width_pt=extraction.metadata.width_pt,
        height_pt=extraction.metadata.height_pt,
        rects=rects,
        line_count=sum(1 for p in extraction.primitives if p.kind == "l"),
        curve_count=sum(1 for p in extraction.primitives if p.kind == "c"),
    )
```

- [ ] **Step 6: Rodar os testes**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_extraction.py -v`
Expected: PASS, 6 testes.

- [ ] **Step 7: Medir o custo real no PDF do projeto**

Run:

```bash
.venv/Scripts/python -c "
import sys, time; sys.path.insert(0,'apps/api')
import fitz
from truss_api.core.settings import Settings
from truss_api.sheetmap.primitives import extract_page
from truss_api.sheetmap.artifacts import write_extraction
from pathlib import Path
import tempfile

path='data/originals/69f87430-6e60-4cd5-bfb8-c4cde0b09d79/09e35528-5556-4fce-939e-806897d7bbb1/7d2f9c32bc9d4988-Proj_Estrutural_RanchoQueimado_geral.pdf'
with tempfile.TemporaryDirectory() as tmp:
    settings = Settings(data_dir=Path(tmp))
    document = fitz.open(path)
    start = time.time()
    total = 0
    for index in range(document.page_count):
        extraction = extract_page(document.load_page(index))
        relative = write_extraction(extraction, project_id='p', revision_id='r', sheet_id=f's{index}', settings=settings)
        total += (settings.data_dir / relative).stat().st_size
    print(f'28 paginas em {time.time()-start:.1f}s | artefatos {total/1e6:.1f} MB')
"
```

Expected: tempo abaixo de 90 segundos e total abaixo de 60 MB. Se o tempo estourar, registrar a
divida tecnica de extracao preguicosa em `docs/DECISIONS.md` e **nao** expandir o escopo aqui.

- [ ] **Step 8: Commit**

```bash
git add apps/api/truss_api/sheetmap/primitives.py apps/api/truss_api/sheetmap/artifacts.py apps/api/truss_api/sheetmap/geometry.py apps/api/tests/test_extraction.py
git commit -m "feat: rich vector and text extraction stored as content-addressed gzip"
```

**Risco de migracao:** nenhum no banco. Em disco, o caminho antigo `geometry/{p}/{r}/{s}.json`
continua existindo e nao e lido por este codigo novo; a Task 3 passa a gravar o formato novo.

**Criterio de conclusao:** primitivas, spans e metadados de pagina persistidos comprimidos e
enderecados por hash, com roundtrip verde e custo medido no material real.

---

### Task 3: Migration 003 - views, regras e rastreabilidade

**Files:**
- Create: `apps/api/truss_api/db/migrations/003_views_rules_traceability.sql`
- Test: `apps/api/tests/test_migrations.py`

**Interfaces:**
- Produces: tabelas `sheet_views` e `rule_evaluations`; colunas novas em `findings`, `sheet_maps` e `audit_runs`.

- [ ] **Step 1: Escrever o teste de preservacao de dados**

Acrescentar em `apps/api/tests/test_migrations.py`:

```python
def test_migration_003_is_additive_and_preserves_existing_rows(tmp_path: Path) -> None:
    """A migration nao pode perder sheets, sheet_maps nem findings ja gravados."""
    settings = Settings(data_dir=tmp_path / "data")
    baseline_dir = (
        Path(__file__).resolve().parents[1] / "truss_api" / "db" / "migrations"
    )

    apply_migrations(settings, directory=baseline_dir)

    with transaction(settings) as connection:
        connection.execute(
            "INSERT INTO projects (id, name, description, created_at, updated_at)"
            " VALUES ('p1', 'Obra', '', '2026-01-01', '2026-01-01')"
        )
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(findings)")
        }
        tables = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert {"rule_id", "rule_version", "view_id", "source_layer", "dedupe_key"} <= columns
    assert {"sheet_views", "rule_evaluations"} <= tables

    # reaplicar nao pode destruir nada
    apply_migrations(settings, directory=baseline_dir)
    with transaction(settings) as connection:
        row = connection.execute("SELECT name FROM projects WHERE id = 'p1'").fetchone()
    assert row is not None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_migrations.py -v`
Expected: FAIL na assercao das colunas de `findings`.

- [ ] **Step 3: Escrever a migration**

Create `apps/api/truss_api/db/migrations/003_views_rules_traceability.sql`:

```sql
CREATE TABLE IF NOT EXISTS sheet_views (
    id TEXT PRIMARY KEY,
    sheet_map_id TEXT NOT NULL,
    region_id TEXT,
    view_kind TEXT NOT NULL,
    identifier TEXT,
    title TEXT,
    declared_scale TEXT,
    level TEXT,
    x0 REAL NOT NULL,
    y0 REAL NOT NULL,
    x1 REAL NOT NULL,
    y1 REAL NOT NULL,
    confidence REAL NOT NULL,
    provenance TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (sheet_map_id) REFERENCES sheet_maps(id) ON DELETE CASCADE,
    FOREIGN KEY (region_id) REFERENCES sheet_regions(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_sheet_views_map
ON sheet_views(sheet_map_id, view_kind);

CREATE TABLE IF NOT EXISTS rule_evaluations (
    id TEXT PRIMARY KEY,
    audit_run_id TEXT NOT NULL,
    sheet_map_id TEXT NOT NULL,
    sheet_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    rule_pack_version TEXT NOT NULL,
    target_kind TEXT NOT NULL,
    target_id TEXT,
    outcome TEXT NOT NULL,
    confidence REAL NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (audit_run_id) REFERENCES audit_runs(id) ON DELETE RESTRICT,
    FOREIGN KEY (sheet_map_id) REFERENCES sheet_maps(id) ON DELETE RESTRICT,
    FOREIGN KEY (sheet_id) REFERENCES sheets(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_rule_evaluations_run
ON rule_evaluations(audit_run_id, outcome);

CREATE INDEX IF NOT EXISTS idx_rule_evaluations_rule
ON rule_evaluations(rule_id, rule_version);

ALTER TABLE findings ADD COLUMN rule_id TEXT;
ALTER TABLE findings ADD COLUMN rule_version TEXT;
ALTER TABLE findings ADD COLUMN sheet_map_id TEXT;
ALTER TABLE findings ADD COLUMN view_id TEXT;
ALTER TABLE findings ADD COLUMN source_layer TEXT;
ALTER TABLE findings ADD COLUMN dedupe_key TEXT;

CREATE INDEX IF NOT EXISTS idx_findings_dedupe
ON findings(sheet_id, dedupe_key);

ALTER TABLE sheet_maps ADD COLUMN snapshot_hash TEXT;
ALTER TABLE sheet_maps ADD COLUMN extractor_version TEXT;
ALTER TABLE sheet_maps ADD COLUMN document_hash TEXT;

ALTER TABLE audit_runs ADD COLUMN sheet_map_id TEXT;
ALTER TABLE audit_runs ADD COLUMN rule_pack_version TEXT;
ALTER TABLE audit_runs ADD COLUMN coverage_json TEXT NOT NULL DEFAULT '{}';

-- Findings anteriores a F2 nao tem rastreabilidade e nao podem ser confundidos
-- com findings de regra. Feedback humano neles e preservado.
UPDATE findings SET source_layer = 'legacy' WHERE source_layer IS NULL;
```

- [ ] **Step 4: Rodar o teste**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_migrations.py -v`
Expected: PASS.

- [ ] **Step 5: Aplicar no banco real e conferir preservacao**

Run:

```bash
cp data/db/truss.sqlite data/db/truss.sqlite.pre-f2
.venv/Scripts/python -c "
import sys; sys.path.insert(0,'apps/api')
from truss_api.db.schema import initialize_database
initialize_database(); print('migration aplicada')
"
.venv/Scripts/python -c "
import sqlite3
c = sqlite3.connect('data/db/truss.sqlite')
print('sheets:', c.execute('select count(*) from sheets').fetchone()[0])
print('sheet_maps:', c.execute('select count(*) from sheet_maps').fetchone()[0])
print('findings:', c.execute('select count(*) from findings').fetchone()[0])
print('findings legacy:', c.execute(\"select count(*) from findings where source_layer='legacy'\").fetchone()[0])
print('confirmados/rejeitados preservados:', c.execute(\"select count(*) from findings where status in ('confirmed','rejected')\").fetchone()[0])
print('migrations:', [r[0] for r in c.execute('select version from schema_migrations')])
"
```

Expected: `sheets: 85`, `sheet_maps: 85`, `findings: 63`, `findings legacy: 63`,
`confirmados/rejeitados preservados: 2`, `migrations: ['001', '002', '003']`

- [ ] **Step 6: Commit**

```bash
git add apps/api/truss_api/db/migrations/003_views_rules_traceability.sql apps/api/tests/test_migrations.py
git commit -m "feat: add views, rule evaluations and finding traceability schema"
```

**Risco de migracao:** medio. Sao seis `ALTER TABLE ADD COLUMN` em `findings`, que em SQLite sao
operacoes de metadados e nao reescrevem linhas. O `UPDATE` de `source_layer` toca as 63 linhas
existentes mas nao altera `status` nem `rejection_reason`. O backup em `truss.sqlite.pre-f2` no
Step 5 e a rede de seguranca; remove-lo apenas ao fim da fase.

**Criterio de conclusao:** as 85 sheets, os 85 sheet_maps e os 63 findings intactos, com os 2
findings validados por humano preservados com status original.

---

### Task 4: Snapshot imutavel do Sheet Map

**Files:**
- Create: `apps/api/truss_api/sheetmap/snapshot.py`
- Modify: `apps/api/truss_api/sheetmap/repository.py`
- Test: `apps/api/tests/test_sheetmap_builder.py`

**Interfaces:**
- Consumes: `DetectedRegion` (Task 6), `DetectedView` (Task 7), `EXTRACTOR_VERSION`
- Produces:
  - `SHEET_MAP_PIPELINE = "sheetmap-v0.2"`
  - `snapshot_hash(*, sheet_type, sheet_code, title_block, regions, views, extraction_hash) -> str`
  - `pipeline_version_for(content_hash: str) -> str` devolve `"sheetmap-v0.2+<hash>"`
  - `save_sheet_map(...)` mantem a assinatura atual e ganha os parametros nomeados
    `views: list[DetectedView]`, `snapshot_hash: str`, `extractor_version: str`, `document_hash: str`
  - `get_sheet_map(sheet_id, settings)` passa a devolver o snapshot mais recente e inclui `views`
  - `get_sheet_map_by_id(sheet_map_id, settings) -> dict[str, object]`

- [ ] **Step 1: Escrever o teste de imutabilidade**

Acrescentar em `apps/api/tests/test_sheetmap_builder.py`:

```python
def test_rebuilding_the_same_input_reuses_the_snapshot(
    settings: Settings, document: dict[str, object]
) -> None:
    first = build_sheet_map_for_document(str(document["id"]), settings)
    second = build_sheet_map_for_document(str(document["id"]), settings)

    assert [item["id"] for item in first] == [item["id"] for item in second]

    with transaction(settings) as connection:
        total = connection.execute("SELECT COUNT(*) FROM sheet_maps").fetchone()[0]
    assert total == len(first), "reprocessar entrada identica nao pode criar snapshot novo"


def test_previous_snapshot_survives_a_pipeline_change(
    settings: Settings, document: dict[str, object]
) -> None:
    """Um Sheet Map referenciado por auditoria nunca pode ser apagado."""
    built = build_sheet_map_for_document(str(document["id"]), settings)
    original_id = str(built[0]["id"])

    sheet = document["sheets"][0]
    sheetmap_repository.save_sheet_map(
        sheet_id=str(sheet["id"]),
        project_id=str(sheet["project_id"]),
        revision_id=str(sheet["revision_id"]),
        geometry_path="geometry/p/r/s.other.json.gz",
        sheet_code="EST-0010-A",
        sheet_type="planta_formas",
        paper_format="A1",
        orientation="paisagem",
        title_block={},
        regions=[],
        views=[],
        snapshot_hash="0000000000000001",
        extractor_version="extract-v0.2",
        document_hash="abc",
        settings=settings,
    )

    with transaction(settings) as connection:
        rows = connection.execute(
            "SELECT id FROM sheet_maps WHERE sheet_id = ?", (str(sheet["id"]),)
        ).fetchall()

    assert original_id in {str(row["id"]) for row in rows}
    assert len(rows) == 2
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_sheetmap_builder.py -v`
Expected: FAIL - o `DELETE` atual remove o snapshot anterior e `save_sheet_map` nao aceita
`views`, `snapshot_hash`, `extractor_version` nem `document_hash`.

- [ ] **Step 3: Criar os modelos de view usados pelo repositorio**

A Task 4 persiste views, entao os modelos precisam existir antes dela. Create
`apps/api/truss_api/sheetmap/views/__init__.py` vazio e
`apps/api/truss_api/sheetmap/views/models.py`:

```python
from dataclasses import dataclass


VIEW_KIND_PLAN = "plan"
VIEW_KIND_SECTION = "section"
VIEW_KIND_DETAIL = "detail"

BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class DetectedView:
    view_kind: str
    identifier: str | None
    title: str | None
    declared_scale: str | None
    level: str | None
    bbox: BBox
    confidence: float
    provenance: str


@dataclass(frozen=True)
class ScaleAnchor:
    text: str
    scale: str
    bbox: BBox
    size: float


@dataclass(frozen=True)
class TitleCandidate:
    identifier: str | None
    title: str
    bbox: BBox
    size: float
```

- [ ] **Step 4: Implementar o hash de snapshot**

Create `apps/api/truss_api/sheetmap/snapshot.py`:

```python
from dataclasses import asdict, is_dataclass
from hashlib import sha256
import json
from typing import Any


SHEET_MAP_PIPELINE = "sheetmap-v0.2"


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    return value


def snapshot_hash(
    *,
    sheet_type: str,
    sheet_code: str | None,
    title_block: dict[str, object],
    regions: list[object],
    views: list[object],
    extraction_hash: str,
) -> str:
    canonical = json.dumps(
        {
            "pipeline": SHEET_MAP_PIPELINE,
            "extraction": extraction_hash,
            "sheet_type": sheet_type,
            "sheet_code": sheet_code,
            "title_block": _plain(title_block),
            "regions": _plain(regions),
            "views": _plain(views),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()[:16]


def pipeline_version_for(content_hash: str) -> str:
    return f"{SHEET_MAP_PIPELINE}+{content_hash}"
```

- [ ] **Step 5: Tornar o repositorio imutavel**

Em `apps/api/truss_api/sheetmap/repository.py`, substituir os dois `DELETE` do inicio de
`save_sheet_map` por reutilizacao, e persistir views. O corpo passa a ser:

```python
def save_sheet_map(
    *,
    sheet_id: str,
    project_id: str,
    revision_id: str,
    geometry_path: str,
    sheet_code: str | None,
    sheet_type: str,
    paper_format: str,
    orientation: str,
    title_block: dict[str, object],
    regions: list[DetectedRegion],
    views: list[DetectedView],
    snapshot_hash: str,
    extractor_version: str,
    document_hash: str,
    settings: Settings,
) -> dict[str, object]:
    pipeline_version = pipeline_version_for(snapshot_hash)
    sheet_map_id = str(uuid4())
    built_at = _now()

    with transaction(settings) as connection:
        existing = connection.execute(
            "SELECT id FROM sheet_maps WHERE sheet_id = ? AND pipeline_version = ?",
            (sheet_id, pipeline_version),
        ).fetchone()

        # Snapshot e enderecado por conteudo: entrada identica reutiliza a linha
        # existente. Nada e apagado, porque auditorias podem referencia-la.
        if existing is not None:
            return get_sheet_map_by_id(str(existing["id"]), settings)

        connection.execute(
            """
            INSERT INTO sheet_maps (
                id, sheet_id, project_id, revision_id, pipeline_version, status,
                geometry_path, sheet_code, sheet_type, paper_format, orientation,
                title_block_json, built_at, snapshot_hash, extractor_version, document_hash
            ) VALUES (?, ?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sheet_map_id,
                sheet_id,
                project_id,
                revision_id,
                pipeline_version,
                geometry_path,
                sheet_code,
                sheet_type,
                paper_format,
                orientation,
                json.dumps(title_block),
                built_at,
                snapshot_hash,
                extractor_version,
                document_hash,
            ),
        )

        for region in regions:
            connection.execute(
                """
                INSERT INTO sheet_regions (
                    id, sheet_map_id, region_kind, x0, y0, x1, y1, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    sheet_map_id,
                    region.region_kind,
                    region.x0,
                    region.y0,
                    region.x1,
                    region.y1,
                    region.confidence,
                    built_at,
                ),
            )

        for view in views:
            connection.execute(
                """
                INSERT INTO sheet_views (
                    id, sheet_map_id, region_id, view_kind, identifier, title,
                    declared_scale, level, x0, y0, x1, y1, confidence, provenance, created_at
                ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    sheet_map_id,
                    view.view_kind,
                    view.identifier,
                    view.title,
                    view.declared_scale,
                    view.level,
                    view.bbox[0],
                    view.bbox[1],
                    view.bbox[2],
                    view.bbox[3],
                    view.confidence,
                    view.provenance,
                    built_at,
                ),
            )

    return get_sheet_map_by_id(sheet_map_id, settings)
```

E acrescentar, substituindo `get_sheet_map`:

```python
def _load(connection, row) -> dict[str, object]:
    sheet_map = dict(row)
    sheet_map["title_block"] = json.loads(str(row["title_block_json"]))
    sheet_map["regions"] = [
        dict(item)
        for item in connection.execute(
            """
            SELECT id, region_kind, x0, y0, x1, y1, confidence
            FROM sheet_regions WHERE sheet_map_id = ? ORDER BY region_kind
            """,
            (str(row["id"]),),
        ).fetchall()
    ]
    sheet_map["views"] = [
        dict(item)
        for item in connection.execute(
            """
            SELECT id, view_kind, identifier, title, declared_scale, level,
                   x0, y0, x1, y1, confidence, provenance
            FROM sheet_views WHERE sheet_map_id = ? ORDER BY y0, x0
            """,
            (str(row["id"]),),
        ).fetchall()
    ]
    return sheet_map


def get_sheet_map_by_id(sheet_map_id: str, settings: Settings) -> dict[str, object]:
    with transaction(settings) as connection:
        row = connection.execute(
            "SELECT * FROM sheet_maps WHERE id = ?", (sheet_map_id,)
        ).fetchone()

        if row is None:
            raise SheetMapNotFoundError(sheet_map_id)

        return _load(connection, row)


def get_sheet_map(sheet_id: str, settings: Settings) -> dict[str, object]:
    """Snapshot corrente da folha: o mais recente do pipeline atual."""
    with transaction(settings) as connection:
        row = connection.execute(
            """
            SELECT * FROM sheet_maps
            WHERE sheet_id = ? AND pipeline_version LIKE ?
            ORDER BY built_at DESC LIMIT 1
            """,
            (sheet_id, f"{SHEET_MAP_PIPELINE}%"),
        ).fetchone()

        if row is None:
            raise SheetMapNotFoundError(sheet_id)

        return _load(connection, row)
```

Acrescentar aos imports do arquivo:

```python
from truss_api.sheetmap.snapshot import SHEET_MAP_PIPELINE, pipeline_version_for
from truss_api.sheetmap.views.models import DetectedView
```

e remover a constante `PIPELINE_VERSION` antiga, substituindo seus usos por `SHEET_MAP_PIPELINE`.

- [ ] **Step 6: Rodar os testes**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_sheetmap_builder.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/truss_api/sheetmap/views/ apps/api/truss_api/sheetmap/snapshot.py apps/api/truss_api/sheetmap/repository.py apps/api/tests/test_sheetmap_builder.py
git commit -m "feat: content-addressed immutable sheet map snapshots"
```

**Risco de migracao:** os 85 sheet_maps existentes tem `pipeline_version = "sheetmap-v0.1"`, que
nao casa com o `LIKE 'sheetmap-v0.2%'` de `get_sheet_map`. Eles permanecem na tabela, intactos,
mas deixam de ser servidos ate a folha ser reprocessada. Isso e intencional e reversivel; a Task
10 reprocessa as 85 folhas.

**Criterio de conclusao:** reprocessar entrada identica nao cria linha nova; mudar a entrada cria
snapshot novo sem apagar o anterior.

---

### Task 5: Ancoras de view - escala, titulo, nivel e identificador

O reconhecimento textual e separado da segmentacao geometrica porque foi medido que a associacao
e o ponto fragil: a regra ingenua acerta 35%. Isolar as ancoras permite testar e ajustar
tolerancias sem mexer no segmentador.

**Files:**
- Create: `apps/api/truss_api/sheetmap/views/anchors.py`
- Modify: `apps/api/truss_api/sheetmap/views/models.py` (criado na Task 4; sem alteracao se ja completo)
- Test: `apps/api/tests/test_view_detection.py`

**Interfaces:**
- Consumes: `TextSpanRecord` (Task 2), `normalize` de `truss_api.core.text`
- Produces:
  - `VIEW_KIND_PLAN = "plan"`, `VIEW_KIND_SECTION = "section"`, `VIEW_KIND_DETAIL = "detail"`
  - `DetectedView` dataclass: `view_kind: str`, `identifier: str | None`, `title: str | None`, `declared_scale: str | None`, `level: str | None`, `bbox: tuple[float, float, float, float]`, `confidence: float`, `provenance: str`
  - `ScaleAnchor` dataclass: `text: str`, `scale: str`, `bbox: tuple[float, float, float, float]`, `size: float`
  - `TitleCandidate` dataclass: `identifier: str | None`, `title: str`, `bbox: tuple[float, float, float, float]`, `size: float`
  - `find_scale_anchors(spans: list[TextSpanRecord], exclude: tuple[float, float, float, float] | None) -> list[ScaleAnchor]`
  - `title_font_floor(spans: list[TextSpanRecord]) -> float`
  - `find_title_for(anchor: ScaleAnchor, spans: list[TextSpanRecord], font_floor: float) -> TitleCandidate | None`
  - `find_level_near(bbox, spans: list[TextSpanRecord]) -> str | None`
  - `view_kind_from_title(title: str | None) -> str`

- [ ] **Step 1: Escrever o teste**

Create `apps/api/tests/test_view_detection.py`:

```python
from truss_api.sheetmap.primitives import TextSpanRecord
from truss_api.sheetmap.views.anchors import (
    find_level_near,
    find_scale_anchors,
    find_title_for,
    title_font_floor,
    view_kind_from_title,
)


def _span(text: str, x0: float, y0: float, size: float) -> TextSpanRecord:
    return TextSpanRecord(
        text=text,
        bbox=(x0, y0, x0 + len(text) * size * 0.5, y0 + size * 1.2),
        font="Helvetica",
        size=size,
        dir=(1.0, 0.0),
    )


def _sheet_spans() -> list[TextSpanRecord]:
    return [
        _span("1 CORTE A-A", 276, 580, 15.8),
        _span("ESCALA 1:50", 276, 599, 5.9),
        _span("CAIBRO 8X16", 300, 667, 11.2),
        _span("19", 800, 700, 7.9),
        _span("2 CORTE B-B", 276, 1252, 15.8),
        _span("ESCALA 1:50", 276, 1271, 5.9),
        _span("NIVEL -0.05", 320, 1300, 7.9),
    ]


def test_finds_every_scale_anchor() -> None:
    anchors = find_scale_anchors(_sheet_spans(), exclude=None)

    assert [anchor.scale for anchor in anchors] == ["1:50", "1:50"]


def test_ignores_scale_inside_the_excluded_title_block() -> None:
    spans = _sheet_spans() + [_span("ESCALA 1:20", 1800, 1500, 8.0)]

    anchors = find_scale_anchors(spans, exclude=(1700.0, 1400.0, 2384.0, 1684.0))

    assert len(anchors) == 2


def test_title_floor_separates_titles_from_dimension_text() -> None:
    floor = title_font_floor(_sheet_spans())

    assert 8.0 < floor <= 15.8


def test_associates_the_title_immediately_above_each_scale() -> None:
    """A tolerancia vertical importa: no material real o titulo termina a fracao
    de ponto do topo da escala, e um limite exato perde a associacao."""
    spans = _sheet_spans()
    floor = title_font_floor(spans)
    anchors = find_scale_anchors(spans, exclude=None)

    titles = [find_title_for(anchor, spans, floor) for anchor in anchors]

    assert [t.title for t in titles if t] == ["CORTE A-A", "CORTE B-B"]
    assert [t.identifier for t in titles if t] == ["1", "2"]


def test_returns_none_when_no_title_precedes_the_scale() -> None:
    spans = [_span("ESCALA 1:50", 100, 500, 5.9), _span("19", 100, 480, 7.9)]

    anchor = find_scale_anchors(spans, exclude=None)[0]

    assert find_title_for(anchor, spans, title_font_floor(spans)) is None


def test_finds_declared_level_inside_the_view_box() -> None:
    level = find_level_near((260.0, 1240.0, 900.0, 1400.0), _sheet_spans())

    assert level == "-0.05"


def test_view_kind_is_derived_from_the_title() -> None:
    assert view_kind_from_title("CORTE A-A") == "section"
    assert view_kind_from_title("DETALHE 01 LAJE") == "detail"
    assert view_kind_from_title("PLANTA DE FORMAS - TERREO") == "plan"
    assert view_kind_from_title(None) == "plan"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_view_detection.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'truss_api.sheetmap.views'`

- [ ] **Step 3: Conferir os modelos**

Os dataclasses `DetectedView`, `ScaleAnchor` e `TitleCandidate` foram criados na Task 4 em
`apps/api/truss_api/sheetmap/views/models.py`. Confirmar que o conteudo bate com o esperado
abaixo e seguir; se algum campo faltar, acrescentar:

```python
from dataclasses import dataclass


VIEW_KIND_PLAN = "plan"
VIEW_KIND_SECTION = "section"
VIEW_KIND_DETAIL = "detail"

BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class DetectedView:
    view_kind: str
    identifier: str | None
    title: str | None
    declared_scale: str | None
    level: str | None
    bbox: BBox
    confidence: float
    provenance: str


@dataclass(frozen=True)
class ScaleAnchor:
    text: str
    scale: str
    bbox: BBox
    size: float


@dataclass(frozen=True)
class TitleCandidate:
    identifier: str | None
    title: str
    bbox: BBox
    size: float
```

- [ ] **Step 4: Implementar as ancoras**

Create `apps/api/truss_api/sheetmap/views/anchors.py`:

```python
import re
import statistics

from truss_api.core.text import normalize
from truss_api.sheetmap.primitives import TextSpanRecord
from truss_api.sheetmap.views.models import (
    VIEW_KIND_DETAIL,
    VIEW_KIND_PLAN,
    VIEW_KIND_SECTION,
    BBox,
    ScaleAnchor,
    TitleCandidate,
)


SCALE_PATTERN = re.compile(r"ESCALA\s*:?\s*(\d+)\s*[:/]\s*(\d+)")
IDENTIFIER_PATTERN = re.compile(r"^(\d{1,2})\s+(.{3,})$")
LEVEL_PATTERN = re.compile(r"(?:NIVEL|N\.A\.|EL\.|E)\s*[:=]?\s*([-+]?\d+[.,]\d+)")

# Tolerancias verticais em pt. O titulo pode transbordar levemente para dentro da
# linha da escala: medido no material real, a folga necessaria e de poucos pontos.
TITLE_OVERLAP_TOLERANCE_PT = 8.0
TITLE_MAX_GAP_PT = 80.0
TITLE_MAX_HORIZONTAL_OFFSET_PT = 600.0

SECTION_TERMS = ("CORTE", "SECAO")
DETAIL_TERMS = ("DETALHE", "DET.", "AMPLIACAO")


def _inside(bbox: BBox, region: BBox) -> bool:
    center_x = (bbox[0] + bbox[2]) / 2
    center_y = (bbox[1] + bbox[3]) / 2
    return region[0] <= center_x <= region[2] and region[1] <= center_y <= region[3]


def find_scale_anchors(
    spans: list[TextSpanRecord],
    exclude: BBox | None,
) -> list[ScaleAnchor]:
    anchors: list[ScaleAnchor] = []

    for span in spans:
        text = normalize(span.text)
        match = SCALE_PATTERN.search(text)
        if match is None:
            continue

        if exclude is not None and _inside(span.bbox, exclude):
            continue

        anchors.append(
            ScaleAnchor(
                text=text,
                scale=f"{match.group(1)}:{match.group(2)}",
                bbox=span.bbox,
                size=span.size,
            )
        )

    return sorted(anchors, key=lambda anchor: (anchor.bbox[1], anchor.bbox[0]))


def title_font_floor(spans: list[TextSpanRecord]) -> float:
    """Piso de fonte que separa titulo de texto de cota.

    Medido no material real: titulos em 15.8 pt e cotas entre 5.9 e 8.4 pt. O piso
    e a media entre a mediana e o maximo, o que tolera folhas com poucos titulos.
    """
    sizes = [span.size for span in spans if span.size > 0]
    if not sizes:
        return 0.0

    return (statistics.median(sizes) + max(sizes)) / 2


def find_title_for(
    anchor: ScaleAnchor,
    spans: list[TextSpanRecord],
    font_floor: float,
) -> TitleCandidate | None:
    candidates: list[TextSpanRecord] = []

    for span in spans:
        if span.size < font_floor:
            continue

        # O topo da escala e a referencia; o titulo pode invadir alguns pontos.
        gap = anchor.bbox[1] - span.bbox[3]
        if gap < -TITLE_OVERLAP_TOLERANCE_PT or gap > TITLE_MAX_GAP_PT:
            continue

        if abs(span.bbox[0] - anchor.bbox[0]) > TITLE_MAX_HORIZONTAL_OFFSET_PT:
            continue

        candidates.append(span)

    if not candidates:
        return None

    closest = min(candidates, key=lambda span: abs(anchor.bbox[1] - span.bbox[3]))
    text = normalize(closest.text)
    match = IDENTIFIER_PATTERN.match(text)

    return TitleCandidate(
        identifier=match.group(1) if match else None,
        title=match.group(2) if match else text,
        bbox=closest.bbox,
        size=closest.size,
    )


def find_level_near(bbox: BBox, spans: list[TextSpanRecord]) -> str | None:
    for span in spans:
        if not _inside(span.bbox, bbox):
            continue

        match = LEVEL_PATTERN.search(normalize(span.text))
        if match:
            return match.group(1).replace(",", ".")

    return None


def view_kind_from_title(title: str | None) -> str:
    if title is None:
        return VIEW_KIND_PLAN

    normalized = normalize(title)
    if any(term in normalized for term in SECTION_TERMS):
        return VIEW_KIND_SECTION
    if any(term in normalized for term in DETAIL_TERMS):
        return VIEW_KIND_DETAIL

    return VIEW_KIND_PLAN
```

- [ ] **Step 5: Rodar os testes**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_view_detection.py -v`
Expected: PASS, 7 testes.

- [ ] **Step 6: Medir a associacao no material real**

Este e o portao da Task 5. Run:

```bash
.venv/Scripts/python -X utf8 -c "
import sys; sys.path.insert(0,'apps/api')
import fitz
from truss_api.sheetmap.primitives import extract_page
from truss_api.sheetmap.geometry import geometry_from_extraction
from truss_api.sheetmap.regions import detect_regions, extract_line_boxes, REGION_TITLE_BLOCK
from truss_api.sheetmap.views.anchors import find_scale_anchors, find_title_for, title_font_floor

path='data/originals/69f87430-6e60-4cd5-bfb8-c4cde0b09d79/09e35528-5556-4fce-939e-806897d7bbb1/7d2f9c32bc9d4988-Proj_Estrutural_RanchoQueimado_geral.pdf'
document = fitz.open(path)
total = matched = 0
for index in [4, 5, 6, 7, 8, 25]:
    page = document.load_page(index)
    extraction = extract_page(page)
    geometry = geometry_from_extraction(extraction)
    title_block = next((r for r in detect_regions(geometry, extract_line_boxes(page)) if r.region_kind == REGION_TITLE_BLOCK), None)
    exclude = (title_block.x0, title_block.y0, title_block.x1, title_block.y1) if title_block else None
    floor = title_font_floor(extraction.spans)
    anchors = find_scale_anchors(extraction.spans, exclude)
    for anchor in anchors:
        total += 1
        found = find_title_for(anchor, extraction.spans, floor)
        matched += found is not None
        print(f'  pag {index:2d} {anchor.scale:6s} -> {found.title[:40] if found else \"SEM TITULO\"}')
print(f'associacao titulo/escala: {matched}/{total} = {100*matched/total:.0f}%')
"
```

Expected: 17 ancoras encontradas. A meta e **>= 90%** de associacao.

**Se ficar abaixo de 90%, ajustar apenas as constantes de tolerancia no topo de `anchors.py`**
(`TITLE_OVERLAP_TOLERANCE_PT`, `TITLE_MAX_GAP_PT`, `TITLE_MAX_HORIZONTAL_OFFSET_PT`, e a formula
de `title_font_floor`) e repetir a medicao. **Nao baixar o threshold.** Registrar em
`docs/DECISIONS.md` o valor final e o numero medido.

- [ ] **Step 7: Commit**

```bash
git add apps/api/truss_api/sheetmap/views/ apps/api/tests/test_view_detection.py
git commit -m "feat: detect view anchors for scale, title, identifier and level"
```

**Risco de migracao:** nenhum. Codigo novo, sem escrita em banco.

**Criterio de conclusao:** associacao titulo/escala >= 90% nas 17 ancoras das seis folhas reais,
com o numero registrado.

---

### Task 6: Regioes hierarquicas e zona de desenho por subtracao

**Files:**
- Modify: `apps/api/truss_api/sheetmap/regions.py`
- Test: `apps/api/tests/test_sheetmap_reading.py`

**Interfaces:**
- Produces:
  - `REGION_TABLE = "table"`, `REGION_NOTE_BLOCK = "note_block"`, `REGION_LEGEND = "legend"`
  - `DetectedRegion` ganha o campo `parent_kind: str | None = None`
  - `detect_tables(geometry: PageGeometry, spans: list[TextSpanRecord]) -> list[DetectedRegion]`
  - `drawing_zones(frame: DetectedRegion, occupied: list[DetectedRegion]) -> list[DetectedRegion]`
  - `detect_regions(geometry, text_boxes, spans=None) -> list[DetectedRegion]` - parametro novo opcional, contrato preservado

- [ ] **Step 1: Escrever o teste**

Acrescentar em `apps/api/tests/test_sheetmap_reading.py`:

```python
def test_drawing_zone_is_not_truncated_at_the_title_block_top() -> None:
    """A zona de desenho nao pode perder a faixa lateral ao lado do carimbo."""
    frame = DetectedRegion(REGION_FRAME, 20, 10, 970, 770, 0.95)
    title_block = DetectedRegion(REGION_TITLE_BLOCK, 700, 700, 970, 770, 0.9)

    zones = drawing_zones(frame, [title_block])

    total_area = sum((z.x1 - z.x0) * (z.y1 - z.y0) for z in zones)
    truncated_area = (frame.x1 - frame.x0) * (title_block.y0 - frame.y0)

    assert total_area > truncated_area
    assert all(z.region_kind == REGION_DRAWING for z in zones)


def test_drawing_zones_do_not_overlap_occupied_regions() -> None:
    frame = DetectedRegion(REGION_FRAME, 0, 0, 1000, 1000, 0.95)
    table = DetectedRegion(REGION_TABLE, 800, 0, 1000, 400, 0.8)

    zones = drawing_zones(frame, [table])

    for zone in zones:
        assert not (zone.x0 < 1000 and zone.x1 > 800 and zone.y0 < 400 and zone.y1 > 0)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_sheetmap_reading.py -v`
Expected: FAIL com `ImportError: cannot import name 'drawing_zones'`

- [ ] **Step 3: Implementar a subtracao de regioes**

Em `apps/api/truss_api/sheetmap/regions.py`, acrescentar as constantes e substituir a construcao
da zona de desenho:

```python
REGION_TABLE = "table"
REGION_NOTE_BLOCK = "note_block"
REGION_LEGEND = "legend"

MIN_ZONE_SIDE_PT = 60.0


def drawing_zones(
    frame: DetectedRegion,
    occupied: list[DetectedRegion],
) -> list[DetectedRegion]:
    """Zona de desenho como faixas disjuntas: moldura menos regioes ocupadas.

    Corta em faixas horizontais definidas pelas bordas verticais das regioes
    ocupadas, e dentro de cada faixa remove os intervalos horizontais cobertos.
    Evita a truncagem anterior, que descartava tudo abaixo do topo do carimbo.
    """
    if not occupied:
        return [
            DetectedRegion(REGION_DRAWING, frame.x0, frame.y0, frame.x1, frame.y1, frame.confidence)
        ]

    edges = sorted({frame.y0, frame.y1} | {edge for region in occupied for edge in (region.y0, region.y1)})
    zones: list[DetectedRegion] = []

    for top, bottom in zip(edges, edges[1:]):
        if bottom - top < MIN_ZONE_SIDE_PT:
            continue

        blockers = sorted(
            (region for region in occupied if region.y0 < bottom and region.y1 > top),
            key=lambda region: region.x0,
        )

        cursor = frame.x0
        for blocker in blockers:
            if blocker.x0 - cursor >= MIN_ZONE_SIDE_PT:
                zones.append(
                    DetectedRegion(REGION_DRAWING, cursor, top, blocker.x0, bottom, frame.confidence)
                )
            cursor = max(cursor, blocker.x1)

        if frame.x1 - cursor >= MIN_ZONE_SIDE_PT:
            zones.append(
                DetectedRegion(REGION_DRAWING, cursor, top, frame.x1, bottom, frame.confidence)
            )

    return zones
```

Acrescentar a deteccao de tabelas, prometida nas interfaces desta tarefa. Uma tabela e uma
grade densa de retangulos pequenos alinhados - o quadro de pilares do material real e exatamente
isso. **Tabela nao e view**, e por isso precisa ser reconhecida para ser subtraida da zona de
desenho e excluida da segmentacao:

```python
TABLE_MIN_CELLS = 12
TABLE_CELL_MAX_AREA_RATIO = 0.01


def detect_tables(geometry: PageGeometry, spans: list[TextSpanRecord]) -> list[DetectedRegion]:
    page_area = geometry.page_area
    cells = [
        rect
        for rect in geometry.rects
        if 0 < rect.area / page_area <= TABLE_CELL_MAX_AREA_RATIO
    ]

    if len(cells) < TABLE_MIN_CELLS:
        return []

    # Agrupa celulas por proximidade em faixas horizontais e verticais.
    clusters: list[list[GeometryRect]] = []
    for cell in sorted(cells, key=lambda rect: (rect.y0, rect.x0)):
        for cluster in clusters:
            reference = cluster[-1]
            if (
                abs(cell.y0 - reference.y0) < reference.height * 3
                and abs(cell.x0 - reference.x0) < reference.width * 6
            ):
                cluster.append(cell)
                break
        else:
            clusters.append([cell])

    regions: list[DetectedRegion] = []
    for cluster in clusters:
        if len(cluster) < TABLE_MIN_CELLS:
            continue

        regions.append(
            DetectedRegion(
                region_kind=REGION_TABLE,
                x0=min(cell.x0 for cell in cluster),
                y0=min(cell.y0 for cell in cluster),
                x1=max(cell.x1 for cell in cluster),
                y1=max(cell.y1 for cell in cluster),
                confidence=0.7,
            )
        )

    return regions
```

Acrescentar aos imports do arquivo:

```python
from truss_api.sheetmap.geometry import GeometryRect
from truss_api.sheetmap.primitives import TextSpanRecord
```

E substituir, no fim de `detect_regions`, o bloco que criava a zona unica:

```python
    if spans:
        regions.extend(detect_tables(geometry, spans))

    occupied = [region for region in regions if region.region_kind != REGION_FRAME]
    regions.extend(drawing_zones(frame, occupied))

    return regions
```

A assinatura passa a ser `detect_regions(geometry, text_boxes, spans=None)`. O parametro e
opcional, entao todos os chamadores atuais continuam validos.

Acrescentar `parent_kind` ao dataclass:

```python
@dataclass(frozen=True)
class DetectedRegion:
    region_kind: str
    x0: float
    y0: float
    x1: float
    y1: float
    confidence: float
    parent_kind: str | None = None
```

- [ ] **Step 4: Rodar os testes**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_sheetmap_reading.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/truss_api/sheetmap/regions.py apps/api/tests/test_sheetmap_reading.py
git commit -m "feat: hierarchical regions and subtraction-based drawing zones"
```

**Risco de migracao:** `detect_regions` passa a devolver varias regioes `area_desenho` em vez de
uma. Nenhum consumidor atual depende de haver exatamente uma; o viewer apenas lista regioes.

**Criterio de conclusao:** a zona de desenho deixa de ser truncada no topo do carimbo e nao
invade tabelas.

---

### Task 7: Detector de views para plantas de formas

**Files:**
- Create: `apps/api/truss_api/sheetmap/views/detector.py`
- Modify: `apps/api/truss_api/sheetmap/builder.py`
- Test: `apps/api/tests/test_view_detection.py`
- Test: `apps/api/tests/factories.py`

**Interfaces:**
- Consumes: `ScaleAnchor`, `TitleCandidate`, `find_scale_anchors`, `find_title_for`, `title_font_floor`, `find_level_near`, `view_kind_from_title`, `drawing_zones`
- Produces:
  - `detect_forms_views(extraction: PageExtraction, regions: list[DetectedRegion]) -> list[DetectedView]`
  - `build_sheet_map_for_document` passa a gravar `views` e o snapshot

- [ ] **Step 1: Escrever o teste com fixture sintetica**

Acrescentar em `apps/api/tests/factories.py`:

```python
def make_forms_sheet_pdf_bytes() -> bytes:
    """Planta de formas sintetica: moldura, carimbo e tres views com titulo e escala."""
    document = fitz.open()
    page = document.new_page(width=2384, height=1684)
    page.draw_rect(fitz.Rect(71, 29, 2356, 1656), color=(0, 0, 0), width=2)

    views = [
        ("1 PLANTA DE FORMAS - TERREO", "ESCALA 1:50", 200, 200),
        ("2 CORTE A-A", "ESCALA 1:50", 200, 800),
        ("3 DETALHE 01 LAJE", "ESCALA 1:20", 1300, 800),
    ]
    for title, scale, x, y in views:
        page.insert_text((x, y), title, fontsize=16)
        page.insert_text((x, y + 20), scale, fontsize=6)
        page.insert_text((x + 40, y + 120), "19", fontsize=8)
        page.draw_rect(fitz.Rect(x, y + 40, x + 700, y + 400), color=(0, 0, 0), width=1)

    page.insert_text((320, 340), "NIVEL -0.05", fontsize=8)

    page.insert_text((1750, 1500), "EST-0050-A", fontsize=11)
    page.insert_text((1750, 1520), "CPF: 951.770.276-00", fontsize=11)
    page.insert_text((1750, 1560), "PROJETO ESTRUTURAL", fontsize=11)
    page.insert_text((1750, 1590), "PLANTA DE FORMAS", fontsize=11)

    buffer = BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()
```

Acrescentar em `apps/api/tests/test_view_detection.py`:

```python
import fitz

from tests.factories import make_forms_sheet_pdf_bytes
from truss_api.sheetmap.geometry import geometry_from_extraction
from truss_api.sheetmap.primitives import extract_page
from truss_api.sheetmap.regions import detect_regions, extract_line_boxes
from truss_api.sheetmap.views.detector import detect_forms_views


def _detect() -> list:
    document = fitz.open(stream=make_forms_sheet_pdf_bytes(), filetype="pdf")
    page = document.load_page(0)
    extraction = extract_page(page)
    regions = detect_regions(geometry_from_extraction(extraction), extract_line_boxes(page))
    return detect_forms_views(extraction, regions)


def test_detects_one_view_per_scale_anchor() -> None:
    assert len(_detect()) == 3


def test_each_view_carries_title_scale_and_kind() -> None:
    views = {view.title: view for view in _detect()}

    assert views["PLANTA DE FORMAS - TERREO"].declared_scale == "1:50"
    assert views["PLANTA DE FORMAS - TERREO"].view_kind == "plan"
    assert views["CORTE A-A"].view_kind == "section"
    assert views["DETALHE 01 LAJE"].view_kind == "detail"


def test_plan_view_captures_the_declared_level() -> None:
    plan = next(view for view in _detect() if view.view_kind == "plan")

    assert plan.level == "-0.05"


def test_views_do_not_include_the_title_block() -> None:
    for view in _detect():
        assert view.bbox[0] < 1700 or view.bbox[1] < 1400


def test_a_table_does_not_become_a_view() -> None:
    """Um quadro de pilares com escala proxima nao pode virar view."""
    from truss_api.sheetmap.regions import REGION_TABLE, DetectedRegion

    document = fitz.open(stream=make_forms_sheet_pdf_bytes(), filetype="pdf")
    page = document.load_page(0)
    extraction = extract_page(page)
    regions = detect_regions(geometry_from_extraction(extraction), extract_line_boxes(page))
    regions.append(DetectedRegion(REGION_TABLE, 190, 190, 950, 640, 0.7))

    views = detect_forms_views(extraction, regions)

    assert all(not (190 <= v.bbox[0] <= 950 and 190 <= v.bbox[1] <= 640) for v in views)


def test_every_view_records_provenance() -> None:
    assert all(view.provenance for view in _detect())
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_view_detection.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'truss_api.sheetmap.views.detector'`

- [ ] **Step 3: Implementar o detector**

Create `apps/api/truss_api/sheetmap/views/detector.py`:

```python
from truss_api.sheetmap.primitives import PageExtraction
from truss_api.sheetmap.regions import (
    REGION_DRAWING,
    REGION_LEGEND,
    REGION_NOTE_BLOCK,
    REGION_TABLE,
    REGION_TITLE_BLOCK,
    DetectedRegion,
)
from truss_api.sheetmap.views.anchors import (
    find_level_near,
    find_scale_anchors,
    find_title_for,
    title_font_floor,
    view_kind_from_title,
)
from truss_api.sheetmap.views.models import BBox, DetectedView


PROVENANCE = "deterministic/forms-view-v1"

# Margem aplicada ao redor do conteudo atribuido a uma view, em pt.
VIEW_PADDING_PT = 12.0


def _excluded_bboxes(regions: list[DetectedRegion]) -> list[BBox]:
    """Carimbo, tabelas, notas e legendas nao sao views e nao podem gerar uma."""
    excluded_kinds = {REGION_TITLE_BLOCK, REGION_TABLE, REGION_NOTE_BLOCK, REGION_LEGEND}
    return [
        (region.x0, region.y0, region.x1, region.y1)
        for region in regions
        if region.region_kind in excluded_kinds
    ]


def _inside_any(bbox: BBox, regions: list[BBox]) -> bool:
    center_x = (bbox[0] + bbox[2]) / 2
    center_y = (bbox[1] + bbox[3]) / 2
    return any(
        region[0] <= center_x <= region[2] and region[1] <= center_y <= region[3]
        for region in regions
    )


def _zone_for(point: tuple[float, float], regions: list[DetectedRegion]) -> DetectedRegion | None:
    for region in regions:
        if region.region_kind != REGION_DRAWING:
            continue
        if region.x0 <= point[0] <= region.x1 and region.y0 <= point[1] <= region.y1:
            return region

    return None


def detect_forms_views(
    extraction: PageExtraction,
    regions: list[DetectedRegion],
) -> list[DetectedView]:
    """Segmenta views usando ancoras de escala, ancoradas na zona de desenho.

    Cada ancora de escala define uma view. O limite vertical de cada view vai do
    seu titulo ate o inicio da proxima view na mesma coluna, ou ate o fim da zona
    de desenho. Deterministico e sem modelo.
    """
    excluded = _excluded_bboxes(regions)
    anchors = [
        anchor
        for anchor in find_scale_anchors(extraction.spans, exclude=None)
        if not _inside_any(anchor.bbox, excluded)
    ]
    if not anchors:
        return []

    font_floor = title_font_floor(extraction.spans)
    views: list[DetectedView] = []

    for index, anchor in enumerate(anchors):
        title = find_title_for(anchor, extraction.spans, font_floor)
        top = (title.bbox[1] if title else anchor.bbox[1]) - VIEW_PADDING_PT
        left = min(anchor.bbox[0], title.bbox[0] if title else anchor.bbox[0]) - VIEW_PADDING_PT

        zone = _zone_for((anchor.bbox[0], anchor.bbox[1]), regions)
        right = (zone.x1 if zone else extraction.metadata.width_pt) - VIEW_PADDING_PT
        bottom_limit = zone.y1 if zone else extraction.metadata.height_pt

        # A proxima ancora na mesma coluna encerra esta view.
        following = [
            other
            for other in anchors[index + 1 :]
            if abs(other.bbox[0] - anchor.bbox[0]) < 400.0
        ]
        if following:
            next_title = find_title_for(following[0], extraction.spans, font_floor)
            bottom_limit = min(
                bottom_limit,
                (next_title.bbox[1] if next_title else following[0].bbox[1]) - VIEW_PADDING_PT,
            )

        bbox: BBox = (
            max(0.0, left),
            max(0.0, top),
            right,
            max(top + VIEW_PADDING_PT, bottom_limit),
        )

        views.append(
            DetectedView(
                view_kind=view_kind_from_title(title.title if title else None),
                identifier=title.identifier if title else None,
                title=title.title if title else None,
                declared_scale=anchor.scale,
                level=find_level_near(bbox, extraction.spans),
                bbox=bbox,
                confidence=0.85 if title else 0.5,
                provenance=PROVENANCE,
            )
        )

    return views
```

- [ ] **Step 4: Ligar ao builder**

Em `apps/api/truss_api/sheetmap/builder.py`, substituir o corpo do laco por pipeline completo.
As linhas que hoje chamam `extract_page_geometry` e `write_page_geometry` passam a ser:

```python
            extraction = extract_page(page)
            geometry = geometry_from_extraction(extraction)
            text_boxes = extract_line_boxes(page)
            regions = detect_regions(geometry, text_boxes)
            views = detect_forms_views(extraction, regions) if classification.sheet_type == "planta_formas" else []

            geometry_path = write_extraction(
                extraction,
                project_id=str(sheet["project_id"]),
                revision_id=str(sheet["revision_id"]),
                sheet_id=str(sheet["id"]),
                settings=settings,
            )
            content_hash = snapshot_hash(
                sheet_type=classification.sheet_type,
                sheet_code=fields.sheet_code,
                title_block=title_block_payload,
                regions=regions,
                views=views,
                extraction_hash=artifact_hash(extraction),
            )
```

e a chamada a `repository.save_sheet_map` ganha os argumentos
`views=views`, `snapshot_hash=content_hash`, `extractor_version=EXTRACTOR_VERSION`,
`document_hash=document_hash`, onde `document_hash` vem de uma consulta a
`documents.content_hash` feita em `_load_document_context`.

Nota de ordem: `classification` e calculada antes de `views`, entao a linha que a define deve
permanecer acima. `title_block_payload` tambem precisa ser montado antes do `snapshot_hash`.

- [ ] **Step 5: Rodar os testes**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_view_detection.py apps/api/tests/test_sheetmap_builder.py -v`
Expected: PASS.

- [ ] **Step 6: Medir a deteccao no material real**

Run:

```bash
.venv/Scripts/python -X utf8 -c "
import sys; sys.path.insert(0,'apps/api')
import fitz
from truss_api.sheetmap.primitives import extract_page
from truss_api.sheetmap.geometry import geometry_from_extraction
from truss_api.sheetmap.regions import detect_regions, extract_line_boxes
from truss_api.sheetmap.views.detector import detect_forms_views

path='data/originals/69f87430-6e60-4cd5-bfb8-c4cde0b09d79/09e35528-5556-4fce-939e-806897d7bbb1/7d2f9c32bc9d4988-Proj_Estrutural_RanchoQueimado_geral.pdf'
document = fitz.open(path)
total = titled = 0
for index in [4, 5, 6, 7, 8, 25]:
    page = document.load_page(index)
    extraction = extract_page(page)
    regions = detect_regions(geometry_from_extraction(extraction), extract_line_boxes(page))
    views = detect_forms_views(extraction, regions)
    total += len(views)
    titled += sum(1 for v in views if v.title and v.declared_scale)
    print(f'  pag {index:2d}: {len(views)} views -> ' + ', '.join(f'{v.view_kind}:{(v.title or \"?\")[:22]}' for v in views))
print(f'views detectadas: {total} | com titulo e escala: {titled} ({100*titled/total:.0f}%)')
"
```

Expected: 17 views, e **>= 90%** com titulo e escala.

- [ ] **Step 7: Commit**

```bash
git add apps/api/truss_api/sheetmap/views/detector.py apps/api/truss_api/sheetmap/builder.py apps/api/tests/
git commit -m "feat: deterministic view detector for forms sheets"
```

**Risco de migracao:** o builder muda o caminho do artefato de geometria. Sheet maps antigos
apontam para `.json` sem hash, que continua em disco e nao e mais lido. Nenhuma perda.

**Criterio de conclusao:** 17 views detectadas nas seis folhas, >= 90% com titulo e escala.

---

### Task 8: Motor de checklist e rule pack de plantas de formas

**Files:**
- Create: `apps/api/truss_api/rules/__init__.py`
- Create: `apps/api/truss_api/rules/models.py`
- Create: `apps/api/truss_api/rules/schema.py`
- Create: `apps/api/truss_api/rules/loader.py`
- Create: `apps/api/truss_api/rules/engine.py`
- Create: `apps/api/truss_api/rules/packs/planta_formas.v1.yml`
- Test: `apps/api/tests/test_rules_engine.py`

**Interfaces:**
- Produces:
  - `RuleOutcome` = `"PASS" | "FAIL" | "UNKNOWN" | "NOT_APPLICABLE" | "SKIPPED"`
  - `RuleEvaluation` dataclass: `rule_id: str`, `rule_version: str`, `rule_pack_version: str`, `target_kind: str`, `target_id: str | None`, `outcome: str`, `confidence: float`, `reason: str`, `evidence: list[str]`, `bbox: BBox | None`, `severity: str`, `category: str`, `finding_type: str`
  - `RulePack` dataclass: `pack_id: str`, `version: str`, `sheet_type: str`, `rules: list[Rule]`
  - `load_pack(sheet_type: str) -> RulePack | None`
  - `validate_pack(payload: dict) -> None` levanta `RulePackSchemaError`
  - `evaluate(pack: RulePack, snapshot: dict[str, object]) -> list[RuleEvaluation]`

- [ ] **Step 1: Escrever o teste**

Create `apps/api/tests/test_rules_engine.py`:

```python
import pytest

from truss_api.rules.engine import evaluate
from truss_api.rules.loader import load_pack
from truss_api.rules.schema import RulePackSchemaError, validate_pack


def _snapshot(views: list[dict], sheet_type: str = "planta_formas") -> dict:
    return {
        "sheet_type": sheet_type,
        "title_block": {"category": "PLANTA DE FORMAS"},
        "views": views,
        "regions": [{"region_kind": "moldura", "x0": 0, "y0": 0, "x1": 100, "y1": 100}],
    }


def _view(**overrides) -> dict:
    base = {
        "id": "v1",
        "view_kind": "plan",
        "identifier": "1",
        "title": "PLANTA DE FORMAS - TERREO",
        "declared_scale": "1:50",
        "level": "-0.05",
        "x0": 10.0,
        "y0": 10.0,
        "x1": 200.0,
        "y1": 200.0,
        "confidence": 0.9,
    }
    base.update(overrides)
    return base


def test_pack_for_forms_sheets_loads_and_validates() -> None:
    pack = load_pack("planta_formas")

    assert pack is not None
    assert pack.sheet_type == "planta_formas"
    assert {rule.rule_id for rule in pack.rules} >= {
        "forms.sheet.has_main_view",
        "forms.view.title_present",
        "forms.view.scale_declared",
        "forms.view.level_declared",
        "forms.sheet.category_matches_content",
        "forms.sheet.duplicate_identifier",
    }


def test_invalid_pack_is_rejected_by_schema() -> None:
    with pytest.raises(RulePackSchemaError):
        validate_pack({"pack_id": "x", "version": "1"})


def test_complete_sheet_produces_only_pass() -> None:
    evaluations = evaluate(load_pack("planta_formas"), _snapshot([_view()]))

    assert {e.outcome for e in evaluations} == {"PASS"}


def test_missing_scale_fails_with_evidence_and_view_target() -> None:
    evaluations = evaluate(
        load_pack("planta_formas"), _snapshot([_view(declared_scale=None)])
    )

    failure = next(e for e in evaluations if e.rule_id == "forms.view.scale_declared")
    assert failure.outcome == "FAIL"
    assert failure.target_kind == "view"
    assert failure.target_id == "v1"
    assert failure.evidence


def test_level_rule_is_not_applicable_to_sections() -> None:
    evaluations = evaluate(
        load_pack("planta_formas"),
        _snapshot([_view(view_kind="section", level=None, title="CORTE A-A")]),
    )

    level_rule = next(e for e in evaluations if e.rule_id == "forms.view.level_declared")
    assert level_rule.outcome == "NOT_APPLICABLE"


def test_sheet_without_views_reports_unknown_not_pass() -> None:
    """Sem views, o motor nao sabe - e nao pode alegar conformidade."""
    evaluations = evaluate(load_pack("planta_formas"), _snapshot([]))

    main_view = next(e for e in evaluations if e.rule_id == "forms.sheet.has_main_view")
    assert main_view.outcome == "FAIL"
    scale_rule = [e for e in evaluations if e.rule_id == "forms.view.scale_declared"]
    assert all(e.outcome == "UNKNOWN" for e in scale_rule) or scale_rule == []


def test_duplicate_identifiers_are_reported_once() -> None:
    evaluations = evaluate(
        load_pack("planta_formas"),
        _snapshot([_view(id="v1", identifier="1"), _view(id="v2", identifier="1")]),
    )

    duplicates = [
        e for e in evaluations
        if e.rule_id == "forms.sheet.duplicate_identifier" and e.outcome == "FAIL"
    ]
    assert len(duplicates) == 1
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_rules_engine.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'truss_api.rules'`

- [ ] **Step 3: Implementar modelos e schema**

Create `apps/api/truss_api/rules/__init__.py` vazio, `apps/api/truss_api/rules/models.py`:

```python
from dataclasses import dataclass, field


BBox = tuple[float, float, float, float]

OUTCOME_PASS = "PASS"
OUTCOME_FAIL = "FAIL"
OUTCOME_UNKNOWN = "UNKNOWN"
OUTCOME_NOT_APPLICABLE = "NOT_APPLICABLE"
OUTCOME_SKIPPED = "SKIPPED"

VALID_OUTCOMES = frozenset(
    {OUTCOME_PASS, OUTCOME_FAIL, OUTCOME_UNKNOWN, OUTCOME_NOT_APPLICABLE, OUTCOME_SKIPPED}
)


@dataclass(frozen=True)
class Rule:
    rule_id: str
    version: str
    check: str
    target: str
    severity: str
    category: str
    finding_type: str
    description: str
    applies_to_view_kinds: tuple[str, ...] = ()


@dataclass(frozen=True)
class RulePack:
    pack_id: str
    version: str
    sheet_type: str
    rules: list[Rule] = field(default_factory=list)


@dataclass(frozen=True)
class RuleEvaluation:
    rule_id: str
    rule_version: str
    rule_pack_version: str
    target_kind: str
    target_id: str | None
    outcome: str
    confidence: float
    reason: str
    evidence: list[str]
    bbox: BBox | None
    severity: str
    category: str
    finding_type: str
```

Create `apps/api/truss_api/rules/schema.py`:

```python
from truss_api.rules.models import VALID_OUTCOMES


class RulePackSchemaError(Exception):
    pass


REQUIRED_PACK_FIELDS = ("pack_id", "version", "sheet_type", "rules")
REQUIRED_RULE_FIELDS = (
    "rule_id",
    "version",
    "check",
    "target",
    "severity",
    "category",
    "finding_type",
    "description",
)
VALID_TARGETS = frozenset({"sheet", "view"})
VALID_SEVERITIES = frozenset({"low", "medium", "high", "critical"})


def validate_pack(payload: dict) -> None:
    missing = [field for field in REQUIRED_PACK_FIELDS if field not in payload]
    if missing:
        raise RulePackSchemaError(f"campos ausentes no pack: {', '.join(missing)}")

    if not isinstance(payload["rules"], list) or not payload["rules"]:
        raise RulePackSchemaError("pack precisa de ao menos uma regra")

    seen: set[str] = set()
    for rule in payload["rules"]:
        absent = [field for field in REQUIRED_RULE_FIELDS if field not in rule]
        if absent:
            raise RulePackSchemaError(
                f"regra {rule.get('rule_id', '?')} sem campos: {', '.join(absent)}"
            )

        if rule["rule_id"] in seen:
            raise RulePackSchemaError(f"rule_id duplicado: {rule['rule_id']}")
        seen.add(rule["rule_id"])

        if rule["target"] not in VALID_TARGETS:
            raise RulePackSchemaError(f"target invalido em {rule['rule_id']}")
        if rule["severity"] not in VALID_SEVERITIES:
            raise RulePackSchemaError(f"severity invalida em {rule['rule_id']}")
```

- [ ] **Step 4: Escrever o rule pack**

Create `apps/api/truss_api/rules/packs/planta_formas.v1.yml`:

```yaml
pack_id: planta_formas
version: "1.0.0"
sheet_type: planta_formas
rules:
  - rule_id: forms.sheet.has_main_view
    version: "1.0.0"
    check: sheet_has_view
    target: sheet
    severity: high
    category: composition
    finding_type: missing_information
    description: A folha de formas nao apresenta nenhuma view identificavel.

  - rule_id: forms.view.title_present
    version: "1.0.0"
    check: view_has_title
    target: view
    severity: medium
    category: identification
    finding_type: missing_information
    description: View sem titulo declarado.

  - rule_id: forms.view.scale_declared
    version: "1.0.0"
    check: view_has_scale
    target: view
    severity: high
    category: identification
    finding_type: missing_information
    description: View sem escala declarada.

  - rule_id: forms.view.level_declared
    version: "1.0.0"
    check: view_has_level
    target: view
    severity: medium
    category: identification
    finding_type: missing_information
    description: Planta sem indicacao de nivel.
    applies_to_view_kinds: [plan]

  - rule_id: forms.sheet.category_matches_content
    version: "1.0.0"
    check: category_matches_views
    target: sheet
    severity: medium
    category: identification
    finding_type: attention
    description: A categoria do carimbo nao corresponde ao conteudo das views.

  # NOT_VERIFIABLE: nao e uma regra separada. Toda regra de view devolve UNKNOWN
  # quando a confianca da segmentacao fica abaixo de 0,6, em vez de afirmar FAIL.
  # Ver `_evaluate_view_rule` em engine.py.
  - rule_id: forms.sheet.duplicate_identifier
    version: "1.0.0"
    check: unique_view_identifiers
    target: sheet
    severity: medium
    category: identification
    finding_type: inconsistency
    description: Duas views compartilham o mesmo identificador ou titulo.
```

- [ ] **Step 5: Implementar loader e engine**

Create `apps/api/truss_api/rules/loader.py`:

```python
from functools import lru_cache
from pathlib import Path

import yaml

from truss_api.rules.models import Rule, RulePack
from truss_api.rules.schema import validate_pack


PACKS_DIR = Path(__file__).resolve().parent / "packs"


@lru_cache(maxsize=8)
def load_pack(sheet_type: str) -> RulePack | None:
    matches = sorted(PACKS_DIR.glob(f"{sheet_type}.v*.yml"))
    if not matches:
        return None

    payload = yaml.safe_load(matches[-1].read_text(encoding="utf-8"))
    validate_pack(payload)

    return RulePack(
        pack_id=payload["pack_id"],
        version=payload["version"],
        sheet_type=payload["sheet_type"],
        rules=[
            Rule(
                rule_id=rule["rule_id"],
                version=rule["version"],
                check=rule["check"],
                target=rule["target"],
                severity=rule["severity"],
                category=rule["category"],
                finding_type=rule["finding_type"],
                description=rule["description"],
                applies_to_view_kinds=tuple(rule.get("applies_to_view_kinds", ())),
            )
            for rule in payload["rules"]
        ],
    )
```

Create `apps/api/truss_api/rules/engine.py`:

```python
from truss_api.core.text import normalize
from truss_api.rules.models import (
    OUTCOME_FAIL,
    OUTCOME_NOT_APPLICABLE,
    OUTCOME_PASS,
    OUTCOME_UNKNOWN,
    Rule,
    RuleEvaluation,
    RulePack,
)


def _bbox(view: dict) -> tuple[float, float, float, float]:
    return (float(view["x0"]), float(view["y0"]), float(view["x1"]), float(view["y1"]))


def _result(
    rule: Rule,
    pack: RulePack,
    *,
    target_kind: str,
    target_id: str | None,
    outcome: str,
    reason: str,
    evidence: list[str],
    bbox: tuple[float, float, float, float] | None,
    confidence: float,
) -> RuleEvaluation:
    return RuleEvaluation(
        rule_id=rule.rule_id,
        rule_version=rule.version,
        rule_pack_version=pack.version,
        target_kind=target_kind,
        target_id=target_id,
        outcome=outcome,
        confidence=confidence,
        reason=reason,
        evidence=evidence,
        bbox=bbox,
        severity=rule.severity,
        category=rule.category,
        finding_type=rule.finding_type,
    )


def _sheet_bbox(snapshot: dict) -> tuple[float, float, float, float] | None:
    frame = next(
        (r for r in snapshot.get("regions", []) if r["region_kind"] == "moldura"), None
    )
    if frame is None:
        return None

    return (float(frame["x0"]), float(frame["y0"]), float(frame["x1"]), float(frame["y1"]))


def evaluate(pack: RulePack, snapshot: dict) -> list[RuleEvaluation]:
    views = list(snapshot.get("views", []))
    results: list[RuleEvaluation] = []

    for rule in pack.rules:
        if rule.target == "sheet":
            results.append(_evaluate_sheet_rule(rule, pack, snapshot, views))
            continue

        for view in views:
            results.append(_evaluate_view_rule(rule, pack, view))

    return results


def _evaluate_sheet_rule(rule: Rule, pack: RulePack, snapshot: dict, views: list[dict]):
    bbox = _sheet_bbox(snapshot)

    if rule.check == "sheet_has_view":
        has_views = bool(views)
        return _result(
            rule,
            pack,
            target_kind="sheet",
            target_id=None,
            outcome=OUTCOME_PASS if has_views else OUTCOME_FAIL,
            reason="" if has_views else "Nenhuma view foi segmentada nesta folha.",
            evidence=[f"views detectadas: {len(views)}"],
            bbox=bbox,
            confidence=0.9,
        )

    if rule.check == "category_matches_views":
        category = normalize(str(snapshot.get("title_block", {}).get("category") or ""))
        if not category or not views:
            return _result(
                rule, pack, target_kind="sheet", target_id=None,
                outcome=OUTCOME_UNKNOWN,
                reason="Sem categoria no carimbo ou sem views para comparar.",
                evidence=[f"categoria: {category or 'ausente'}", f"views: {len(views)}"],
                bbox=bbox, confidence=0.4,
            )

        expects_plan = "FORMAS" in category
        has_plan = any(view["view_kind"] == "plan" for view in views)
        coherent = has_plan or not expects_plan
        return _result(
            rule, pack, target_kind="sheet", target_id=None,
            outcome=OUTCOME_PASS if coherent else OUTCOME_FAIL,
            reason="" if coherent else "Carimbo declara formas, mas nenhuma view e planta.",
            evidence=[f"categoria: {category}", f"tipos: {[v['view_kind'] for v in views]}"],
            bbox=bbox, confidence=0.7,
        )

    if rule.check == "unique_view_identifiers":
        keys = [
            (view.get("identifier") or normalize(str(view.get("title") or "")))
            for view in views
            if view.get("identifier") or view.get("title")
        ]
        duplicated = sorted({key for key in keys if keys.count(key) > 1})
        return _result(
            rule, pack, target_kind="sheet", target_id=None,
            outcome=OUTCOME_FAIL if duplicated else OUTCOME_PASS,
            reason=f"Identificadores repetidos: {', '.join(duplicated)}" if duplicated else "",
            evidence=[f"identificadores: {keys}"],
            bbox=bbox, confidence=0.85,
        )

    return _result(
        rule, pack, target_kind="sheet", target_id=None,
        outcome=OUTCOME_UNKNOWN, reason=f"Check nao implementado: {rule.check}",
        evidence=[], bbox=bbox, confidence=0.0,
    )


def _evaluate_view_rule(rule: Rule, pack: RulePack, view: dict):
    view_id = str(view.get("id") or "")
    bbox = _bbox(view)

    if rule.applies_to_view_kinds and view["view_kind"] not in rule.applies_to_view_kinds:
        return _result(
            rule, pack, target_kind="view", target_id=view_id,
            outcome=OUTCOME_NOT_APPLICABLE,
            reason=f"Regra vale para {', '.join(rule.applies_to_view_kinds)}.",
            evidence=[f"view_kind: {view['view_kind']}"], bbox=bbox, confidence=1.0,
        )

    field_by_check = {
        "view_has_title": "title",
        "view_has_scale": "declared_scale",
        "view_has_level": "level",
    }
    field = field_by_check.get(rule.check)

    if field is None:
        return _result(
            rule, pack, target_kind="view", target_id=view_id,
            outcome=OUTCOME_UNKNOWN, reason=f"Check nao implementado: {rule.check}",
            evidence=[], bbox=bbox, confidence=0.0,
        )

    # Confianca baixa na segmentacao torna a ausencia nao verificavel, nao um erro.
    if float(view.get("confidence", 1.0)) < 0.6:
        return _result(
            rule, pack, target_kind="view", target_id=view_id,
            outcome=OUTCOME_UNKNOWN,
            reason="Segmentacao da view pouco confiavel para afirmar ausencia.",
            evidence=[f"confianca da view: {view.get('confidence')}"],
            bbox=bbox, confidence=0.3,
        )

    present = bool(view.get(field))
    return _result(
        rule, pack, target_kind="view", target_id=view_id,
        outcome=OUTCOME_PASS if present else OUTCOME_FAIL,
        reason="" if present else rule.description,
        evidence=[f"{field}: {view.get(field) or 'ausente'}"],
        bbox=bbox, confidence=0.85,
    )
```

- [ ] **Step 6: Rodar os testes**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_rules_engine.py -v`
Expected: PASS, 7 testes.

- [ ] **Step 7: Commit**

```bash
git add apps/api/truss_api/rules/ apps/api/tests/test_rules_engine.py
git commit -m "feat: declarative rule engine and forms rule pack v1"
```

**Risco de migracao:** nenhum. Modulo novo, sem escrita em banco.

**Criterio de conclusao:** pack validado por schema, os seis checks implementados, e
`NOT_APPLICABLE` / `UNKNOWN` distinguidos de `FAIL`.

---

### Task 9: Orquestrador, findings rastreaveis e cache versionado

**Files:**
- Modify: `apps/api/truss_api/audit/orchestrator.py`
- Modify: `apps/api/truss_api/audit/repository.py`
- Modify: `apps/api/truss_api/audit/models.py`
- Test: `apps/api/tests/test_findings_traceability.py`

**Interfaces:**
- Consumes: `evaluate`, `load_pack`, `get_sheet_map`
- Produces:
  - `AUDIT_PIPELINE_VERSION = "audit-v0.2"`
  - `audit_cache_key(*, document_hash, extractor_version, pipeline_version, snapshot_hash, rule_pack_id, rule_pack_version) -> str`
  - `dedupe_key_for(evaluation: RuleEvaluation, sheet_id: str) -> str`
  - `run_deterministic_audit(sheet_id, settings)` devolve o audit run com `coverage`

- [ ] **Step 1: Escrever o teste**

Create `apps/api/tests/test_findings_traceability.py`:

```python
from pathlib import Path

import pytest

from truss_api.audit import repository as audit_repository
from truss_api.audit.orchestrator import audit_cache_key, run_deterministic_audit
from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.db.schema import initialize_database
from truss_api.documents import repository as documents_repository
from truss_api.documents.importer import prepare_pdf_storage
from truss_api.projects import repository as projects_repository
from truss_api.projects.models import ProjectCreate, RevisionCreate
from truss_api.sheetmap.builder import build_sheet_map_for_document
from tests.factories import make_forms_sheet_pdf_bytes


@pytest.fixture()
def sheet(tmp_path: Path) -> tuple[Settings, str]:
    settings = Settings(data_dir=tmp_path / "data")
    initialize_database(settings)
    project = projects_repository.create_project(ProjectCreate(name="P"), settings)
    revision = projects_repository.create_revision(
        str(project["id"]), RevisionCreate(notes="R"), settings
    )
    prepared = prepare_pdf_storage(
        content=make_forms_sheet_pdf_bytes(),
        filename="formas.pdf",
        project_id=str(project["id"]),
        revision_id=str(revision["id"]),
        settings=settings,
    )
    document = documents_repository.create_document_from_prepared_pdf(
        project_id=str(project["id"]),
        revision_id=str(revision["id"]),
        prepared_pdf=prepared,
        settings=settings,
    )
    build_sheet_map_for_document(str(document["id"]), settings)
    return settings, str(document["sheets"][0]["id"])


def test_clean_sheet_produces_zero_findings_and_a_coverage_summary(
    sheet: tuple[Settings, str]
) -> None:
    """A folha sintetica esta completa: nada deve ser apontado, e o fallback sumiu."""
    settings, sheet_id = sheet

    run = run_deterministic_audit(sheet_id, settings)

    assert run["findings"] == []
    assert run["coverage"]["evaluated"] > 0
    assert run["coverage"]["passed"] > 0


def test_every_automatic_finding_carries_full_traceability(
    sheet: tuple[Settings, str]
) -> None:
    settings, sheet_id = sheet

    with transaction(settings) as connection:
        connection.execute(
            "UPDATE sheet_views SET declared_scale = NULL WHERE declared_scale IS NOT NULL"
        )

    run = run_deterministic_audit(sheet_id, settings)

    assert run["findings"]
    for finding in run["findings"]:
        assert finding["rule_id"]
        assert finding["rule_version"]
        assert finding["view_id"]
        assert finding["source_layer"] == "deterministic"
        assert finding["dedupe_key"]
        assert finding["evidence"]
        assert finding["bbox"]["x1"] > finding["bbox"]["x0"]


def test_rerunning_the_audit_does_not_duplicate_findings(
    sheet: tuple[Settings, str]
) -> None:
    settings, sheet_id = sheet
    with transaction(settings) as connection:
        connection.execute("UPDATE sheet_views SET declared_scale = NULL")

    first = run_deterministic_audit(sheet_id, settings)
    audit_repository.clear_audit_cache(settings)
    second = run_deterministic_audit(sheet_id, settings)

    assert len(second["findings"]) == len(first["findings"])
    with transaction(settings) as connection:
        total = connection.execute(
            "SELECT COUNT(*) FROM findings WHERE sheet_id = ? AND origin = 'ai'",
            (sheet_id,),
        ).fetchone()[0]
    assert total == len(first["findings"])


def test_cache_key_changes_when_the_rule_pack_changes() -> None:
    base = dict(
        document_hash="d",
        extractor_version="extract-v0.2",
        pipeline_version="audit-v0.2",
        snapshot_hash="s",
        rule_pack_id="planta_formas",
        rule_pack_version="1.0.0",
    )

    assert audit_cache_key(**base) != audit_cache_key(**{**base, "rule_pack_version": "1.0.1"})
    assert audit_cache_key(**base) != audit_cache_key(**{**base, "snapshot_hash": "other"})
    assert audit_cache_key(**base) == audit_cache_key(**base)


def test_human_validated_findings_are_never_replaced(sheet: tuple[Settings, str]) -> None:
    settings, sheet_id = sheet
    with transaction(settings) as connection:
        connection.execute("UPDATE sheet_views SET declared_scale = NULL")

    first = run_deterministic_audit(sheet_id, settings)
    finding_id = str(first["findings"][0]["id"])
    audit_repository.update_finding_status(
        finding_id,
        FindingStatusUpdate(status="confirmed"),
        settings,
    )
    audit_repository.clear_audit_cache(settings)

    run_deterministic_audit(sheet_id, settings)

    with transaction(settings) as connection:
        row = connection.execute(
            "SELECT status FROM findings WHERE id = ?", (finding_id,)
        ).fetchone()
    assert str(row["status"]) == "confirmed"
```

Acrescentar ao topo do arquivo:

```python
from truss_api.audit.models import FindingStatusUpdate
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_findings_traceability.py -v`
Expected: FAIL com `ImportError: cannot import name 'audit_cache_key'`

- [ ] **Step 3: Reescrever o orquestrador**

Substituir integralmente `apps/api/truss_api/sheetmap/../audit/orchestrator.py` por:

```python
from hashlib import sha256

from truss_api.audit import repository
from truss_api.core.settings import Settings
from truss_api.rules.engine import evaluate
from truss_api.rules.loader import load_pack
from truss_api.rules.models import OUTCOME_FAIL, OUTCOME_PASS, RuleEvaluation
from truss_api.sheetmap import repository as sheetmap_repository
from truss_api.sheetmap.primitives import EXTRACTOR_VERSION


AUDIT_PIPELINE_VERSION = "audit-v0.2"


def audit_cache_key(
    *,
    document_hash: str,
    extractor_version: str,
    pipeline_version: str,
    snapshot_hash: str,
    rule_pack_id: str,
    rule_pack_version: str,
) -> str:
    material = "|".join(
        [
            document_hash,
            extractor_version,
            pipeline_version,
            snapshot_hash,
            rule_pack_id,
            rule_pack_version,
        ]
    )
    return f"audit:{sha256(material.encode('utf-8')).hexdigest()[:24]}"


def dedupe_key_for(evaluation: RuleEvaluation, sheet_id: str) -> str:
    material = f"{sheet_id}|{evaluation.rule_id}|{evaluation.target_kind}|{evaluation.target_id or ''}"
    return sha256(material.encode("utf-8")).hexdigest()[:24]


def _finding_from_evaluation(
    evaluation: RuleEvaluation,
    sheet_context: dict[str, object],
) -> dict[str, object]:
    bbox = evaluation.bbox or (
        0.0,
        0.0,
        float(sheet_context["width_pt"]),
        float(sheet_context["height_pt"]),
    )

    return {
        "category": evaluation.category,
        "type": evaluation.finding_type,
        "description": evaluation.reason or evaluation.rule_id,
        "severity": evaluation.severity,
        "confidence": evaluation.confidence,
        "bbox": {"x0": bbox[0], "y0": bbox[1], "x1": bbox[2], "y1": bbox[3]},
        "evidence": evaluation.evidence,
        "rule_id": evaluation.rule_id,
        "rule_version": evaluation.rule_version,
        "view_id": evaluation.target_id if evaluation.target_kind == "view" else None,
        "source_layer": "deterministic",
        "dedupe_key": dedupe_key_for(evaluation, str(sheet_context["sheet_id"])),
    }


def run_deterministic_audit(sheet_id: str, settings: Settings) -> dict[str, object]:
    sheet_context = repository.get_sheet_context(sheet_id, settings)
    sheet_map = sheetmap_repository.get_sheet_map(sheet_id, settings)
    pack = load_pack(str(sheet_map["sheet_type"]))

    if pack is None:
        # Sem rule pack para o tipo, o Truss nao inventa conformidade nem erro.
        return repository.create_audit_run(
            sheet_context=sheet_context,
            findings=[],
            settings=settings,
            cache_key=None,
            sheet_map_id=str(sheet_map["id"]),
            rule_pack_version="",
            coverage={"evaluated": 0, "passed": 0, "failed": 0, "unknown": 0, "skipped": 0},
            evaluations=[],
        )

    cache_key = audit_cache_key(
        document_hash=str(sheet_map.get("document_hash") or ""),
        extractor_version=str(sheet_map.get("extractor_version") or EXTRACTOR_VERSION),
        pipeline_version=AUDIT_PIPELINE_VERSION,
        snapshot_hash=str(sheet_map.get("snapshot_hash") or ""),
        rule_pack_id=pack.pack_id,
        rule_pack_version=pack.version,
    )
    cached = repository.get_cached_audit_run(cache_key, settings)
    if cached is not None:
        return cached

    evaluations = evaluate(pack, sheet_map)
    findings = [
        _finding_from_evaluation(evaluation, sheet_context)
        for evaluation in evaluations
        if evaluation.outcome == OUTCOME_FAIL
    ]

    coverage = {
        "evaluated": len(evaluations),
        "passed": sum(1 for e in evaluations if e.outcome == OUTCOME_PASS),
        "failed": len(findings),
        "unknown": sum(1 for e in evaluations if e.outcome == "UNKNOWN"),
        "not_applicable": sum(1 for e in evaluations if e.outcome == "NOT_APPLICABLE"),
        "skipped": sum(1 for e in evaluations if e.outcome == "SKIPPED"),
    }

    return repository.create_audit_run(
        sheet_context=sheet_context,
        findings=findings,
        settings=settings,
        cache_key=cache_key,
        sheet_map_id=str(sheet_map["id"]),
        rule_pack_version=f"{pack.pack_id}@{pack.version}",
        coverage=coverage,
        evaluations=evaluations,
    )
```

- [ ] **Step 4: Estender o repositorio de auditoria**

Em `apps/api/truss_api/audit/repository.py`, alterar `create_audit_run` para aceitar os
parametros novos, persistir `rule_evaluations`, gravar as colunas de rastreabilidade nos findings
e **deduplicar por `dedupe_key`**, preservando status humano:

```python
def create_audit_run(
    *,
    sheet_context: dict[str, object],
    findings: list[dict[str, object]],
    settings: Settings,
    cache_key: str | None = None,
    sheet_map_id: str | None = None,
    rule_pack_version: str = "",
    coverage: dict[str, int] | None = None,
    evaluations: list[object] | None = None,
) -> dict[str, object]:
```

No `INSERT INTO audit_runs`, acrescentar as colunas `sheet_map_id`, `rule_pack_version` e
`coverage_json` com `json.dumps(coverage or {})`.

Substituir o laco de insercao de findings por:

```python
        for finding in findings:
            dedupe_key = finding.get("dedupe_key")
            existing = None

            if dedupe_key:
                existing = connection.execute(
                    """
                    SELECT id, status FROM findings
                    WHERE sheet_id = ? AND dedupe_key = ?
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (str(sheet_context["sheet_id"]), dedupe_key),
                ).fetchone()

            if existing is not None:
                # Achado ja conhecido: atualiza a vinculacao com a nova execucao e
                # preserva integralmente o status decidido por humano.
                connection.execute(
                    "UPDATE findings SET audit_run_id = ?, updated_at = ? WHERE id = ?",
                    (audit_run_id, now, str(existing["id"])),
                )
                continue

            connection.execute(
                """
                INSERT INTO findings (
                    id, audit_run_id, sheet_id, document_id, project_id, revision_id,
                    category, type, description, severity, confidence,
                    x0, y0, x1, y1, evidence_json, origin, status, rejection_reason,
                    created_at, updated_at,
                    rule_id, rule_version, sheet_map_id, view_id, source_layer, dedupe_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ai', 'pending', NULL, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    audit_run_id,
                    str(sheet_context["sheet_id"]),
                    str(sheet_context["document_id"]),
                    str(sheet_context["project_id"]),
                    str(sheet_context["revision_id"]),
                    finding["category"],
                    finding["type"],
                    finding["description"],
                    finding["severity"],
                    finding["confidence"],
                    finding["bbox"]["x0"],
                    finding["bbox"]["y0"],
                    finding["bbox"]["x1"],
                    finding["bbox"]["y1"],
                    json.dumps(finding["evidence"]),
                    now,
                    now,
                    finding.get("rule_id"),
                    finding.get("rule_version"),
                    sheet_map_id,
                    finding.get("view_id"),
                    finding.get("source_layer"),
                    dedupe_key,
                ),
            )

        for evaluation in evaluations or []:
            connection.execute(
                """
                INSERT INTO rule_evaluations (
                    id, audit_run_id, sheet_map_id, sheet_id, rule_id, rule_version,
                    rule_pack_version, target_kind, target_id, outcome, confidence,
                    reason, evidence_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    audit_run_id,
                    sheet_map_id,
                    str(sheet_context["sheet_id"]),
                    evaluation.rule_id,
                    evaluation.rule_version,
                    evaluation.rule_pack_version,
                    evaluation.target_kind,
                    evaluation.target_id,
                    evaluation.outcome,
                    evaluation.confidence,
                    evaluation.reason,
                    json.dumps(evaluation.evidence),
                    now,
                ),
            )
```

Acrescentar tambem:

```python
def clear_audit_cache(settings: Settings) -> None:
    with transaction(settings) as connection:
        connection.execute("DELETE FROM cache_entries WHERE namespace = 'audit'")
```

E em `get_audit_run`, incluir `coverage` no retorno:

```python
    result["coverage"] = json.loads(str(row["coverage_json"] or "{}"))
```

- [ ] **Step 5: Expor os campos novos no contrato**

Em `apps/api/truss_api/audit/models.py`, acrescentar ao modelo `Finding`:

```python
    rule_id: str | None = None
    rule_version: str | None = None
    view_id: str | None = None
    source_layer: str | None = None
    dedupe_key: str | None = None
```

Todos com default, para que os findings legados continuem serializando.

- [ ] **Step 6: Rodar os testes**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_findings_traceability.py -v`
Expected: PASS, 5 testes.

- [ ] **Step 7: Golden file de RuleEvaluation e findings**

O escopo exige golden files. Um so, sobre a folha sintetica, pega mudanca silenciosa de outcome,
severidade ou rastreabilidade sem exigir um teste por regra.

Acrescentar em `apps/api/tests/test_findings_traceability.py`:

```python
GOLDEN = Path(__file__).parent / "golden" / "forms_sheet_evaluations.json"


def test_rule_evaluations_match_the_golden_file(sheet: tuple[Settings, str]) -> None:
    """Congela outcome e alvo por regra. Regenerar so com mudanca intencional."""
    settings, sheet_id = sheet
    with transaction(settings) as connection:
        connection.execute("UPDATE sheet_views SET declared_scale = NULL")

    run_deterministic_audit(sheet_id, settings)

    with transaction(settings) as connection:
        rows = connection.execute(
            """
            SELECT rule_id, rule_version, target_kind, outcome
            FROM rule_evaluations
            ORDER BY rule_id, target_kind, outcome
            """
        ).fetchall()

    actual = [
        {
            "rule_id": str(row["rule_id"]),
            "rule_version": str(row["rule_version"]),
            "target_kind": str(row["target_kind"]),
            "outcome": str(row["outcome"]),
        }
        for row in rows
    ]

    if not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(actual, indent=2), encoding="utf-8")
        pytest.skip("golden gerado; rodar de novo para comparar")

    assert actual == json.loads(GOLDEN.read_text(encoding="utf-8"))
```

Acrescentar `import json` ao topo do arquivo. O golden vai para o git: e ele que denuncia
mudanca silenciosa de comportamento das regras.

Rodar duas vezes: a primeira gera o golden, a segunda compara.

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_findings_traceability.py -v`
Expected: primeira execucao SKIP no golden, segunda PASS.

- [ ] **Step 8: Rodar a suite inteira**

Run: `.venv/Scripts/python -m pytest apps/api/tests -q`
Expected: PASS. `apps/api/tests/test_audit.py` provavelmente falha porque esperava o finding de
fallback - **atualizar o teste para esperar zero findings e cobertura**, nunca reintroduzir o
fallback.

- [ ] **Step 9: Commit**

```bash
git add apps/api/truss_api/audit/ apps/api/tests/
git commit -m "feat: rule-driven audit with traceable findings and no fallback"
```

**Risco de migracao:** alto no comportamento. Auditorias passam a poder devolver zero findings, o
que o frontend precisa tolerar (Task 10). Findings legados nao tem `dedupe_key`, entao nunca
casam na deduplicacao e permanecem intocados - que e o comportamento desejado.

**Criterio de conclusao:** folha sem problemas produz zero findings e resumo de cobertura; todo
finding automatico tem `rule_id`, `view_id`, bbox e evidencia; reexecutar nao duplica nem
sobrescreve status humano.

---

### Task 10: Overlays de view no viewer

**Files:**
- Create: `apps/web/components/canvas/view-overlays.tsx`
- Modify: `apps/web/lib/projects-api.ts`
- Modify: `apps/web/components/sheet-viewer.tsx`
- Test: `apps/web/tests/view-overlays.test.tsx`

**Interfaces:**
- Consumes: `SheetMap` de `projects-api`
- Produces:
  - `SheetView` type em `projects-api.ts`
  - `ViewOverlays` component: props `views: SheetView[]`, `activeViewId: string | null`, `onSelect: (view: SheetView) => void`

- [ ] **Step 1: Escrever o teste**

Create `apps/web/tests/view-overlays.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ViewOverlays } from "@/components/canvas/view-overlays";
import type { SheetView } from "@/lib/projects-api";

function view(overrides: Partial<SheetView> = {}): SheetView {
  return {
    id: "v1",
    view_kind: "plan",
    identifier: "1",
    title: "PLANTA DE FORMAS - TERREO",
    declared_scale: "1:50",
    level: "-0.05",
    x0: 10,
    y0: 20,
    x1: 210,
    y1: 220,
    confidence: 0.9,
    provenance: "deterministic/forms-view-v1",
    ...overrides
  };
}

describe("ViewOverlays", () => {
  it("renders one inspectable overlay per view with its label", () => {
    render(<ViewOverlays activeViewId={null} onSelect={vi.fn()} views={[view()]} />);

    const overlay = screen.getByRole("button", { name: /PLANTA DE FORMAS - TERREO/ });
    expect(overlay).toBeTruthy();
    expect(overlay.textContent).toContain("1:50");
  });

  it("marks the active view so the finding can be located in it", () => {
    render(<ViewOverlays activeViewId="v1" onSelect={vi.fn()} views={[view()]} />);

    expect(screen.getByRole("button", { name: /PLANTA/ }).dataset.active).toBe("true");
  });

  it("labels a view without title by its kind instead of showing nothing", () => {
    render(
      <ViewOverlays activeViewId={null} onSelect={vi.fn()} views={[view({ title: null })]} />
    );

    expect(screen.getByRole("button", { name: /plan/i })).toBeTruthy();
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `npm --workspace apps/web run test -- view-overlays`
Expected: FAIL - modulo nao existe.

- [ ] **Step 3: Acrescentar o tipo**

Em `apps/web/lib/projects-api.ts`, acrescentar antes de `SheetMap` e incluir no tipo:

```typescript
export type SheetView = {
  id: string;
  view_kind: string;
  identifier: string | null;
  title: string | null;
  declared_scale: string | null;
  level: string | null;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  confidence: number;
  provenance: string;
};
```

e dentro de `SheetMap`, acrescentar `views: SheetView[];`.

- [ ] **Step 4: Implementar o componente**

Create `apps/web/components/canvas/view-overlays.tsx`:

```tsx
"use client";

import { CANVAS_NAVIGATION } from "@/lib/canvas-navigation";
import type { SheetView } from "@/lib/projects-api";

const KIND_LABEL: Record<string, string> = {
  plan: "planta",
  section: "corte",
  detail: "detalhe"
};

export function ViewOverlays({
  activeViewId,
  onSelect,
  views
}: {
  activeViewId: string | null;
  onSelect: (view: SheetView) => void;
  views: SheetView[];
}) {
  return (
    <>
      {views.map((view) => {
        const label = view.title ?? KIND_LABEL[view.view_kind] ?? view.view_kind;

        return (
          <button
            aria-label={`Inspecionar view ${label}`}
            className="absolute border border-dashed border-truss-info/60 bg-truss-info/5 text-left transition-colors hover:bg-truss-info/10 data-[active=true]:border-truss-info data-[active=true]:bg-truss-info/15"
            data-active={view.id === activeViewId}
            key={view.id}
            onPointerDown={() => onSelect(view)}
            style={{
              left: view.x0 * CANVAS_NAVIGATION.renderScale,
              top: view.y0 * CANVAS_NAVIGATION.renderScale,
              width: (view.x1 - view.x0) * CANVAS_NAVIGATION.renderScale,
              height: (view.y1 - view.y0) * CANVAS_NAVIGATION.renderScale
            }}
            type="button"
          >
            <span className="absolute -top-5 left-0 flex items-center gap-1.5 border border-truss-info/60 bg-truss-panel px-1.5 py-0.5 font-mono text-[8.5px] uppercase tracking-[0.08em] text-truss-info">
              {view.identifier ? `${view.identifier} ` : ""}
              {label}
              {view.declared_scale ? ` · ${view.declared_scale}` : ""}
            </span>
          </button>
        );
      })}
    </>
  );
}
```

- [ ] **Step 5: Render no viewer**

Em `apps/web/components/sheet-viewer.tsx`, acrescentar o estado e o render dentro da camada
transformada, logo antes do bloco `{showFindings ? ...}`:

```tsx
  const [activeViewId, setActiveViewId] = useState<string | null>(null);
```

```tsx
              {showViews && sheetMap ? (
                <ViewOverlays
                  activeViewId={activeViewId}
                  onSelect={(view) => setActiveViewId(view.id)}
                  views={sheetMap.views}
                />
              ) : null}
```

com `const [showViews, setShowViews] = useState(true);` e um botao na barra do canvas
reaproveitando a classe `truss-icon-button`, ao lado do botao de achados:

```tsx
          <button
            aria-label="Mostrar ou ocultar views"
            aria-pressed={showViews}
            className="truss-icon-button"
            onClick={() => setShowViews((current) => !current)}
            type="button"
          >
            <LayoutGrid aria-hidden="true" className="truss-icon h-4 w-4" />
          </button>
```

importando `LayoutGrid` de `lucide-react` e `ViewOverlays` de `@/components/canvas/view-overlays`.

Quando um finding tiver `view_id`, selecionar a view correspondente ao foca-lo, dentro de
`focusFinding`:

```tsx
    if (finding.view_id) {
      setActiveViewId(finding.view_id);
    }
```

- [ ] **Step 6: Validar o frontend**

Run: `npm run lint && npm run typecheck && npm run test:web`
Expected: PASS nos tres.

- [ ] **Step 7: Commit**

```bash
git add apps/web/
git commit -m "feat: inspectable view overlays on the sheet canvas"
```

**Risco de migracao:** `sheetMap.views` nao existe nos sheet maps antigos servidos pela API. O
componente recebe `[]` e nao renderiza nada. Sem quebra.

**Criterio de conclusao:** views aparecem como overlays inspecionaveis, o toggle funciona, e focar
um finding com `view_id` destaca a view correspondente.

---

### Task 11: Reprocessamento, calibracao medida e fechamento

**Files:**
- Modify: `calibration/rancho-queimado-r01.yml`
- Modify: `apps/api/tests/test_calibration.py`
- Create: `docs/DECISIONS.md` (entrada nova)

**Interfaces:**
- Consumes: tudo das tarefas anteriores.

- [ ] **Step 1: Reprocessar as 85 folhas com o pipeline novo**

Run:

```bash
.venv/Scripts/python -c "
import sys; sys.path.insert(0,'apps/api')
from truss_api.core.settings import get_settings
from truss_api.db.connection import transaction
from truss_api.sheetmap.builder import build_sheet_map_for_document
settings = get_settings()
with transaction(settings) as connection:
    documents = [str(row['id']) for row in connection.execute('SELECT id FROM documents')]
total = 0
for document_id in documents:
    total += len(build_sheet_map_for_document(document_id, settings))
print('sheet maps v0.2:', total)
with transaction(settings) as connection:
    print('views:', connection.execute('SELECT COUNT(*) FROM sheet_views').fetchone()[0])
    print('sheet_maps totais (v0.1 preservados + v0.2):', connection.execute('SELECT COUNT(*) FROM sheet_maps').fetchone()[0])
"
```

Expected: `sheet maps v0.2: 85`, views > 0, e o total de `sheet_maps` **maior que 85**, provando
que os snapshots v0.1 nao foram apagados.

- [ ] **Step 2: Preencher o gabarito com a saida, marcada como draft**

Run:

```bash
.venv/Scripts/python -X utf8 - <<'PY'
import sys, pathlib, yaml; sys.path.insert(0,'apps/api')
import fitz
from truss_api.sheetmap.primitives import extract_page
from truss_api.sheetmap.geometry import geometry_from_extraction
from truss_api.sheetmap.regions import detect_regions, extract_line_boxes
from truss_api.sheetmap.views.detector import detect_forms_views

path = 'data/originals/69f87430-6e60-4cd5-bfb8-c4cde0b09d79/09e35528-5556-4fce-939e-806897d7bbb1/7d2f9c32bc9d4988-Proj_Estrutural_RanchoQueimado_geral.pdf'
source = pathlib.Path('calibration/rancho-queimado-r01.yml')
document_yaml = yaml.safe_load(source.read_text(encoding='utf-8'))
pdf = fitz.open(path)

for sheet in document_yaml['sheets']:
    if sheet['sheet_type'] != 'planta_formas':
        continue
    page = pdf.load_page(sheet['page_index'])
    extraction = extract_page(page)
    regions = detect_regions(geometry_from_extraction(extraction), extract_line_boxes(page))
    sheet['content_regions'] = [
        {'kind': r.region_kind, 'bbox': [round(r.x0, 1), round(r.y0, 1), round(r.x1, 1), round(r.y1, 1)]}
        for r in regions
    ]
    sheet['views'] = [
        {
            'view_id': f'v{index + 1}',
            'view_kind': v.view_kind,
            'identifier': v.identifier,
            'title': v.title,
            'declared_scale': v.declared_scale,
            'level': v.level,
            'bbox': [round(c, 1) for c in v.bbox],
            'status': 'draft_unverified',
        }
        for index, v in enumerate(detect_forms_views(extraction, regions))
    ]

source.write_text(yaml.safe_dump(document_yaml, allow_unicode=True, sort_keys=False), encoding='utf-8')
print('gabarito preenchido; permanece draft_unverified ate revisao humana')
PY
```

- [ ] **Step 3: Estender o teste de calibracao para medir views**

Acrescentar em `apps/api/tests/test_calibration.py`:

```python
def test_view_detection_meets_calibration_thresholds(tmp_path: Path) -> None:
    expected = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    pdf_path = _find_reference_pdf(expected["document"]["filename"])

    if pdf_path is None:
        pytest.skip("PDF de referencia ausente.")

    import fitz

    from truss_api.calibration.metrics import match_boxes, precision, recall
    from truss_api.sheetmap.geometry import geometry_from_extraction
    from truss_api.sheetmap.primitives import extract_page
    from truss_api.sheetmap.regions import detect_regions, extract_line_boxes
    from truss_api.sheetmap.views.detector import detect_forms_views

    document = fitz.open(pdf_path)
    thresholds = expected["thresholds"]
    matched_total = missed_total = spurious_total = 0
    attributes_total = attributes_ok = 0

    for sheet in expected["sheets"]:
        if sheet["sheet_type"] != "planta_formas" or not sheet["views"]:
            continue

        page = document.load_page(sheet["page_index"])
        extraction = extract_page(page)
        regions = detect_regions(geometry_from_extraction(extraction), extract_line_boxes(page))
        detected = detect_forms_views(extraction, regions)

        matched, missed, spurious = match_boxes(
            [tuple(view["bbox"]) for view in sheet["views"]],
            [view.bbox for view in detected],
            min_iou=thresholds["content_block_iou"],
        )
        matched_total += matched
        missed_total += missed
        spurious_total += spurious

        for view in detected:
            attributes_total += 1
            attributes_ok += bool(view.title and view.declared_scale)

    block_recall = recall(matched_total, missed_total)
    block_precision = precision(matched_total, spurious_total)
    attribute_accuracy = attributes_ok / attributes_total if attributes_total else 0.0

    print(
        f"\nviews: recall {block_recall:.1%} | precisao {block_precision:.1%} "
        f"| atributos {attribute_accuracy:.1%} ({attributes_total} views)"
    )
    if expected["status"] != "human_verified":
        print("AVISO: gabarito draft_unverified - detecta regressao, nao prova correcao.")

    assert block_recall >= thresholds["content_block_recall"]
    assert attribute_accuracy >= thresholds["view_attribute_accuracy"]
```

- [ ] **Step 4: Rodar a calibracao**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_calibration.py -v -s`
Expected: impressao das metricas e PASS. Se o recall ou a acuracia ficarem abaixo, **ajustar o
detector**, nunca o threshold.

- [ ] **Step 5: Rodar tudo**

Run:

```bash
.venv/Scripts/python -m pytest apps/api/tests -q
npm run lint && npm run typecheck && npm run test:web
```

Expected: tudo verde.

- [ ] **Step 6: Registrar as decisoes**

Acrescentar a `docs/DECISIONS.md` uma entrada com data, contendo: o formato de artefato
comprimido enderecado por hash, a decisao de embutir o hash no `pipeline_version` em vez de
reconstruir a tabela, os valores finais das tolerancias de `anchors.py` com o numero de
associacao medido, e a remocao do finding de fallback com preservacao dos 63 findings legados.

- [ ] **Step 7: Commit**

```bash
git add calibration/ apps/api/tests/test_calibration.py docs/DECISIONS.md
git commit -m "feat: measure view detection against calibration ground truth"
```

**Risco de migracao:** o Step 1 grava 85 sheet maps novos. Os antigos permanecem. O banco cresce,
o que e o custo esperado da imutabilidade.

**Criterio de conclusao:** metricas impressas e acima dos thresholds, com o gabarito ainda
marcado `draft_unverified`.

---

## Criterios de aceite da F2

Nenhum e verificado por leitura; todos por comando rodado.

- [ ] recall de content blocks >= 85% com IoU >= 0,50
- [ ] associacao correta de titulo, escala e nivel >= 90%
- [ ] cobertura dos findings do ground truth >= 60%
- [ ] precisao dos findings >= 70%
- [ ] 100% dos findings automaticos com `rule_id`, `view_id`, bbox e evidencia
- [ ] nenhum finding artificial de "nenhum problema encontrado"
- [ ] `.venv/Scripts/python -m pytest apps/api/tests` integralmente verde
- [ ] `npm run lint && npm run typecheck && npm run test:web` integralmente verde
- [ ] migrations preservando as 85 sheets e os 63 findings, com os 2 findings validados por humano
      com status original
- [ ] **validacao manual das seis folhas unicas de formas pelo proprietario**, mudando o gabarito
      para `human_verified`

O ultimo item nao pode ser satisfeito por nenhum agente. Enquanto o gabarito estiver
`draft_unverified`, as metricas medem regressao, nao correcao, e **a fase nao esta concluida**.

## Fora do escopo

Extracao de pilares, vigas, lajes ou aberturas; visao multimodal; aprendizado com feedback;
armaduras e resumos de aco; OCR como caminho principal; autenticacao, SaaS ou multiusuario;
comparacao entre revisoes; grandes refatoracoes de UI. Nenhuma tarefa acima abre essas frentes.
