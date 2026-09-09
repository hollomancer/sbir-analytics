---
Type: Research Report
Owner: research@project
Last-Reviewed: 2026-09-09
Status: draft
---

# Public private-capital baseline candidates

**Prepared for:** maintainers of `agency_private_capital` baselines
**Audience:** maintainers
**Evidence status:** Exploratory and non-citable. This note records candidate
registry rows. It does not load them, and it is not a program-performance
finding.

> **Do not copy these rows into
> `config/agency_private_capital/published_baselines.yaml` in this PR.**
> Every new `kind: rate` baseline needs a matching metric in `outcomes.py`
> plus `_ATTRIBUTION` / `_CAVEAT` text in `reconcile.py`. Dollar medians and
> year-counts do not fit the current `kind` enum (`rate`, `effect_size`,
> `framing`). Live config stays free of Yearbook organization names per
> PR #599.

## Why this is a note, not a live registry change

PR #404 already found that a CSV of Yearbook tables would duplicate the YAML
registry, and that a baseline without an SBIR-side numerator is an empty
reconcile row. PR #599 then removed the one Yearbook rate that had been
wired (`nvca_seed_to_series_a` = 0.33) because it was a 30–35% public-summary
range, not a page-cited Yearbook table. That 0.33 figure is still not in the
Yearbook PDFs.

What changed in 2026 is access, not the pairing problem:

- The Yearbook PDFs and a public supplemental data pack are on nvca.org.
  PitchBook owns the copyright and allows a few attributed data points, not
  table dumps ([citation guidelines](https://pitchbook.com/pitchbook-citation-guidelines)).
- Carta publishes the **cohort conversion** #404 wanted (share of a seed
  vintage that raises a Series A within a stated horizon), plus round-size
  and valuation medians, from cap-table records.

Neither source joins to an SBIR UEI or CIK. Firm-level capital events stay on
Form D / 8-K. Licensed firm-level Carta, PitchBook, or Crunchbase access is
still out of scope.

## YAML candidates

`cohort_metric` is the **intended** pairing. None of these metrics exist in
`outcomes.py` today (`phase_i_to_ii_graduation`,
`phase_ii_to_federal_contract_transition`, `five_year_survival_proxy`,
`ma_exit_rate`). `point_estimate` for rates is a proportion, matching BLS
`0.50`.

### Carta — fits `kind: rate` once a pairing metric exists

Source for conversion: [Carta VC Fund Performance Q4 2025](https://carta.com/data/vc-fund-performance-q4-2025-full-report/)
(Market context; data through 2025-12-31; published 2026-03-19).
Source for dilution: [State of Private Markets: 2025 in review](https://carta.com/data/state-of-private-markets-q4-2025-full-report/)
(snapshot 2026-02-01).

| id | cohort_metric (missing) | point_estimate | as_of | page / URL |
|---|---|---:|---|---|
| `carta_seed_to_a_q2_2024_6q` | `form_d_follow_on_within_horizon` | 0.206 | 2025 | Fund Performance Q4 2025, Market context. Q2 2024 seed vintage; Series A within six quarters. |
| `carta_seed_to_a_q2_2022_6q` | `form_d_follow_on_within_horizon` | 0.096 | 2025 | Same report, same horizon, Q2 2022 vintage. Kept as a second row so reconcile can show vintage sensitivity instead of overwriting. |
| `carta_dilution_seed_through_c_q4_2025` | *(none — Form D has no dilution)* | 0.16 | 2025-Q4 | SOPM 2025 in review, Deal terms. Median dilution, primary rounds, seed through Series C. |

```yaml
# Cite-only. Do not load until form_d_follow_on_within_horizon exists.
- id: carta_seed_to_a_q2_2024_6q
  cohort_metric: form_d_follow_on_within_horizon
  label: "Carta seed → Series A within six quarters, Q2 2024 vintage"
  kind: rate
  point_estimate: 0.206
  as_of: "2025"
  population: "US Carta cap-table companies that raised a seed round in Q2 2024"
  citation: "Carta (2026). VC Fund Performance Q4 2025."
  citation_url: "https://carta.com/data/vc-fund-performance-q4-2025-full-report/"
  notes: |
    Share of the Q2 2024 seed vintage that closed a Series A within the next
    six quarters. Carta series labels come from the charter share-class name.
    US headquarters only. Historical vintages can revise as new companies
    join Carta.

- id: carta_seed_to_a_q2_2022_6q
  cohort_metric: form_d_follow_on_within_horizon
  label: "Carta seed → Series A within six quarters, Q2 2022 vintage"
  kind: rate
  point_estimate: 0.096
  as_of: "2025"
  population: "US Carta cap-table companies that raised a seed round in Q2 2022"
  citation: "Carta (2026). VC Fund Performance Q4 2025."
  citation_url: "https://carta.com/data/vc-fund-performance-q4-2025-full-report/"
  notes: |
    Same estimand as carta_seed_to_a_q2_2024_6q, earlier vintage. The 9.6%
    vs 20.6% gap is why a single 0.33 constant is not a usable comparator.

- id: carta_dilution_seed_through_c_q4_2025
  cohort_metric: median_primary_round_dilution
  label: "Carta median dilution, seed through Series C, Q4 2025"
  kind: rate
  point_estimate: 0.16
  as_of: "2025-Q4"
  population: "US Carta primary equity rounds, seed through Series C, Q4 2025"
  citation: "Carta (2026). State of Private Markets: 2025 in review."
  citation_url: "https://carta.com/data/state-of-private-markets-q4-2025-full-report/"
  notes: |
    No SBIR-side dilution metric exists. Form D does not report percent sold.
    Leave unloaded until a pairing is designed, if ever.
```

### Carta — does not fit `kind: rate`

These are levels, not proportions. Loading them today would require a new
`kind` (for example `level`) or stuffing the number into `effect_description`.
Do not overload `rate`.

| id | intended metric (missing) | reported figure | as_of | page / URL |
|---|---|---|---|---|
| `carta_median_seed_round_q4_2025` | `median_form_d_offering_size` | $4.5M median seed deal | 2025-Q4 | [SOPM 2025 in review](https://carta.com/data/state-of-private-markets-q4-2025-full-report/), Deal terms |
| `carta_median_series_a_round_q4_2025` | `median_form_d_offering_size` | $13.5M median Series A deal | 2025-Q4 | Same |
| `carta_median_seed_post_money_q4_2025` | *(none — Form D has no post-money)* | $24M median seed post-money | 2025-Q4 | Same, Valuations |
| `carta_median_series_a_post_money_q4_2025` | *(none)* | $78.7M median Series A post-money | 2025-Q4 | Same, Valuations |
| `carta_seed_to_a_interval_2025` | `median_years_between_form_d_rounds` | 2.1 years median seed → A | 2025 | Same, Deal terms (annual). Q4 2025 in the Fund Performance report is 1.9 years; use the annual figure if only one row is kept. |

Carta round-benchmarking CSV
([tool](https://carta.com/data/explore/round-benchmarking/)) covers ~20,000 US
primary equity rounds from January 2021, excluding bridges and convertibles.
Do not vendor that CSV. Cite published medians.

### Yearbook — cite-only industry totals, not live YAML

Source: [NVCA 2026 Yearbook](https://nvca.org/wp-content/uploads/2026/04/NVCA-2026-Yearbook-4.9.26.pdf)
(data provided by PitchBook; as of 2025-12-31) and
[NVCA 2025 Yearbook](https://nvca.org/wp-content/uploads/2025/03/2025-NVCA-Yearbook.pdf)
(data year 2024). PitchBook copyright; a few attributed data points only.
These rows reverse PR #599 if copied into live config. They also have no
matching `outcomes.py` metric.

| id | intended metric (missing) | reported figure | as_of | page / URL |
|---|---|---|---|---|
| `pb_median_seed_deal_2025` | `median_form_d_offering_size` | $16.0M median seed deal value | 2025 | 2026 Yearbook p. 29 |
| `pb_median_series_a_deal_2025` | `median_form_d_offering_size` | $49.0M median Series A deal value | 2025 | 2026 Yearbook p. 29 |
| `pb_median_years_first_vc_to_ipo_2025` | `median_years_first_award_to_ma` | 7.85 years median first VC → IPO | 2025 | 2026 Yearbook p. 33 |
| `pb_vc_backed_ipo_count_2025` | *(none — a count, not a cohort rate)* | 49 VC-backed IPOs | 2025 | 2026 Yearbook p. 34 |
| `pb_median_years_first_vc_to_ipo_2024` | `median_years_first_award_to_ma` | 5.71 years median first VC → IPO | 2024 | 2025 Yearbook p. 24 |

The seed deal-value gap (Carta Q4 2025 $4.5M vs Yearbook 2025 $16.0M) is a
definition gap, not a transcription error. Carta is priced cap-table rounds on
Carta customers. PitchBook seed includes large preemptive rounds; the 2026
Yearbook notes that some seed/pre-seed deals exceeded $100 million.

## Pairing work still required

| Candidate family | `outcomes.py` gap | Notes |
|---|---|---|
| Carta seed → A conversion | `form_d_follow_on_within_horizon` | Closest SBIR analogue is a later, larger Form D after an earlier one, in a seed-size bucket, with an explicit horizon. That is not Phase I → II. NSF 2015–2019 Phase I → II is 44.7% at five years; Carta seed → A is 9.6–20.6% at ~18 months. Do not pair them. |
| Carta / Yearbook round size | `median_form_d_offering_size` | Form D offering amount is the current field. Stratify by size bucket, not by Series A/B labels Form D does not carry. |
| Yearbook time-to-IPO | `median_years_first_award_to_ma` | `ma_exit_rate` exists; a median duration does not. IPO is not in the 8-K M&A file. |
| Carta dilution and post-money | none | Form D does not report either. Leave as context, not a reconcile pair. |

Suggested `_ATTRIBUTION` if the conversion rows ever load:

> SBIR follow-on Form D is gated on a later disclosed Reg D filing. Carta
> seed → Series A is gated on a priced preferred round among cap-table
> customers. Horizons, populations, and selection filters differ; magnitudes
> are descriptive, not causal.

## What not to do

- Do not restore `nvca_seed_to_series_a` / 0.33. It is not a Yearbook table.
- Do not add `data/reference/` CSV packs or scrape the Carta benchmarking tool
  into pipeline inputs.
- Do not treat Carta or Yearbook figures as citable SBIR program performance.
- Do not design a licensed `PITCHBOOK` / Carta API directory until a
  subscription exists.
