# SEC Source Fidelity — Design

**Target epistemic tier:** `exploratory`

## EDGAR type-anchored dates

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

## Form D amendment chains

Amendments restate cumulative totals, so the correct total for a chain is its final restatement, not
the sum of its filings. Collapsing chains requires grouping filings that belong to the same
offering, which needs the SEC file number.

The interim behavior now in `form_d_inputs.py` sums originals only and falls back to the largest
restatement for amendment-only chains. It is deliberately conservative: it under-reports rather than
over-reports, and the code comment says so. It is not a design, and it should be deleted when task 5
lands rather than kept as a fallback path.

## What this spec does not do

- It does not promote these artifacts above `exploratory`. Every named consumer is a
  `scripts/data/` script; promotion needs a pipelines-tier consumer first.
- It does not add conflict quarantine or legacy-profile migration guards. Those were proposed in the
  reviewed spec and cut: build them when there is a pipelines-tier consumer to protect.
