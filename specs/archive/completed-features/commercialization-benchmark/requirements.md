# Requirements — §638(qq)(3) Commercialization Benchmark

> **Status:** Implemented on `main`. CLI: `scripts/run_benchmark.py`. Models:
> `sbir_etl/models/benchmark_models.py`. Evaluator:
> `packages/sbir-ml/sbir_ml/transition/analysis/benchmark_evaluator.py`.
> Tests: `tests/unit/test_benchmark_evaluator.py`.
> Supports inventory question **B3** in [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** B3 — which Phase II awardees subject to §638(qq)(3)
Increased Performance Standards meet the statutory Commercialization Benchmark?
**Answers for:** SBA program oversight analysts, GAO compliance reviewers, policy analysts
**Complexity tier:** Inferential (Tier 3)

---

## Done when

> An SBA program oversight analyst can run `poetry run benchmark evaluate` against a
> cohort of Phase II awardees subject to §638(qq)(3) and receive per-firm compliance
> status (`MEETS` / `DOES_NOT_MEET` / `INSUFFICIENT_DATA`) with the underlying
> components (FPDS contract dollars, SEC Form D investment, FABS grant dollars) shown
> separately, and aggregate pass/fail rates by agency and cohort FY.

---

## Introduction

Pub. L. 117-183 (SBIR/STTR Extension Act of 2022) §638(qq)(3) established Increased
Performance Standards for firms receiving multiple Phase II awards. This feature
evaluates whether subject firms meet the statutory Commercialization Benchmark:
(sales + private investment over the 10-FY covered period) ÷ SBIR funding ≥ the
specified statutory ratio. The pipeline draws on three data sources — FPDS federal
contract obligations, SEC Form D private placements, and FABS grant records — to
construct per-firm numerator components, then applies the statutory formula.

---

## User Stories

**As an SBA program officer,** I want per-firm §638(qq)(3) compliance status computed
from FPDS, Form D, and FABS data, so that I can identify which firms meet the statutory
Commercialization Benchmark before applying increased performance standards.

**As a GAO analyst reviewing SBIR program effectiveness,** I want aggregate pass/fail
rates by agency and cohort year, so that I can report on program-wide commercialization
outcomes under the SBIR/STTR Extension Act of 2022.

**As a policy analyst benchmarking against GAO-24-106398,** I want the pipeline's
coverage rate (share of subject firms with sufficient data to evaluate) stated alongside
the compliance rate, so that figures cited in congressional reports carry an explicit
denominator-coverage qualifier.

---

## Requirements

### Requirement 1 — Per-firm benchmark evaluation

**User Story:** As an SBA program officer, I want per-firm compliance status
for each Phase II awardee in the subject cohort, so that I can identify
firms approaching or below the statutory threshold.

#### Acceptance Criteria

1. THE System SHALL evaluate each subject firm using the statutory formula:
   (FPDS contract obligations + Form D investment + FABS grants over the
   10-FY covered period) ÷ total Phase II SBIR funding received.
2. THE System SHALL classify each firm as `MEETS`, `DOES_NOT_MEET`, or
   `INSUFFICIENT_DATA` based on the computed ratio and data availability.
3. THE System SHALL expose the three component values (contract dollars, Form D
   dollars, FABS dollars) separately in the output so analysts can attribute
   benchmark performance to specific data channels.
4. WHEN a firm lacks sufficient data to evaluate (e.g., no FPDS match and no
   Form D filing), THE System SHALL classify it `INSUFFICIENT_DATA` and
   record which component is missing.

### Requirement 2 — Aggregate reporting by agency and cohort

**User Story:** As a GAO analyst, I want aggregate compliance rates by
awarding agency and first-Phase-II fiscal year, so that agency-level
program effectiveness can be compared against the statutory intent.

#### Acceptance Criteria

1. THE System SHALL produce a summary table of `MEETS` / `DOES_NOT_MEET` /
   `INSUFFICIENT_DATA` counts and percentages by awarding agency.
2. THE System SHALL produce a cohort-by-year breakdown using the firm's first
   Phase II award fiscal year as the cohort anchor.
3. WHEN any cell contains fewer than 10 firms, THE System SHALL suppress the
   rate and note the suppression reason.

### Requirement 3 — CLI interface

**User Story:** As a pipeline engineer, I want a CLI command for running the
benchmark evaluation so that it can be integrated into CI pipelines and
called from Dagster jobs.

#### Acceptance Criteria

1. THE System SHALL expose `poetry run benchmark evaluate [--agency <name>]
   [--cohort-fy <year>] [--output <path>]` as the primary evaluation interface.
2. THE System SHALL expose `poetry run benchmark sensitivity` to compute
   compliance rates under alternative statutory ratio assumptions.
3. THE System SHALL expose `poetry run benchmark company <firm_id>` for
   per-firm audit output with full component breakdown.
