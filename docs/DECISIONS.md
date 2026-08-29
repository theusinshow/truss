# Decisions

## 2026-07-27 - Testable local settings in API routes

FastAPI routes that touch persistence receive `Settings` through dependency injection.

Rationale:

- production uses the default local `data/` directory;
- tests can override the dependency with a temporary data directory;
- persistence behavior can be verified without polluting `data/db/truss.sqlite`;
- this keeps the app local-first and avoids adding a heavier migration/runtime layer before it is needed.

This does not change the architectural decisions in `AGENTS.md`: the backend remains FastAPI, SQLite remains the initial database, and PDFs/renders stay on disk.

## 2026-07-27 - Canonical PDF coordinates

Sheet dimensions and future regions/findings use PDF page points (`pt`) as the canonical coordinate system.

Rationale:

- PDF points are independent from render DPI and browser zoom;
- rendered PNG pixels can be derived from points through a known scale;
- findings must remain stable if the page is re-rendered at another resolution;
- this follows the repository rule that coordinates are first-class data.

## 2026-07-27 - Deterministic audit before multimodal AI

The first audit orchestrator uses deterministic rules over native PDF text before any model call.

Rationale:

- the product should not become a monolithic prompt;
- native text absence, missing scale markers, and missing title terms are cheap and reproducible checks;
- every deterministic finding already uses the same structured `findings` table that AI findings will use later;
- tests can validate the full persistence and feedback loop without network calls or secrets.

## 2026-07-27 - Local AI provider as first provider

The first AIProvider implementation is a local deterministic provider.

Rationale:

- V0.1 can validate chat context, usage accounting, memory, and UI flow without secrets;
- provider boundaries are in place before adding OpenAI or another external model;
- tests remain deterministic and do not depend on network calls;
- usage events can record zero-cost local operations now and paid provider operations later.

## 2026-07-27 - OpenAI provider uses environment-only secrets

The OpenAI provider is optional and is selected only when `TRUSS_AI_PROVIDER=openai` is explicitly configured, or when `TRUSS_AI_PROVIDER=auto` is configured and the backend receives an API key through `OPENAI_API_KEY` or `TRUSS_OPENAI_API_KEY`.

Rationale:

- API keys must not be persisted in SQLite, JSON, browser storage, repository files, or logs;
- `TRUSS_AI_PROVIDER=local` is the default so an ambient or compromised API key is not used accidentally;
- `TRUSS_AI_PROVIDER=auto` keeps the app functional without a key by falling back to the local provider;
- explicit `TRUSS_AI_PROVIDER=openai` fails fast when the key is missing instead of silently pretending to use AI;
- usage events record provider, model, token counts, and estimated cost when the OpenAI response exposes usage data.

## 2026-08-29 - Title/scale association gate measured at 94% on the base project

Task 5 of the F2 plan is gated on associating title, scale, and level to at least 90% of the
view anchors. Measured against `calibration/juliano-corbellini-r05.yml` over the six forms
sheets (pages 4, 5, 6, 7, 8, 25) of `docs/projeto_base/Projeto Estrutural_Juliano
Corbellini_R05.pdf`: **16 anchors found, 15 associated to the correct ground-truth title for
their scale = 94%**. The tolerance constants stay as calibrated
(`TITLE_OVERLAP_TOLERANCE_PT=12.0`, `TITLE_MAX_GAP_PT=90.0`,
`TITLE_MAX_HORIZONTAL_OFFSET_PT=700.0`, `title_font_floor` as the mean of median and maximum
span size). The threshold was not lowered.

The single residual error is page 8: the `1:20` anchor of `DETALHE 01 LAJE PRE-FABRICADA -
TRELICADA` takes the neighbouring `PLANTA DE FORMAS - TOPO RESERVATORIO` title instead, because
the 700 pt horizontal tolerance reaches across the adjacent view. Tightening the tolerance to
fix it costs correct associations on the wider sheets, so it is left for the geometric
segmentation of Task 7, which bounds each anchor by its own view box.

Rationale:

- the measurement is against the human-verified ground truth, not against the detector's own output;
- pairing is by scale as well as title, so an anchor that picks any other title on the same sheet
  counts as an error rather than a hit;
- non-numeric declarations (`ESCALA REPRESENTATIVA` on the auxiliary perspectives) are paired as
  non-numeric instead of being discarded, per the confirmed human policy;
- the number is recorded so Task 7 can be judged as an improvement or a regression against it.

## 2026-08-29 - A span with no letters is never a view title

`find_title_for` rejects candidate spans whose normalized text contains no alphabetic character.

Rationale:

- `title_font_floor` is relative to each sheet's own span sizes, so on a sheet with only small
  text the floor collapses and any span clears it;
- without the guard, a bare page number or dimension above a scale declaration ("19") is returned
  as the view title;
- a false title is worse than no title: it silently associates a view to the wrong name, while
  `None` is visible and can be handled;
- the guard is content-based and independent of the calibrated tolerances, so it does not disturb
  the 94% measurement - the association output on the base project is byte-identical before and
  after it.

## 2026-08-29 - Sheet Map snapshots are immutable and content-addressed

`save_sheet_map` no longer deletes the previous Sheet Map. The `pipeline_version` now embeds the
snapshot hash (`sheetmap-v0.2+<hash16>`), so the existing `UNIQUE (sheet_id, pipeline_version)`
constraint doubles as the immutability guarantee. Reprocessing identical input finds the row and
reuses it; changed input writes a new row beside the old one. `get_sheet_map` serves the most
recent snapshot of the current pipeline, and `get_sheet_map_by_id` addresses one directly.

This closes conflict C1 of the F2 plan: a Sheet Map referenced by an audit run could previously be
destroyed by a rebuild, leaving findings pointing at a row that no longer existed.

Rationale:

- audits, findings, and human feedback reference a specific snapshot, so deleting one rewrites
  history that a person already reviewed;
- addressing by content means a rebuild is free when nothing changed, and honest when something did;
- no table was rebuilt and no migration is destructive - the change is a write-path change plus the
  additive columns of migration `003`.

Consequence to plan for: the 85 existing sheet_maps carry `pipeline_version = "sheetmap-v0.1"`,
which does not match the `LIKE 'sheetmap-v0.2%'` filter. **The rows are intact and nothing was
deleted, but they stop being served, so the viewer returns 404 for every sheet map until the
sheets are reprocessed.** Reprocessing requires the original PDFs under `data/originals/`, which
are not versioned and are currently absent from this clone.

## 2026-08-29 - Views cross the API boundary with raw and normalized apart

`SheetMap.views` was added to the API response model, carrying `title_raw`/`title`,
`declared_scale_raw`/`declared_scale`, and `level_raw`/`level` as separate fields.

Rationale:

- the repository returns views, and without the field the pydantic `response_model` dropped them
  silently - the contract would have looked correct while serving nothing;
- the viewer must be able to show what the PDF literally says, not an unconfirmed interpretation,
  so collapsing raw and normalized into one column would destroy the distinction the ground truth
  depends on;
- the list is empty until the detector of Task 7 fills it, so the change is additive and observable.

## 2026-08-29 - Drawing zone is the frame minus the title block, in disjoint bands

The drawing zone was a single rectangle cut off at the top edge of the title block. It is now a
list of disjoint bands: the frame with the title block subtracted, sliced at the horizontal edges
of the occupied regions. This closes conflict C3.

Measured on all 29 pages of the base project: **+7.4% drawing area recovered, 2 zones per sheet**.
The recovered strip is not cosmetic - **5 of the 16 view anchors on the six forms sheets sit
inside it**, including the only view on pages 4 and 25. The old truncation would have cost the
Task 7 detector roughly a third of the views and two sheets entirely.

Rationale:

- the title block occupies a corner, not a full-width band, so cutting at its top edge threw away
  the strip beside it;
- bands keep the zone exact instead of approximating it with one rectangle;
- `DetectedRegion` gained `parent_kind`, so a zone records that it is nested in the frame. The
  column is not persisted - migration `003` has no `parent_kind` on `sheet_regions` - so it lives
  in memory and inside the snapshot hash only.

## 2026-08-29 - No table detector: the material has no rectangle cells

Task 6 of the F2 plan specified `detect_tables(geometry, spans)` and subtracting the result from
the drawing zone. Neither half survived contact with the material, so neither shipped.

The plan's algorithm was implemented and measured first. On page 6 it reported **10 tables, each
of them a piece of the floor plan itself** - the largest 1585x742 pt, containing `L301`, `L302`,
`h=15`, the slab labels. It chains each cell to the previous one in the cluster, so a cluster
snakes across the whole sheet.

A stricter grid test - shared edges, uniform cell size, mostly-filled rows and columns - was then
tried, and found **zero** tables. The reason is structural, and holds for any cell-based approach:

- `geometry_from_extraction` keeps only rects above 0.0002 of page area. On page 6 that discards
  8050 of 15785 distinct rects, and what survives has a median size of 76x76 pt - slab and beam
  outlines, not table cells. `detect_tables(geometry, ...)` cannot see a cell even in principle.
- Going to the raw primitives does not help: pages 6 and 25 contain **zero `re` primitives**
  (41711 lines, 762 curves, 33 quads on page 6). The tables are drawn as line segments, and the
  `rect` of a line primitive is the bounding box of its whole drawing path - which is exactly why
  the plan's version produced page-sized blobs.

Reconstructing cells from line intersections is a real piece of work, it is not what Task 6
describes, and there is no table ground truth in `calibration/juliano-corbellini-r05.yml` to
measure it against.

Subtracting tables was also wrong on its own terms. `forms-policy-decisions-v1.md`, the confirmed
human source of truth, says tables *belong to the view*: "Tabelas de vigas, pilares, lajes e
materiais proximas das plantas pertencem ao contexto da view". Carving a table out of the drawing
zone would split a view's own area. The policy only requires that a table not become an
independent view - and it will not, because the Task 7 detector builds views from scale anchors,
and a table declares no scale.

`REGION_TABLE`, `REGION_NOTE_BLOCK` and `REGION_LEGEND` are kept as declared names with no
detector behind them. The `spans` parameter of `detect_regions` was dropped rather than kept
unused, so the signature does not promise something it ignores.
