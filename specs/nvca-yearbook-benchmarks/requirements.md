# Requirements — NVCA Yearbook Benchmark Reference Data

> **Status:** **Partially implemented; spec was mis-framed on first pass.** A
> 2026-06-29 audit (paralleling #400 and #402) found that
> `agency_private_capital/baselines.py` already provides a fully-functional
> `PublishedBaseline` + `PublishedBaselineRegistry` registry that loads from
> `config/agency_private_capital/published_baselines.yaml`. **One NVCA Yearbook
> entry is already wired in** (`nvca_seed_to_series_a`, 0.33 graduation rate
> paired with the `phase_i_to_ii_graduation` SBIR cohort metric). `reconcile.py`
> consumes the registry and emits paired SBIR-vs-baseline reconciliation rows.
>
> The audit also found the original spec was *mis-anchored against F3*. The
> canonical F3 question in [docs/research-questions.md](../../docs/research-questions.md):289
> is the **private-to-SBIR leverage ratio** (private capital raised ÷ SBIR
> funding) mirroring NASEM's 4:1 DoD figure [L1] — not the
> median-deal-size / exit-count figures the original spec listed. NVCA Yearbook
> data feeds the F2 cohort-outcome comparison; the F3 anchor metric is
> a leverage-ratio computation.
>
> This rewrite reframes the work scope honestly, defers source-access-dependent
> data acquisition to a clearly-marked follow-up, and corrects the F2/F3
> anchoring.

**Research question anchor:** F2 — SBIR-firm capital structure vs. NVCA Yearbook cohort outcome metrics; F3 — private-to-SBIR leverage ratio with NASEM 4:1 DoD figure as the canonical published comparator
**Answers for:** entrepreneurial finance researchers, NVCA / Kauffman-style investment researchers
**Complexity tier:** Data acquisition + paired cohort-metric implementation

---

## Done when

> An entrepreneurial finance researcher can state: "The
> `published_baselines.yaml` registry contains NVCA Yearbook public-summary
> figures paired with implemented SBIR cohort metrics in
> `outcomes.py` — every baseline is reportable via `reconcile.py` against a
> real SBIR-side numerator. The F3 private-to-SBIR leverage ratio is
> computed and compared against NASEM 4:1 [L1]."

---

## Current state (what's already shipped)

`packages/sbir-analytics/sbir_analytics/assets/agency_private_capital/` has:

- **`baselines.py`** — `PublishedBaseline` dataclass with all needed fields
  (id, cohort_metric, label, kind ∈ {rate, effect_size, framing},
  point_estimate, as_of, population, citation, citation_url, notes,
  effect_description). `PublishedBaselineRegistry.load(yaml_path)` reads from
  YAML. Frozen dataclasses; tested.
- **`published_baselines.yaml`** — 5 entries today: `nvca_seed_to_series_a`,
  `bls_bed_5yr_survival`, `lerner_growth_effect`, `howell_followon_vc`,
  `itif_seed_fund_framing`. All paired against the **four** cohort metrics
  `outcomes.py` produces today: `phase_i_to_ii_graduation`,
  `phase_ii_to_federal_contract_transition`, `five_year_survival_proxy`,
  `ma_exit_rate`.
- **`reconcile.py`** — iterates the registry, joins to outcomes on
  `cohort_metric == metric`, emits one row per (metric, baseline) pair with a
  curated `_ATTRIBUTION` narrative explaining the cohort-vs-baseline
  divergence.

The infrastructure works. The gap is **which** additional baselines + paired
SBIR-side cohort metrics are worth adding.

---

## What's wrong with the original spec

The original spec asked for `data/reference/nvca/nvca_yearbook_benchmarks.csv`
populated with median deal size, exit counts, M&A/IPO rates 2009–present.
Three problems:

1. **CSV duplicates the YAML pattern.** Existing baselines are YAML with
   multi-line `notes:`, structured citations, and string-typed kind enums —
   YAML is the right format for hand-curated baseline metadata. CSV would
   require restructuring or duplicating storage.

2. **Each new baseline needs a paired SBIR-side cohort metric in
   `outcomes.py`.** When a baseline's `cohort_metric` has no matching rows
   in outcomes, `reconcile.py` emits an "empty" record (`cohort_available=False`,
   numeric fields `None`) rather than skipping the pair — useful for surfacing
   gaps but the comparison row carries no SBIR-side numerator. Adding
   "median seed deal size" as a baseline produces only empty rows until
   `median_form_d_round_size_phase_ii` (or similar) is implemented in
   `outcomes.py`. Original spec didn't acknowledge the paired-work
   requirement.

3. **F3 anchor is mis-stated.** F3's canonical metric per
   `docs/research-questions.md:289` is the private-to-SBIR leverage ratio,
   not deal sizes. NVCA Yearbook data feeds F2's cohort-outcome comparison,
   not F3's leverage-ratio question. Original spec conflated the two.

---

## User Stories

**As an entrepreneurial finance researcher,** I want each NVCA Yearbook
baseline in `published_baselines.yaml` to be paired with a real SBIR-side
cohort metric in `outcomes.py`, so the reconciliation report never produces
empty rows — every comparison is a genuine cohort-vs-baseline number.

**As a policy analyst citing F3 private-to-SBIR leverage,** I want the
NASEM 4:1 DoD figure [L1] in the baseline registry paired with a computed
`private_to_sbir_leverage_ratio` metric, so the report has the right F3
anchor — not a deal-size analogue that the public reader won't recognize.

---

## Requirements

### Requirement 1 — NVCA Yearbook public-figure expansion (**source-access-dependent**)

> **Implementation gate:** This requirement is blocked on someone with NVCA
> Yearbook PDF access transcribing verified figures. Do not add YAML entries
> with unverified numbers — the existing 5 baselines all carry primary-source
> citations (`citation_url`); new entries must too.

#### Acceptance Criteria

1. THE System SHALL append additional `kind: rate` NVCA Yearbook entries to
   `config/agency_private_capital/published_baselines.yaml`, each with
   `as_of`, `population`, `citation` (e.g. "NVCA (2024). NVCA Yearbook 2024,
   p. NN"), and `citation_url`.
2. EACH new NVCA entry SHALL be paired with a `cohort_metric` value that is
   **already implemented** in `outcomes.py`, or paired with a new metric
   added under Requirement 2.
3. The existing entry `nvca_seed_to_series_a` SHALL stay; if a more recent
   NVCA Yearbook edition is cited, add a new entry with the newer
   `as_of` rather than overwriting (lets `reconcile.py` show the temporal
   robustness of the comparison).

### Requirement 2 — Paired SBIR-side cohort metrics

#### Acceptance Criteria

1. EACH new baseline added under Requirement 1 SHALL be paired with a
   matching `outcomes.py` cohort metric — either an existing one
   (`phase_i_to_ii_graduation`, `phase_ii_to_federal_contract_transition`,
   `five_year_survival_proxy`, `ma_exit_rate`) or a newly added metric that
   `agency_private_capital_outcomes` emits.
2. WHEN adding a new cohort metric, THE System SHALL also add a
   corresponding `_ATTRIBUTION` entry in `reconcile.py` explaining the
   plausible-cause framing for the SBIR-vs-baseline divergence, matching
   the existing five attribution narratives.
3. THE registry-loading and `reconcile.py` tests SHALL stay green; new tests
   SHALL cover any newly added cohort metric.

### Requirement 3 — F3 leverage-ratio baseline (NASEM 4:1)

#### Acceptance Criteria

1. THE System SHALL add a `nasem_dod_leverage_ratio` baseline entry to
   `published_baselines.yaml` paired with a new cohort metric
   `private_to_sbir_leverage_ratio` (NASEM 4:1 DoD figure per [L1]).
2. THE System SHALL implement `private_to_sbir_leverage_ratio` in
   `outcomes.py` per Requirement 2, drawing on the existing
   Form-D-pipeline data (private capital raised) ÷ SBIR funding amounts
   (already in cohort). Stratified by agency, vintage bucket, and firm
   size per the F3 anchor language.

---

## Out of scope / deferred

- **Original spec's CSV at `data/reference/nvca/nvca_yearbook_benchmarks.csv`.**
  Existing YAML registry is the canonical storage; introducing a competing
  CSV pattern fragments the comparison surface. If a future use case
  genuinely requires a flat CSV export, write it as a *derived view* of the
  YAML registry, not as the source of truth.
- **Original spec's `licensed/` directory + PITCHBOOK schema.** Punt until a
  PITCHBOOK subscription is actually acquired and the integration is
  prioritized. Designing the directory layout in advance is speculative.
- **`comparison_precision` metadata flag.** The current `kind` enum
  ({rate, effect_size, framing}) already encodes baseline precision;
  adding another flag is duplicate information.
- **Per-agency `agency_private_capital_baseline_comparison` stratification.**
  Already supported by `agency_parametrized` shape of the asset; not the
  data-acquisition layer's responsibility.

---

## Notes on this rewrite

The audit-then-rewrite pattern (cf. #400, #402) produced a small,
verifiable-fix PR in both prior cases. For #404, the genuine gap is
*data acquisition + paired metric implementation*, both of which require
verifiable source figures and substantial code work — neither of which fits
in a single audit-rewrite PR. This rewrite ships the **corrected spec
alone**; implementation lands in a follow-up that has NVCA Yearbook source
access and can implement the paired `outcomes.py` metrics.
