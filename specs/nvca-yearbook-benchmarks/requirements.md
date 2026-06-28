# Requirements — NVCA Yearbook Benchmark Reference Data

> **Status:** Not yet started. The `agency_private_capital_baseline_comparison` Dagster
> asset (PR #321, group `agency_private_capital`) currently uses internal baselines.
> NVCA Yearbook figures are needed for the publishable comparison in
> `specs/acquirer-concentration/` (Requirement 3) and the F3 NVCA-baseline comparison.
> Anchors inventory questions **F2** and **F3** in
> [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** F2 — how does SBIR-firm capital structure benchmark against the NVCA Yearbook cohort? F3 — do follow-on funding and exit outcomes match published private-capital-backed-startup baselines?
**Answers for:** entrepreneurial finance researchers, NVCA / Kauffman-style investment researchers
**Complexity tier:** Foundational data acquisition

---

## Done when

> An entrepreneurial finance researcher can state: "NVCA Yearbook benchmark figures
> for seed and early-stage companies (median deal size, round type distribution,
> fill rate, exit rate, M&A rate) are available in
> `data/reference/nvca/nvca_yearbook_benchmarks.csv` for years 2009–2024, with
> source citations. The `agency_private_capital_baseline_comparison` asset uses these
> as the non-SBIR comparison cohort."

---

## Introduction

The F3 research questions require benchmarking SBIR-firm capital raises (via Form D)
against what comparable private-capital-backed startups raise. The NVCA Yearbook [L25]
is the industry-standard source for VC fundraising, deployment, deal stage and size,
and exit activity. It is published annually by the National Venture Capital Association
and PITCHBOOK.

NVCA publishes selected summary statistics publicly (press releases, annual report
highlights); detailed deal-level data requires an NVCA/PITCHBOOK subscription. This
spec covers both paths: (a) manual transcription of public summary figures sufficient
for headline comparisons, and (b) a structured placeholder for licensed data if the
detailed cohort comparison is needed.

**Caveat:** The SBIR Form D cohort includes all Reg D offerings (angel, seed,
institutional non-VC, debt, convertible). The NVCA Yearbook measures VC deals only.
The comparison must carry an explicit "different instruments" qualifier — consistent
with the caveat in `specs/acquirer-concentration/` Requirement 3.

---

## User Stories

**As an entrepreneurial finance researcher,** I want NVCA Yearbook benchmark figures
in a machine-readable reference file, so that the `agency_private_capital_baseline_comparison`
asset can produce a side-by-side table without manual spreadsheet lookup each time
a report is generated.

**As a policy analyst citing SBIR vs. VC outcomes in a congressional briefing,** I
want the NVCA source year and page number attached to each benchmark figure, so that
the comparison is auditable and a staff researcher can verify the figures independently.

---

## Requirements

### Requirement 1 — Public summary figure transcription

#### Acceptance Criteria

1. THE System SHALL populate `data/reference/nvca/nvca_yearbook_benchmarks.csv`
   with the following figures from publicly available NVCA Yearbook editions for
   years 2009–present:
   - Median seed deal size ($M)
   - Median early-stage deal size ($M)
   - Share of deals by stage (seed / early / late / growth)
   - National M&A exit count and median exit valuation
   - National IPO exit count and median offering size
2. EACH row SHALL include: `year`, `metric_name`, `value`, `unit`, `stage`,
   `source_edition`, `source_page_or_url`, `access_date`.
3. THE System SHALL include a `data/reference/nvca/README.md` documenting the
   transcription process, the difference between public summary figures vs.
   PITCHBOOK licensed data, and the instrument-type caveat (Form D ≠ VC-only).

### Requirement 2 — Licensed data placeholder

#### Acceptance Criteria

1. THE System SHALL define a `data/reference/nvca/licensed/` directory structure
   and a schema specification (`licensed_schema.md`) for PITCHBOOK-exported deal
   data, so that licensed data can be dropped in and immediately consumed by the
   comparison asset without code changes.
2. THE `agency_private_capital_baseline_comparison` asset SHALL detect whether the
   licensed directory is populated and upgrade its comparison from summary-figure
   to deal-level if so, logging which mode is active.
3. WHEN only public summary figures are available, THE asset SHALL emit a
   `comparison_precision = "summary_figures"` metadata flag on its output to
   signal that the comparison is approximate.

### Requirement 3 — Integration with comparison asset

#### Acceptance Criteria

1. THE `agency_private_capital_baseline_comparison` asset (group `agency_private_capital`)
   SHALL be updated to load NVCA benchmark figures from
   `data/reference/nvca/nvca_yearbook_benchmarks.csv` rather than any hardcoded
   internal baseline.
2. THE asset SHALL produce a side-by-side table: SBIR-firm Form D metrics (from
   `specs/form-d-pipeline/`) vs. NVCA Yearbook metrics for the matched year range,
   with the instrument-type caveat prominently noted.
3. THE asset SHALL stratify the SBIR side by funding agency (HHS / DoD / NSF / DOE)
   since capital structure differs materially across these populations.
