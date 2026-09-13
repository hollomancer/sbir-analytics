# Promotion plan — `transition-scoring`

**From:** `exploratory`
**To:** `reproducible`

`reproducible` means specified inputs and implementation can be rerun. This
study already has the implementation half: five registered entry points, three
frozen artifacts, materialization allowed, and no open blockers. What it does
not have is the inputs half, and one of the gaps is a deliberate design choice
rather than an oversight.

## What is already in place

- **Implementation registered** — `TransitionScorer`, `TransitionDetector`,
  `load_fusion_coefficients`, `TransitionEvaluator`, and the Dagster asset
  `transformed_transition_detections`.
- **Three frozen artifacts** — `fusion_coefficients.json`, the notice-corpus
  `corpus.manifest.json`, and `refit_ladder.json`.
- **A reproduced result on record** — the notice-corpus fusion refit reproduced
  the published award-grain linkage result on its frozen corpus (828 rows, 138
  positives, 101 firms).
- **A determinism claim already permitted** — given a fixed detection
  configuration and the frozen, hash-validated fusion coefficients, scoring is
  deterministic for a fixed input.

Read that last claim carefully. It is conditional on *a fixed detection
configuration*, and the configuration is not fixed.

## The three gaps, in the order they bind

### 1. The scoring weights live in a deliberately mutable config

`config/transition/detection.yaml` holds hand-set expert-judgment weights, and
the study's own limitations record that this live configuration is deliberately
mutable. That is incompatible with `reproducible` as written: the same code
against the same inputs produces different scores after anyone edits it, and
nothing in the manifest would detect that.

**Decided 2026-09-13: identify by digest, do not freeze the file.**

The named-profile option was recommended first and was wrong for this codebase.
It assumes a central loader to resolve a profile name; there is none. Config
reaches the scorer as a plain dict passed to ``TransitionDetector(config=...)``,
so a profile registry would bind nothing that a caller could not bypass.

``Config.scoring_digest`` now hashes the ``to_detector_config()`` surface -- by
construction, exactly the values that reach ``TransitionScorer``, and nothing
operational like ``batch_size_contracts`` that cannot move a score. The
committed ``detection.yaml`` digests to
``779cf5bc662997c83da3080b747372b9556821c0f23bd0d3362606c3fba15009``, which the
study cites and ``tests/unit/transition/test_scoring_config_digest.py`` enforces.
A weight change fails that test rather than silently producing a different
number.

One thing this surfaced: the digest has no structured home in ``StudyManifest``.
``frozen_artifacts`` means *these exact bytes* and the validator correctly
rejected a config-surface digest filed there; ``extra="forbid"`` rules out an ad
hoc field. It is recorded in ``limitations`` with the enforcing test registered
under ``implementation``. A manifest field for "the configuration identity a
result was measured under" would be a real addition, adjacent to what #726 added
for validation results.

The three options considered were:

- **Freeze the file** as a `frozen_artifacts` entry. Cheapest to verify,
  costliest operationally — tuning then requires an amendment.
- **Freeze a named profile** and let the live file override it, with the study
  pinning the profile and the code recording which one produced a given score.
  This is the pattern `sbir_etl.identity` already uses for name profiles.
- **Emit the config digest with every score** and pin that digest in the study,
  so a rerun that used different weights is detectable rather than prevented.

The second is the closest fit to existing repository practice. Pick one before
touching the manifest.

### 2. The fusion corpus parquet is local-only and gitignored

Its bytes are not SHA-enforced here. The limitation notes it is regenerable from
committed scripts and pinned manifests, which is the workable path: record the
regeneration command and the expected digest, so a fresh checkout can rebuild
the corpus and prove it matches. Without that, "can be rerun" is true only on a
machine that already has the file.

### 3. No stored benchmark report

The `>=85%` precision target is not tied to a declared data cut or a
ground-truth label set. `CLAUDE.md` is explicit that the number is measured only
by a manual run of `scripts/phase_iii_precision_backtest.py` against the S3
corpus and is not a CI gate, and the study's first limitation says when it was
last measured, and against what labels, is an open question.

This does not block `reproducible` — a reproducible study may have an unmeasured
benchmark — but it is the single largest obstacle to any later `validated`
promotion, and gap 2 has to be closed before it can be attempted at all.

## Steps

1. **Decide the configuration question** (gap 1). Record the choice and its
   operational cost in a new `studies/transition-scoring/amendments.md`.
2. Implement the choice. Under the frozen-profile option this touches
   `config/transition/detection.yaml`, the scorer's config loading, and the
   manifest's `frozen_artifacts`.
3. **Pin the corpus regeneration** (gap 2): commit the command and the expected
   digest, and verify a clean-checkout rebuild reproduces it.
4. Rerun the refit and confirm it still reproduces 828 rows / 138 positives /
   101 firms from the frozen inputs alone.
5. Set `evidence_status: reproducible` and rewrite the limitations that
   currently describe the mutable config and the unpinned corpus.
6. `uv run python scripts/ci/validate_study_manifests.py` and
   `uv run python scripts/ci/check_epistemic_tiers.py`.

## What this plan does not do

It does not attempt `validated`. That needs a preregistered validation design
with a `threshold_basis`, a `threshold_value`, and a `validation_result`, and
the natural design — the `>=85%` precision benchmark — cannot be run as a
preregistered test until the corpus is pinned and the label set is declared.
Gap 3 is named here so the sequencing is visible, not because this promotion
closes it.

## A correction to the earlier estimate

An earlier assessment ranked this study as the second-easiest promotion,
described as verification rather than research, on the grounds that the
implementation and frozen artifacts were already in place. That underestimated
it. The mutable-configuration gap is a deliberate design decision with an
operational cost, and it has to be settled by a person before any manifest edit
is meaningful.
