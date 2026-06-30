# Literature Map & Citation Audit

A recent-literature map of the SBIR/STTR commercialization subfield, cross-referenced against
the repo's `[L#]` benchmark list in [`docs/research-questions.md`](../../research-questions.md),
plus a survey of `specs/` implementation status. Generated from OpenAlex (via the literature
connector), covering 2019–2026.

## Contents

**Literature map**
- [`sbir_literature_map.md`](sbir_literature_map.md) — narrative map across the six A–F policy
  areas, with cross-cutting observations.
- [`sbir_literature_map.csv`](sbir_literature_map.csv) — 179 works (53 core + 126 adjacent) with
  DOIs, citation counts, FWCI, OA status, and relevance/area tags.
- `lit_overview.png` — volume-by-year, A–F coverage, and venue breakdown.

**Citation-gap analysis (map vs. `[L#]`)**
- [`citation_gap_memo.md`](citation_gap_memo.md) — which recent works are not yet in `[L#]`,
  ranked and tied to the slot each would update.
- [`citation_additions_core.csv`](citation_additions_core.csv) — 51 SBIR-specific core
  candidates, full metadata.
- [`recommended_citation_additions.csv`](recommended_citation_additions.csv) — top-5-per-area
  scored shortlist.
- [`proposed-L-entries.md`](proposed-L-entries.md) — **paste-ready** `[L34]–[L46]` benchmark
  entries (13 SBIR-specific works, verified DOIs/authors via OpenAlex), formatted to drop into
  `research-questions.md`. Advisory — not yet merged.

**Spec implementation-status survey**
- [`spec_status_survey.md`](spec_status_survey.md) — implemented vs. partial vs. still-a-research-
  target, by policy area.
- [`spec_status_summary.csv`](spec_status_summary.csv) — 20 specs with area, status, evidence.
- `spec_status.png` — status × policy-area overview.

## Method & caveats

Pooled ~989 OpenAlex works via thematic A–F keyword searches, direct SBIR/STTR searches, and
forward-citation pulls from two anchor papers (Howell 2017, Myers & Lanahan 2022), then
machine-classified each for relevance and policy area. OpenAlex covers journals and NBER/SSRN
working papers well but is thin on the GAO/CSIS/NASEM grey literature that dominates `[L#]` —
those institutional sources are best tracked directly. Abstracts were largely license-gated;
thematic summaries rest on titles, venues, topics, and citation context.
