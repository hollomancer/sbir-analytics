---
Type: Research Report
Owner: research@project
Last-Reviewed: 2026-08-09
Status: draft
---

# NSF Phase I to Phase II baseline comparison

> **Exploratory and non-citable.** This is the Phase 1 review artifact, not a
> validated program-performance finding. No external private-capital comparator
> is applied, and four requested outcome channels were unavailable in this run.

## Review result

On the pinned SBIR.gov award snapshot, **672 of 1,502 uniquely identified NSF
firms with a Phase I award in 2015–2019 had a Phase II award no earlier than the
Phase I and within five calendar years**. The exploratory rate is **44.7%** with
a 95% Wilson interval of **42.2%–47.3%**.

| Measure | Value |
| --- | ---: |
| NSF Phase I firms, 2015–2019 | 1,502 |
| Firms with a qualifying Phase II within five years | 672 |
| Graduation rate | 44.7% |
| 95% Wilson interval | 42.2%–47.3% |

This artifact reports an internal SBIR phase-graduation measure. It does not
apply an external private-capital comparator, and the result must not be used to
claim relative program performance.

## Cohort and estimand

- **Input:** SBIR.gov bulk awards, 219,500 rows, award years 1983–2026.
- **Agency:** `National Science Foundation`, resolved by the shared agency
  cohort builder from canonical raw `Agency` values.
- **Vintage:** firms with at least one Phase I award in calendar years
  2015–2019.
- **Firm key:** UEI when present, then DUNS, then lower-cased company name.
- **Numerator:** a firm with at least one Phase II award in `[Phase I year,
  Phase I year + 5]` for any of its Phase I awards in the vintage.
- **Denominator:** unique recoverable firm keys with a Phase I award in the
  vintage.
- **Interval:** two-sided 95% Wilson score interval.

This definition fixes two problems in the prior implementation: Phase II awards
that predated Phase I could count as graduation, and there was no follow-up
horizon. Entity changes that are not bridged by UEI or DUNS can still undercount
graduation; this run does not claim that the fallback name key fully resolves
firm lineage.

## Outcome availability

| Metric | Available? | Reason |
| --- | --- | --- |
| Phase I to Phase II graduation | Yes | Computed from the pinned awards file |
| Phase II to federal-contract transition | No | Transition-score enrichment was not supplied to the standalone runner |
| Five-year survival proxy | No | Federal recipient/vendor activity was not supplied |
| M&A exit rate | No | `sbir_ma_events.jsonl` was not available on the host |
| Patent rate | No | PATLINK remains deferred to Phase 2 |

Unavailable means **not measured**, never zero.

## Provenance

The machine-readable manifest is
[agency-private-capital-phase1-nsf.manifest.json](agency-private-capital-phase1-nsf.manifest.json).

| Input | SHA-256 | Size / rows |
| --- | --- | --- |
| `award_data.csv` | `73d646fc6883ed93b36d19518b0d9442a9ebae94c5b49ad5a7fcd6d3c2b872dd` | 394,456,822 bytes / 219,500 rows |
| `published_baselines.yaml` | `5bfa088e1a86c2290d08befae1e3d35ca46c6f3aaf28bbdb684279d69c4405f7` | 3,578 bytes / 4 entries |
| `sbir_ma_events.jsonl` | unavailable | M&A metric suppressed |

Reproduce from a checkout with the awards snapshot available:

```bash
uv run --extra stack-dev python \
  scripts/archive/data/run_agency_private_capital_phase1.py \
  --agency NSF \
  --awards-csv data/raw/sbir/award_data.csv \
  --headline-vintage 2015-2019 \
  --graduation-horizon-years 5 \
  --skip-download
```

The command emits the comparison Markdown, structured JSON, outcome Parquet,
and deterministic `run_manifest.json` under
`data/processed/agency_private_capital/nsf/`.

## Gate decision

Phase 1 is **materialized but not signed off**. Review must resolve the following
before Phase 2 begins:

1. accept or revise the five-year graduation estimand and entity-key fallback;
2. decide whether the missing transition, survival, M&A, and patent channels
   must be populated before Phase 1 is considered complete.

Phase 2 control construction, multi-agency publication, the FY M&A trend, and a
filer/non-filer or crowd-in/crowd-out design remain separate gated work.
