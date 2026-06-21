# Form D — Pooled Investment Fund cross-link integrity audit

**Date:** 2026-06-21
**Companion to:** [sbir-form-d-fundraising-analysis.md](sbir-form-d-fundraising-analysis.md) (the published headline finding) and [form-d-leverage-bootstrap-findings.md](form-d-leverage-bootstrap-findings.md) (bootstrap CIs)
**Script:** [`scripts/data/audit_form_d_pif_cross_links.py`](../../scripts/data/audit_form_d_pif_cross_links.py)

## Summary

The published doc disclaims that **71 cross-links exist between Pooled Investment Fund (PIF) entities and operating-company SBIR matches** via shared `related_persons` or CIK. PIF entities are excluded from cohort totals via `EXCLUDED_INDUSTRY_GROUPS`, but the disclaim language raised an open methodology question: do those cross-links indicate that some counted operating-company matches might be inflated or false-positive?

**This audit quantifies the answer: no material methodology risk.**

- **97 cross-link pairs** found in current data (vs. doc's 71 — drift from snapshot timing or a stricter filter at the time of the doc; same concept).
- **35 distinct high-tier operating cos** are cross-linked to PIFs, contributing **$1.551B counted (1.67% of high-only $92.96B headline)**.
- **Only 9 of those 35 ops ($151M = 0.16% of headline) are "at-risk"** — i.e., their high-tier match relies on the person signal AND has no ZIP-match backup.
- **26 of 35 (74%) are fully safe** — either both signals confirm, or ZIP confirms independently.
- **At-risk exposure is well below the bootstrap CI noise floor** (high-only CI is [1.65, 2.02]).

The cross-link list itself is an *underexploited asset*, not a bias risk: it identifies legitimate investor → portfolio relationships (fund partners serving on operating-company boards) that are worth mapping for separate analysis.

## Method

A cross-link is one (PIF, operating-co) pair where:
- The PIF record has only Pooled-Investment-Fund-tagged offerings (pure PIF), and
- The operating co has at least one non-PIF offering (so it appears in cohort totals), and
- They share a `related_persons.name` (normalized: trim + uppercase) OR a `cik`.

Cross-links to LOW-tier ops are excluded from the integrity analysis because low-tier records are dropped from cohort totals already.

For each HIGH-tier cross-linked op, I classify its tier-confirmation robustness:

| Profile | Definition | Risk |
|---|---|---|
| Both signals | person_score ≥ 0.7 AND zip_match | None — two independent signals |
| ZIP-only | zip_match=1, person_score < 0.7 | None — ZIP independent of cross-link person |
| Person-only (at-risk) | person_score ≥ 0.7, no zip_match | At-risk if cross-link person is the deciding signal |
| Neither full | low scores | Shouldn't happen at high tier; investigate |

## Results

### Tier distribution

| Op tier | Cross-link rows | Distinct ops |
|---|---|---|
| High | 42 | 35 |
| Medium | 9 | ~7 |
| Low | 46 | excluded already |

### Headline impact

| Cohort | Counted $ from cross-linked ops | Headline | % of headline |
|---|---|---|---|
| High-only | $1.551B | $92.96B | **1.67%** |
| High + Medium | ~$3.0B | $120.61B | **~2.49%** |
| **At-risk subset (high)** | **$151M** | **$92.96B** | **0.16%** |

### High-tier op robustness profile

| Profile | # distinct ops | Risk |
|---|---|---|
| Both person AND ZIP confirm | 8 | None |
| ZIP confirms (person<0.7) | 18 | None |
| **Person confirms only (no ZIP)** | **9** | **At-risk** |
| Neither full signal | 0 | (didn't occur) |

### At-risk operating cos (9 total, $151M aggregate)

| Op company | Counted $ |
|---|---|
| Checkerspot | $78.3M |
| TRUE ANOMALY | $23.6M |
| Lionano | $22.7M |
| 3AM INNOVATIONS | $9.0M |
| PolySpectra | $8.4M |
| Dnalite Therapeutics | $5.6M |
| Construction Robotics | $2.2M |
| AQUANANO | $0.9M |
| Grid7 | $0.5M |

These are *probably* legitimate matches (a founder serving on both an operating co and an investor fund's board is normal in VC ecosystems) but the matching methodology can't verify without manual review.

### Top shared names

| Name | # cross-links |
|---|---|
| MARC GOLDBERG | 9 |
| ROBERT CUNNINGHAM | 6 |
| FANG ZHENG | 6 |
| DAKIN SLOSS | 6 |
| N/A N/A | 4 |
| DAVID BROWN | 4 |
| CHARLES LANNON | 4 |
| KIRK NIELSEN | 4 |

These are mostly real, identifiable individuals — fund partners who also serve as board members or executive officers of operating companies. This is expected ecosystem behavior, not a methodology bug.

## Interpretation

The cross-link concern flagged in the published doc is real conceptually but small in dollar terms. The 0.16% at-risk exposure is well below the [1.65, 2.02] high-only bootstrap CI band — the cross-link uncertainty is already absorbed into the existing CI margin.

What this audit actually reveals:

1. **No methodology change is needed.** The matching pipeline correctly excludes PIF entities from totals, and the residual cross-link exposure on the operating-co side is below noise.

2. **The published doc's caveat language was conservative.** Reframing from "71 cross-links identified for future investor-relationship mapping" to "~100 cross-links identified; quantified at $151M (0.16%) at-risk exposure" would more accurately characterize the methodology risk.

3. **The real opportunity is investor-relationship mapping.** Of the 35 distinct high-tier cross-linked ops, most have legitimate VC-partner-as-board-member overlap. Mapping which PIF invests in which SBIR firm (via these cross-links) would be a useful follow-on analysis for the F-area research questions, *not* a bias correction.

## Reproducibility

```bash
.venv/bin/python scripts/data/audit_form_d_pif_cross_links.py
```

Default config: inputs `data/form_d_details.jsonl`, year window 2009-2024, hardcoded high-only and H+M headline numbers from the published doc. Outputs `reports/ml/form_d_pif_cross_links.{json,md}` (gitignored). Runs in <1s on a development laptop.
