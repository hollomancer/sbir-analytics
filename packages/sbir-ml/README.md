# sbir-ml

SBIR ML / data science — CET classification, transition detection, and analysis
tools.

Houses the machine-learning and scoring layers of the pipeline: the Critical &
Emerging Technology (CET) classifier, the multi-signal Phase II → Phase III
transition detector, and the analytics that aggregate their outputs. Methodology
is documented under [`docs/ml/`](../../docs/ml/) and
[`docs/transition/`](../../docs/transition/).

## Installation

Installed automatically with the ML extra or the full pipeline:

```bash
pip install "sbir-etl[ml]"   # ETL library + this package
pip install sbir-analytics    # full pipeline (includes [ml])
```

Core deps: `sbir-etl`, `scikit-learn`, `tqdm`. Optional extras:

| Extra | Adds |
|-------|------|
| `sbir-ml[nlp]` | spaCy + huggingface-hub (NLP feature extraction) |
| `sbir-ml[modernbert-local]` | sentence-transformers + torch + transformers (local ModernBERT embeddings) |

## Key Entry Points

| Import | Purpose |
|--------|---------|
| `sbir_ml.ml.models.cet_classifier` — `CETClassifier` | Per-CET TF-IDF → logistic-regression classifier (0–100 scores) |
| `sbir_ml.ml.models.rule_engine` — `RuleEngine` | Post-ML rule layer (negative keywords, context boosts, agency priors) driven by `config/cet/classification.yaml` |
| `sbir_ml.transition.detection.scoring` — `TransitionScorer` | Six-signal composite transition scoring |
| `sbir_ml.transition.detection.detector` / `evidence` | Detection orchestration + evidence bundles |
| `sbir_ml.transition.features.vendor_resolver` — `VendorResolver` | UEI/CAGE/DUNS + fuzzy (`token_sort_ratio`) vendor matching |
| `sbir_ml.transition.features.cet_analyzer` / `patent_analyzer` | CET and patent signal extraction |
| `sbir_ml.transition.analysis.analytics` — `TransitionAnalytics` | KPI aggregation over detections |

## Notes

- Transition scoring changes must maintain the ≥85% precision benchmark
  (`scripts/phase_iii_precision_backtest.py`).
- The six scored signals and their default weights are documented in
  [`docs/transition/scoring-guide.md`](../../docs/transition/scoring-guide.md).
