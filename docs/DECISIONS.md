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
