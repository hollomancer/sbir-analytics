# EDGAR Event-Date Fidelity — Requirements

> **Lifecycle status:** Gated backlog
> **Spec-file progress:** Not yet started
> Anchors inventory questions **F1–F2** in
> [docs/research-questions.md](../../docs/research-questions.md).

**Target epistemic tier:** `exploratory`

**Research question anchor:** F1 M&A exit timing and F2 SBIR↔M&A event coverage
**Answers for:** engineers maintaining SEC EDGAR-derived capital-event inputs
**RQ complexity tier:** Descriptive; this spec preserves source event records

---

## Done when

An EDGAR profile can no longer pair an acquisition-related mention *type* with a "latest" date
belonging to a different type.

---

## Background

Reviewed as PR #690. `sbir_etl/enrichers/sec_edgar/enricher.py:769-780` keys the dedup map on
`filer_name or cik`, discarding distinct accessions from the same filer. It then unions
`mention_types` across the survivors and takes `max(filing_date)` across *all* types. A profile can
therefore report an acquisition-related type and a recent date without those being the same filing.

The mis-attribution is live, not hypothetical. Two consumers already perform exactly that unsafe
join — `scripts/data/nano_prime_acquisitions.py:283-288` and `scripts/data/nano_ma_signal.py:139-144`
both intersect `mention_types` with `MA_SIGNAL_TYPES` and then read `latest_mention_date` as the M&A
date.

## Scope note

This spec was briefly merged with the Form D amendment work reviewed as PR #691. That was a
mistake: the two share a topic (SEC source fidelity) but not a package or an owner. The Form D work
lives in `packages/sbir-analytics/sbir_analytics/assets/agency_private_capital/form_d_inputs.py`,
which is owned and solely consumed by the Active `agency-private-capital-comparison` spec, and it
now sits there as that spec's tasks F.1–F.3. This spec touches only
`sbir_etl/enrichers/sec_edgar/` and shares no files with it.

## Tier note

PR #690 declared `pipelines`. That is not yet warranted: both named consumers of these event
artifacts are under `scripts/data/`, which is exploratory. Promotion is separate, explicit work per
[docs/steering/epistemic-tiers.md](../../docs/steering/epistemic-tiers.md) — name a pipelines-tier
consumer before re-tiering.

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
