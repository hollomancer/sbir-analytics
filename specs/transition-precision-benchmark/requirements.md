# Transition Precision Benchmark Automation — Requirements

**Target epistemic tier:** `pipelines`

- **Research question:** none directly. Operational obligation: CLAUDE.md holds
  transition scoring to a ≥85% Phase III retrospective HIGH-precision benchmark,
  but that gate is enforced today only by a fixture-level PR canary
  (`tests/unit/scripts/test_phase_iii_precision_backtest.py`). The full benchmark
  against the real corpus (`scripts/phase_iii_precision_backtest.py`) is run by
  hand and recorded nowhere. This spec automates the full-corpus run so the gate
  is a measured fact rather than an asserted policy, and so the transition-scoring
  study (`studies/transition-scoring/`) has a recurring number to promote on.
- **Status:** active.
- **Out of scope:** running the full benchmark on GitHub runners (they cannot
  reach the corpus); committing corpus bytes to git; building the
  true-negative/decoy label set that a clean precision estimand needs (that is
  `phase3-transition-groundtruth` territory — named here as the gate to evidence,
  not solved here); changing scorer weights, thresholds, or the fusion model;
  enabling any server schedule (an operator decision per the runbook).
- **Verification that proves completion:** the corpus is pinned by a committed
  manifest (hash + coarse aggregates, bytes uncommitted); a server-side job
  reproduces the benchmark from the pinned cut and records a provenance-stamped
  result; a blocking asset check fails the run below the floor; the PR canary is
  unchanged; docs describe the two-tier signal honestly.

## Problem

The ≥85% gate is currently proven only on a golden fixture — the canary shows the
plumbing works, not that the model clears 85% on real data. The full benchmark
needs the retrospective corpus (contracts + Phase II parquets), which is
`*.parquet`/`/data/*` gitignored and lives on server storage no CI runner
reaches. Three now-corrected docs had claimed CI automation that never existed.
Automating it honestly means solving *where it runs* and *how the corpus is
pinned without publishing it* — not adding a workflow step.

## R1 — Pin the benchmark corpus as a versioned artifact (bytes stay private)

1.1 THE benchmark corpus (the contracts and Phase II frames the backtest scores)
    SHALL be pinned by a committed manifest at
    `studies/transition-scoring/benchmark-corpus.manifest.json` following the
    existing `specs/phase3-notice-corpus-fusion/corpus.manifest.json` pattern:
    a SHA256 `frame_hash` per input frame, row/positive/firm counts, generation
    timestamp, and source provenance paths.

1.2 THE manifest SHALL contain only the hash and **coarse** aggregates. IT SHALL
    NOT contain records, firm identities, raw notice text, or any small-cell
    breakdown that could be disclosive. The repository is public; the manifest is
    world-readable and must be safe as such.

1.3 THE corpus bytes SHALL NOT be committed. `.gitignore` already excludes
    `*.parquet` and `/data/*`; the spec SHALL NOT add exceptions for corpus
    files. Bytes live on server storage (or a private bucket); the pin ties the
    public hash to those private bytes.

1.4 WHEN the benchmark runs, IT SHALL verify each input frame's SHA256 against
    the manifest before scoring. IF a hash does not match, THEN the run SHALL
    fail loudly (no scoring against an unpinned or drifted corpus).

## R2 — Server-side operated benchmark run with a blocking check

2.1 THE full benchmark SHALL run where the corpus lives — the self-hosted server
    — as a Dagster asset/job invoking the existing
    `scripts/phase_iii_precision_backtest.py` logic in `--strict` mode (missing
    inputs fail, never a vacuous pass). It SHALL NOT run on GitHub runners and
    SHALL NOT be placed on the PR or merge test path.

2.2 THE run SHALL be deterministic and reproducible from the declared cut: pinned
    corpus hash + frozen fusion coefficients + fixed scorer config produce the
    same precision. The result SHALL be written with full provenance (corpus
    hash, coefficient hash, config version, timestamp, sample size, precision@K).

2.3 A blocking asset check SHALL fail the run when HIGH precision falls below the
    configured floor (default 0.85), following the census / production-asset-checks
    blocking pattern. The floor SHALL come from config, not a call-site literal.

2.4 THE run SHALL be manually triggerable and SHALL default to disabled as a
    schedule; enabling any cadence is a separate operator decision recorded per
    the server runbook, not shipped by this spec.

## R3 — Preserve the two-tier signal

3.1 THE PR-time fixture canary SHALL remain unchanged as the fast signal. This
    spec adds the deep signal (real corpus, server-side); it does not move the
    canary onto the corpus or the corpus onto the PR path.

3.2 Documentation (CLAUDE.md, the study contract, this spec) SHALL state plainly
    which signal is which: canary = plumbing on a fixture per PR; benchmark =
    measured precision on the pinned corpus, server-side, recorded.

## R4 — Route the citable claim through a study contract

4.1 THE recorded precision result SHALL be exploratory until a
    `studies/transition-scoring/` contract promotes it: producing the number does
    not make it citable.

4.2 THE spec SHALL name the estimand prerequisite explicitly: the current
    backtest scores HIGH-rate on known positives only (no true negatives;
    `recall == precision` in the script by construction), so the metric is not a
    clean precision estimand. Promotion to `validated`/`citable` evidence SHALL
    require the decoy/true-negative set from `phase3-transition-groundtruth` and a
    declared estimand — this spec builds the reproducible measurement and the
    gate, not the citable claim.
