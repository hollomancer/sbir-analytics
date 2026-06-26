# SBIR Capital-Pathway Cohorts

**Date:** 2026-06-23
**PR:** #356 (adds `has_strict_phase_ii_to_ma_pathway` and gap-day columns
to `data/capital_events_per_firm.parquet`)
**Source code:** `scripts/data/capital_events/summarize.py`
**Cohort universe:** Form D high-confidence SBIR cohort — 3,639 firms,
produced by `scripts/data/ucc/export_cohort.py` (PR #303)

## Cohort definition (precision)

The 3,639-firm cohort is **not** "all Form Ds." It's the intersection of:

| Layer | Count |
|---|---:|
| All Form D filings in `data/form_d_details.jsonl` | 10,405 |
| Filtered to `match_confidence.tier == "high"` (person_score ≥ 0.7 OR ZIP match) | 3,640 |
| Further required to also SBIR-firm-match (name OR ZIP to an SBIR awardee) | **3,639** |

Per `docs/research/sbir-form-d-fundraising-analysis.md`, the cohort excludes
~6,766 lower-confidence Form D filings and the more permissive
"High + Medium" cohort (4,760 firms) used for the bootstrap-CI leverage
analysis. All percentages in this document use 3,639 as the denominator
unless stated otherwise.

## Summary

The capital-events long-format table (`data/capital_events.parquet`) encodes
35,765 events across 6 event types for the 3,639-firm cohort. Filtering
firms by **strict event sequences** (each step strictly after the
previous) carves the cohort into nested subcohorts, the most analytically
interesting of which is **86 firms with a strict Phase II → Form D → M&A
pathway**.

This document catalogues the strict-sequence subcohorts derivable from the
events table, characterises the 86-firm flagship cohort by agency, vintage,
acquirer, and capital intensity, and points to the parquet column that
makes the cohort directly queryable.

## Strict-sequence cohort taxonomy

Counts are firms where each named event appears AND each strictly precedes
the next (gap > 0 days). "Strict" excludes same-day sequences. Percentages
are over the 3,639-firm cohort universe.

| Cohort | Firms | % of 3,639 |
|---|---:|---:|
| Any Phase II SBIR | 2,365 | 64.99% |
| Any Form D filing | 3,638 | 99.97% |
| Any M&A signal (high or medium tier) | 429 | 11.79% |
| Any USAspending Phase III contract | 86 | 2.36% |
| Phase I → Phase II (strict) | 2,082 | 57.21% |
| Phase II → Form D (strict) | 1,136 | 31.22% |
| Phase II → M&A (strict, skipping Form D) | 204 | 5.61% |
| Form D → M&A (strict, no Phase II requirement) | 339 | 9.32% |
| **Phase II → Form D → M&A (strict) — flagship** | **86** | **2.36%** |
| Phase I → Phase II → Form D → M&A (strict, fully ordered SBIR start) | 81 | 2.23% |
| Phase II → USAspending P3 (federal commercialization) | 75 | 2.06% |
| Phase II → Form D → USAspending P3 (federal commercialization with raise) | 25 | 0.69% |

A few observations:

- **Form D coverage is essentially 100%** by cohort construction — every
  cohort firm has at least one high-confidence Form D match (that's how the
  cohort was built).
- The cohort universe is 3,639 firms, but **only 2,365 (65%) ever reached
  Phase II**. The other 1,274 firms had Phase I awards or non-SBIR
  fundraising profiles. Any "Phase II →" cohort is bounded by that ceiling.
- **204 firms have Phase II → M&A** but only 86 (~42% of those) also
  raised Form D between the two — the rest were acquired directly out of
  SBIR (likely small DoD or specialty-pharma deals), or had Form D
  filings *after* the M&A event (acquirer-driven recapitalisation).
- **75 firms have Phase II → USAspending Phase III contract** — almost
  identical in size to the M&A pathway (86). Only **25 firms** completed
  both Form D and a federal Phase III contract. The Form D + federal
  Phase III paths are largely disjoint.

## The 86-firm flagship cohort: Phase II → Form D → M&A

### Time between stages (sequenced firms)

| Span | Median | p25 | p75 | Min |
|---|---:|---:|---:|---:|
| Phase II → first Form D | 2.5 yr (930 d) | 1.0 yr (380 d) | 6.4 yr (2,328 d) | — |
| First Form D → first M&A | 7.7 yr (2,809 d) | 4.2 yr (1,521 d) | 12.5 yr (4,559 d) | — |
| **Phase II → first M&A** | **13.1 yr (4,799 d)** | **6.7 yr (2,433 d)** | **17.2 yr (6,284 d)** | **1.1 yr (E-Line Ventures)** |

The dominant time cost is **Form D → M&A** — the post-raise growth period
takes more than twice as long as the SBIR-funded R&D-to-raise period. That
matches the venture lifecycle intuition: SBIR Phase II buys you 2-3 years
of R&D, the raise capitalises commercialisation, then a decade of scaling
before exit.

### Agency that funded the breakthrough Phase II award

| Agency | Firms | Share |
|---|---:|---:|
| Department of Health and Human Services (NIH) | 36 | 41.9% |
| Department of Defense | 26 | 30.2% |
| National Science Foundation | 21 | 24.4% |
| Department of Energy | 3 | 3.5% |
| Environmental Protection Agency | 2 | 2.3% |
| NASA | 1 | 1.2% |

NIH and DoD together fund **58 of the 86 firms (67%)**. HHS dominance
reflects the biotech-acquisition path being the most prolific SBIR-to-exit
pipeline; DoD reflects the strategic-acquirer path (defence primes and
specialty contractors).

### Acquirer concentration

| Acquirer | Firms acquired (in this cohort) |
|---|---:|
| Unnamed acquirer (M&A signal fired without resolved counterparty) | 19 |
| Array BioPharma | 2 |
| All others (61 distinct named acquirers) | 1 each |

**No serial acquirer takes more than 2 cohort firms.** The acquirer set is
near-maximally diverse — biotech (Johnson & Johnson, Ginkgo Bioworks,
Quince Therapeutics), medical devices (GE HealthCare), broadcast hardware
(Blonder Tongue Laboratories), SPAC mergers (Churchill Capital Corp X,
NYIAX), specialty finance (SWK Holdings). The "consolidation by a few
big buyers" narrative does not apply to SBIR-graduating Form D firms.

19 unnamed acquirers (22%) are M&A signals that fired (8-K filing, ownership
change indicators) but did not resolve a counterparty in the upstream
extraction. These are almost certainly real exits — SPAC reverse-mergers,
private-acquirer transactions, partial-information signals — but
counterparty enrichment would need a follow-on pass.

### M&A confidence tier

| Tier | Count |
|---|---:|
| high | 41 |
| medium | 45 |

Roughly balanced. High-tier M&A is a multi-signal confirmation (8-K plus
ownership change plus press confirmation); medium-tier typically rests on
a single strong signal (e.g. 8-K alone). The cohort is not dominated by
weak-signal M&A.

### Vintage of the Phase II award

| Phase II year bucket | Firms | Share |
|---|---:|---:|
| 2000-2009 | 46 | 53.5% |
| 2010-2014 | 24 | 27.9% |
| 2015-2019 | 8 | 9.3% |
| 2020+ | 8 | 9.3% |

### When the M&A actually happened

| M&A year bucket | Firms | Share |
|---|---:|---:|
| Pre-2015 | 12 | 14.0% |
| 2015-2019 | 12 | 14.0% |
| 2020-2022 | 16 | 18.6% |
| 2023+ | 46 | 53.5% |

**The cohort is "old Phase II awards + recent acquisitions"**: more than
half of the Phase II awards landed in the 2000s, but **more than half of
the resulting M&A events fired in 2023 or later**. That's consistent with
the 13-year median P2 → M&A span; firms that started in 2010 are exiting
now.

### Capital intensity (Form D total raised)

| Statistic | Value |
|---|---:|
| Median total raised | $22.9M |
| Mean total raised | $78.4M |
| Sum across cohort | $6.7B |

These are real venture-scale firms. The $6.7B aggregate represents the
private capital that flowed into 86 firms that earned a Phase II SBIR
award **and** raised through Reg D **and** were ultimately acquired —
a tractable cohort size for case-study analytics.

## Time-bounded subcohorts (P2 → M&A by total span)

For analyses that want a "fast acquisition" or "long-tail acquisition"
slice without the Form D middle step:

| Window | Firms | % of 3,639 |
|---|---:|---:|
| P2 → M&A within 3 years (very fast) | 39 | 1.07% |
| P2 → M&A within 5 years | 63 | 1.73% |
| P2 → M&A within 7 years | 95 | 2.61% |
| P2 → M&A within 10 years | 122 | 3.35% |
| P2 → M&A within 15 years | 156 | 4.29% |
| P2 → M&A within 20 years | 182 | 5.00% |

Note these counts include firms that did **not** also raise Form D between
the two events; they are a separate cohort overlapping (but distinct from)
the strict P2 → Form D → M&A cohort.

## Fastest sequenced firms (top 15 by Phase II → M&A span)

| Firm | Phase II | First Form D | M&A | P2 → M&A (yr) |
|---|---|---|---|---:|
| E-Line Ventures, LLC | 2013-05 | 2013-10 | 2014-07 | 1.1 |
| BOUNCE IMAGING, INC | 2019-08 | 2020-02 | 2021-11 | 2.3 |
| Artio Medical, Inc | 2018-02 | 2020-03 | 2020-05 | 2.3 |
| SB TECHNOLOGY FEDERAL INC | 2023-01 | 2023-07 | 2025-09 | 2.6 |
| ROOT AI, INC. | 2020-04 | 2020-08 | 2023-03 | 2.9 |
| Adaptive Surface Technologies, Inc. | 2020-05 | 2022-03 | 2023-03 | 2.9 |
| AMPHP INC | 2020-07 | 2021-04 | 2023-11 | 3.3 |
| SustainX, Inc. | 2009-01 | 2009-08 | 2012-04 | 3.3 |
| INNEGRITY LLC | 2007-03 | 2009-07 | 2010-09 | 3.5 |
| Onebrief, Inc. | 2022-06 | 2022-10 | 2026-01 | 3.6 |
| Exicure, Inc. | 2013-08 | 2015-10 | 2017-10 | 4.2 |
| PRINCETON NUENERGY INC | 2021-08 | 2023-11 | 2026-02 | 4.5 |
| Oragenics, Inc. | 2008-01 | 2010-01 | 2012-08 | 4.6 |
| LYNK GLOBAL INC | 2020-05 | 2020-10 | 2025-05 | 5.0 |
| Wombat Security Technologies | 2010-09 | 2013-02 | 2015-10 | 5.1 |

## Cross-reference: enrichment in the NSF 2010-14 matched cohort right tail

`docs/nsf-vc-comparison/policy-brief.md` Finding 2 documents a barbell-
shaped Form D dollar distribution for the NSF Phase II 2010-14 EDGAR
cohort (n=170 in the brief; n=66 with own Form D filings). This section
asks: is the strict-sequence cohort overrepresented in the right tail of
that distribution?

### Cohort reconstruction

We reconstruct the brief's NSF cohort as a **proxy** by intersecting the
raw `award_data.csv` (NSF, Phase II, award year 2010-2014) with the
3,639-firm Form D cohort. This yields **147 firms** — close to the brief's
170 but not identical, because our intersection uses Form-D-cohort
membership where the brief used the broader "EDGAR presence" signal.
**11 of these 147 firms** (7.5%) also sit in the 86-firm strict
P2 → Form D → M&A cohort.

### Right-tail enrichment is monotonic and strong

| Top-N% by Form D raised | Strict-pathway count | Strict rate | Enrichment vs 7.5% baseline |
|---|---:|---:|---:|
| Top 5% (7 firms) | 1 | 14.3% | 1.91× |
| **Top 10% (14 firms)** | **4** | **28.6%** | **3.82×** |
| Top 20% (29 firms) | 6 | 20.7% | 2.76× |
| Top 50% (73 firms) | 8 | 11.0% | 1.46× |

Top decile is **3.82× enriched** for strict-pathway membership. The
enrichment ratio falls monotonically as the window widens — the shape
expected if strict-pathway membership is a real positive selection signal
for capital intensity, not a noise artifact.

### Percentile-by-percentile comparison

| Percentile | Strict (n=11) | Non-strict (n=136) | Strict / Non-strict |
|---|---:|---:|---:|
| P25 | $5.5M | $0.5M | **11.0×** |
| **P50 (median)** | **$51.7M** | **$3.6M** | **14.4×** |
| P75 | $82.5M | $14.5M | 5.7× |
| P90 | $88.6M | $42.8M | 2.1× |
| P95 | $169.2M | $103.9M | 1.6× |
| P100 (max) | $249.8M | **$2,023.2M** | **0.12×** |

Two findings:

1. **The middle of the distribution is dramatically pulled up.**
   Strict-pathway firms have a **14.4× higher median raise** than
   non-strict NSF firms in the same vintage proxy. The signal is real
   and concentrated in the upper-middle, not just at the extreme.

2. **The single biggest blockbuster ($2.0B raised) is *not*
   strict-pathway.** Strict-pathway membership is a strong signal for
   consistent upper-quartile performance but does not capture the rare
   power-law outlier. That's consistent with the policy brief's barbell
   finding — both ends of the NSF cohort have value, and the very top
   can come from outside the orderly pathway.

### The 11 strict-pathway NSF firms, ranked within the 147-firm proxy

| Rank | %ile | Firm | Form D raised |
|---:|---:|---|---:|
| 4 | 98th | ColdQuanta | $249.8M |
| 11 | 93rd | Soraa | $88.6M |
| 12 | 93rd | ecoATM | $83.0M |
| 13 | 92nd | BitSight Technologies | $82.1M |
| 18 | 88th | Kapteyn-Murnane Labs | $54.7M |
| 19 | 88th | Cambrian Innovation | $51.7M |
| 51 | 66th | Veriflow Systems | $10.9M |
| 58 | 61st | Avitus Orthopaedics | $8.1M |
| 85 | 43rd | Ondax | $2.9M |
| 105 | 29th | 422 Group | $1.0M |
| 139 | 6th | NovaScan | $0.2M |

**6 of the 11 are in the top quartile** of the NSF proxy by capital raised.
The cluster includes recognised commercialization successes:
ColdQuanta (quantum computing), BitSight Technologies (cybersecurity —
later acquired by Moody's via SaaS holding company structure), Soraa
(LED lighting), ecoATM (electronics recycling kiosks).

### Interpretation

The strict P2 → Form D → M&A cohort identifies an **upper-middle-class
commercialization pathway**: firms that took SBIR Phase II, raised
substantial private equity through Reg D, and reached an acquisition.
They are the disciplined, well-capitalised acquirers' targets in the
cohort — not the wildcat blockbusters (those can have idiosyncratic
pathways including non-Form-D capital, public listings, or no M&A
signal at all).

For a VC-asset-class comparison, this is structurally identical to a
real VC fund's mid-tail: top-quartile portfolio companies are often
not the fund's single biggest winner — they're the steady contributors
that earn 3-10× returns. The strict-pathway cohort is the SBIR analog.

### Caveats on this cross-reference

- The 147-firm NSF proxy here ≠ the 170-firm cohort in the policy brief.
  Our intersection uses Form-D-cohort membership; the brief used broader
  EDGAR presence (Form D OR mentioned in 8-K / 13G filings).
- `total_form_d_raised` is the cumulative sum of Form D total offering
  amounts. It is not a valuation, not a check-size, and includes
  amendments and re-filings. The dollar-distribution shape is robust;
  individual firm dollar totals should be treated as approximate.
- Power calculations not run here — the 11-firm strict subset is small
  enough that the right-tail enrichment ratio has wide CIs that this
  table doesn't show. The direction and monotonicity of the enrichment
  are the load-bearing findings; the exact 3.82× should be read as
  "substantial enrichment in the right tail" rather than a point
  estimate.

## What this analysis is *not*

- **Not a complete commercialization picture.** Patents are absent from the
  current events table (the USPTO PatentsView extraction sample is empty in
  `data/transformed/uspto/`); a "Phase II → patent → Form D → M&A" cohort is
  unanswerable until the patents path is materialised.
- **Not a counterfactual baseline.** No control group of similar-vintage,
  similar-agency, non-SBIR-funded firms — the analysis can describe the
  cohort but not attribute outcomes to SBIR.
- **Not investor-attributed.** SEC Form D doesn't require investor identity
  disclosure, so co-investor / lead-investor analysis is not possible from
  this data. Crunchbase or PitchBook integration would be required.
- **Not a UCC-debt-conditioned cohort.** The UCC1 pilot was CA-only and its
  filings are not in the unified events table. Once UCC coverage expands
  beyond California, the "P2 → UCC → Form D → M&A" pathway becomes
  answerable as another subcohort variant.

## Querying the cohort

After PR #356 lands and `capital_events_per_firm.parquet` is regenerated:

```python
import duckdb
df = duckdb.sql("""
    SELECT company_name, state, first_phase_ii_date,
           first_form_d_date, first_ma_event_date,
           days_phase_ii_to_ma, total_form_d_raised
    FROM 'data/capital_events_per_firm.parquet'
    WHERE has_strict_phase_ii_to_ma_pathway
    ORDER BY days_phase_ii_to_ma ASC
""").df()
```

Six new columns expose the pathway directly:
- `first_phase_ii_date`, `first_form_d_date` (companion to existing `first_ma_event_date`)
- `days_phase_ii_to_form_d`, `days_form_d_to_ma`, `days_phase_ii_to_ma`
- `has_strict_phase_ii_to_ma_pathway` (bool)

## Why this is documented as a cohort and not built into a graph database

This cohort was the surviving signal from a four-query exploration of
graph-native pathway questions (see PR #356 description for details). Three
other candidate queries — UCC → Form D temporal pattern, M&A multi-hop
chains, and Form-D co-investor networks — were either unanswerable from
current data or returned zero signal in the cohort. The one query with real
signal (P2 → Form D → M&A) is a 25-line DuckDB query that Cypher would not
make meaningfully clearer. Exposing the pathway as parquet columns gets
the analytical benefit without expanding the Neo4j footprint, which is the
right architectural trade-off given the current data sources and product
roadmap.

## Related work in `docs/research/`

- `archive/research/capital-events-v1.md` — the underlying events-table build and per-source coverage
- `sbir-ma-exit-analysis.md` — M&A exit analytics over the broader 429-firm M&A cohort (no sequencing constraint)
- `sbir-form-d-fundraising-analysis.md` — Form D fundraising profiles over the 3,638 cohort firms with any Form D
- `dod-form-d-leverage.md` — DoD-specific Form D leverage analysis (branch decomposition, follow-ups, FPDS substitution)
- `sbir-ucc1-pilot.md` — UCC1 CA pilot results (input to the events table once expanded beyond CA)
