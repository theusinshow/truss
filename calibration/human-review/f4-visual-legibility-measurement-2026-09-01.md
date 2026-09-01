# F4.1 visual-legibility candidate measurement

Date: 2026-09-01

Mode: local deterministic measurement, no AI provider and no network

## Purpose

Measure how many native-text regions reach the visual legibility gate before enabling paid
multimodal analysis. This is a pressure and coverage measurement. It does not measure model
precision, recall or engineering correctness.

## Configuration

- small-text threshold: `< 5.5 pt`;
- overlap threshold: intersection / smaller span area `>= 0.12`;
- selection cap: 8 candidates per PDF page/sheet;
- crop defaults: 18 pt padding, 3x render scale, 1600 px maximum dimension;
- provider calls: zero;
- duplicate PDFs: removed by SHA-256 before counting.

## Corpus

Five local PDF files were available. Three copies of Rancho Queimado had identical content, so
the measured corpus contains three distinct hashes and 58 pages.

| SHA-256 prefix | Document | Pages | Pages with candidates | Native spans | Small text | Overlap | Selected at cap 8 | Time |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `7d2f9c32bc9d4988` | Proj_Estrutural_RanchoQueimado_geral.pdf | 28 | 20 | 18,686 | 174 | 368 | 131 | 5.945 s |
| `5c7d3d3d7433b606` | 017_26_est_geral-01.pdf | 1 | 1 | 866 | 5 | 1 | 6 | 0.320 s |
| `147b730c0189a78e` | Projeto Estrutural_Juliano Corbellini_R05.pdf | 29 | 14 | 15,608 | 11 | 119 | 85 | 6.460 s |
| **Total** | **3 distinct PDFs** | **58** | **35** | **35,160** | **190** | **488** | **222** | **12.725 s** |

## Interpretation

- Candidate generation covered 35 of 58 pages and produced 678 raw candidates.
- Overlap is the dominant trigger: 488 candidates, or 72.0% of the raw total.
- The cap retained 222 candidates. It prevents dense drawing pages from expanding one user action
  into an uncontrolled number of calls.
- Revision-wide call and estimated-cost gates remain necessary because a document can contain many
  candidate-bearing sheets.
- The measurement deliberately did not inspect or transmit crop pixels. Crop rendering and
  content-addressing are covered by the synthetic positive/negative fixture.
- No precision claim is valid yet. The next validation gate is human labeling of sampled crops,
  followed by a deliberately authorized provider run on that fixed sample.

## Reproduction

The reusable entry point is `truss_api.calibration.vision.measure_visual_candidates`. It extracts
each page with the same native-text primitive used by the Sheet Map, applies the production
candidate detector and returns per-page and per-document counts without constructing a provider.

## Controlled provider validation

After explicit owner authorization, three real crops from page 6 of
`Proj_Estrutural_RanchoQueimado_geral.pdf` were inspected locally and sent individually to
`gpt-5.6-sol`. The fixed run used reasoning `low`, image detail `high`, at most 400 output tokens,
at most 3 calls and an operational ceiling of USD 0.06. No PDF or full-page render was sent.

| Candidate | Crop SHA-256 prefix | Local visual expectation | Provider result | Confidence |
| --- | --- | --- | --- | ---: |
| `visual-e8fddcef7228203e6a5a` | `2cfae4d5fd6b6a18` | Attention: `Tipo` and `m2` collide | `ATTENTION` | 0.98 |
| `visual-7f3818b2399afbf280d3` | `bd6fc6191d48dff1` | Attention: lifecycle and dimension annotations collide | `ATTENTION` | 0.97 |
| `visual-1ead35c3c6fb732092fe` | `ac552fb0776a0514` | Attention: `LE1` and `PAR5` overprint | `ATTENTION` | 0.98 |

The run produced 3 localized pending `ATTENTION_POINT/MEDIUM` findings. Recorded usage was 3 calls
and USD 0.019245 estimated total cost. Repeating the identical run returned the same audit run and
left usage at 3 calls, proving the content/configuration cache prevented a fourth provider call.

This is a small contract and smoke-quality sample, not a statistical accuracy claim. Broader
precision/recall measurement requires an owner-confirmed labeled crop dataset.
