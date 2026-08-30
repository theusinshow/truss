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

## 2026-08-29 - A title belongs to exactly one view

`find_title_for` accepts a set of already-claimed title bboxes, and the detector assigns titles to
anchors greedily by smallest global distance instead of letting each anchor search on its own.

Rationale:

- searching independently let two neighbouring anchors pick the same title. Measured on page 8 of
  the base project: the `1:20` anchor of `DETALHE 01 LAJE PRE-FABRICADA` and the `1:50` anchor of
  the plan beside it both returned `PLANTA DE FORMAS - TOPO RESERVATORIO`;
- the distance is `hypot(dx, dy)`, so horizontal separation breaks the tie a vertical-only metric
  cannot - the two anchors sat at the same height;
- **this closed the last association error: 15/16 became 16/16.**

`TitleCandidate` also gained `raw`, the literal span text with the ordinal prefix removed, because
`title` is normalized (uppercase, unaccented) for pattern matching and the ground truth records
what the sheet actually says.

## 2026-08-29 - View detection is not gated by sheet_type

The plan gated `detect_forms_views` on `classification.sheet_type == "planta_formas"`. The gate was
removed.

Rationale:

- it produced zero views for two of the six human-reviewed sheets. The classifier calls page 4
  `desconhecido` and page 25 `planta_armaduras`, while the ground truth records one view on each -
  so the gate was keyed on a classification that had failed;
- it buys no safety. The detector only builds a view from an explicit `ESCALA` anchor, so a sheet
  that declares no scale yields nothing. Measured ungated over all 29 pages: **49 views, 49 of them
  with a title** - there is no low-confidence noise for the gate to suppress;
- views are data, not findings. What must be scoped to forms sheets is the Task 8 checklist, not
  the extraction of views.

A test replaces the gate with the real safety property: a sheet without a scale declaration yields
no views.

## 2026-08-29 - View detection measured; bounding boxes remain unverified

Detector measured against the human ground truth over the six forms sheets of the base project:

- **16 views detected, ground truth has 16**
- **16/16 with title and scale (100%)**
- **16/16 associated to the correct ground-truth title for their scale (100%)**
- **16/16 correct `view_kind`**
- no invalid bounding box, no view overlapping the title block

The **bounding boxes themselves are not validated**, and the plan's completion criterion does not
cover them. The ground truth has no spatial boxes - only a free-text `position_hint` such as
"superior esquerda". Scored against that proxy, only **8 of 16** boxes have their centre in the
quadrant the owner described: the plan sets a view's right edge to the drawing zone's right edge,
so every view spans the full sheet width, and a view with no following anchor in its column runs to
the bottom of the zone.

A row-and-column partition was prototyped as an alternative and measured **8/16 under the same
criterion** - no better. `position_hint` is free text and too noisy to tune geometry against, so
the plan's simpler rule was kept rather than replaced by an equally unvalidated one.

This is what the plan already anticipates: boxes are `draft_unverified` until the owner confirms
them visually against the overlays of Task 10. Task 8 should not assume the boxes are tight.

## 2026-08-29 - Two rule packs: general rule and personal preference

The F2 plan specified one pack, `planta_formas.v1.yml`. Two shipped instead: `formas_geral.v1.yml`
(`scope: general`) and `formas_pessoal.v1.yml` (`scope: personal`).

Rationale:

- `forms-policy-decisions-v1.md`, confirmed by the owner, separates them explicitly on levels: "A
  regra geral pode reconhecer casos simples em que base/topo seriam compreensiveis sem nivel, mas o
  rule pack pessoal deve exigir nivel sempre";
- a preference presented as a norm is a false positive with extra steps. The general pack reports a
  missing level as `attention` / `low`; the personal pack reports the same absence as
  `missing_information` / `high`;
- the `rule_scope` column already exists on `rule_evaluations` and `findings`, so nothing new was
  needed to keep them apart downstream;
- the personal pack carries **only** what diverges. Everything already normative lives in the
  general pack and is not repeated.

Scope lives inside the pack file, not in its name: a pack declares which sheet type it covers and
with what authority. `finding_type` is constrained by the schema to the vocabulary `findings.type`
already uses, so a pack cannot invent a parallel one.

The negative rules of the ground truth are encoded as `applies_to_view_kinds` and explicit
exemptions, not as special cases in the engine:

- an auxiliary perspective is never an incomplete technical view - the title, scale, and level rules
  are `NOT_APPLICABLE` to `perspective`;
- `ESCALA INDICADA` is a valid declaration for a technical view; `ESCALA REPRESENTATIVA` is not, and
  a plan, section, or detail declaring only it fails;
- a subview does not repeat its grouping detail's title;
- `P21=P38` and `P28=P37` are intentional equivalences, so a title carrying `=` keys duplicate
  detection by title rather than by ordinal.

## 2026-08-29 - Checklist measured against the ground truth: zero findings, as confirmed

Both packs were run over the views the detector actually produces on the six forms sheets:

- **general pack: 0 FAIL. Personal pack: 0 FAIL.** The ground truth declares
  `expected_findings: confirmed_zero` for `EST-0050-B` through `EST-0090-B`, so this matches.

Zero findings is only meaningful if the rules were exercised, so the outcome distribution was
measured too: `level_declared` 8 PASS / 8 NOT_APPLICABLE, `scale_declared` 13 PASS / 3
NOT_APPLICABLE, `title_present` 13 PASS / 3 NOT_APPLICABLE, `category_matches_content` 5 PASS / 1
UNKNOWN. The three `NOT_APPLICABLE` in each view rule are the three auxiliary perspectives, exactly
as the policy requires. **No rule is vacuous and none was silenced to reach zero.**

The plan's acceptance criteria "cobertura dos findings do ground truth >= 60%" and "precisao >= 70%"
**cannot be computed here**: the ground truth expects zero findings on all six sheets, so there is
no positive set to recall against. They need sheets with known defects, which the calibration
material does not yet contain.

## 2026-08-29 - A view's level comes from its own title, not from a spatial scan

`find_level_in` reads the level from the view's title, and the detector falls back to the bounding
box scan only when the title carries none.

Rationale:

- found by the Task 8 measurement, not by a test. `find_level_near` returns the first level span
  inside the bounding box **in document order**, and the boxes are wide enough to reach a
  neighbour's title. On page 5 the middle plan reported `-167`, the level of the plan beside it,
  instead of its own `-350`;
- the checklist rule then **passed**, asserting "level declared" while holding the wrong value - a
  silent wrong answer is worse than a reported absence;
- the human policy puts the level in the title: "toda planta de formas deve declarar nivel no
  titulo". The title is the authoritative source and does not depend on box precision.

Measured against the ground truth over the eight plan views that declare a single numeric level:
**7/8 before, 8/8 after**. The eight remaining ground-truth levels are descriptive
(`varios`, `338 -> 680 principalmente`) and have no single value to compare.

## 2026-08-29 - The audit runs both scopes and the dedupe key carries the scope

`run_deterministic_audit` evaluates every pack registered for the sheet type, not one, and
`dedupe_key_for` includes `evaluation.scope`.

Rationale:

- both packs declare `forms.view.level_declared` against the same view. Without the scope in the
  key, the second finding would match the first on rerun and be swallowed, so the owner's own
  requirement would never appear - the exact failure the two-pack split exists to prevent;
- the cache key combines every pack id and version, so adding, removing, or bumping a pack
  invalidates the cached run instead of serving a stale verdict;
- findings carry `rule_scope`, and `rule_evaluations` records `rule_pack_id` and `rule_scope`, so a
  preference is always distinguishable from a norm downstream.

## 2026-08-29 - The fallback finding is gone; absence of findings is reported as coverage

The orchestrator no longer emits "Auditoria deterministica inicial nao encontrou inconsistencias
textuais obvias" when nothing failed. A clean sheet returns zero findings plus a coverage summary
(`evaluated`, `passed`, `failed`, `unknown`, `not_applicable`, `skipped`).

Rationale:

- a finding that says "nothing was found" is not a finding. It trains the reader to dismiss the
  list, and it is indistinguishable from a real low-severity note;
- coverage answers the question the fallback was pretending to answer - what was actually checked -
  without fabricating an entry;
- the three old text heuristics (no native text, no `ESCALA` anywhere, no recognisable title term)
  were whole-sheet guesses with no rule identity. They are replaced by rules with `rule_id`,
  version, scope, target, and evidence.

Measured end to end over the base project - import, sheet map, view detection, audit:
**0 findings on the six reviewed sheets**, matching the ground truth's `confirmed_zero`, with
coverage of 19/15/19/15 evaluations on the four `planta_formas` sheets.

Consequence to plan for: pages 4 and 25 report `evaluated: 0`. Their views are detected, but they
classify as `desconhecido` and `planta_armaduras`, and a forms pack must not judge a sheet it does
not cover. The ground truth agrees they are `detalhamento_*` sheets. **Two of the six reviewed
sheets therefore get no checklist at all** until a pack exists for detail sheets, which is outside
F2. The alternative - letting the forms pack judge them - would invent authority the pack does not
have.

Legacy findings have no `dedupe_key`, so they never match during deduplication and are left
untouched. That is the intended behaviour.

## 2026-08-29 - View overlays show the sheet's own wording

`ViewOverlays` renders one inspectable rectangle per detected view, labelled with the raw title,
the scale, and the raw level. Clicking one selects it; focusing a finding that carries `view_id`
selects the view it was evaluated against.

Rationale:

- the boxes are `draft_unverified` and the owner is the only one who can confirm them, so the
  overlay has to be legible enough to judge - a bare rectangle would not be;
- the label uses `title_raw` and `level_raw`, never the normalized columns. The viewer shows what
  the sheet says; a normalized level the owner has not confirmed would be an invention presented as
  a reading;
- the scale prefers the normalized value when it is numeric and falls back to the raw wording
  otherwise, because `ESCALA REPRESENTATIVA` is a valid declaration and rendering it as empty would
  read as an absence;
- old sheet maps have no `views`, so the component receives `[]` and renders nothing.

## 2026-08-29 - An empty findings list states what was checked

The findings drawer distinguishes "no findings on this sheet" from "no findings in this filter",
and the former is followed by the coverage line from `auditCoverageSummary`.

Rationale:

- removing the fallback finding made an empty list a normal outcome for the first time. Without
  coverage beside it, an empty list is ambiguous between "checked and clean" and "never checked" -
  which is precisely the ambiguity the fallback was papering over;
- `auditCoverageSummary` reports "Nenhuma regra se aplica a esta folha" when `evaluated` is zero,
  and never phrases anything as approval;
- unknown counts are surfaced, not hidden, so a sheet whose rules could not be decided does not
  look conformant.

Not verified visually. The overlays are covered by component tests, but nobody has yet seen them on
a real sheet: the viewer needs a project imported under the current pipeline, which is Task 11.
