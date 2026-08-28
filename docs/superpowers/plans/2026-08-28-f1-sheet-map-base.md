# F1 - Sheet Map Base - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir a camada Sheet Map base - extracao vetorial, deteccao de moldura e carimbo, parse dos campos do carimbo e classificacao do tipo de prancha - com sistema de migrations e gabarito de calibracao.

**Architecture:** Um modulo novo `truss_api/sheetmap/` monta, no momento do import, uma estrutura deterministica por folha a partir da geometria vetorial e do texto nativo. A geometria bruta vai para disco em `data/geometry/`; apenas a estrutura derivada entra no SQLite, em duas tabelas novas. Nada do pipeline existente muda de contrato: `findings`, viewer, canvas e feedback continuam falando bbox em `pt`.

**Tech Stack:** Python 3.11, FastAPI, PyMuPDF (`fitz`), SQLite, pytest, Next.js 15, TypeScript, Vitest.

> **Status: EXECUTADO em 2026-08-28.** A pedido do proprietario ("sem muitos testes"), a suite foi
> enxugada de ~46 para 20 testes, mantendo os que cobrem falha silenciosa: as tres armadilhas de
> extracao, persistencia, o endpoint e a calibracao. Os arquivos de teste foram consolidados -
> `test_sheetmap_reading.py` cobre as Tasks 4, 5 e 6 juntas, e nao existem
> `test_sheetmap_regions.py`, `test_sheetmap_title_block.py`, `test_sheetmap_classifier.py` nem
> `test_sheetmap_repository.py` separados. As contagens "Expected: PASS, N tests" abaixo refletem
> o plano original, nao o executado.
>
> Um defeito encontrado apos a execucao e corrigido: o titulo da prancha era escolhido pelo
> candidato mais longo do carimbo, o que trazia o nome da obra. Passou a ser escolhido por
> proximidade a categoria (28/28 corretos).

## Global Constraints

- Coordenadas canonicas em pontos PDF (`pt`). Pixels de render sao derivados, nunca persistidos como fonte.
- Construcao do Sheet Map e 100% deterministica. Nenhuma chamada a modelo nesta fase.
- Geometria bruta nunca entra no SQLite. Vai para `data/geometry/{project_id}/{revision_id}/{sheet_id}.json`.
- Rotas FastAPI recebem `Settings` por `Depends(get_settings)`, para permitir override em teste.
- Nenhum teste pode depender de rede nem de material de cliente.
- Revisoes sao imutaveis: nada nesta fase sobrescreve PDF, render ou revisao existente.
- Texto tecnico e comparado sempre via `truss_api.core.text.normalize`, nunca com `.upper()` cru.
- Toda tabela nova usa a convencao existente: PK `TEXT` uuid4, timestamps `TEXT` ISO-8601 UTC, FK `ON DELETE RESTRICT`.

## Evidencia que fundamenta os algoritmos

Medida em `Proj_Estrutural_RanchoQueimado_geral.pdf` (28 paginas, A0 e A1). Os numeros abaixo
foram verificados antes da escrita deste plano e sao os criterios de aceite reais.

| Fato medido | Valor |
|---|---|
| Material vetorial | 26.019 drawings, 32.708 segmentos de linha na folha 1 |
| Moldura como retangulo | presente em 28/28, area entre 92,6% e 94,8% da pagina, origem `(71,29)` |
| **Carimbo como retangulo fechado** | **NAO EXISTE - 0 candidatos.** E desenhado com linhas soltas |
| Carimbo por ancora de texto | **28/28**, sempre no quadrante inferior direito |
| Codigo da prancha `EST-0010-A` | 84/85 folhas no banco, um por folha |
| Categoria no carimbo | `PLANTA DE LOCACAO` (1), `PLANTA DE FORMAS` (5), `PLANTA DE ARMADURAS` (17) |
| Ordem das linhas do carimbo | **instavel** entre paginas - nao usar indice de linha |

Duas consequencias que o plano incorpora e que uma implementacao ingenua erraria:

1. **O carimbo nao pode ser detectado por retangulo.** A deteccao e por ancora de texto
   (codigo da prancha, `CPF`, `REVISAO`, `EMISSAO`, `PROJETO ESTRUTURAL`), tomando o bbox
   envolvente dos blocos que casam.
2. **Os campos do carimbo nao podem ser lidos por posicao na lista de linhas.** Em algumas
   paginas a categoria vem antes de `PROJETO ESTRUTURAL`, em outras depois. A categoria e
   identificada por igualdade exata contra um vocabulario conhecido.

---

### Task 1: Sistema de migrations

Substitui o `CREATE TABLE IF NOT EXISTS` + `_ensure_column()` manual de `db/schema.py`, que ja
esta fragil com dois dicts de colunas e nao sustenta as tabelas novas.

Foi verificado no banco real (`data/db/truss.sqlite`) que todas as colunas legadas de
`chat_messages` e `chat_message_context_items` ja existem, portanto o caminho de `_ensure_column`
pode ser aposentado com seguranca.

**Files:**
- Create: `apps/api/truss_api/db/migrations.py`
- Create: `apps/api/truss_api/db/migrations/001_baseline.sql`
- Modify: `apps/api/truss_api/db/schema.py`
- Test: `apps/api/tests/test_migrations.py`

**Interfaces:**
- Consumes: `truss_api.core.settings.Settings`, `truss_api.db.connection.transaction`
- Produces:
  - `available_migrations(directory: Path | None = None) -> list[tuple[str, Path]]`
  - `apply_migrations(settings: Settings, directory: Path | None = None) -> list[str]`
  - `initialize_database(settings: Settings | None = None) -> None` (assinatura preservada)

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_migrations.py`:

```python
from pathlib import Path

from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.db.migrations import apply_migrations, available_migrations


def _table_names(settings: Settings) -> set[str]:
    with transaction(settings) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    return {str(row["name"]) for row in rows}


def test_available_migrations_are_sorted_by_version() -> None:
    versions = [version for version, _ in available_migrations()]
    assert versions == sorted(versions)
    assert "001" in versions


def test_apply_migrations_creates_baseline_schema(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data")

    applied = apply_migrations(settings)

    assert "001" in applied
    tables = _table_names(settings)
    assert {"projects", "revisions", "documents", "sheets", "findings"} <= tables
    assert "schema_migrations" in tables


def test_apply_migrations_is_idempotent(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data")

    apply_migrations(settings)
    second_run = apply_migrations(settings)

    assert second_run == []


def test_apply_migrations_on_legacy_database_without_version_table(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data")
    baseline = (
        Path(__file__).resolve().parents[1]
        / "truss_api"
        / "db"
        / "migrations"
        / "001_baseline.sql"
    )
    with transaction(settings) as connection:
        connection.executescript(baseline.read_text(encoding="utf-8"))

    applied = apply_migrations(settings)

    assert applied == ["001"]
    assert "projects" in _table_names(settings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_migrations.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'truss_api.db.migrations'`

- [ ] **Step 3: Create the baseline migration**

Create `apps/api/truss_api/db/migrations/001_baseline.sql` with the exact content of the
`SCHEMA_SQL` string currently in `apps/api/truss_api/db/schema.py` (from `CREATE TABLE IF NOT
EXISTS projects` through the final `idx_cache_entries_namespace` index), plus this index that
`initialize_database` currently creates separately:

```sql
CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation
ON chat_messages(conversation_id, created_at);
```

Copy the SQL verbatim - every statement already uses `IF NOT EXISTS`, so it is safe to run
against the existing local database.

- [ ] **Step 4: Write the migrations runner**

Create `apps/api/truss_api/db/migrations.py`:

```python
from datetime import UTC, datetime
from pathlib import Path
from sqlite3 import Connection

from truss_api.core.settings import Settings, get_settings
from truss_api.db.connection import transaction


MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

SCHEMA_MIGRATIONS_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def available_migrations(directory: Path | None = None) -> list[tuple[str, Path]]:
    resolved = directory or MIGRATIONS_DIR
    migrations = [
        (path.name.split("_", 1)[0], path)
        for path in sorted(resolved.glob("*.sql"))
    ]
    return migrations


def applied_versions(connection: Connection) -> set[str]:
    rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
    return {str(row["version"]) for row in rows}


def apply_migrations(
    settings: Settings | None = None,
    directory: Path | None = None,
) -> list[str]:
    resolved = settings or get_settings()
    applied: list[str] = []

    with transaction(resolved) as connection:
        connection.executescript(SCHEMA_MIGRATIONS_SQL)
        already_applied = applied_versions(connection)

        for version, path in available_migrations(directory):
            if version in already_applied:
                continue

            connection.executescript(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, _now()),
            )
            applied.append(version)

    return applied
```

- [ ] **Step 5: Rewrite schema.py to delegate**

Replace the entire content of `apps/api/truss_api/db/schema.py` with:

```python
from truss_api.core.settings import Settings
from truss_api.db.migrations import apply_migrations


def initialize_database(settings: Settings | None = None) -> None:
    apply_migrations(settings)
```

This removes `SCHEMA_SQL`, `CHAT_MESSAGE_COLUMNS`, `CHAT_MESSAGE_CONTEXT_COLUMNS` and
`_ensure_column`, whose only remaining purpose was upgrading databases that no longer exist.

- [ ] **Step 6: Run the full suite to verify nothing regressed**

Run: `.venv/Scripts/python -m pytest apps/api/tests -v`
Expected: PASS - the 33 existing tests plus the 4 new ones, 37 total.

- [ ] **Step 7: Verify against the real local database**

Run:

```bash
.venv/Scripts/python -c "from truss_api.db.schema import initialize_database; initialize_database(); print('ok')"
```

Expected: prints `ok`. Then confirm the existing data survived:

```bash
.venv/Scripts/python -c "
import sqlite3
c = sqlite3.connect('data/db/truss.sqlite')
print('sheets:', c.execute('select count(*) from sheets').fetchone()[0])
print('findings:', c.execute('select count(*) from findings').fetchone()[0])
print('migrations:', c.execute('select version from schema_migrations').fetchall())
"
```

Expected: `sheets: 85`, `findings: 63`, `migrations: [('001',)]`

- [ ] **Step 8: Commit**

```bash
git add apps/api/truss_api/db/migrations.py apps/api/truss_api/db/migrations/001_baseline.sql apps/api/truss_api/db/schema.py apps/api/tests/test_migrations.py
git commit -m "feat: add numbered sql migrations with baseline"
```

---

### Task 2: Normalizacao de texto

Infra usada por todo o resto da fase. A regra atual em `audit/orchestrator.py:62` tenta cobrir
acentuacao listando `"LOCACAO"` e `"LOCACAO"` acentuado na mao dentro de `title_terms`, o que nao
escala.

**Files:**
- Create: `apps/api/truss_api/core/text.py`
- Test: `apps/api/tests/test_text.py`

**Interfaces:**
- Produces:
  - `normalize(value: str) -> str`
  - `contains_term(haystack: str, term: str) -> bool`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_text.py`:

```python
from truss_api.core.text import contains_term, normalize


def test_normalize_removes_accents_and_uppercases() -> None:
    assert normalize("Planta de Locação") == "PLANTA DE LOCACAO"


def test_normalize_collapses_whitespace() -> None:
    assert normalize("  ARMAÇÃO\n  NEGATIVA\tDAS LAJES  ") == "ARMACAO NEGATIVA DAS LAJES"


def test_normalize_handles_empty_string() -> None:
    assert normalize("") == ""


def test_contains_term_is_accent_insensitive_in_both_directions() -> None:
    assert contains_term("PLANTA DE LOCACAO DAS FUNDACOES", "Locação") is True
    assert contains_term("Planta de Locação das Fundações", "LOCACAO") is True


def test_contains_term_returns_false_when_absent() -> None:
    assert contains_term("PLANTA DE FORMAS", "ARMADURAS") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_text.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'truss_api.core.text'`

- [ ] **Step 3: Write the implementation**

Create `apps/api/truss_api/core/text.py`:

```python
import re
import unicodedata


_WHITESPACE = re.compile(r"\s+")


def normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return _WHITESPACE.sub(" ", without_accents).strip().upper()


def contains_term(haystack: str, term: str) -> bool:
    return normalize(term) in normalize(haystack)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_text.py -v`
Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add apps/api/truss_api/core/text.py apps/api/tests/test_text.py
git commit -m "feat: add accent-insensitive text normalization"
```

---

### Task 3: Extracao e persistencia de geometria

A folha 1 tem 32.708 segmentos de linha. Com 85 folhas isso passa de 2,8 milhoes de registros,
que nao podem ir para o SQLite. A geometria vai para disco em JSON e o banco guarda so o caminho.

**Files:**
- Create: `apps/api/truss_api/sheetmap/__init__.py` (vazio)
- Create: `apps/api/truss_api/sheetmap/geometry.py`
- Modify: `apps/api/truss_api/core/settings.py` (add `geometry_dir` property)
- Modify: `apps/api/truss_api/core/storage.py` (include `geometry_dir`)
- Test: `apps/api/tests/test_sheetmap_geometry.py`

**Interfaces:**
- Consumes: `Settings`
- Produces:
  - `GeometryRect` dataclass with fields `x0, y0, x1, y1` and properties `width`, `height`, `area`
  - `PageGeometry` dataclass with fields `width_pt, height_pt, rects: list[GeometryRect], line_count: int, curve_count: int` and property `page_area`
  - `extract_page_geometry(page: fitz.Page, min_area_ratio: float = 0.0002) -> PageGeometry`
  - `geometry_relative_path(project_id, revision_id, sheet_id) -> str`
  - `write_page_geometry(geometry, *, project_id, revision_id, sheet_id, settings) -> str`
  - `read_page_geometry(relative_path: str, settings: Settings) -> PageGeometry`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_sheetmap_geometry.py`:

```python
from pathlib import Path

import fitz

from truss_api.core.settings import Settings
from truss_api.sheetmap.geometry import (
    extract_page_geometry,
    read_page_geometry,
    write_page_geometry,
)


def _page_with_rects() -> fitz.Page:
    document = fitz.open()
    page = document.new_page(width=1000, height=800)
    page.draw_rect(fitz.Rect(20, 20, 980, 780))
    page.draw_rect(fitz.Rect(700, 650, 970, 770))
    page.draw_line(fitz.Point(100, 100), fitz.Point(400, 400))
    return page


def test_extract_page_geometry_reads_page_size() -> None:
    geometry = extract_page_geometry(_page_with_rects())

    assert geometry.width_pt == 1000
    assert geometry.height_pt == 800
    assert geometry.page_area == 800000


def test_extract_page_geometry_collects_rectangles() -> None:
    geometry = extract_page_geometry(_page_with_rects())

    areas = sorted(round(rect.area) for rect in geometry.rects)
    assert 960 * 760 in areas
    assert 270 * 120 in areas


def test_extract_page_geometry_counts_line_items() -> None:
    geometry = extract_page_geometry(_page_with_rects())

    assert geometry.line_count >= 1


def test_extract_page_geometry_drops_rectangles_below_threshold() -> None:
    document = fitz.open()
    page = document.new_page(width=1000, height=800)
    page.draw_rect(fitz.Rect(0, 0, 2, 2))

    geometry = extract_page_geometry(page, min_area_ratio=0.001)

    assert geometry.rects == []


def test_write_and_read_page_geometry_roundtrip(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data")
    geometry = extract_page_geometry(_page_with_rects())

    relative = write_page_geometry(
        geometry,
        project_id="project-1",
        revision_id="revision-1",
        sheet_id="sheet-1",
        settings=settings,
    )
    restored = read_page_geometry(relative, settings)

    assert relative == "geometry/project-1/revision-1/sheet-1.json"
    assert (settings.data_dir / relative).exists()
    assert restored.width_pt == geometry.width_pt
    assert len(restored.rects) == len(geometry.rects)
    assert restored.line_count == geometry.line_count
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_sheetmap_geometry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'truss_api.sheetmap'`

- [ ] **Step 3: Add the geometry directory to settings and storage**

In `apps/api/truss_api/core/settings.py`, add this property right after `cache_dir`:

```python
    @property
    def geometry_dir(self) -> Path:
        return self.data_dir / "geometry"
```

In `apps/api/truss_api/core/storage.py`, add `resolved.geometry_dir,` to the tuple returned by
`storage_directories`, after `resolved.cache_dir,`.

- [ ] **Step 4: Write the geometry module**

Create the empty file `apps/api/truss_api/sheetmap/__init__.py`, then create
`apps/api/truss_api/sheetmap/geometry.py`:

```python
from dataclasses import dataclass
import json
from pathlib import Path

import fitz

from truss_api.core.settings import Settings


@dataclass(frozen=True)
class GeometryRect:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)


@dataclass(frozen=True)
class PageGeometry:
    width_pt: float
    height_pt: float
    rects: list[GeometryRect]
    line_count: int
    curve_count: int

    @property
    def page_area(self) -> float:
        return self.width_pt * self.height_pt


def extract_page_geometry(page: fitz.Page, min_area_ratio: float = 0.0002) -> PageGeometry:
    rect = page.rect
    page_area = rect.width * rect.height
    minimum_area = page_area * min_area_ratio

    rects: list[GeometryRect] = []
    line_count = 0
    curve_count = 0

    for drawing in page.get_drawings():
        for item in drawing["items"]:
            if item[0] == "l":
                line_count += 1
            elif item[0] == "c":
                curve_count += 1

        bounds = drawing["rect"]
        if bounds.width * bounds.height < minimum_area:
            continue

        rects.append(
            GeometryRect(
                x0=float(bounds.x0),
                y0=float(bounds.y0),
                x1=float(bounds.x1),
                y1=float(bounds.y1),
            )
        )

    return PageGeometry(
        width_pt=float(rect.width),
        height_pt=float(rect.height),
        rects=rects,
        line_count=line_count,
        curve_count=curve_count,
    )


def geometry_relative_path(project_id: str, revision_id: str, sheet_id: str) -> str:
    return f"geometry/{project_id}/{revision_id}/{sheet_id}.json"


def write_page_geometry(
    geometry: PageGeometry,
    *,
    project_id: str,
    revision_id: str,
    sheet_id: str,
    settings: Settings,
) -> str:
    relative = geometry_relative_path(project_id, revision_id, sheet_id)
    target = settings.data_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "width_pt": geometry.width_pt,
        "height_pt": geometry.height_pt,
        "line_count": geometry.line_count,
        "curve_count": geometry.curve_count,
        "rects": [
            [rect.x0, rect.y0, rect.x1, rect.y1] for rect in geometry.rects
        ],
    }
    target.write_text(json.dumps(payload), encoding="utf-8")
    return relative


def read_page_geometry(relative_path: str, settings: Settings) -> PageGeometry:
    source = Path(settings.data_dir / relative_path)
    payload = json.loads(source.read_text(encoding="utf-8"))

    return PageGeometry(
        width_pt=float(payload["width_pt"]),
        height_pt=float(payload["height_pt"]),
        rects=[
            GeometryRect(x0=values[0], y0=values[1], x1=values[2], y1=values[3])
            for values in payload["rects"]
        ],
        line_count=int(payload["line_count"]),
        curve_count=int(payload["curve_count"]),
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_sheetmap_geometry.py -v`
Expected: PASS, 5 tests.

- [ ] **Step 6: Commit**

```bash
git add apps/api/truss_api/sheetmap/ apps/api/truss_api/core/settings.py apps/api/truss_api/core/storage.py apps/api/tests/test_sheetmap_geometry.py
git commit -m "feat: extract and persist page vector geometry to disk"
```

---

### Task 4: Deteccao de moldura e carimbo

**A moldura e detectada por retangulo. O carimbo NAO.** Foi verificado que o carimbo das pranchas
reais nao existe como retangulo fechado (0 candidatos em 3 paginas testadas); ele e desenhado com
linhas soltas. A deteccao do carimbo e por ancora de texto, abordagem que acertou 28/28 paginas.

**Files:**
- Create: `apps/api/truss_api/sheetmap/regions.py`
- Test: `apps/api/tests/test_sheetmap_regions.py`

**Interfaces:**
- Consumes: `PageGeometry`, `GeometryRect` from Task 3; `normalize` from Task 2
- Produces:
  - Constants `REGION_FRAME = "moldura"`, `REGION_TITLE_BLOCK = "carimbo"`, `REGION_DRAWING = "area_desenho"`
  - `TextBox` dataclass with fields `text: str, x0: float, y0: float, x1: float, y1: float`
  - `DetectedRegion` dataclass with fields `region_kind: str, x0, y0, x1, y1: float, confidence: float`
  - `extract_line_boxes(page: fitz.Page) -> list[TextBox]`
  - `detect_frame(geometry: PageGeometry) -> DetectedRegion`
  - `detect_title_block(text_boxes: list[TextBox], geometry: PageGeometry, frame: DetectedRegion) -> DetectedRegion | None`
  - `detect_regions(geometry: PageGeometry, text_boxes: list[TextBox]) -> list[DetectedRegion]`

**Duas armadilhas verificadas experimentalmente durante o desenho deste plano.** Ambas produzem
falha silenciosa, nao excecao:

1. **Nao use `page.get_text("blocks")` aqui.** O modo `blocks` agrupa linhas vizinhas num unico
   bloco, e o carimbo inteiro vira uma string so - com isso a categoria nunca casa por igualdade
   exata e o tipo da prancha sai sempre `desconhecido`. A extracao tem de ser em granularidade de
   **linha**, via `page.get_text("dict")`. Medido: com `blocks`, 0/28 categorias; com linhas,
   28/28. A tabela `text_blocks` existente continua usando `blocks` e nao muda.
2. **O bbox das ancoras e apenas um limite inferior do carimbo.** Campos que ficam abaixo da
   ultima ancora caem fora dele. Como o carimbo ocupa o canto da moldura, a regiao detectada e
   estendida ate `frame.x1` e `frame.y1`. Sem essa extensao o fixture sintetico da Task 7 falha,
   embora o PDF real passe - exatamente o tipo de divergencia que esconde o defeito ate producao.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_sheetmap_regions.py`:

```python
from truss_api.sheetmap.geometry import GeometryRect, PageGeometry
from truss_api.sheetmap.regions import (
    REGION_DRAWING,
    REGION_FRAME,
    REGION_TITLE_BLOCK,
    TextBox,
    detect_frame,
    detect_regions,
    detect_title_block,
)


def _geometry() -> PageGeometry:
    return PageGeometry(
        width_pt=1000,
        height_pt=800,
        rects=[
            GeometryRect(0, 0, 1000, 800),
            GeometryRect(20, 10, 970, 770),
            GeometryRect(300, 300, 500, 450),
        ],
        line_count=1200,
        curve_count=30,
    )


def _title_block_boxes() -> list[TextBox]:
    return [
        TextBox("EST-0060-A", 700, 700, 820, 715),
        TextBox("CPF: 951.770.276-00", 700, 720, 850, 735),
        TextBox("REVISÃO", 860, 700, 920, 715),
        TextBox("L33", 100, 100, 130, 115),
    ]


def test_detect_frame_picks_largest_rect_below_full_page() -> None:
    frame = detect_frame(_geometry())

    assert frame.region_kind == REGION_FRAME
    assert (frame.x0, frame.y0, frame.x1, frame.y1) == (20, 10, 970, 770)


def test_detect_frame_falls_back_to_full_page_when_no_candidate() -> None:
    geometry = PageGeometry(
        width_pt=1000, height_pt=800, rects=[], line_count=0, curve_count=0
    )

    frame = detect_frame(geometry)

    assert (frame.x0, frame.y0, frame.x1, frame.y1) == (0, 0, 1000, 800)
    assert frame.confidence < 0.5


def test_detect_title_block_uses_text_anchors_in_bottom_right() -> None:
    frame = detect_frame(_geometry())

    title_block = detect_title_block(_title_block_boxes(), _geometry(), frame)

    assert title_block is not None
    assert title_block.region_kind == REGION_TITLE_BLOCK
    assert title_block.x0 == 700
    assert title_block.y0 == 700


def test_detect_title_block_extends_to_the_frame_corner() -> None:
    frame = detect_frame(_geometry())

    title_block = detect_title_block(_title_block_boxes(), _geometry(), frame)

    assert title_block is not None
    assert title_block.x1 == frame.x1
    assert title_block.y1 == frame.y1


def test_detect_title_block_ignores_anchors_outside_bottom_right() -> None:
    boxes = [TextBox("EST-0060-A", 40, 40, 160, 55)]

    assert detect_title_block(boxes, _geometry(), detect_frame(_geometry())) is None


def test_detect_title_block_returns_none_without_anchors() -> None:
    boxes = [TextBox("L33", 700, 700, 730, 715)]

    assert detect_title_block(boxes, _geometry(), detect_frame(_geometry())) is None


def test_detect_regions_returns_frame_title_block_and_drawing_area() -> None:
    regions = detect_regions(_geometry(), _title_block_boxes())

    kinds = [region.region_kind for region in regions]
    assert kinds == [REGION_FRAME, REGION_TITLE_BLOCK, REGION_DRAWING]


def test_drawing_area_excludes_title_block_band() -> None:
    regions = detect_regions(_geometry(), _title_block_boxes())
    drawing = next(r for r in regions if r.region_kind == REGION_DRAWING)

    assert drawing.y1 == 700
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_sheetmap_regions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'truss_api.sheetmap.regions'`

- [ ] **Step 3: Write the implementation**

Create `apps/api/truss_api/sheetmap/regions.py`:

```python
from dataclasses import dataclass
import re

import fitz

from truss_api.core.text import normalize
from truss_api.sheetmap.geometry import PageGeometry


REGION_FRAME = "moldura"
REGION_TITLE_BLOCK = "carimbo"
REGION_DRAWING = "area_desenho"

FRAME_MIN_AREA_RATIO = 0.70
FRAME_MAX_AREA_RATIO = 0.995

TITLE_BLOCK_MIN_X_RATIO = 0.50
TITLE_BLOCK_MIN_Y_RATIO = 0.70

SHEET_CODE_PATTERN = re.compile(r"\b[A-Z]{2,5}-\d{3,5}-[A-Z0-9]{1,3}\b")
TITLE_BLOCK_ANCHORS = ("CPF", "REVISAO", "EMISSAO", "PROJETO ESTRUTURAL")


@dataclass(frozen=True)
class TextBox:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class DetectedRegion:
    region_kind: str
    x0: float
    y0: float
    x1: float
    y1: float
    confidence: float


def extract_line_boxes(page: fitz.Page) -> list[TextBox]:
    """Text at line granularity.

    Deliberately NOT page.get_text("blocks"): that mode merges neighbouring lines
    into one block, which collapses the whole title block into a single string and
    makes exact category matching impossible.
    """
    boxes: list[TextBox] = []

    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"]).strip()
            if not text:
                continue

            x0, y0, x1, y1 = line["bbox"]
            boxes.append(
                TextBox(text=text, x0=float(x0), y0=float(y0), x1=float(x1), y1=float(y1))
            )

    return boxes


def is_title_block_anchor(text: str) -> bool:
    normalized = normalize(text)
    if SHEET_CODE_PATTERN.search(normalized):
        return True
    return any(anchor in normalized for anchor in TITLE_BLOCK_ANCHORS)


def detect_frame(geometry: PageGeometry) -> DetectedRegion:
    page_area = geometry.page_area
    candidates = [
        rect
        for rect in geometry.rects
        if FRAME_MIN_AREA_RATIO <= rect.area / page_area < FRAME_MAX_AREA_RATIO
    ]

    if not candidates:
        return DetectedRegion(
            region_kind=REGION_FRAME,
            x0=0.0,
            y0=0.0,
            x1=geometry.width_pt,
            y1=geometry.height_pt,
            confidence=0.3,
        )

    best = max(candidates, key=lambda rect: rect.area)
    return DetectedRegion(
        region_kind=REGION_FRAME,
        x0=best.x0,
        y0=best.y0,
        x1=best.x1,
        y1=best.y1,
        confidence=0.95,
    )


def detect_title_block(
    text_boxes: list[TextBox],
    geometry: PageGeometry,
    frame: DetectedRegion,
) -> DetectedRegion | None:
    minimum_x = geometry.width_pt * TITLE_BLOCK_MIN_X_RATIO
    minimum_y = geometry.height_pt * TITLE_BLOCK_MIN_Y_RATIO

    anchors = [
        box
        for box in text_boxes
        if is_title_block_anchor(box.text)
        and (box.x0 + box.x1) / 2 >= minimum_x
        and (box.y0 + box.y1) / 2 >= minimum_y
    ]

    if not anchors:
        return None

    # As ancoras dao apenas o canto superior-esquerdo confiavel. O carimbo ocupa o
    # canto da moldura, entao a regiao e estendida ate a borda - sem isso, campos
    # abaixo da ultima ancora (a categoria, por exemplo) ficam de fora.
    return DetectedRegion(
        region_kind=REGION_TITLE_BLOCK,
        x0=min(box.x0 for box in anchors),
        y0=min(box.y0 for box in anchors),
        x1=frame.x1,
        y1=frame.y1,
        confidence=0.9 if len(anchors) >= 2 else 0.6,
    )


def detect_regions(
    geometry: PageGeometry,
    text_boxes: list[TextBox],
) -> list[DetectedRegion]:
    frame = detect_frame(geometry)
    regions = [frame]

    title_block = detect_title_block(text_boxes, geometry, frame)
    if title_block is not None:
        regions.append(title_block)

    drawing_bottom = title_block.y0 if title_block is not None else frame.y1
    regions.append(
        DetectedRegion(
            region_kind=REGION_DRAWING,
            x0=frame.x0,
            y0=frame.y0,
            x1=frame.x1,
            y1=drawing_bottom,
            confidence=frame.confidence,
        )
    )

    return regions
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_sheetmap_regions.py -v`
Expected: PASS, 8 tests.

- [ ] **Step 5: Validate against the real project**

Run this ad-hoc check to confirm the algorithm holds on all 28 real pages:

```bash
.venv/Scripts/python -c "
import fitz
from truss_api.sheetmap.geometry import extract_page_geometry
from truss_api.sheetmap.regions import REGION_TITLE_BLOCK, detect_regions, extract_line_boxes

path = 'data/originals/69f87430-6e60-4cd5-bfb8-c4cde0b09d79/09e35528-5556-4fce-939e-806897d7bbb1/7d2f9c32bc9d4988-Proj_Estrutural_RanchoQueimado_geral.pdf'
document = fitz.open(path)
found = 0
for index in range(document.page_count):
    page = document.load_page(index)
    geometry = extract_page_geometry(page)
    regions = detect_regions(geometry, extract_line_boxes(page))
    found += any(r.region_kind == REGION_TITLE_BLOCK for r in regions)
print(f'carimbos detectados: {found}/{document.page_count}')
"
```

Expected: `carimbos detectados: 28/28`

- [ ] **Step 6: Commit**

```bash
git add apps/api/truss_api/sheetmap/regions.py apps/api/tests/test_sheetmap_regions.py
git commit -m "feat: detect sheet frame and text-anchored title block"
```

---

### Task 5: Parse dos campos do carimbo

A ordem das linhas do carimbo e instavel entre paginas: em algumas a categoria vem antes de
`PROJETO ESTRUTURAL`, em outras depois. Por isso os campos sao identificados por conteudo
(regex e vocabulario), nunca por indice de linha.

**Files:**
- Create: `apps/api/truss_api/sheetmap/title_block.py`
- Test: `apps/api/tests/test_sheetmap_title_block.py`

**Interfaces:**
- Consumes: `TextBox`, `DetectedRegion`, `SHEET_CODE_PATTERN` from Task 4; `normalize` from Task 2
- Produces:
  - `SHEET_CATEGORIES: tuple[str, ...]` - vocabulario normalizado de categorias conhecidas
  - `TitleBlockFields` dataclass with fields `sheet_code: str | None, revision_code: str | None, category: str | None, title: str | None`
  - `boxes_inside(region: DetectedRegion, text_boxes: list[TextBox]) -> list[TextBox]`
  - `parse_title_block(region: DetectedRegion, text_boxes: list[TextBox]) -> TitleBlockFields`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_sheetmap_title_block.py`:

```python
from truss_api.sheetmap.regions import REGION_TITLE_BLOCK, DetectedRegion, TextBox
from truss_api.sheetmap.title_block import boxes_inside, parse_title_block


def _region() -> DetectedRegion:
    return DetectedRegion(
        region_kind=REGION_TITLE_BLOCK,
        x0=700,
        y0=700,
        x1=990,
        y1=790,
        confidence=0.9,
    )


def _boxes(lines: list[str]) -> list[TextBox]:
    return [
        TextBox(line, 710, 700 + index * 10, 980, 708 + index * 10)
        for index, line in enumerate(lines)
    ]


def test_boxes_inside_filters_by_region() -> None:
    inside = TextBox("EST-0060-A", 710, 705, 800, 715)
    outside = TextBox("L33", 100, 100, 140, 115)

    assert boxes_inside(_region(), [inside, outside]) == [inside]


def test_parse_extracts_sheet_code_and_revision() -> None:
    fields = parse_title_block(_region(), _boxes(["EST-0060-A", "PROJETO ESTRUTURAL"]))

    assert fields.sheet_code == "EST-0060-A"
    assert fields.revision_code == "A"


def test_parse_identifies_category_by_exact_vocabulary_match() -> None:
    lines = [
        "PROJETO ESTRUTURAL",
        "PLANTA DE FORMAS - FUNDO PISCINA E COBERTURA",
        "PLANTA DE FORMAS",
    ]

    fields = parse_title_block(_region(), _boxes(lines))

    assert fields.category == "PLANTA DE FORMAS"
    assert fields.title == "PLANTA DE FORMAS - FUNDO PISCINA E COBERTURA"


def test_parse_is_insensitive_to_line_order() -> None:
    lines = [
        "PLANTA DE LOCAÇÃO DAS FUNDAÇÕES",
        "PLANTA DE LOCAÇÃO",
        "PROJETO ESTRUTURAL",
    ]

    fields = parse_title_block(_region(), _boxes(lines))

    assert fields.category == "PLANTA DE LOCACAO"
    assert fields.title == "PLANTA DE LOCACAO DAS FUNDACOES"


def test_parse_returns_none_fields_when_title_block_is_empty() -> None:
    fields = parse_title_block(_region(), [])

    assert fields.sheet_code is None
    assert fields.category is None
    assert fields.title is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_sheetmap_title_block.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'truss_api.sheetmap.title_block'`

- [ ] **Step 3: Write the implementation**

Create `apps/api/truss_api/sheetmap/title_block.py`:

```python
from dataclasses import dataclass

from truss_api.core.text import normalize
from truss_api.sheetmap.regions import (
    SHEET_CODE_PATTERN,
    DetectedRegion,
    TextBox,
)


SHEET_CATEGORIES: tuple[str, ...] = (
    "PLANTA DE LOCACAO",
    "PLANTA DE FORMAS",
    "PLANTA DE ARMADURAS",
    "PLANTA DE COBERTURA",
    "PLANTA DE FUNDACOES",
)

CONSTANT_LINES: tuple[str, ...] = (
    "PROJETO ESTRUTURAL",
    "REVISAO",
    "DATA",
    "EMISSAO INICIAL",
)


@dataclass(frozen=True)
class TitleBlockFields:
    sheet_code: str | None
    revision_code: str | None
    category: str | None
    title: str | None


def boxes_inside(region: DetectedRegion, text_boxes: list[TextBox]) -> list[TextBox]:
    return [
        box
        for box in text_boxes
        if box.x0 >= region.x0
        and box.y0 >= region.y0
        and box.x1 <= region.x1
        and box.y1 <= region.y1
    ]


def _is_noise(line: str) -> bool:
    if len(line) < 8:
        return True
    if any(constant in line for constant in CONSTANT_LINES):
        return True
    if SHEET_CODE_PATTERN.search(line):
        return True
    return "CPF" in line


def parse_title_block(
    region: DetectedRegion,
    text_boxes: list[TextBox],
) -> TitleBlockFields:
    lines = [
        normalize(box.text)
        for box in boxes_inside(region, text_boxes)
        if normalize(box.text)
    ]

    sheet_code: str | None = None
    revision_code: str | None = None
    for line in lines:
        match = SHEET_CODE_PATTERN.search(line)
        if match:
            sheet_code = match.group(0)
            revision_code = sheet_code.rsplit("-", 1)[-1]
            break

    category = next(
        (line for line in lines if line in SHEET_CATEGORIES),
        None,
    )

    candidates = [
        line for line in lines if line != category and not _is_noise(line)
    ]
    title = max(candidates, key=len) if candidates else None

    return TitleBlockFields(
        sheet_code=sheet_code,
        revision_code=revision_code,
        category=category,
        title=title,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_sheetmap_title_block.py -v`
Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add apps/api/truss_api/sheetmap/title_block.py apps/api/tests/test_sheetmap_title_block.py
git commit -m "feat: parse title block fields by content not line order"
```

---

### Task 6: Classificacao do tipo de prancha

A categoria lida do carimbo e o sinal primario, e e deterministica. A contagem de termos na folha
inteira nao serve como sinal primario: foi medido que `FORMA` aparece em 67 folhas e
`RELACAO DO ACO` em 60 das mesmas 85, ou seja, elas se sobrepoem. O escore por termos existe
apenas como fallback quando o carimbo nao traz categoria.

**Files:**
- Create: `apps/api/truss_api/sheetmap/classifier.py`
- Test: `apps/api/tests/test_sheetmap_classifier.py`

**Interfaces:**
- Consumes: `TitleBlockFields` from Task 5; `normalize` from Task 2
- Produces:
  - `SHEET_TYPE_UNKNOWN = "desconhecido"`
  - `SheetTypeResult` dataclass with fields `sheet_type: str, confidence: float, source: str`
  - `classify_sheet_type(fields: TitleBlockFields, sheet_text: str) -> SheetTypeResult`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_sheetmap_classifier.py`:

```python
from truss_api.sheetmap.classifier import SHEET_TYPE_UNKNOWN, classify_sheet_type
from truss_api.sheetmap.title_block import TitleBlockFields


def _fields(category: str | None) -> TitleBlockFields:
    return TitleBlockFields(
        sheet_code="EST-0060-A",
        revision_code="A",
        category=category,
        title="DETALHAMENTO VIGAS",
    )


def test_category_from_title_block_wins() -> None:
    result = classify_sheet_type(_fields("PLANTA DE FORMAS"), "RELACAO DO ACO FORMA")

    assert result.sheet_type == "planta_formas"
    assert result.source == "carimbo"
    assert result.confidence >= 0.9


def test_all_known_categories_map_to_slugs() -> None:
    assert classify_sheet_type(_fields("PLANTA DE LOCACAO"), "").sheet_type == "planta_locacao"
    assert classify_sheet_type(_fields("PLANTA DE ARMADURAS"), "").sheet_type == "planta_armaduras"


def test_falls_back_to_sheet_text_when_category_missing() -> None:
    result = classify_sheet_type(_fields(None), "PLANTA DE ARMADURAS DAS LAJES")

    assert result.sheet_type == "planta_armaduras"
    assert result.source == "texto"
    assert result.confidence < 0.9


def test_fallback_is_accent_insensitive() -> None:
    result = classify_sheet_type(_fields(None), "Planta de Locação das Fundações")

    assert result.sheet_type == "planta_locacao"


def test_returns_unknown_when_no_signal() -> None:
    result = classify_sheet_type(_fields(None), "L33 h=13 L40")

    assert result.sheet_type == SHEET_TYPE_UNKNOWN
    assert result.source == "nenhum"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_sheetmap_classifier.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'truss_api.sheetmap.classifier'`

- [ ] **Step 3: Write the implementation**

Create `apps/api/truss_api/sheetmap/classifier.py`:

```python
from dataclasses import dataclass

from truss_api.core.text import normalize
from truss_api.sheetmap.title_block import TitleBlockFields


SHEET_TYPE_UNKNOWN = "desconhecido"

CATEGORY_TO_SHEET_TYPE: dict[str, str] = {
    "PLANTA DE LOCACAO": "planta_locacao",
    "PLANTA DE FORMAS": "planta_formas",
    "PLANTA DE ARMADURAS": "planta_armaduras",
    "PLANTA DE COBERTURA": "planta_cobertura",
    "PLANTA DE FUNDACOES": "planta_fundacoes",
}


@dataclass(frozen=True)
class SheetTypeResult:
    sheet_type: str
    confidence: float
    source: str


def classify_sheet_type(
    fields: TitleBlockFields,
    sheet_text: str,
) -> SheetTypeResult:
    if fields.category and fields.category in CATEGORY_TO_SHEET_TYPE:
        return SheetTypeResult(
            sheet_type=CATEGORY_TO_SHEET_TYPE[fields.category],
            confidence=0.97,
            source="carimbo",
        )

    normalized_text = normalize(sheet_text)
    for category, sheet_type in CATEGORY_TO_SHEET_TYPE.items():
        if category in normalized_text:
            return SheetTypeResult(
                sheet_type=sheet_type,
                confidence=0.6,
                source="texto",
            )

    return SheetTypeResult(
        sheet_type=SHEET_TYPE_UNKNOWN,
        confidence=0.2,
        source="nenhum",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_sheetmap_classifier.py -v`
Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add apps/api/truss_api/sheetmap/classifier.py apps/api/tests/test_sheetmap_classifier.py
git commit -m "feat: classify sheet type from title block category"
```

---

### Task 7: Tabelas e repositorio do Sheet Map

**Files:**
- Create: `apps/api/truss_api/db/migrations/002_sheet_maps.sql`
- Create: `apps/api/truss_api/sheetmap/repository.py`
- Test: `apps/api/tests/test_sheetmap_repository.py`

**Interfaces:**
- Consumes: `DetectedRegion` from Task 4; `Settings`, `transaction`
- Produces:
  - `PIPELINE_VERSION = "sheetmap-v0.1"`
  - `SheetMapNotFoundError(Exception)`
  - `save_sheet_map(*, sheet_id, project_id, revision_id, geometry_path, sheet_code, sheet_type, paper_format, orientation, title_block, regions, settings) -> dict[str, object]`
  - `get_sheet_map(sheet_id: str, settings: Settings) -> dict[str, object]`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_sheetmap_repository.py`:

```python
from pathlib import Path

import pytest

from truss_api.core.settings import Settings
from truss_api.db.schema import initialize_database
from truss_api.documents import repository as documents_repository
from truss_api.documents.importer import prepare_pdf_storage
from truss_api.projects import repository as projects_repository
from truss_api.projects.models import ProjectCreate, RevisionCreate
from truss_api.sheetmap import repository as sheetmap_repository
from truss_api.sheetmap.regions import REGION_FRAME, DetectedRegion
from tests.factories import make_structural_pdf_bytes


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    resolved = Settings(data_dir=tmp_path / "data")
    initialize_database(resolved)
    return resolved


@pytest.fixture()
def sheet(settings: Settings) -> dict[str, str]:
    project = projects_repository.create_project(ProjectCreate(name="P"), settings)
    revision = projects_repository.create_revision(
        str(project["id"]), RevisionCreate(notes="R"), settings
    )
    prepared = prepare_pdf_storage(
        content=make_structural_pdf_bytes(),
        filename="obra.pdf",
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
    first_sheet = document["sheets"][0]
    return {
        "sheet_id": str(first_sheet["id"]),
        "project_id": str(project["id"]),
        "revision_id": str(revision["id"]),
    }


def _save(settings: Settings, sheet: dict[str, str], sheet_type: str = "planta_formas"):
    return sheetmap_repository.save_sheet_map(
        sheet_id=sheet["sheet_id"],
        project_id=sheet["project_id"],
        revision_id=sheet["revision_id"],
        geometry_path="geometry/p/r/s.json",
        sheet_code="EST-0060-A",
        sheet_type=sheet_type,
        paper_format="A1",
        orientation="paisagem",
        title_block={"category": "PLANTA DE FORMAS"},
        regions=[DetectedRegion(REGION_FRAME, 20, 10, 970, 770, 0.95)],
        settings=settings,
    )


def test_save_sheet_map_persists_identity_and_regions(
    settings: Settings, sheet: dict[str, str]
) -> None:
    saved = _save(settings, sheet)

    assert saved["sheet_code"] == "EST-0060-A"
    assert saved["sheet_type"] == "planta_formas"
    assert len(saved["regions"]) == 1
    assert saved["regions"][0]["region_kind"] == REGION_FRAME


def test_get_sheet_map_returns_saved_record(
    settings: Settings, sheet: dict[str, str]
) -> None:
    _save(settings, sheet)

    loaded = sheetmap_repository.get_sheet_map(sheet["sheet_id"], settings)

    assert loaded["sheet_code"] == "EST-0060-A"
    assert loaded["title_block"]["category"] == "PLANTA DE FORMAS"


def test_saving_twice_for_same_pipeline_version_replaces_previous(
    settings: Settings, sheet: dict[str, str]
) -> None:
    _save(settings, sheet)
    _save(settings, sheet, sheet_type="planta_armaduras")

    loaded = sheetmap_repository.get_sheet_map(sheet["sheet_id"], settings)

    assert loaded["sheet_type"] == "planta_armaduras"
    assert len(loaded["regions"]) == 1


def test_get_sheet_map_raises_when_missing(settings: Settings) -> None:
    with pytest.raises(sheetmap_repository.SheetMapNotFoundError):
        sheetmap_repository.get_sheet_map("missing-sheet", settings)
```

- [ ] **Step 2: Create the shared test factory**

Create `apps/api/tests/factories.py`:

```python
from io import BytesIO

import fitz


def make_structural_pdf_bytes(page_count: int = 3) -> bytes:
    """Synthetic multi-sheet structural PDF: frame rect + bottom-right title block."""
    categories = ["PLANTA DE LOCACAO", "PLANTA DE FORMAS", "PLANTA DE ARMADURAS"]
    document = fitz.open()

    for index in range(page_count):
        page = document.new_page(width=1000, height=800)
        page.draw_rect(fitz.Rect(20, 10, 970, 770))
        page.insert_text((120, 200), "L33 h=13")
        page.insert_text((710, 706), f"EST-{(index + 1) * 10:04d}-A")
        page.insert_text((710, 726), "CPF: 951.770.276-00")
        page.insert_text((710, 741), "PROJETO ESTRUTURAL")
        page.insert_text((710, 756), categories[index % len(categories)])
        page.insert_text((710, 716), f"DETALHAMENTO GENERICO {index + 1}")

    buffer = BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_sheetmap_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'truss_api.sheetmap.repository'`

- [ ] **Step 4: Create migration 002**

Create `apps/api/truss_api/db/migrations/002_sheet_maps.sql`:

```sql
CREATE TABLE IF NOT EXISTS sheet_maps (
    id TEXT PRIMARY KEY,
    sheet_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    pipeline_version TEXT NOT NULL,
    status TEXT NOT NULL,
    geometry_path TEXT NOT NULL,
    sheet_code TEXT,
    sheet_type TEXT NOT NULL,
    paper_format TEXT NOT NULL,
    orientation TEXT NOT NULL,
    title_block_json TEXT NOT NULL,
    built_at TEXT NOT NULL,
    FOREIGN KEY (sheet_id) REFERENCES sheets(id) ON DELETE RESTRICT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT,
    FOREIGN KEY (revision_id) REFERENCES revisions(id) ON DELETE RESTRICT,
    UNIQUE (sheet_id, pipeline_version)
);

CREATE INDEX IF NOT EXISTS idx_sheet_maps_revision_type
ON sheet_maps(revision_id, sheet_type);

CREATE TABLE IF NOT EXISTS sheet_regions (
    id TEXT PRIMARY KEY,
    sheet_map_id TEXT NOT NULL,
    region_kind TEXT NOT NULL,
    x0 REAL NOT NULL,
    y0 REAL NOT NULL,
    x1 REAL NOT NULL,
    y1 REAL NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (sheet_map_id) REFERENCES sheet_maps(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sheet_regions_map
ON sheet_regions(sheet_map_id, region_kind);
```

`sheet_regions` uses `ON DELETE CASCADE` because a region has no meaning without its sheet map -
this is the one deliberate exception to the `RESTRICT` convention, which exists to protect
user-validated data such as findings.

- [ ] **Step 5: Write the repository**

Create `apps/api/truss_api/sheetmap/repository.py`:

```python
from datetime import UTC, datetime
import json
from uuid import uuid4

from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.sheetmap.regions import DetectedRegion


PIPELINE_VERSION = "sheetmap-v0.1"


class SheetMapNotFoundError(Exception):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


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
    settings: Settings,
) -> dict[str, object]:
    sheet_map_id = str(uuid4())
    built_at = _now()

    with transaction(settings) as connection:
        connection.execute(
            "DELETE FROM sheet_maps WHERE sheet_id = ? AND pipeline_version = ?",
            (sheet_id, PIPELINE_VERSION),
        )
        connection.execute(
            """
            INSERT INTO sheet_maps (
                id, sheet_id, project_id, revision_id, pipeline_version, status,
                geometry_path, sheet_code, sheet_type, paper_format, orientation,
                title_block_json, built_at
            ) VALUES (?, ?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sheet_map_id,
                sheet_id,
                project_id,
                revision_id,
                PIPELINE_VERSION,
                geometry_path,
                sheet_code,
                sheet_type,
                paper_format,
                orientation,
                json.dumps(title_block),
                built_at,
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

    return get_sheet_map(sheet_id, settings)


def get_sheet_map(sheet_id: str, settings: Settings) -> dict[str, object]:
    with transaction(settings) as connection:
        row = connection.execute(
            """
            SELECT * FROM sheet_maps
            WHERE sheet_id = ? AND pipeline_version = ?
            """,
            (sheet_id, PIPELINE_VERSION),
        ).fetchone()

        if row is None:
            raise SheetMapNotFoundError(sheet_id)

        regions = connection.execute(
            """
            SELECT id, region_kind, x0, y0, x1, y1, confidence
            FROM sheet_regions WHERE sheet_map_id = ?
            ORDER BY region_kind
            """,
            (str(row["id"]),),
        ).fetchall()

    sheet_map = dict(row)
    sheet_map["title_block"] = json.loads(str(row["title_block_json"]))
    sheet_map["regions"] = [dict(region) for region in regions]
    return sheet_map
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_sheetmap_repository.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 7: Commit**

```bash
git add apps/api/truss_api/db/migrations/002_sheet_maps.sql apps/api/truss_api/sheetmap/repository.py apps/api/tests/test_sheetmap_repository.py apps/api/tests/factories.py
git commit -m "feat: persist sheet maps and regions"
```

---

### Task 8: Builder e integracao no import

**Files:**
- Create: `apps/api/truss_api/sheetmap/builder.py`
- Modify: `apps/api/truss_api/documents/routes.py:60-63` (call builder after document creation)
- Test: `apps/api/tests/test_sheetmap_builder.py`

**Interfaces:**
- Consumes: everything from Tasks 3-7
- Produces:
  - `paper_format_for(width_pt: float, height_pt: float) -> str`
  - `orientation_for(width_pt: float, height_pt: float) -> str`
  - `build_sheet_map_for_document(document_id: str, settings: Settings) -> list[dict[str, object]]`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_sheetmap_builder.py`:

```python
from pathlib import Path

import pytest

from truss_api.core.settings import Settings
from truss_api.db.schema import initialize_database
from truss_api.documents import repository as documents_repository
from truss_api.documents.importer import prepare_pdf_storage
from truss_api.projects import repository as projects_repository
from truss_api.projects.models import ProjectCreate, RevisionCreate
from truss_api.sheetmap import repository as sheetmap_repository
from truss_api.sheetmap.builder import (
    build_sheet_map_for_document,
    orientation_for,
    paper_format_for,
)
from tests.factories import make_structural_pdf_bytes


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    resolved = Settings(data_dir=tmp_path / "data")
    initialize_database(resolved)
    return resolved


@pytest.fixture()
def document(settings: Settings) -> dict[str, object]:
    project = projects_repository.create_project(ProjectCreate(name="P"), settings)
    revision = projects_repository.create_revision(
        str(project["id"]), RevisionCreate(notes="R"), settings
    )
    prepared = prepare_pdf_storage(
        content=make_structural_pdf_bytes(),
        filename="obra.pdf",
        project_id=str(project["id"]),
        revision_id=str(revision["id"]),
        settings=settings,
    )
    return documents_repository.create_document_from_prepared_pdf(
        project_id=str(project["id"]),
        revision_id=str(revision["id"]),
        prepared_pdf=prepared,
        settings=settings,
    )


def test_paper_format_detects_a1_landscape() -> None:
    assert paper_format_for(2384, 1684) == "A1"
    assert orientation_for(2384, 1684) == "paisagem"


def test_paper_format_detects_a0() -> None:
    assert paper_format_for(3370, 2384) == "A0"


def test_paper_format_returns_custom_for_unknown_size() -> None:
    assert paper_format_for(1000, 800) == "personalizado"


def test_build_creates_one_sheet_map_per_sheet(
    settings: Settings, document: dict[str, object]
) -> None:
    built = build_sheet_map_for_document(str(document["id"]), settings)

    assert len(built) == 3


def test_build_extracts_sheet_code_and_type_from_title_block(
    settings: Settings, document: dict[str, object]
) -> None:
    build_sheet_map_for_document(str(document["id"]), settings)
    first_sheet = document["sheets"][0]

    sheet_map = sheetmap_repository.get_sheet_map(str(first_sheet["id"]), settings)

    assert sheet_map["sheet_code"] == "EST-0010-A"
    assert sheet_map["sheet_type"] == "planta_locacao"


def test_build_writes_geometry_file_to_disk(
    settings: Settings, document: dict[str, object]
) -> None:
    build_sheet_map_for_document(str(document["id"]), settings)
    first_sheet = document["sheets"][0]

    sheet_map = sheetmap_repository.get_sheet_map(str(first_sheet["id"]), settings)

    assert (settings.data_dir / str(sheet_map["geometry_path"])).exists()


def test_build_is_idempotent(settings: Settings, document: dict[str, object]) -> None:
    build_sheet_map_for_document(str(document["id"]), settings)
    built_again = build_sheet_map_for_document(str(document["id"]), settings)

    assert len(built_again) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_sheetmap_builder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'truss_api.sheetmap.builder'`

- [ ] **Step 3: Write the builder**

Create `apps/api/truss_api/sheetmap/builder.py`:

```python
from dataclasses import asdict

import fitz

from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.sheetmap import repository
from truss_api.sheetmap.classifier import classify_sheet_type
from truss_api.sheetmap.geometry import extract_page_geometry, write_page_geometry
from truss_api.sheetmap.regions import (
    REGION_TITLE_BLOCK,
    detect_regions,
    extract_line_boxes,
)
from truss_api.sheetmap.title_block import TitleBlockFields, parse_title_block


PAPER_FORMATS: tuple[tuple[str, float, float], ...] = (
    ("A0", 3370.0, 2384.0),
    ("A1", 2384.0, 1684.0),
    ("A2", 1684.0, 1191.0),
    ("A3", 1191.0, 842.0),
    ("A4", 842.0, 595.0),
)

FORMAT_TOLERANCE_PT = 20.0


def paper_format_for(width_pt: float, height_pt: float) -> str:
    longer = max(width_pt, height_pt)
    shorter = min(width_pt, height_pt)

    for name, format_long, format_short in PAPER_FORMATS:
        if (
            abs(longer - format_long) <= FORMAT_TOLERANCE_PT
            and abs(shorter - format_short) <= FORMAT_TOLERANCE_PT
        ):
            return name

    return "personalizado"


def orientation_for(width_pt: float, height_pt: float) -> str:
    return "paisagem" if width_pt >= height_pt else "retrato"


def _load_document_context(
    document_id: str,
    settings: Settings,
) -> tuple[str, list[dict[str, object]]]:
    with transaction(settings) as connection:
        document = connection.execute(
            "SELECT stored_file_path FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()

        if document is None:
            raise repository.SheetMapNotFoundError(document_id)

        sheets = connection.execute(
            """
            SELECT id, project_id, revision_id, page_index
            FROM sheets WHERE document_id = ? ORDER BY page_index
            """,
            (document_id,),
        ).fetchall()

    return str(document["stored_file_path"]), [dict(row) for row in sheets]


def build_sheet_map_for_document(
    document_id: str,
    settings: Settings,
) -> list[dict[str, object]]:
    stored_path, sheets = _load_document_context(document_id, settings)
    pdf_path = settings.data_dir / stored_path
    built: list[dict[str, object]] = []

    pdf = fitz.open(pdf_path)
    try:
        for sheet in sheets:
            page = pdf.load_page(int(sheet["page_index"]))
            geometry = extract_page_geometry(page)

            text_boxes = extract_line_boxes(page)
            regions = detect_regions(geometry, text_boxes)
            title_block_region = next(
                (r for r in regions if r.region_kind == REGION_TITLE_BLOCK), None
            )

            if title_block_region is None:
                fields = TitleBlockFields(None, None, None, None)
            else:
                fields = parse_title_block(title_block_region, text_boxes)

            sheet_text = " ".join(box.text for box in text_boxes)
            classification = classify_sheet_type(fields, sheet_text)

            geometry_path = write_page_geometry(
                geometry,
                project_id=str(sheet["project_id"]),
                revision_id=str(sheet["revision_id"]),
                sheet_id=str(sheet["id"]),
                settings=settings,
            )

            title_block_payload = dict(asdict(fields))
            title_block_payload["classification_source"] = classification.source
            title_block_payload["classification_confidence"] = classification.confidence

            built.append(
                repository.save_sheet_map(
                    sheet_id=str(sheet["id"]),
                    project_id=str(sheet["project_id"]),
                    revision_id=str(sheet["revision_id"]),
                    geometry_path=geometry_path,
                    sheet_code=fields.sheet_code,
                    sheet_type=classification.sheet_type,
                    paper_format=paper_format_for(geometry.width_pt, geometry.height_pt),
                    orientation=orientation_for(geometry.width_pt, geometry.height_pt),
                    title_block=title_block_payload,
                    regions=regions,
                    settings=settings,
                )
            )
    finally:
        pdf.close()

    return built
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_sheetmap_builder.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 5: Hook the builder into the import route**

In `apps/api/truss_api/documents/routes.py`, add this import at the top:

```python
from truss_api.sheetmap.builder import build_sheet_map_for_document
```

Then, inside `import_revision_document`, replace the `return repository.create_document_from_prepared_pdf(...)` call with:

```python
        document = repository.create_document_from_prepared_pdf(
            project_id=project_id,
            revision_id=revision_id,
            prepared_pdf=prepared_pdf,
            settings=settings,
        )
        build_sheet_map_for_document(str(document["id"]), settings)
        return document
```

- [ ] **Step 6: Run the full API suite**

Run: `.venv/Scripts/python -m pytest apps/api/tests -v`
Expected: PASS, all tests including the existing 33.

- [ ] **Step 7: Commit**

```bash
git add apps/api/truss_api/sheetmap/builder.py apps/api/truss_api/documents/routes.py apps/api/tests/test_sheetmap_builder.py
git commit -m "feat: build sheet map on document import"
```

---

### Task 9: Endpoint do Sheet Map

**Files:**
- Create: `apps/api/truss_api/sheetmap/models.py`
- Create: `apps/api/truss_api/sheetmap/routes.py`
- Modify: `apps/api/truss_api/main.py` (register router)
- Test: `apps/api/tests/test_sheetmap_api.py`

**Interfaces:**
- Consumes: `get_sheet_map`, `SheetMapNotFoundError` from Task 7
- Produces: `GET /sheets/{sheet_id}/sheet-map` returning `SheetMap`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_sheetmap_api.py`:

```python
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from truss_api.core.settings import Settings, get_settings
from truss_api.db.schema import initialize_database
from truss_api.main import app
from tests.factories import make_structural_pdf_bytes


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    resolved = Settings(data_dir=tmp_path / "data")
    initialize_database(resolved)
    return resolved


@pytest.fixture()
def client(settings: Settings) -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def imported_sheet_id(client: TestClient) -> str:
    project = client.post("/projects", json={"name": "Obra"}).json()
    revision = client.post(
        f"/projects/{project['id']}/revisions", json={"notes": "R01"}
    ).json()
    response = client.post(
        f"/projects/{project['id']}/revisions/{revision['id']}/documents",
        files={"file": ("obra.pdf", make_structural_pdf_bytes(), "application/pdf")},
    )
    return str(response.json()["sheets"][0]["id"])


def test_get_sheet_map_returns_identity_and_regions(
    client: TestClient, imported_sheet_id: str
) -> None:
    response = client.get(f"/sheets/{imported_sheet_id}/sheet-map")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sheet_code"] == "EST-0010-A"
    assert payload["sheet_type"] == "planta_locacao"
    assert payload["paper_format"] == "personalizado"
    assert any(r["region_kind"] == "carimbo" for r in payload["regions"])


def test_get_sheet_map_returns_404_for_unknown_sheet(client: TestClient) -> None:
    response = client.get("/sheets/does-not-exist/sheet-map")

    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_sheetmap_api.py -v`
Expected: FAIL with 404 on the first test (route not registered).

- [ ] **Step 3: Write the models**

Create `apps/api/truss_api/sheetmap/models.py`:

```python
from pydantic import BaseModel


class SheetRegion(BaseModel):
    id: str
    region_kind: str
    x0: float
    y0: float
    x1: float
    y1: float
    confidence: float


class SheetMap(BaseModel):
    id: str
    sheet_id: str
    project_id: str
    revision_id: str
    pipeline_version: str
    status: str
    geometry_path: str
    sheet_code: str | None
    sheet_type: str
    paper_format: str
    orientation: str
    title_block: dict
    built_at: str
    regions: list[SheetRegion]
```

- [ ] **Step 4: Write the routes**

Create `apps/api/truss_api/sheetmap/routes.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, status

from truss_api.core.settings import Settings, get_settings
from truss_api.sheetmap import repository
from truss_api.sheetmap.models import SheetMap


router = APIRouter(tags=["sheet-map"])


@router.get("/sheets/{sheet_id}/sheet-map", response_model=SheetMap)
def get_sheet_map(
    sheet_id: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return repository.get_sheet_map(sheet_id, settings)
    except repository.SheetMapNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sheet map not found",
        ) from error
```

In `apps/api/truss_api/main.py`, add the import alongside the others:

```python
from truss_api.sheetmap.routes import router as sheetmap_router
```

and register it after `app.include_router(documents_router)`:

```python
app.include_router(sheetmap_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_sheetmap_api.py -v`
Expected: PASS, 2 tests.

- [ ] **Step 6: Commit**

```bash
git add apps/api/truss_api/sheetmap/models.py apps/api/truss_api/sheetmap/routes.py apps/api/truss_api/main.py apps/api/tests/test_sheetmap_api.py
git commit -m "feat: expose sheet map endpoint"
```

---

### Task 10: Codigo e tipo da prancha no viewer

Hoje o viewer mostra `activeSheet.label`, que e o generico `"Folha 13"` gerado em
`importer.py:92`. Passa a mostrar o codigo real (`EST-0130-A`) e o tipo classificado.

**Files:**
- Modify: `apps/web/lib/projects-api.ts` (add types + fetch function)
- Modify: `apps/web/components/sheet-viewer.tsx:1707-1713` (header display)
- Test: `apps/web/tests/sheet-identity.test.ts`

**Interfaces:**
- Consumes: `GET /sheets/{sheet_id}/sheet-map` from Task 9
- Produces:
  - `export type SheetRegion` and `export type SheetMap` in `projects-api.ts`
  - `export async function fetchSheetMap(apiBaseUrl: string, sheetId: string): Promise<SheetMap | null>`
  - `export function sheetIdentityLabel(sheet: Sheet, sheetMap: SheetMap | null): string`
  - `export function sheetTypeLabel(sheetType: string): string`

- [ ] **Step 1: Write the failing test**

Create `apps/web/tests/sheet-identity.test.ts`:

```typescript
import { describe, expect, it } from "vitest";

import { sheetIdentityLabel, sheetTypeLabel } from "@/lib/projects-api";
import type { Sheet, SheetMap } from "@/lib/projects-api";

const sheet = { label: "Folha 13" } as Sheet;

function sheetMap(overrides: Partial<SheetMap>): SheetMap {
  return {
    id: "map-1",
    sheet_id: "sheet-1",
    project_id: "p",
    revision_id: "r",
    pipeline_version: "sheetmap-v0.1",
    status: "completed",
    geometry_path: "geometry/p/r/s.json",
    sheet_code: null,
    sheet_type: "desconhecido",
    paper_format: "A1",
    orientation: "paisagem",
    title_block: {},
    built_at: "2026-08-28T00:00:00+00:00",
    regions: [],
    ...overrides,
  };
}

describe("sheetIdentityLabel", () => {
  it("prefers the real sheet code from the title block", () => {
    expect(sheetIdentityLabel(sheet, sheetMap({ sheet_code: "EST-0130-A" }))).toBe(
      "EST-0130-A",
    );
  });

  it("falls back to the generic label when there is no sheet map", () => {
    expect(sheetIdentityLabel(sheet, null)).toBe("Folha 13");
  });

  it("falls back to the generic label when the code is missing", () => {
    expect(sheetIdentityLabel(sheet, sheetMap({ sheet_code: null }))).toBe("Folha 13");
  });
});

describe("sheetTypeLabel", () => {
  it("renders known types in readable form", () => {
    expect(sheetTypeLabel("planta_formas")).toBe("Planta de formas");
    expect(sheetTypeLabel("planta_armaduras")).toBe("Planta de armaduras");
    expect(sheetTypeLabel("planta_locacao")).toBe("Planta de locação");
  });

  it("renders unknown types as a dash", () => {
    expect(sheetTypeLabel("desconhecido")).toBe("—");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --workspace apps/web run test -- sheet-identity`
Expected: FAIL with `sheetIdentityLabel is not exported`

- [ ] **Step 3: Add types and helpers to projects-api.ts**

Append to `apps/web/lib/projects-api.ts`:

```typescript
export type SheetRegion = {
  id: string;
  region_kind: string;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  confidence: number;
};

export type SheetMap = {
  id: string;
  sheet_id: string;
  project_id: string;
  revision_id: string;
  pipeline_version: string;
  status: string;
  geometry_path: string;
  sheet_code: string | null;
  sheet_type: string;
  paper_format: string;
  orientation: string;
  title_block: Record<string, unknown>;
  built_at: string;
  regions: SheetRegion[];
};

const SHEET_TYPE_LABELS: Record<string, string> = {
  planta_locacao: "Planta de locação",
  planta_formas: "Planta de formas",
  planta_armaduras: "Planta de armaduras",
  planta_cobertura: "Planta de cobertura",
  planta_fundacoes: "Planta de fundações",
};

export function sheetTypeLabel(sheetType: string): string {
  return SHEET_TYPE_LABELS[sheetType] ?? "—";
}

export function sheetIdentityLabel(sheet: Sheet, sheetMap: SheetMap | null): string {
  return sheetMap?.sheet_code ?? sheet.label;
}

export async function fetchSheetMap(
  apiBaseUrl: string,
  sheetId: string,
): Promise<SheetMap | null> {
  const response = await fetch(`${apiBaseUrl}/sheets/${sheetId}/sheet-map`);

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw new Error(`Falha ao carregar o sheet map (${response.status})`);
  }

  return (await response.json()) as SheetMap;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --workspace apps/web run test -- sheet-identity`
Expected: PASS, 5 tests.

- [ ] **Step 5: Wire the viewer header**

In `apps/web/components/sheet-viewer.tsx`, add to the imports from `@/lib/projects-api`:
`fetchSheetMap`, `sheetIdentityLabel`, `sheetTypeLabel`, and the type `SheetMap`.

Add this state next to the other `useState` declarations (near line 507):

```tsx
  const [sheetMap, setSheetMap] = useState<SheetMap | null>(null);
```

Add this effect next to the other effects that react to `activeSheet`:

```tsx
  useEffect(() => {
    if (!activeSheet) {
      setSheetMap(null);
      return;
    }

    let cancelled = false;

    fetchSheetMap(apiBaseUrl, activeSheet.id)
      .then((loaded) => {
        if (!cancelled) {
          setSheetMap(loaded);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSheetMap(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, activeSheet?.id]);
```

Replace the header block at lines 1707-1713 with:

```tsx
        <div className="min-w-0">
          <p className="truss-mono-label">Prancha ativa</p>
          <p className="mt-1 truncate text-sm font-semibold text-truss-text">
            {sheetIdentityLabel(activeSheet, sheetMap)}
            {"documentName" in activeSheet ? ` / ${activeSheet.documentName}` : ""}
          </p>
          {sheetMap ? (
            <p className="mt-0.5 truncate font-mono text-[10.5px] uppercase tracking-[0.09em] text-truss-subtle">
              {sheetTypeLabel(sheetMap.sheet_type)} · {sheetMap.paper_format}
            </p>
          ) : null}
        </div>
```

- [ ] **Step 6: Run the full frontend validation**

Run: `npm run lint && npm run typecheck && npm run test:web`
Expected: PASS on all three.

- [ ] **Step 7: Commit**

```bash
git add apps/web/lib/projects-api.ts apps/web/components/sheet-viewer.tsx apps/web/tests/sheet-identity.test.ts
git commit -m "feat: show real sheet code and type in viewer"
```

---

### Task 11: Harness de calibracao

O gabarito e o unico jeito de responder "ficou mais inteligente?" com um numero. Nesta fase ele
mede a classificacao; a partir da F2 passa a medir tambem os findings.

**Files:**
- Create: `calibration/README.md`
- Create: `calibration/rancho-queimado-r01.yml`
- Create: `apps/api/tests/test_calibration.py`
- Modify: `apps/api/requirements-dev.txt` (add `pyyaml`)

**Interfaces:**
- Consumes: `build_sheet_map_for_document` from Task 8, `get_sheet_map` from Task 7
- Produces: a pytest that skips when the reference PDF is absent, and prints an accuracy report

- [ ] **Step 1: Write the calibration fixture**

Create `calibration/rancho-queimado-r01.yml` with the ground truth verified during design:

```yaml
document:
  filename: Proj_Estrutural_RanchoQueimado_geral.pdf
  page_count: 28
minimum_type_accuracy: 0.90
minimum_code_coverage: 0.95
sheets:
  - page_index: 0
    sheet_code: EST-0010-A
    sheet_type: planta_locacao
  - page_index: 1
    sheet_code: EST-0020-A
    sheet_type: planta_armaduras
  - page_index: 2
    sheet_code: EST-0030-A
    sheet_type: planta_armaduras
  - page_index: 3
    sheet_code: EST-0040-A
    sheet_type: planta_armaduras
  - page_index: 4
    sheet_code: EST-0050-A
    sheet_type: planta_formas
  - page_index: 5
    sheet_code: EST-0060-A
    sheet_type: planta_formas
  - page_index: 6
    sheet_code: EST-0070-A
    sheet_type: planta_formas
  - page_index: 7
    sheet_code: EST-0080-A
    sheet_type: planta_formas
  - page_index: 8
    sheet_code: EST-0090-A
    sheet_type: planta_formas
  - page_index: 9
    sheet_code: EST-0100-A
    sheet_type: planta_armaduras
  - page_index: 10
    sheet_code: EST-0110-A
    sheet_type: planta_armaduras
  - page_index: 11
    sheet_code: EST-0120-A
    sheet_type: planta_armaduras
  - page_index: 12
    sheet_code: EST-0130-A
    sheet_type: planta_armaduras
  - page_index: 13
    sheet_code: EST-0140-A
    sheet_type: planta_armaduras
  - page_index: 14
    sheet_code: EST-0150-A
    sheet_type: planta_armaduras
  - page_index: 15
    sheet_code: EST-0160-A
    sheet_type: planta_armaduras
  - page_index: 16
    sheet_code: EST-0170-A
    sheet_type: planta_armaduras
  - page_index: 17
    sheet_code: EST-0180-A
    sheet_type: planta_armaduras
  - page_index: 18
    sheet_code: EST-0190-A
    sheet_type: planta_armaduras
  - page_index: 19
    sheet_code: EST-0200-A
    sheet_type: planta_armaduras
  - page_index: 20
    sheet_code: EST-0210-A
    sheet_type: planta_armaduras
  - page_index: 21
    sheet_code: EST-0220-A
    sheet_type: planta_armaduras
  - page_index: 22
    sheet_code: EST-0230-A
    sheet_type: planta_armaduras
  - page_index: 23
    sheet_code: EST-0240-A
    sheet_type: planta_armaduras
  - page_index: 24
    sheet_code: EST-0250-A
    sheet_type: planta_armaduras
  - page_index: 25
    sheet_code: EST-0260-A
    sheet_type: planta_formas
  - page_index: 26
    sheet_code: EST-0270-A
    sheet_type: planta_armaduras
  - page_index: 27
    sheet_code: EST-0280-A
    sheet_type: planta_armaduras
```

Create `calibration/README.md`:

```markdown
# Gabarito de calibracao

Cada arquivo `.yml` descreve o que o proprietario espera que o Truss identifique num projeto
real. E o unico criterio objetivo de "ficou mais inteligente".

Os PDFs de referencia nao ficam no repositorio: sao material de cliente. O teste em
`apps/api/tests/test_calibration.py` procura o arquivo em `data/originals/` pelo nome e
**pula automaticamente** quando ele nao esta presente, de modo que a suite continua verde numa
maquina limpa.

Na F1 o gabarito cobre codigo da prancha e tipo. A partir da F2 ganha os findings esperados
por folha.
```

- [ ] **Step 2: Add the pyyaml dependency**

Add `pyyaml` to `apps/api/requirements-dev.txt`, then run:

```bash
.venv/Scripts/python -m pip install pyyaml
```

- [ ] **Step 3: Write the calibration test**

Create `apps/api/tests/test_calibration.py`:

```python
from pathlib import Path

import pytest
import yaml

from truss_api.core.settings import Settings
from truss_api.db.schema import initialize_database
from truss_api.documents import repository as documents_repository
from truss_api.documents.importer import prepare_pdf_storage
from truss_api.projects import repository as projects_repository
from truss_api.projects.models import ProjectCreate, RevisionCreate
from truss_api.sheetmap import repository as sheetmap_repository
from truss_api.sheetmap.builder import build_sheet_map_for_document


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "calibration" / "rancho-queimado-r01.yml"


def _find_reference_pdf(filename: str) -> Path | None:
    matches = sorted((REPO_ROOT / "data" / "originals").rglob(f"*{filename}"))
    return matches[0] if matches else None


def test_sheet_map_matches_calibration_ground_truth(tmp_path: Path) -> None:
    expected = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    pdf_path = _find_reference_pdf(expected["document"]["filename"])

    if pdf_path is None:
        pytest.skip(
            f"PDF de referencia ausente: {expected['document']['filename']}. "
            "Importe o projeto localmente para rodar a calibracao."
        )

    settings = Settings(data_dir=tmp_path / "data")
    initialize_database(settings)

    project = projects_repository.create_project(ProjectCreate(name="Calibracao"), settings)
    revision = projects_repository.create_revision(
        str(project["id"]), RevisionCreate(notes="R01"), settings
    )
    prepared = prepare_pdf_storage(
        content=pdf_path.read_bytes(),
        filename=expected["document"]["filename"],
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

    sheets_by_page = {
        int(sheet["page_index"]): str(sheet["id"]) for sheet in document["sheets"]
    }

    type_hits = 0
    code_hits = 0
    failures: list[str] = []

    for entry in expected["sheets"]:
        page_index = int(entry["page_index"])
        sheet_map = sheetmap_repository.get_sheet_map(sheets_by_page[page_index], settings)

        if sheet_map["sheet_code"] == entry["sheet_code"]:
            code_hits += 1
        else:
            failures.append(
                f"pagina {page_index}: codigo {sheet_map['sheet_code']} != {entry['sheet_code']}"
            )

        if sheet_map["sheet_type"] == entry["sheet_type"]:
            type_hits += 1
        else:
            failures.append(
                f"pagina {page_index}: tipo {sheet_map['sheet_type']} != {entry['sheet_type']}"
            )

    total = len(expected["sheets"])
    type_accuracy = type_hits / total
    code_coverage = code_hits / total

    print(f"\ncalibracao: tipo {type_accuracy:.1%} | codigo {code_coverage:.1%} ({total} folhas)")
    for failure in failures:
        print(f"  {failure}")

    assert type_accuracy >= expected["minimum_type_accuracy"]
    assert code_coverage >= expected["minimum_code_coverage"]
```

- [ ] **Step 4: Run the calibration test**

Run: `.venv/Scripts/python -m pytest apps/api/tests/test_calibration.py -v -s`
Expected: PASS, printing something like `calibracao: tipo 100.0% | codigo 100.0% (28 folhas)`

If it fails, the printed failure lines name the exact pages that diverged. Fix the classifier or
the title block parser - do not lower the thresholds in the fixture.

- [ ] **Step 5: Verify the suite still passes without the reference PDF**

Run:

```bash
.venv/Scripts/python -m pytest apps/api/tests/test_calibration.py -v -p no:cacheprovider --override-ini="testpaths=apps/api/tests" -k calibration
```

Then temporarily rename the PDF directory and confirm the test reports SKIPPED rather than
failing. Restore the directory afterwards.

- [ ] **Step 6: Run the complete validation suite**

Run:

```bash
.venv/Scripts/python -m pytest apps/api/tests -v
npm run lint
npm run typecheck
npm run test:web
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add calibration/ apps/api/tests/test_calibration.py apps/api/requirements-dev.txt
git commit -m "feat: add calibration harness measuring sheet map accuracy"
```

---

## Criterio de aceite da F1

A fase so fecha quando todos os itens abaixo forem verificados com comando rodado, nao por leitura:

- [ ] `.venv/Scripts/python -m pytest apps/api/tests` passa inteiro
- [ ] `npm run lint && npm run typecheck && npm run test:web` passa inteiro
- [ ] `test_calibration.py` reporta **tipo >= 90%** e **codigo >= 95%** nas 28 folhas reais
- [ ] O banco local real sobreviveu a migration: 85 sheets e 63 findings intactos
- [ ] Reimportar o projeto real gera 28 sheet maps, e `data/geometry/` contem 28 arquivos
- [ ] O viewer mostra `EST-0130-A` e `Planta de armaduras` no lugar de `Folha 13`
- [ ] Passada manual do proprietario no projeto real confirmando que os tipos estao corretos

## Fora do escopo desta fase

`sheet_views`, `sheet_elements` e `rule_preferences` pertencem a F2, F3 e F5 e nao devem ser
criadas aqui. O checklist, o cruzamento entre folhas, a visao multimodal e o loop de aprendizado
tambem sao fases posteriores. Esta fase entrega apenas a fundacao e a regua de medicao.
