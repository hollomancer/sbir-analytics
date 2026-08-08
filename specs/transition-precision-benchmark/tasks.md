# Transition Precision Benchmark Automation — Tasks

> Prerequisite: the corpus bytes exist on server storage (they do — the manual
> backtest runs against them today). T1 first (pinning is what makes the rest
> trustworthy); T2 depends on T1; T3/T4 are documentation and can land alongside.
> Nothing here runs on GitHub runners or enables a server schedule.

- [ ] 1. Corpus pinning helper + manifest.
  - Add a hash helper (compute + verify SHA256 per input frame) beside the
    backtest, and generate `studies/transition-scoring/benchmark-corpus.manifest.json`
    (frame hashes + coarse row/positive/firm counts + provenance), mirroring
    `phase3-notice-corpus-fusion/corpus.manifest.json`. Coarse aggregates only.
  - Verify: manifest commits; no `.gitignore` exception added; a unit test on a
    fixture proves hash mismatch is detected and matching frames pass;
    `git check-ignore` confirms the corpus parquets stay ignored.
  - Requirements: 1.1, 1.2, 1.3, 1.4

- [ ] 2. Operated benchmark asset + blocking check.
  - Add a Dagster asset (heavy-assets group, server profile) that verifies the
    pinned hashes, runs `run_backtest(...)` in strict mode, writes a
    provenance-stamped `reports/phase_iii/backtest.json`, and carries a
    `@asset_check(blocking=True)` on `precision >= floor` (floor from
    `config/base.yaml`, default 0.85). No re-implementation of scoring; wrap the
    existing script logic.
  - Verify: `Definitions.validate_loadable` passes; a hermetic asset test shows a
    below-floor fixture failing the check and an above-floor fixture passing;
    determinism check (same inputs ⇒ same precision); the asset is not in any
    schedule and not on the PR/Full-Tests path.
  - Requirements: 2.1, 2.2, 2.3, 2.4

- [ ] 3. Keep the two-tier signal honest (docs).
  - Confirm the PR fixture canary is untouched; note the canary-vs-benchmark
    split in the benchmark asset's docstring and cross-link from CLAUDE.md's
    precision line (already corrected to describe the canary + manual full run —
    update it to point at the automated asset once T2 lands).
  - Verify: `make docs-check` passes; canary tests still pass unchanged.
  - Requirements: 3.1, 3.2

- [ ] 4. Record the promotion boundary in the study contract.
  - In `studies/transition-scoring/study.yaml`, reference the pinned
    benchmark-corpus manifest and the blocking check as the reproducible
    measurement, and state the two remaining gates to `validated`: the
    estimand/decoy set (owned by `phase3-transition-groundtruth`) and the frozen
    study spec. Do not change the study's `evidence_status` — that is a later
    promotion, not this spec's to grant.
  - Verify: `uv run python scripts/ci/validate_study_manifests.py` still passes;
    the study names the benchmark as its measurement source.
  - Requirements: 4.1, 4.2

Explicit non-tasks (named, owned elsewhere):
- Building the decoy/true-negative label set and the precision estimand
  (`phase3-transition-groundtruth`).
- Enabling a benchmark schedule (operator decision, server runbook).
- Any GitHub-runner execution or corpus-byte publication.
