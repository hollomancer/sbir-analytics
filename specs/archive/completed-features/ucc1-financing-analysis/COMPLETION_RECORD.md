# Completion Record — ucc1-financing-analysis

**Status**: CA-only pilot complete; extension explicitly deferred by the
research memo. Treated as a completed feature, not superseded work: the
pilot answered its Phase 0 question and the stop was a deliberate scope
decision, not a replacement by other machinery.
**Archived**: 2026-08-07

Evidence:

- PRs #303 / #305 (merged) — Phase 0 probe and the CA-only pilot run.
- [docs/research/sbir-ucc1-pilot.md](../../../../docs/research/sbir-ucc1-pilot.md)
  — findings and the scope-narrowing decision. Phase 0 established that
  Delaware has no free public UCC search, so the original DE+CA scope was
  not achievable on free data; the pilot ran CA-only against the
  CA-organized cohort subset. The partial run (alphabetical-first 70 of
  3,639 cohort firms) produced a representative result before Imperva
  anti-bot limits stopped full coverage.
- `sbir_etl/ucc/` — the pilot's matcher and support code remain in-tree
  (pipelines-tier package default; `ucc/matcher.py` labeled exploratory).

Stop/defer rationale: full CA coverage is operationally blocked by
anti-bot limits, Delaware requires paid authorized searchers, and the
research memo defers any extension until UCC-1 financing evidence becomes
a selected research priority. The spec's target tier was `evidence`; no
study contract was ever created, and none is owed for an archived pilot —
any revival starts from a fresh scope decision against
docs/research-questions.md.
