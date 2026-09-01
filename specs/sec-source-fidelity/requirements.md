# SEC Source Fidelity — Requirements

> **Lifecycle status:** Gated backlog
> **Spec-file progress:** Not yet started
> Anchors inventory questions **F1–F2** in
> [docs/research-questions.md](../../docs/research-questions.md).

**Target epistemic tier:** `exploratory`

**Research question anchor:** F1 M&A exit timing and F2 SBIR↔M&A event coverage
**Answers for:** engineers maintaining SEC-derived capital-event and Form D inputs
**RQ complexity tier:** Descriptive; this spec preserves and de-duplicates source event records

---

## Done when

Two SEC-derived source defects are closed: an EDGAR profile can no longer pair an
acquisition-related mention *type* with a "latest" date belonging to a different type, and Form D
amendment chains no longer inflate cumulative raised totals.

---

## Background

These were reviewed as two proposals (PRs #690 and #691) and merged here because they are one
surface: both touch `sbir_etl/enrichers/sec_edgar/` and `sbir_etl/capital_events/`, and both feed
the same downstream consumers.

**EDGAR type/date decoupling.** `sbir_etl/enrichers/sec_edgar/enricher.py:769-780` keys the dedup
map on `filer_name or cik`, discarding distinct accessions from the same filer. It then unions
`mention_types` across the survivors and takes `max(filing_date)` across *all* types. A profile can
therefore report an acquisition-related type and a recent date without those being the same filing.
Two consumers already perform exactly that unsafe join —
`scripts/data/nano_prime_acquisitions.py:283-288` and `scripts/data/nano_ma_signal.py:139-144` both
intersect `mention_types` with `MA_SIGNAL_TYPES` and then read `latest_mention_date` as the M&A
date. The mis-attribution is live, not hypothetical.

**Form D amendment chains.** Form D amendments (D/A) restate *cumulative* offering totals rather
than adding to them, so summing an original alongside its amendments double-counts. A partial fix is
in place: `form_d_inputs.py` now sums non-amendment offerings only, falling back to the largest
restatement when a chain arrives as amendments alone. That is a documented lower bound, not an exact
total — an original plus amendments of 5/8/10 reports 5 where the correct answer is 10.

## Tier note

Both proposals originally declared `pipelines`. That is not yet warranted: every named consumer of
these event artifacts is under `scripts/data/`, which is exploratory. This spec declares
`exploratory` and treats promotion as separate, explicit work per
[docs/steering/epistemic-tiers.md](../../docs/steering/epistemic-tiers.md). Name a pipelines-tier
consumer before re-tiering.

## Gate

The Form D half is blocked on an open question, not on effort: the SEC **file number** (the
`021-…` offering identifier) is the chain key, and it appears nowhere in the codebase.
`FormDFiling` (`sbir_etl/models/sec_edgar.py:195`) carries only the `is_amendment` boolean and a
per-filing `accession_number`, neither of which groups filings into chains. Resolve that in a
notebook before implementing an exact collapse.

This spec also overlaps the **Active** `agency-private-capital-comparison` spec, whose Phase 2 is
gated on a reproducible Form D control-universe producer and whose direct input is
`form_d_inputs.py`. Coordinate ownership with that spec and with PR #582 before starting.

---

## Requirements

### 1. EDGAR event records preserve their own provenance

1.1 Each retained filing hit SHALL persist its own accession, form type, filer, filing date, and
mention type rather than being collapsed to one row per filer.

1.2 Any profile-level "latest" date SHALL be derived for a *named* mention type. A date SHALL NOT
be paired with a union of unrelated types.

1.3 The existing `mention_types` / `latest_mention_date` fields SHALL either keep their current
meaning or be renamed. They SHALL NOT silently change meaning under the same key.

### 2. Consumers read a type-anchored date

2.1 `nano_prime_acquisitions.py` and `nano_ma_signal.py` SHALL read an M&A-anchored date rather
than reconstructing one from a type set and an all-type maximum.

2.2 Any artifact regenerated after this change SHALL record that its event dates come from the
type-anchored field, since prior artifacts were built on the unsafe join.

### 3. Form D amendment chains collapse exactly

3.1 Once the chain key is known, offerings SHALL be grouped into amendment chains and each chain
SHALL contribute its final restatement to cumulative totals.

3.2 `total_form_d_raised`, `total_form_d_offered`, and `offering_count` SHALL agree on that grain.

3.3 The interim lower-bound behavior SHALL be replaced, not layered over, and its code comment
SHALL be removed with it.
