# EDGAR Event-Date Fidelity — Design

**Target epistemic tier:** `exploratory`

## Type-anchored dates

The dedup at `enricher.py:769-780` exists to keep one row per filer. The fix is not to remove
deduplication but to stop deriving a profile-level date from the deduplicated set:

- Key the retained-event map on `(cik, accession_number)` so distinct filings survive.
- Replace the single `latest_mention_date` with a per-type mapping, so an M&A date is always the
  date of an M&A-typed filing.
- Keep `mention_types` as the type set it already is; add the anchored dates beside it rather than
  redefining either existing field in place.

Field naming is a decision, not an implementation detail: `latest_mention_date` has two live
readers, and silently changing its meaning would leave their existing artifacts unexplained. Prefer
a new field and a deprecation of the old one.

## What this spec does not do

- It does not promote these artifacts above `exploratory`. Both named consumers are
  `scripts/data/` scripts; promotion needs a pipelines-tier consumer first.
- It does not add conflict quarantine or legacy-profile migration guards. Those were proposed in
  PR #690 and cut: build them when there is a pipelines-tier consumer to protect.
- It does not cover Form D amendment chains. That work is
  `specs/agency-private-capital-comparison/tasks.md` F.1–F.3.
