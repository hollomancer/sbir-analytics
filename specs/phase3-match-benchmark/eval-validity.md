# Eval validity: attributing the AUC, and de-biasing the lag

Status: **both analyses run and reproduced from committed code.** Prompted by external review (2026-07-17)
that the transition numbers, though promising, were not yet *interpretable*: a metric that rose after the
benchmark changed is a different exam, not an improvement.

## 1. The AUC gain was unattributed — now the text axis is isolated

Between #423 (ModernBERT-Embed, thin USAspending agreement text, classification framing → AUC ~0.56) and the
current ranker (TF-IDF, rich abstracts→notices, firm-clustered retrieval → 0.84–0.88), **three factors moved
at once**: text field, model, and task framing. The gain was therefore unattributable to any one.

`scripts/phase3_benchmark/text_richness_2x2.py` isolates the **text axis** by holding everything else fixed —
same 375 firms, same hard negatives, same TF-IDF model, same firm-clustered retrieval — varying only text
volume per side (query: award *titles* vs *abstracts*; target: NASA project *title* vs *description*):

| model = TF-IDF (fixed) | target = thin (title) | target = rich (description) |
|---|--:|--:|
| **query = thin (title)** | 0.655 | 0.827 |
| **query = rich (abstract)** | 0.769 | 0.872 |

**Text richness alone moves AUC 0.655 → 0.872 (+0.22) with the model held constant.** So the
ModernBERT→TF-IDF swap is *explanatorily unnecessary* — text is a sufficient cause, which is exactly what we
predicted before seeing the result (an informal pre-registration; predicting the direction ≠ isolating the
cause, which this now does). Two honest corrections to the earlier story:

- **Thin/thin is 0.655, not 0.5.** Thin text is *weaker*, not empty — "the embedding was fine, the text was
  empty" overstated it. Titles carry real signal.
- **Target richness (+0.17) dominates query richness (+0.11).** The follow-on notice/description text is where
  the discriminative content lives.

**Built and run** (`--negatives metadata`: same NASA TX taxonomy area + year ±2, different firm — the
NAICS-analogue; true-hard for 310/375 firms):

| | random neg | metadata-hard neg |
|---|--:|--:|
| thin/thin | 0.655 | 0.618 |
| rich/rich | 0.872 | **0.816** |
| **target main effect** | +0.138 | **+0.136** |
| query main effect | +0.080 | +0.062 |
| interaction | −0.069 | −0.057 |

**The target-richness effect is robust to negative construction (+0.138 → +0.136).** The feared artifact
would have collapsed it under proper hard negatives; it didn't — so the finding is real. What moves is the
*absolute* level: random negatives were ~0.05 optimistic (rich/rich 0.872 → **0.816**). Trustworthy absolute:
rich/rich ≈ **0.82** under metadata-hard negatives; DoD production (thin target) sits below that.

### Reproducible scripts
- `text_richness_2x2.py --negatives {random,metadata}` — the ablation under both negative regimes.
- `auc_by_target_length.py` — the operating curve (AUC by target-length decile; the step-function evidence).
- Pure cores tested in `tests/unit/scripts/test_eval_validity.py` (10 passed).

Not isolated here: the **model** and **task-framing** axes. #423's 0.56 sits *below* this 2×2's thin/thin
0.655 — the residual ~0.10 is the model + classification→retrieval-framing change, which we did not separately
control (the dense model is not installed in any environment on this machine). Defensible summary: *of the
~0.31 total move, ~0.22 is text richness (isolated, model constant); ~0.10 is model + task framing (not
separately isolated).*

## 2. The "median transition lag" is not a median

`scripts/phase3_benchmark/transition_survival.py`. Cohort = DoD SBIR firms (origin = earliest DoD SBIR award);
event = first coded DoD Phase III; firms with none are **censored** at the 2025 observation end.

- **13% of DoD SBIR firms (1,027 / 7,770) ever show an observed Phase III; 87% are censored.**
- **(a) Naive conditional median lag (event-only): 9y** — but this is conditional on transitioning *within the
  window* and is itself right-censored (long-lag transitioners still pending), so it is a **lower bound**.
- **(b) Kaplan-Meier, left-truncation-free (first DoD SBIR 2016+, n=4,509):** transitioned by year 2 = 3.8%,
  year 5 = 11.0%, year 7 = 16.0%. **Median time-to-Phase-III is NOT REACHED** — the survival curve never
  crosses 0.5 because most firms never transition.

**The unconditional median time-to-Phase-III is undefined.** Any single "N-year median lag" must be stated as
*conditional on transition* and as a *right-censored lower bound*. Censoring strengthens rather than weakens
"long lags are real": the true conditional lag is ≥ the observed 9y.

Caveat carried in the script: coded Phase III is observed only ~2016–2025, so a pre-2016 entrant's early
transition is unobservable (left truncation). (a) uses all entrants (sees long lags, but truncated early);
(b) restricts origin to 2016+ (truncation-free, but short follow-up). They bound the truth from opposite sides.

## What this changes

The defensible sentences replace the tempting ones:
- ~~"we fixed the ranker, AUC went 0.5→0.85"~~ → "the ranker is uninformative on thin text and informative on
  rich; text richness (+0.22, model constant) is a sufficient cause; ~0.10 of the historical move is
  model+framing we did not isolate."
- ~~"median transition lag ~6–9y"~~ → "unconditional median undefined (13% ever transition); conditional lag
  ≥9y, right-censored."

Pure cores (`firm_retrieval_auc`, `kaplan_meier`) are covered by `tests/unit/scripts/test_eval_validity.py`.
The remaining trust artifact — precision/recall/unsure/self-agreement from the blind hand-adjudication — is
in flight (`~/Documents/phase3_adjudication_*`); see the methodology memory for the standing rules.
