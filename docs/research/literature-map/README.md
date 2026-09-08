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

**Status:** the 2026-08 citation audit merged the shortlist below into the `[L#]` list as
[L34]–[L48]. This directory is the provenance record for those entries, not a pending queue.

**Citation-gap analysis (map vs. `[L#]`)**
- [`citation_gap_memo.md`](citation_gap_memo.md) — which recent works are not yet in `[L#]`,
  ranked and tied to the slot each would update.
- [`citation_additions_core.csv`](citation_additions_core.csv) — 51 SBIR-specific core
  candidates, full metadata.
- [`recommended_citation_additions.csv`](recommended_citation_additions.csv) — top-5-per-area
  scored shortlist.

**Spec implementation-status survey**
- [`spec_status_survey.md`](spec_status_survey.md) — implemented vs. partial vs. still-a-research-
  target, by policy area.
- [`spec_status_summary.csv`](spec_status_summary.csv) — 20 specs with area, status, evidence.
- `spec_status.png` — status × policy-area overview.

## Method & caveats

Pooled ~989 OpenAlex works via thematic A–F keyword searches, direct SBIR/STTR searches, and
forward-citation pulls from two anchor papers (Howell 2017, Myers & Lanahan 2022), then
machine-classified each for relevance and policy area. The weekly refresh also pulls National
Academies Press books from OpenAlex (source `S4306463641`) and recent GAO / NAP / CRS / ITIF
items from public RSS/Atom feeds, filtered to SBIR/STTR and a short industrial-base/FOCI
keyword list. CSIS web analysis is still thin in both OpenAlex and CSIS's public RSS (the
feed is mostly old events); those `[L#]` entries stay hand-tracked. Abstracts were largely
license-gated; thematic summaries rest on titles, venues, topics, and citation context.

## Refresh

The CSV is exploratory. Re-run locally or wait for the Monday GitHub Action:

```bash
make literature-map
# or: uv run python scripts/data/update_literature_map.py
```

That updates `sbir_literature_map.csv` (citation counts and new keyword-classified works)
and overwrites `refresh_status.md`. It does **not** rewrite this README, `sbir_literature_map.md`,
or `citation_gap_memo.md`. Existing rows keep their stored relevance/area labels.

Grey-literature rows without an OpenAlex work id use a synthetic key in `openalex_id`
(`gao:GAO-24-106398`, `nap:29329`, `crs:R43695`, `itif:…`). A later OpenAlex hit with the
same title or DOI is merged onto that row and the key is upgraded to `W…`. RSS feeds are
recency windows, not a full corpus — historical GAO/CRS reports already in `[L#]` are not
backfilled. CRS is read from the unofficial EveryCRSReport mirror. One failed feed does
not abort the OpenAlex half of the run.

`.github/workflows/literature-map.yml` runs the same command weekly (Monday 09:17 UTC) and
opens `chore/literature-map-refresh` when those two files change. Optional secret:
`OPENALEX_MAILTO` (OpenAlex polite pool). No API key is required.

The workflow is not a study promotion and does not edit `[L#]` entries.
