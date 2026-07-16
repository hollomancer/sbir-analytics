# Phase III benchmark research tools

Status: **research-only**. These scripts produce bounded, inspectable benchmark
artifacts; they are not a production FPDS client or a Dagster asset.

The work is intentionally stacked on the award-identity and dataset-grain
contract in PR #449. A production external-source adapter, including retry,
checkpoint, and source-lifecycle policy, belongs in issue #442.

## Workflow

Pull an explicit number of FPDS Element 10Q pages and record provenance:

```bash
python scripts/phase3_benchmark/pull_fpds_10q.py SR3 \
  --pages 40 \
  --output data/derived/fpds_sr3.parquet \
  --manifest data/derived/fpds_sr3.manifest.json \
  --cache-dir data/raw/fpds/sr3 \
  --source-vintage 2026-07-16
```

Build same-firm proxy positives, same-office hard negatives, and a deterministic
lexical baseline:

```bash
python scripts/phase3_benchmark/build_pairs_and_score.py \
  --phase-ii data/raw/sbir/award_data.csv \
  --phase-iii data/derived/fpds_sr3.parquet \
  --pairs-out data/derived/phase3_pairs.parquet \
  --metrics-out data/derived/phase3_metrics.json
```

The pull manifest captures the exact query, source vintage, retrieval time,
page and row counts, raw-page hash, parameters, field completeness, and whether
the bounded pull exhausted the reported feed. Generated data stays under
`data/` and is not committed.

## Interpretation guardrails

- FPDS entries are transactions. The benchmark constructs an award-grade key
  and selects one representative transaction before pairing.
- A same-firm coded Phase III / earlier Phase II pair is a **proxy positive**,
  not proof that the contract derives from that award.
- A Phase II is eligible only when its date is on or before the Phase III
  action date. Year-only Phase II dates become December 31, conservatively
  excluding ambiguous same-year matches.
- A lexical AUC is a separability diagnostic, not a production transition
  classifier or an estimate of Phase III undercount.
