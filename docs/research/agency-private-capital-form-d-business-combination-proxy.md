---
Type: Research Report
Owner: research@project
Last-Reviewed: 2026-08-09
Status: draft
---

# Symmetric Form D business-combination filing proxy audit

> **Exploratory and non-citable.** This is a source-adapter and coverage audit,
> not a treated-versus-control comparison. The metric is a filing proxy, not a
> verified acquisition, merger, or exit outcome.

## Materialization result

The maintained producer verified complete proxy-event ascertainment within the
emitted exact-CIK Form D issuer universe for 2009Q1–2024Q4: 673,656 live D or
D/A filings across 311,809 exact issuer CIKs. It emitted 14,408 filings for
which the official `ISBUSINESSCOMBINATIONTRANS` field is true, representing
10,224 CIKs. Of those filings, 1,535 are amendments. Flagged filing dates run
from 2009-01-09 through 2024-12-31, and every one of the 64 source quarters
contains flagged evidence.

The upstream audit reconciled all 673,679 selected filings into 14,408 true and
659,271 false source flags, with no invalid flag values and no omitted true
flags. Twenty-three false-flag filings were excluded because their blank issuer
names could not satisfy the identity contract. They receive no coverage row and
therefore cannot be interpreted as observed zero outcomes.

| Source-adapter audit measure | Value |
| --- | ---: |
| SEC quarters verified | 64 / 64 |
| Selected source filings reconciled | 673,679 |
| Selected true / false flags | 14,408 / 659,271 |
| Emitted exact-CIK filing rows verified | 673,656 |
| Omitted true / false flags | 0 / 23 |
| Exact Form D CIKs with coverage rows | 311,809 |
| Flagged filing-evidence rows | 14,408 |
| CIKs with at least one flagged filing | 10,224 |
| CIKs without a flagged filing in the source window | 301,585 |
| Flagged D/A amendment rows | 1,535 |
| Source-wide CIK share ever flagged | 3.28% |

The 3.28% figure is only a full-window source diagnostic. It mixes issuers,
industries, and exposure durations and is not an SBIR rate, control rate, exit
rate, or causal estimate.

## What the field measures

The [official Form D](https://www.sec.gov/files/Form_D.pdf) asks whether the
offering is being made in connection with a business-combination transaction,
with examples including a merger, acquisition, or exchange offer. The
[SEC DERA quarterly data sets](https://www.sec.gov/data-research/sec-markets-data/form-d-data-sets)
carry that filer-supplied field in the offering table.

Accordingly, the exact metric name is
`form_d_business_combination_filing_proxy`. Its event date is the SEC filing
date. That date is observable and traceable, but it is not necessarily the
announcement, signing, or closing date of a transaction. A checked Form D can
indicate financing associated with a transaction without proving that a legal
business combination occurred or that the issuer exited. Each evidence row
therefore retains the accession number, filing date, source quarter, D/D-A
status, prior accession when present, source snapshot, and
`evidence_kind="proxy"`.

This proxy is not a verified acquisition, merger, or exit outcome and must not
be labeled as a verified acquisition or M&A exit.

## Symmetric outcome contract

The shared evaluator applies one rule to treated and control firms:

```text
index_date <= Form D filing date <= index_date + 5 calendar years
```

Both endpoints are inclusive, and a February 29 anchor clamps to February 28 in
a non-leap horizon year. Multiple original and amended filings remain available
as evidence but count once for binary firm presence.

An observed zero is valid only when the firm has an exact `form_d_cik:<CIK>`
identity and the full five-year window lies within the verified source interval.
Missing or invalid CIKs, missing or ambiguous coverage, incomplete source
snapshots, and insufficient follow-up are unavailable and excluded from the
rate denominator. Even an early observed event does not make a right-censored
five-year row denominator-eligible. Arm-label swapping leaves firm results
unchanged.

The existing matched asset no longer consumes the SBIR-only
`data/sbir_ma_events.jsonl` artifact. Until the eligible matched risk set and
these symmetric event/coverage records are supplied together, the proxy remains
unavailable rather than becoming a control-side zero.

## Products and provenance

The full [tracked materialization manifest](agency-private-capital-form-d-business-combination-proxy.manifest.json)
pins the producer commit, audited input manifest and universe, source interval,
quarter-level filing and event counts, output hashes, and uniqueness/coverage
invariants.

| Product | Rows | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| Filing evidence | 14,408 | 8,356,489 | `8ad27fa2cc319971853f6aaed8b637c7267ca4803901fa62b3b30799da5086fb` |
| Exact-CIK coverage | 311,809 | 125,345,249 | `1a8b017959109e8c14ce8469fd93b6ef3df5751b93678a4b092b8af7562c510b` |

The producer verified the 725,072,925-byte issuer universe against SHA-256
`28bb167e0281bca00652444600b6635c4c0b60b0103817715df34a98f67e3fe5`.
It also verified the 247,889-byte source manifest against SHA-256
`1777119114c4f7385dd09d6b60c603f2c5c59db765311255440513190d94b331`.
All 673,656 accessions and all emitted event IDs are unique, and filing and
event counts reconcile in every source quarter. A second full streaming build
produced byte-identical event, coverage, and manifest hashes. Products use
content-addressed filenames and the manifest pointer is published last. The
large JSONL products remain gitignored; the complete manifest is tracked.

Reproduce after materializing the audited issuer universe from the preceding
control-identity build:

```bash
uv run python scripts/data/build_form_d_business_combination_events.py \
  --code-version fc691b397f851fc77ce17e25243014292c5bc805
```

## Gate decision

This run closes the first symmetric source-adapter and date/coverage-contract
prerequisite in Phase 2 task 2.4. It does **not** close task 2.4 or authorize the
matched report. The remaining gates are a higher-recall SBIR identity exclusion,
validated matching covariates and exact cohort index dates, symmetric FPDS and
patent adapters, and a separately verified M&A source if an M&A-exit metric is
to be reported.
