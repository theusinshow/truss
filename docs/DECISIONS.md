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
