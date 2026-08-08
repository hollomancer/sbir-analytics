# Transition Precision Benchmark Automation — Design

## The binding constraint: data locality, not CI config

The benchmark scores the real retrospective corpus. That corpus is gitignored
(`*.parquet`, `/data/*`) and lives on server storage; GitHub runners have no
access and `USE_REAL_SBIR_DATA` is deliberately unset in CI. So "automation"
means running server-side where the corpus already is — not a GitHub workflow
step. This is why three prior docs that claimed CI automation were wrong, not
just stale: the automation cannot live on GitHub runners as designed.

Everything below follows from that: pin the corpus by hash (public) while its
bytes stay private; run the benchmark as an operated server-side asset; keep the
fast fixture canary exactly where it is.

```
studies/transition-scoring/benchmark-corpus.manifest.json   (committed: hash + coarse stats)
        │  frame_hash  ── verifies ──►  corpus parquet bytes (server storage, gitignored)
        ▼
Dagster asset: transition_precision_benchmark (server profile, heavy-assets)
   run_backtest(contracts, phase_ii, threshold)  ── scripts/phase_iii_precision_backtest.py
        │
        ├─ writes reports/phase_iii/backtest.json  (provenance-stamped result)
        └─ @asset_check(blocking=True)  precision >= floor  → fails the run below the floor
```

## R1 — Corpus pinning (public hash, private bytes)

Reuse the `phase3-notice-corpus-fusion/corpus.manifest.json` shape verbatim —
it already pins a corpus by `frame_hash` + coarse aggregates and commits only
the manifest. The new `benchmark-corpus.manifest.json` records, per input frame
(contracts, Phase II):

```json
{
  "generated_at": "<UTC ts, passed in — not computed in-run>",
  "frames": {
    "contracts": {"frame_hash": "<sha256>", "rows": 0, "positives": 0},
    "phase_ii":  {"frame_hash": "<sha256>", "rows": 0, "firms": 0}
  },
  "sources": ["<provenance path>"]
}
```

Governance decisions baked in:

- **Public/private split.** The repo is public (`private: false`). The manifest
  (hash + coarse counts) is world-readable and safe; the bytes never enter git.
  A hash discloses nothing about contents.
- **Coarse only.** No per-firm, per-agency small-cell, or record-level fields in
  the manifest — those could be disclosive even as "aggregates." Frame-level
  totals and the hash are the ceiling.
- **Hash verification is a gate, not a note.** The benchmark recomputes each
  frame's SHA256 and refuses to score on a mismatch, so a "regression" can never
  secretly be corpus drift. This is the discipline that lets the number gate.

A tiny helper (`scripts/ci/verify_corpus_manifest.py` or a function beside the
backtest) computes/verifies frame hashes; it does not need the study-manifest
validator, which governs `study.yaml`, not data-frame pinning.

## R2 — Operated benchmark asset

A Dagster asset in the analytics package (heavy-assets group, server profile),
wrapping the existing backtest logic — no re-implementation:

- Loads the pinned frames, verifies hashes (R1.4), runs `run_backtest(...)` in
  strict mode, writes `reports/phase_iii/backtest.json` with provenance (corpus
  hashes, coefficient hash, config version, timestamp, sample size, precision@K).
- A `@asset_check(blocking=True)` asserts `precision >= floor`
  (`config/base.yaml`, default 0.85). Below the floor fails the materialization —
  the census/production-asset-checks pattern.
- Deterministic: pinned corpus + frozen coefficients + fixed scorer config ⇒
  identical precision. No `Date.now()`-style nondeterminism inside scoring;
  timestamps are stamped onto the result, not mixed into it.

**Why an operated asset, not a schedule or a GitHub cron.** A calendar run of a
comprehensive test on drifting real data is exactly the brittle, owner-less
nightly pattern the repo deleted: entangled failure domains (model regression vs
corpus drift vs infra) and red nobody acts on. An operated asset with a blocking
check has an owner (whoever materializes it) and a single failure domain (the
hash pin removes drift; strict mode removes silent-skip). Enabling a cadence is a
later operator decision, kept STOPPED by default per the runbook.

## R3 — Two-tier signal

| Signal | Where | Data | Speed | Role |
|---|---|---|---|---|
| Fixture canary (exists) | PR, Fast Tests | golden fixture | seconds | plumbing regression guard |
| Full benchmark (this spec) | server asset | pinned real corpus | minutes | measured precision, recorded |

The canary is untouched. It catches "a weight change broke the scoring path" on
every PR; the benchmark answers "does the model actually clear 85% on real data"
when materialized. Neither moves onto the other's turf.

## R4 — Promotion boundary (what this spec does NOT claim)

This spec builds the *reproducible measurement and the gate* — pipelines-tier
work. It does not make the precision number citable. Two things block that,
named here, owned elsewhere:

1. **Estimand.** `run_backtest` scores HIGH-rate over known positives only; the
   script sets `recall = precision` because there are no true negatives in the
   scored population. That is a recall-flavored quantity, not a precision
   estimand. A citable claim needs the decoy/true-negative set that
   `phase3-transition-groundtruth` is scoped to produce, plus a written estimand.
2. **Study contract.** Once the estimand is sound and the benchmark records a
   recurring number from the pinned cut, `studies/transition-scoring/study.yaml`
   promotes `exploratory → reproducible → validated` with the four evidence-tier
   items. This spec supplies the SHA-pinned inputs and the blocking check (two of
   the four); the study supplies the frozen spec and the estimand.

## Alternatives considered

- **Fetch the corpus into GitHub CI** — rejected: storage/transfer cost,
  credentials, and re-introducing external-data flakiness on the hot path, for a
  corpus that is server-resident anyway. Public-repo exposure risk if mishandled.
- **Commit the corpus (LFS or plain)** — rejected: public repo; bytes must stay
  private; `.gitignore` already forbids it; size is the reason it was ignored.
- **A nightly/weekly schedule** — rejected as the primary mechanism: rebuilds the
  deleted brittle-suite pattern. A cadence is allowed only as a later, explicit
  operator choice on top of the operated asset.
- **Extend the fixture canary to "big fixture"** — rejected: a bigger fixture is
  still not the real corpus and still cannot certify the 85% claim; it only
  slows PRs.
