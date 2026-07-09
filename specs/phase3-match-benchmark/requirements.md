# Phase III Match-Quality Benchmark — Requirements

> **Status:** Spec / design. Small-sample result delivered ([findings.md](./findings.md)); full
> A0 census + agency/kind stratification outstanding.
> Supports inventory questions **B3** (Phase III undercount / transition detection) and **A2** (DIB
> integration via FPDS) in [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** B3 — can semantic similarity distinguish true Phase III derivative
pairs from plausible non-derivative pairs given real FPDS text quality? (Gates Product 2.)
**Answers for:** SBIR program managers, OII / oversight staff, pipeline engineers
**Complexity tier:** Relational → Inferential (Tier 2–3)

## Done when

> An analyst can state: "Text-similarity scoring of Phase II abstracts against FPDS descriptions
> separates true derivative pairs from hard negatives with AUC = [X] in the well-described stratum
> and [Y] overall; Product 2 is therefore [viable gated on description length / not viable], and
> its performance is an upper bound because positives are agency-coded."

## Background

Product 2 (bypass leads) rests on an untested premise: that text similarity between Phase II
abstracts and FPDS/USAspending contract descriptions can distinguish derivative from
non-derivative pairs. No labeled corpus exists, and no ground-truth *violation* corpus can exist
from public data. The only trainable labels are agency-certified derivative pairs (10Q-coded
Phase III) and, later, human adjudication of leads. This benchmark builds the labeled sample and
measures separability before any Product 2 build.

## Requirements

### Requirement 1 — Description-quality census (A0)
**User story:** As a pipeline engineer, I want the distribution of FPDS description quality by
agency and award kind, so that Product 2 blocking excludes strata where text scoring is hopeless.
#### Acceptance Criteria
1. WHEN the candidate FPDS population is assembled, THE System SHALL emit
   `data/derived/fpds_description_census.parquet` with per-agency, per-award-kind length
   distributions, boilerplate/near-duplicate rate, and IDV-text-inheritance share.
2. IF the median usable-text profile is hopeless for major strata, THE System SHALL report and
   stop before labeling (go/no-go gate).

### Requirement 2 — Labeled pair sample (A1, trimmed to 3 strata)
**User story:** As a program manager, I want a reproducible labeled pair sample, so that match
quality is auditable.
#### Acceptance Criteria
1. THE System SHALL construct **P1** (same-firm, 10Q-coded Phase III × prior Phase II abstract),
   **N1** (different-firm same-office/adjacent-NAICS hard negatives), and **N3** (same-topic
   sibling) pairs, ~200/class, with full provenance (source, retrieval date, pairing rule).
2. P1 positives SHALL be labeled from the **structured 10Q code, never description keywords**
   (no label leakage).
3. N1 non-lineage SHALL be confirmed *after* `resolve_entities` — an acquirer of the Phase II
   firm is NOT a negative.
4. THE System SHALL emit `data/derived/phase3_match_benchmark_pairs.parquet`.

### Requirement 3 — Separability harness (A2, trimmed)
**User story:** As an analyst, I want baseline-vs-embedding separability per stratum, so that the
Product 2 go/no-go is evidence-based.
#### Acceptance Criteria
1. THE System SHALL score P1-vs-N1 with a lexical baseline (Jaccard/BM25) **and** ModernBERT-Embed
   cosine, reporting ROC-AUC + bootstrap CI overall and by description-length quartile and agency.
2. THE System SHALL report N3 sibling discrimination.
3. THE System SHALL let the cheaper baseline win where it wins.

### Requirement 4 — Decision report (A3)
**User story:** As OII/oversight staff, I want an explicit viability call with the ceiling caveat.
#### Acceptance Criteria
1. THE report SHALL answer the four A3 questions, state the ceiling caveat verbatim, and recommend
   descoping Product 2 to string-evidence-only if thresholds miss.

## Dependencies
- `ModernBertClient` (`packages/sbir-ml/.../modernbert_client.py`) — EXISTS
- `resolve_entities` (`packages/sbir-analytics/.../phase0/resolve_entities.py`) — EXISTS
- FPDS ATOM 10Q feed — EXISTS (reachable; `q=RESEARCH:SR3`)
- Full candidate contract population (M0a) — NOT STARTED (needed for A0 + realistic N1)

## Out of scope
- No violation classifier, no model training on violations, no adjudication logic.
- Strata P2/N2 and P3 recall@50 cut from the go/no-go gate (deferred to post-go tuning).
