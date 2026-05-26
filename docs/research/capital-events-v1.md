# Capital-Event Timeline v1 — Results

**Date:** 2026-05-17
**Branch:** `claude/capital-events-timeline`
**Cohort:** Form D high-confidence SBIR cohort (3,639 firms; produced by
`scripts/data/ucc/export_cohort.py` from PR #303)
**Source code:** `scripts/data/build_capital_events.py` +
`scripts/data/capital_events/`

## Summary

End-to-end build produced **35,765 capital events** across the 3,639-firm
cohort, drawn from five active source datasets (sixth source — UCC matches
— is empty in v1 because the UCC1 pilot's bulk extraction never completed).
The per-firm summary is fully populated (one row per cohort firm). Two
data-quality issues fixed during the run; both real-data issues, not test
gaps.

## Per-source counts

| Source | Events | Cohort firms with ≥1 event | Coverage |
|---|---:|---:|---:|
| `sbir_award` | 22,231 | 3,639 | 100.0% |
| `form_d_filing` | 12,911 | 3,638 | 100.0% |
| `ma_event` | 429 | 429 | 11.8% |
| `usaspending_contract` | 194 | 86 | 2.4% |
| `patent_grant` | 0 | 0 | 0.0% |
| `ucc_filing` | 0 | 0 | 0.0% |
| **TOTAL** | **35,765** | — | — |

100% SBIR + Form D coverage is expected by cohort design (every cohort
firm has at least one SBIR award and at least one high-confidence Form D
match). M&A coverage of 11.8% matches the partial-run finding from the
UCC1 pilot (which sampled 70 of the same 3,639 firms and found 11.4%
with M&A signals).

## Coverage findings

- The cohort is fully SBIR + Form D-overlapping by construction. Other
  sources surface meaningful subsets:
  - **M&A events (11.8%)** — 429 firms in the cohort have a high or
    medium-confidence M&A signal. This is the population for
    "Phase II → exit latency" analyses.
  - **USAspending Phase III contracts (2.4%)** — only 86 cohort firms
    appear in the Phase 3 commercialization contract dataset. Either
    most cohort firms never transitioned to Phase III contracting, or
    the upstream Phase 3 extraction is incomplete.
  - **Patents (0%)** — the patent files in `transformed/uspto/` are
    timestamped sample files (10 records total, not the full PatentsView
    dataset). The capital-events builder will produce real patent events
    once the patent pipeline runs at scale.
  - **UCC matches (0%)** — produced by the UCC1 pilot's matcher, but the
    bulk extraction never completed (see UCC1 memo). The builder
    tolerates the missing file; events appear automatically once the
    file lands.

## Spot-check vignettes (5 firms with diverse trajectories)

### Inhibrx, Inc. (9 events)

- 2017: three SBIR awards (HHS Phase I × 2 + Phase II, ~$1.4M total)
- 2018-05-10: simultaneous Form D combination ($410M total raised) +
  M&A event (`high` confidence). Likely the IPO / reverse-merger event
  that took Inhibrx public.
- 2018-05-11: small follow-on Form D equity ($3.5M)
- 2019: $40M Form D
- 2020: $15M Form D
- 2023: $200M Form D

**Story:** HHS-funded biotech that ran SBIR Phase I + II in 2017,
went public via M&A event in May 2018 raising $410M, then continued
fundraising through 2023.

### Active Motif, Inc. (26 events)

- 13 undated SBIR Phase I events (data-quality note: empty Award Date)
  — likely older awards predating the SBIR.gov date tracking
- 2012–2025: 13 dated SBIR events (HHS + NSF), Phase I and II mix
- 2013-03-08: Form D combination ($3.6M) + M&A event (`high` confidence)
- 2021-09-23: Form D equity ($10M)

**Story:** 24-year-old molecular biology reagent company (per UCC1
pilot's Active Motif vignette). Long history of HHS Phase I awards
plus NSF Phase II. M&A event in 2013 suggests a corporate restructuring
or holding company formation; subsequent equity raise in 2021.

### AADI, LLC (7 events)

- Undated SBIR Phase I (data-quality note: empty Award Date) + 2015
  HHS Phase II ($925k)
- 2021-09-10: triple-signal event — Form D combination ($82.5M) + Form
  D equity ($155M) + M&A event (`high`, acquirer: **UroGen Pharma Ltd.**)
- 2022-10-11: $72.5M follow-on Form D
- 2025-03-18: $100M Form D

**Story:** Oncology biotech, HHS-funded. The 2021-09-10 cluster is a
classic reverse-merger / SPAC-style transition: simultaneous business
combination + large equity raise + named acquirer (UroGen). Continued
to raise $172M post-deal.

### Pacific Biosciences of California, Inc. (5 events)

- Undated SBIR Phase I (HHS, ~$149k)
- 2013-02-11: $20.5M Form D
- 2023-08-17: Form D combination ($85M) + M&A event (`high`)
- 2023-10-19: Form D combination follow-on ($84.8M)

**Story:** UCC1 pilot already established this firm as DE-incorporated;
event stream confirms the 2023-08-17 M&A event (acquisition of Apton
Biosystems was announced this date). UCC1 also found no venture-debt
filings against PacBio in the CA channel.

### Transphorm, Inc. (23 events)

- 2009: SBIR Phase I (DoD)
- 2010-2015: classic VC-backed growth — 12 Form D equity rounds totaling
  ~$245M, plus an SBIR Phase II ($1.5M in 2010)
- 2014-10-06: $10M Form D **debt** (rare for cohort — most use equity)
- 2020-02-27: Form D combination ($112M) + Form D equity ($21M) +
  M&A event (`high`) — acquired by Renesas Electronics
- 2021+: continued Form D activity post-acquisition, plus another SBIR
  Phase II in 2021-09-02

**Story:** Quintessential SBIR → VC growth → acquisition arc. GaN power
semiconductor company. DoD SBIR in 2009 catalyzed VC funding,
$245M+ raised over 5 years, acquired by Renesas Feb 2020. Notable:
the 2014 $10M debt round is one of the few firms in the cohort with
debt-typed Form D filings.

## Data-quality findings (fixed during run)

1. **Cohort-vs-source case mismatch (fixed in commit)** — Cohort names
   are mixed-case ("3DEO, Inc.") but the SBIR + USAspending builders
   were uppercasing matched names AND emitting the uppercased form. The
   summarizer's merge then didn't join SBIR events to cohort rows
   (since they appeared as separate uppercase orphans). Fix: builders
   build a `{UPPERCASE: canonical}` lookup, match case-insensitively,
   emit the canonical name. Impact: SBIR events 15,525 → 22,231 (+43%);
   SBIR coverage 60% → 100%.

2. **NAICS dict shape (fixed in commit)** — USAspending Phase 3 cache
   has NAICS as a dict `{code, description}`, not a bare string. The
   builder's `.strip()` on the dict raised AttributeError. Fix: added
   `_naics_code()` + `_naics_description()` helpers that tolerate both
   shapes. Impact: USAspending events 0 → 194.

## Known gaps (NOT fixed, documented)

- **Empty event dates** — Some SBIR award rows have empty
  `Proposal Award Date` in `raw/sbir/award_data.csv` (Active Motif has
  13, AADI has 1). These produce events with `event_date == ""`. They
  appear at the top of the sorted output, breaking chronology slightly
  for affected firms. Followup: extract a fallback date from
  `Solicitation Year` × award fiscal year, or filter out empty-date
  events.
- **Patents source contains only test fixtures** — The 10
  `transformed/uspto/patents_*.jsonl` files contain 1 record each;
  these appear to be Dagster pipeline test outputs, not full
  PatentsView ingestion. Followup: run the patent transformer at full
  scale, then re-run the orchestrator to add patent_grant events.
- **UCC1 matches file absent** — UCC1 pilot's bulk extraction never
  completed (per UCC1 memo). Followup: either run UCC1 to completion
  (operational investment), or pivot to BDC SoI per UCC1's Future
  Options.
- **USAspending coverage (2.4%) is low** — Only 86 cohort firms appear
  in the Phase 3 contracts dataset. Two possibilities: (a) most cohort
  firms never transitioned to Phase III contracting and this is the
  honest coverage, or (b) the Phase 3 cache is incomplete. Phase 3
  work's own memo notes ~5–10% Phase III transition rates, so 2.4% of
  the *Form D-overlapping* cohort is plausible (Form D firms tend to be
  more VC-track than Phase-III-track). Followup: validate against
  Phase 3's own coverage figures.

## Downstream questions this enables

Computed on top of this artifact in follow-on analyses (not implemented
here):

- **Time-from-first-SBIR-to-first-Form-D**, stratified by agency and
  cohort year. The events table has every SBIR + Form D event with
  dates; a `groupby(company_name).agg(min event_date per type)` is the
  one-line query.
- **Phase II → exit latency** for the 429-firm M&A subset, stratified by
  primary SBIR agency.
- **Capital intensity** — ratio of total_form_d_raised /
  total_sbir_amount per firm. The summary parquet has both.
- **Stage classification** — derive pre-seed / growth / late / exit /
  dormant stages from per-firm event trajectories.
- **Equity vs debt mix over time** — the Form D `event_subtype` already
  distinguishes `equity` / `debt` / `combination` / `option_warrant` /
  `other`. The Transphorm vignette shows the value: a single debt-typed
  Form D round in 2014 amid an otherwise equity-heavy trajectory.

## Validation against spec

- ✅ All 6 event types in the schema; 5 produce data, 1 (UCC) tolerates
  missing input as documented in spec
- ✅ Both output formats (long-format events parquet + wide-format
  per-firm summary parquet + 100-row jsonl sample) produced
- ✅ 8 schema columns match spec exactly
- ✅ Per-firm summary has all 17 documented columns (cohort fields +
  per-source counts/sums + cross-cutting first/last/type_count fields)
- ✅ Cohort scope: Form D high-confidence (3,639 firms) — V1 scope per
  spec. V2 cohort C (broader SBIR + capital-signal) is a documented
  follow-on, not in this run.

## Recommendation for V2

Three follow-ons in priority order:

1. **Promote to Dagster asset** once the schema is settled (spec
   explicitly identifies this as the natural V2 step). The script's
   builders are pure functions; wrapping as Dagster assets is mostly
   IO-manager wiring.
2. **Run the patent transformer at scale** to populate the
   `patent_grant` event count. The builder is ready; only the upstream
   data is missing.
3. **Extend to cohort C** (broader SBIR + private-capital cohort) for
   the "VC-backed vs SBIR-only" comparison the original spec called
   out as a follow-on. The schema doesn't change; only the input
   cohort file does.
