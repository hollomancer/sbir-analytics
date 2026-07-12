# ML Methodology Review Checklist

## Overview

This is the standing review checklist for ML code in `packages/sbir-ml/`. It exists to catch methodology bugs — the kind where code runs, tests pass, and reported metrics are still wrong (data leakage, missing seeds, hand-rolled metrics with magic epsilons, accuracy as a headline for imbalanced multi-label problems).

The patterns are drawn from [`scicode-lint`](https://github.com/authentic-research-partners/scicode-lint)'s published 66-pattern catalog (v1.0 registry, 2026-03-15), filtered to the subset relevant to our sklearn + HuggingFace-Inference stack. PyTorch-specific patterns are documented but currently not load-bearing.

Methodology bugs in the CET classifier directly distort its own reported precision/recall/F1 (computed in `trainer.py` and stored in the metrics dict). Indirectly, degraded CET classifications feed `transition/features/cet_analyzer.py` and become one signal in the rule-based **transition scorer** — which is what CLAUDE.md's "≥85% precision benchmark" actually references. The cascade is dampened by `cet_alignment`'s weight (1 of 6 signals), but real: a data-leakage bug here doesn't just produce a worse classifier, it can quietly degrade downstream transition-scoring precision in ways the CET-classifier-internal metrics don't show.

### What this checklist does and does not cover

**Covers:** ML methodology in `packages/sbir-ml/sbir_ml/ml/` — TF-IDF + LogisticRegression CET classifier (`cet_classifier.py`), patent classifier (`patent_classifier.py`), trainer (`trainer.py`), vectorizers (`multi_source_vectorizer.py`).

> **Note (2026-07 repo cleanup):** The unused `huggingface_inference.py` client was removed. Historical findings below that reference it are retained for audit traceability but no longer apply to live code.

**Does NOT cover:** the rule-based **transition scorer** at `packages/sbir-ml/sbir_ml/transition/`. That's a separate system with separate methodology risks (signal weight calibration, threshold drift, ground-truth labeling protocol). CLAUDE.md's ≥85% precision target lives there, not here. See "Next audit scope" below.

## When to use this checklist

- **Reviewing any PR that touches `packages/sbir-ml/sbir_ml/ml/`** — required pass before merge
- **Before re-running training that produces an artifact downstream consumers depend on** — verify the methodology hasn't drifted from this checklist
- **Periodic baseline refresh** — re-run the checklist annually (or whenever scicode-lint releases a new pattern version) against the full ML surface area and update the "Initial Findings" appendix

## How to apply

For each section below, read the code being reviewed and answer the verification question. Findings are recorded against the relevant pattern ID so future reviewers can trace decisions. Pattern IDs match scicode-lint's registry (e.g., `ml-008`, `rep-001`) — useful for cross-referencing when a real tool run is later performed.

## The checklist

### 1. Data leakage (highest severity)

| ID | Verify | Where it bites |
|---|---|---|
| `ml-001` | Vectorizers/scalers are inside an sklearn `Pipeline` so `fit` only sees train data, `transform` is used on test | `cet_classifier.py:264-277` — TfidfVectorizer wrapped correctly. Watch for any direct `vectorizer.fit_transform(X)` outside a Pipeline |
| `ml-007` | Test-set transforms use `transform()`, never `fit_transform()` | Anywhere we do `vectorizer.fit_transform(X_test)` is wrong |
| `ml-010` | If using `CalibratedClassifierCV`, calibration runs on training data only — never on test | `cet_classifier.py:257-261` correctly uses internal cv |
| `ml-009` | No duplicate rows or near-duplicates leaking between train and test (e.g., same SBIR award assigned to multiple Phase II's with identical abstract) | SBIR abstracts can be reused across Phase I → Phase II → continuation contracts. Deduplicate before split |
| `ml-005` | Time-ordered data uses time-based splits, not random splits | SBIR awards span 1985–present. Random splits leak future eras into training |
| `ml-006` | Feature-engineering does not use future information (target-encoding leakage, lookahead bias) | Audit any target-encoded categorical, aggregation, or rolling feature for whether it sees future rows |
| `ml-002` | The target column (or anything trivially derived from it) is not included as a feature | E.g., don't include `phase_iii_award_year` as a feature for predicting "did Phase III happen?" |
| `ml-003` | If using target encoding, the encoding is fit on train only and applied to test as a transform | Same as `ml-001` but for target encoding specifically |

### 2. Reproducibility

| ID | Verify | Where it bites |
|---|---|---|
| `rep-001` | All sources of randomness are seeded: `random.seed`, `np.random.seed`, and per-estimator `random_state` | `trainer.py` only seeds `train_test_split` and `LogisticRegression` — neither numpy nor python random are seeded |
| `rep-009` | All CV splitters (`StratifiedKFold`, `KFold`, `CalibratedClassifierCV(cv=...)`) have explicit `random_state` | `cet_classifier.py:257-261` `CalibratedClassifierCV(cv=3)` has no `random_state` |
| `rep-014` | A single `RandomState` instance is not reused across independent stages (which couples them in surprising ways) | Prefer integer seeds passed independently to each estimator |
| `rep-008` | Any `pandas.DataFrame.sample()` call passes `random_state` | grep `\.sample\(` and verify |
| `rep-011` | No iteration over a `set()` whose order affects model output | `patent_classifier.py:281-291` iterates a CET set non-deterministically across runs |
| `rep-005` | File iteration uses sorted order (`sorted(os.listdir(...))`, not raw `os.listdir(...)`) | Affects training data ordering when reading from directories |
| `rep-007` | Sort calls with possible ties use a stable sort or include a secondary key | `sorted(items, key=lambda x: x.score)` ties are broken by insertion order — usually fine, but verify it's intentional |
| `rep-012` | Model artifacts persist library versions (sklearn, numpy, scipy, joblib, python) alongside the model | Current code persists `model_version` and `training_date` but no library versions — sklearn upgrades can silently change behavior |
| `rep-010` | Datetimes are timezone-aware. Use `datetime.now(datetime.UTC)` — never `datetime.now()` or deprecated `datetime.utcnow()` | Project standard per CLAUDE.md. Current code mixes both forms |
| `rep-003` | Thresholds used in evaluation are read from the same config as production thresholds — never hardcoded in trainer code | `trainer.py:245,304` hardcode `>= 40` while config can override the `medium` threshold |

### 3. Numerical correctness

| ID | Verify | Where it bites |
|---|---|---|
| `num-001` | Float equality comparisons (`==`, `!=`) replaced with `np.isclose` or `math.isclose` | Currently clean |
| `num-003` | `log()`, `log1p()` calls protected against zero/negative inputs | Currently clean |
| `num-005` | Division-by-zero protection uses sklearn's `zero_division` parameter rather than hand-rolled `+ 1e-10` epsilon | `cet_classifier.py:345-347` rolls precision/recall/F1 by hand with `+ 1e-10`. Use `sklearn.metrics.precision_score(zero_division=0)` |
| `num-006` | Test assertions on floats use `pytest.approx` or `np.allclose`, not `==` | Verify in test files |
| `num-004` | No int32 overflow risk in counters that could exceed 2³¹ (~2.1B). Use int64 explicitly | Cumulative SBIR-corpus counters might cross this in 2030+ |

### 4. Metrics and evaluation

These are not a single scicode-lint pattern but were the most consequential class of findings in the baseline audit. Treat as load-bearing.

| Verify | Where it bites |
|---|---|
| `accuracy` is **not** the headline metric for multi-label or imbalanced binary classification — use precision/recall/F1 with `average='macro'` (or per-class) | `trainer.py:312,400-401` and `cet_classifier.py:344` |
| Hand-rolled precision/recall/F1 are replaced with `sklearn.metrics.*` with explicit `zero_division=0` | `cet_classifier.py:345-347` is the worst offender |
| Split methodology matches documentation. If docstrings claim "cross-validation with stratified splits," the code is doing k-fold, not single-split | `trainer.py` docstring claims CV; code does a single train/val split |
| Multi-label splits use `iterstrat.MultilabelStratifiedShuffleSplit` or equivalent — sklearn's `train_test_split` cannot stratify multi-label `y` | `trainer.py:119` uses `stratify=None` explicitly |
| If multiple binary classifiers' scores are compared to pick a "primary" label, calibration comparability across classifiers is verified or documented as a known limitation | `cet_classifier.py:440` picks `primary` by max score across independently-calibrated classifiers |

### 5. Inference and serving

| ID | Verify | Where it bites |
|---|---|---|
| `pt-007` | PyTorch models call `.eval()` before inference (handled internally by `SentenceTransformer.encode`; verify if any raw `nn.Module` is added) | Currently N/A — no live HF inference client in repo |
| `pt-013` | Inference paths use `torch.inference_mode()` or `torch.no_grad()` (also handled internally by `SentenceTransformer`) | Currently N/A — verify when raw PyTorch lands |
| `pt-011` | GPU inference is batched (not one item per `predict()` call) | N/A — `huggingface_inference.py` removed (2026-07 cleanup) |
| API retry logic distinguishes retryable (5xx, 429) from non-retryable (4xx auth/validation) errors | N/A — `huggingface_inference.py` removed (2026-07 cleanup) |
| Embedding outputs maintain 2-D shape even for single-item batches | N/A — `huggingface_inference.py` removed (2026-07 cleanup) |
| Normalization protected against zero-norm vectors (`/ (norms + 1e-8)` is OK as long as the epsilon is documented) | N/A — `huggingface_inference.py` removed (2026-07 cleanup) |

### 6. Error handling

| Verify | Where it bites |
|---|---|
| No bare `except Exception:` that masks fitting failures by falling back to a different feature representation | `patent_classifier.py:308-322` — silent fit on wrong representation |
| Errors at system boundaries (HF API, disk I/O) are explicit, propagated, and not retried indiscriminately | N/A — `huggingface_inference.py` removed (2026-07 cleanup) |
| `is_trained = True` is set only after all per-class pipelines actually fit successfully — not when some silently failed | Verify before sign-off |

### 7. Performance (lower priority)

| ID | Verify | Where it bites |
|---|---|---|
| `perf-001` | No Python `for` loops over array elements where vectorized numpy/pandas operations exist | Skim before merge |
| `perf-002` | No array allocation inside a hot loop (preallocate once outside) | Skim before merge |
| `par-001` | No `threading` for CPU-bound work (Python GIL) | Skim before merge |

## Initial findings (baseline as of 2026-06-17)

The first full pass of this checklist against `packages/sbir-ml/sbir_ml/ml/` surfaced **17 findings** — 4 critical, 7 high, 6 medium. They serve as the baseline: any new PR should not regress these, and existing fixes should be tracked here as they ship.

### Critical (4)

- **C1 — `trainer.py:118-127, 232`** — Docstring claims "cross-validation with stratified splits"; code does a single random train/val split with `stratify=None`. Pattern: `ml-008` + documentation drift. Impact: single-split variance makes the CET classifier's reported precision/F1 numbers noisy at the ±3pp level. Downstream effect on transition-scoring precision is dampened by `cet_alignment` weighting but not zero.
- **C2 — `cet_classifier.py:344-347`** — Hand-rolled precision/recall/F1 with `+ 1e-10` epsilon, and `accuracy_score` headlined for imbalanced binary classification. Pattern: `num-005` + `ml-004`. Impact: a model predicting "no positives" for an underrepresented CET reports ~95% accuracy.
- **C3 — `patent_classifier.py:281-291`** — Iteration over `set()` with no deterministic ordering; affects pipeline factory order and downstream fit order. Pattern: `rep-011` + `rep-005`. Impact: model artifacts hash differently across runs of identical inputs.
- **C4 — `patent_classifier.py:308-322`** — `try/except Exception` falls back to a different feature representation when `pipeline.fit()` raises. Pattern: silent failure. Impact: a malformed feature matrix silently trains on raw text instead, with `is_trained=True` set anyway.

### High (7)

- **H1 — `trainer.py` + `cet_classifier.py:257-261`** — `CalibratedClassifierCV(cv=3)` has no `random_state`; no global numpy/python seeds set. Pattern: `rep-001` + `rep-009`.
- **H2 — `trainer.py:312,400-401`** — `accuracy_score` prominent in metrics dict and report. Pattern: `ml-004`.
- **H3 — `cet_classifier.py:411-440`** — "Primary" CET selected by argmax across independently-calibrated binary classifiers; cross-classifier comparability is an implicit assumption.
- **H4 — `trainer.py:119`** — Random train/test split on inherently time-ordered SBIR data. Pattern: `ml-005`/`ml-006`.
- **H5 — `huggingface_inference.py:194-208`** — Retries 4xx HTTP errors with exponential backoff. *(Module removed 2026-07; finding archived.)*
- **H6 — `huggingface_inference.py:215-217`** — Single-batch shape can collapse from `(1, D)` to `(D,)`, breaking downstream normalization. *(Module removed 2026-07; finding archived.)*
- **H7 — `multi_source_vectorizer.py:95-99`** — Integer-cast weighting (`int(weight * 10)`) silently drops sources whose weight rounds to zero.

### Medium (6)

- **M1** — Saved model dicts lack library versions (sklearn/numpy/scipy/joblib). Pattern: `rep-012`. All three model files.
- **M2** — `trainer.py:245,304` hardcode `>= 40` while config supports threshold override. Pattern: `rep-003`.
- **M3** — Datetime usage mixes naive `datetime.now()`, deprecated `datetime.utcnow()`, and project-standard `datetime.now(datetime.UTC)` inconsistently across `trainer.py`, `cet_classifier.py`, `patent_classifier.py`. Pattern: `rep-010` + CLAUDE.md project standard.

### Confirmed clean (negative findings)

| Pattern | File | Why it passes |
|---|---|---|
| `ml-001` (scaler-leakage) | `cet_classifier.py:264-277` | TF-IDF vectorizer is correctly inside the `Pipeline` |
| `ml-007` (test-set preprocessing) | `cet_classifier.py:335-341` | `pipeline.predict_proba(X_test)` uses transform path correctly |
| `ml-010` (multi-test-leakage) | `cet_classifier.py:257-261` | Calibration runs on training data only via internal CV |
| `num-005` (division-by-zero, normalization) | `huggingface_inference.py:221-222` | Module removed 2026-07; was clean at removal |
| PT inference modes (`pt-007/011/013`) | `huggingface_inference.py` | Module removed 2026-07 |

## Running scicode-lint for real

### What works on this team's hardware (validated 2026-06-17)

scicode-lint ships expecting `vLLM in podman + nvidia-container-toolkit`. We don't have an NVIDIA box. But we **do** have a working path via the local `omlx` server (homebrew package, `omlx serve`) on port 8080, which exposes OpenAI-compatible endpoints with several model aliases:

| omlx alias | Backend | Local? |
|---|---|---|
| `auto`, `fast`, `tiny` | Qwen3-Coder-Next-MLX-4bit | **Yes (local MLX)** |
| `smart`, `creative` | gpt-4o-2024-08-06 (OpenAI) | No — code would leave the building |

**Use `auto` (or `fast`/`tiny`) — never `smart` or `creative`** for code analysis. The smart/creative aliases route to OpenAI's API and would send source code to a cloud provider.

The Qwen3-Coder-MLX model is arguably a *better* fit than scicode-lint's own default (`Qwen3-8B-FP8-dynamic`) because it's a Coder variant specifically tuned for code understanding.

### Required local patch

scicode-lint's `DetectionResult` schema enforces `reasoning: max_length=400` in `~/.local/share/uv/tools/scicode-lint/lib/python3.13/site-packages/scicode_lint/llm/models.py:147`. That constraint is **enforced server-side by vLLM/XGrammar** in the supported path, but omlx doesn't enforce it. Qwen3-Coder produces correct-but-verbose 800–2000 char explanations, and scicode-lint discards them.

The minimal patch is to bump `max_length=400` → `max_length=4000` on that field. Apply after every `uv tool install scicode-lint` upgrade.

If we end up running this regularly, the right long-term answer is either (a) a wrapper that truncates the `reasoning` field before validation, or (b) an upstream PR to scicode-lint adding a configurable max-length env var so non-grammar-constrained backends are first-class.

### The validated command

```bash
SCICODE_LINT_MODEL_SERVED_NAME=auto \
OPENAI_BASE_URL=http://localhost:8080/v1 \
scicode-lint lint \
  packages/sbir-ml/sbir_ml/ml/models/trainer.py \
  packages/sbir-ml/sbir_ml/ml/models/cet_classifier.py \
  packages/sbir-ml/sbir_ml/ml/models/patent_classifier.py \
  packages/sbir-ml/sbir_ml/ml/models/multi_source_vectorizer.py \
  --vllm-url http://localhost:8080 \
  --category ai-training,scientific-reproducibility,scientific-numerical \
  --format json \
  > reports/scicode-lint/full_run.json
```

Measured runtime on M5 Pro / omlx / Qwen3-Coder-MLX-4bit: **~1 min for `ai-training` (10 patterns) + ~6.5 min for `scientific-reproducibility` + `scientific-numerical` (24 patterns)** across all 5 files. So **~8 minutes for a full high-priority pass**, no GPU rental required, code never leaves the laptop.

### Other environments

If the local omlx setup is unavailable (e.g., another contributor's machine):

| Environment | Path |
|---|---|
| Linux + NVIDIA GPU (16 GB+ VRAM) | Direct path: `scicode-lint vllm-server start && scicode-lint lint ...` |
| Linux + institutional vLLM | `scicode-lint lint myfile.py --vllm-url https://your-vllm.edu` |
| Rented cloud GPU | Lambda Labs A10G or RunPod RTX 4090 (~$0.50–1.00/hr), `--vllm-url` to the rented instance |
| Apple Silicon **without omlx** | Use Ollama as OpenAI-compat backend with a Qwen3-Coder model; same local-patch caveat applies |

### When to do the real run

- Adding a new PyTorch model (the `pt-*` patterns become load-bearing and harder to apply by hand)
- After a major refactor of the training or inference path
- Before a release that publicly attaches precision/recall numbers (the CET classifier's own, or transition-scoring's via the cascade) to a model artifact
- Annually as a calibration check against the manual checklist

## Real scicode-lint run — 2026-06-17

First validated tool run against the codebase. Setup: omlx + Qwen3-Coder-Next-MLX-4bit, max_length patch applied, scope = `ai-training` + `scientific-reproducibility` + `scientific-numerical` categories (34 of 66 patterns).

**Outputs:** `reports/scicode-lint/ml_patterns.json` (ai-training findings), `reports/scicode-lint/rep_num_patterns.json` (reproducibility + numerical findings).

**Tool aggregate:** 28 findings across the 5 ML files — 4 critical, 7 high, 17 medium. Zero pattern errors after the schema patch.

### Findings the tool surfaced that the manual baseline missed

These are the net-new findings — what justified running the tool:

- **trainer.py:115 (ml-008, critical)** — `self.mlb.fit_transform(labels)` runs on the *full label set* before `train_test_split`. The MultiLabelBinarizer's `classes_` vocabulary is fit on data that includes the future test set. *Impact in our specific case is low* (CET label vocabulary is fixed a priori via `self.cet_areas`), but the structural pattern is real and worth fixing.
- **trainer.py `train()` (ml-007, critical)** — `train()` computes `test_metrics` (line 173) but returns only the model, leaving callers to dig into `self.metrics`. Soft finding — not a leakage bug — but a signature inconsistency that hides the evaluation result from the call site.
- **patent_classifier.py:268-275 (ml-007, critical)** — `feature_matrix_builder.fit_transform(feature_vectors)` runs on *all* feature vectors before any train/test split inside `train_from_dataframe`. The function's contract delegates splitting to the caller, but the API invites callers to pass full data and silently leak through the feature builder. Real leakage risk if callers don't split first.
- **trainer.py `_cross_validate` (rep-011)** — `ParameterGrid` iteration uses set semantics internally; iteration order across runs is not strictly stable. Minor reproducibility nit.
- **cet_classifier.py `_scores_to_classifications` (rep-007)** — `classifications.sort(key=lambda x: x.score, reverse=True)` can have ties (scores are `probas * 100`, so granularity is bounded). Sort is stable in Python so ties resolve in insertion order, which is itself non-deterministic earlier in the pipeline. Minor.

### Findings the tool confirmed (overlap with manual baseline)

The tool re-found and validated:

- C1 (split methodology, `trainer.py:118-127`) — confirmed via ml-008
- C3 (set iteration, `patent_classifier.py:281-291`) — confirmed via rep-011/rep-005
- H1 (CalibratedClassifierCV `random_state`, missing global seeds) — confirmed via rep-001/rep-009 (3 separate findings)
- M1 (no library versions in pickled models) — confirmed via rep-012 across all 3 model files
- M3 (`datetime.utcnow()` / naive `datetime.now()`) — confirmed via rep-010 in 3 files

### Findings the tool did NOT surface (manual baseline-only)

The tool's ai-training/rep/num scope doesn't directly target these, but they are real:

- C2 (hand-rolled precision/recall/F1 with `1e-10` epsilon, `cet_classifier.py:344-347`) — partially overlaps with `num-005` but tool didn't fire on it. Likely because the epsilon is small enough that the model judged it "intentional and safe."
- C4 (silent `except Exception` fit fallback, `patent_classifier.py:308-322`) — no scicode-lint pattern targets this anti-pattern directly. Stays a manual-only finding.
- H3 (cross-classifier calibration comparability for "primary" label) — methodology subtlety, not in scicode-lint's catalog.
- H4 (random vs temporal split for time-ordered SBIR data) — `ml-005` exists for this but didn't fire; the tool likely needs explicit time-column context to recognize the temporal dimension.
- H5 (4xx retry in HF client) — not in scope of the categories we ran.
- H6 (single-batch shape collapse) — not in scope.
- H7 (weight quantization in `multi_source_vectorizer.py`) — not in scope.

### Confirmed false positives from the tool

- **huggingface_inference.py:221-222 (high)** — Tool claims "epsilon is added AFTER the norm computation and division, meaning if all embeddings are zero vectors (norm=0), the division would produce inf/NaN." This is **wrong** — the code is `embeddings_array / (norms + 1e-8)`, epsilon is inside the divisor. Manual audit correctly identified this as clean.
- **Several "in-place numpy modification" findings on `X.copy()` then `X[..] *= ...` patterns** (`cet_classifier.py`, `multi_source_vectorizer.py`). The `.copy()` is explicit and intentional precisely to isolate the in-place mutation. Tool flagged them anyway, sometimes multiple times for the same code region.
- **Some "dict iteration order" findings** where iteration order is actually deterministic in Python 3.7+ for our use case.

### Confidence-weighted action items from the combined audit

**Fix before next retrain (high confidence — multiple sources agree):**

1. Split methodology — proper k-fold stratified CV (C1 + tool ml-008 + tool ml-007 train signature)
2. `CalibratedClassifierCV` `random_state` and global seeds (H1 + 3 separate tool rep-* findings)
3. `MultiLabelBinarizer` fit-before-split (new from tool — even if low-impact here, fix the pattern)
4. `patent_classifier` `feature_matrix_builder.fit_transform` before split (new from tool — real leakage risk via API contract)
5. Hand-rolled metrics → sklearn metrics with `zero_division=0` (C2 — tool agreed implicitly by not finding leakage but didn't directly flag the metric quality)

**Fix in next ML maintenance pass:**

6. Silent fit fallback in `patent_classifier.py` (C4 — manual-only finding)
7. Deterministic set iteration in `patent_classifier.py` + `ParameterGrid` (C3 + new tool finding)
8. ~~HF retry semantics + shape collapse (H5, H6)~~ — module removed 2026-07; no action needed
9. Library version persistence in saved models (M1 — confirmed)
10. Datetime hygiene (M3 — confirmed)

**Document as known limitations:**

- Cross-classifier calibration comparability (H3) — out of scope for the tool, important for the team
- Random split for time-ordered data (H4) — tool's ml-005 didn't catch it; worth an internal analysis pass to quantify the gap

**Don't fix:**

- Tool's false-positive on HF normalization epsilon (module since removed)
- Tool's "in-place mutation" flags on `X.copy()` then mutate-copy patterns
- Tool's dict iteration order flags where determinism is already guaranteed by insertion-order semantics

### What this run tells us about scicode-lint's value-for-money

- **3 net-new substantive findings** that would have been missed without the tool (MultiLabelBinarizer leak, feature_matrix_builder leak, train() signature)
- **~5 confirmed false positives** that needed manual review to dismiss
- **Strong agreement** on the seeding, datetime hygiene, version-persistence, and split-methodology findings — useful corroboration
- **~8 minutes of compute on local hardware** versus ~30+ minutes of focused human time for the equivalent manual pass

Net: worth running. The 3 new findings have non-trivial impact on the **CET classifier's** reported precision/F1 honesty (and indirectly, via the `cet_alignment` signal, on the rule-based transition scorer's measured precision against the CLAUDE.md ≥85% target). The false positives are cheap to triage. The run is fast enough to be a pre-merge gate if we wanted (we don't yet — ML PR cadence doesn't justify it).

## Next audit scope — rule-based transition scorer

This checklist exists for the **ML** subsystem. The **rule-based transition scorer** in `packages/sbir-ml/sbir_ml/transition/` carries the CLAUDE.md ≥85% precision target directly and has not been audited at the same depth. Different system, different failure modes, different methodology.

### Why scicode-lint doesn't apply

scicode-lint targets **ML methodology bugs** (data leakage, missing seeds, calibration errors, gradient management). The transition scorer is rule-based signal aggregation — six weighted signals (agency continuity, timing proximity, competition type, patent signal, CET alignment, vendor match) summed to a final score, classified by static thresholds. None of the 66 scicode-lint patterns target rule-based scoring methodology.

### Code surface in scope

Approximately **3,500 LOC of audit-relevant code**:

| File | LOC | Why it matters |
|---|---|---|
| `transition/detection/scoring.py` | 526 | Core scorer; signal weights and thresholds live here |
| `transition/detection/detector.py` | 489 | Detection pipeline; pulls features and invokes scorer |
| `transition/detection/evidence.py` | 574 | Evidence aggregation; what gets recorded per detection |
| `transition/evaluation/evaluator.py` | 509 | Where the ≥85% target is *measured* against ground truth |
| `transition/analysis/benchmark_evaluator.py` | 795 | Benchmark harness; how the historical claim was computed |
| `transition/features/cet_analyzer.py` | 420 | CET-signal extraction (the cascade from the ML audit lands here) |
| `transition/features/patent_analyzer.py` | 356 | Patent-signal extraction |
| `transition/features/vendor_resolver.py` | 448 | Vendor matching |
| `transition/features/vendor_crosswalk.py` | 580 | Vendor entity resolution |

The configuration files defining weights and thresholds are also in scope — `config/base.yaml` and any `transition/*.yaml` overrides.

### Questions the audit should answer

**Threshold calibration:**

1. When was the ≥85% precision target last *measured*, against what ground truth, and on what data slice? Is there a stored benchmark report?
2. Does the 0.85 score threshold actually produce ≥85% precision on the current data, or has the precision drifted as data grew?
3. Is precision measured on an out-of-sample test set, or on the same data used to calibrate weights? (Leakage at the system level.)

**Weight calibration:**

4. Who chose the signal weights (`agency_continuity.weight`, `timing_proximity.weight`, etc.)? Are they empirically tuned, expert-judgment, or arbitrary defaults?
5. Are any signals **correlated** in ways that cause double-counting? (e.g., same-agency contracts within a tight time window — does the agency-continuity signal independently capture what timing-proximity does?)
6. What's the sensitivity of precision-at-threshold to ±10% perturbations in each weight? (Identifies fragile weight choices.)

**Signal-level methodology:**

7. Each `score_*` method in `scoring.py` — does it handle missing data correctly? Does a missing agency field produce a zero score (correct) or a misleading default (incorrect)?
8. The `cet_alignment` signal: is it consuming raw CET-classifier outputs, or thresholded "high confidence" labels? Either choice has cascading implications from this ML audit.
9. Patent signal: when is the patent considered "associated" with the SBIR award? Filing date, publication date, application date? Patents filed BEFORE the SBIR can't be attributed to it (echoes the Bayh-Dole subject-invention discussion from prior conversations).
10. Vendor matching: how is "same vendor" determined across SBIR award records and federal contract records? UEI? Name fuzzy match? What's the false-match rate?

**Ground-truth labeling:**

11. What counts as a "Phase III transition" for evaluation purposes? Is the label sourced from SBIR.gov, from a manual labeling pass, from FPDS/USAspending heuristics, or some hybrid?
12. How stale is the ground truth? If labels were assembled in 2024 and we're evaluating in 2026, recent awards in transition have no label and are silently treated as non-transitions (depressing measured recall, inflating measured precision).
13. Are there ambiguous edge cases in the labeling protocol (e.g., a Phase III award via a different agency than the originating SBIR) — and how is the rule about them documented?

**Evaluation methodology:**

14. Is the precision measurement on a single static test set, or does it cross-validate?
15. Does the test set composition cover the relevant award-year distribution, or is it skewed toward easy years (where ground truth is denser)?
16. What's the confidence interval around the ≥85% claim? A 60-detection test set gives wide CIs; a 6,000-detection test set narrow ones.

### Methodology for the audit

Not LLM-as-judge. Three pass types:

1. **Code review pass** (~half day) — read `scoring.py`, `detector.py`, `evaluator.py`, and the four feature analyzers. Apply standard correctness review: missing-data handling, edge cases, double-counting, threshold drift. Catalog findings using the same Severity/Confidence taxonomy as this checklist.
2. **Configuration audit** (~quarter day) — read the YAML configs that set weights and thresholds. Trace each value back to its justification (commit history, design doc, or "unknown — needs investigation").
3. **Empirical sensitivity pass** (~1 day) — run the existing benchmark harness with perturbed weights (±10%) and perturbed thresholds (0.80, 0.85, 0.90). Plot precision vs. recall curves. Identify which signals carry real weight vs. which are decorative. Quantify the CI around the headline number.

### Deliverables

- A **transition-scorer-methodology-review.md** companion to this document, with the same Initial Findings / Resolved structure
- A **measured-precision baseline report** capturing the current state under the *current* methodology (so future changes have a comparison point)
- A **weight-sensitivity table** showing how each of the six signals' weight affects precision-at-threshold

### Estimated effort

~2 engineering days total: half day code review + quarter day config + 1 day empirical + half day write-up. Less than the ML audit took because the surface is more uniform (rule-based aggregation has fewer hidden failure modes than ML pipelines).

### When to do it

**Before any external claim referencing the ≥85% transition-scoring precision number**, including:

- Public reports or papers citing transition detection performance
- Documentation aimed at stakeholders who treat the threshold as a guarantee
- Releases that surface "high confidence" labels to end users as a quality signal

The CET classifier fixes from this audit's Phase 1 PRs will probably trigger a small shift in transition-scoring precision via the `cet_alignment` cascade. That's a good moment to do the transition-scorer audit, because re-measurement is needed anyway.

## Maintenance

- **scicode-lint version pin** — this checklist was derived from registry v1.0 dated 2026-03-15. Re-derive when the registry advances.
- **Pattern coverage** — 30 of 66 patterns are currently active. The PyTorch-specific patterns become load-bearing if/when raw `nn.Module` training lands in the codebase.
- **Findings tracking** — as critical/high findings are fixed, move them from "Initial findings" to a "Resolved" subsection with the resolving commit SHA. Don't delete — the historical record matters for understanding why specific patterns exist.
- **Two artifacts, two systems** — this checklist covers `ml/`. The forthcoming `transition-scorer-methodology-review.md` covers `transition/`. The CLAUDE.md ≥85% target lives in the latter; don't conflate.
