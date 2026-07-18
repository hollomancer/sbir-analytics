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

**Do not read the corner-to-corner +0.22 — it's the diagonal, the least actionable summary.** The factorial
decomposition (all figures **under TF-IDF**):

| Effect | Computation | Value |
|---|---|--:|
| Target richness (main) | avg[(.827−.655), (.872−.769)] | **+0.138** |
| Query richness (main) | avg[(.769−.655), (.872−.827)] | **+0.080** |
| Interaction | .103 − .172 | **−0.069** (sub-additive) |

Text richness is a *sufficient* cause (the ModernBERT→TF-IDF swap is explanatorily unnecessary), as
predicted before the result. But three sharper reads:

- **Thin/thin is 0.655, not 0.5** — thin text is *weaker*, not empty; "the embedding was fine, the text was
  empty" overstated it.
- **The two levers are asymmetric in what we control.** Target richness (+0.138) does ~1.7× the work of query
  richness (+0.080), **and it is exogenous** — contracting officers write the contract description, many write
  nothing. The lever we control (query = our own SBIR abstracts) is the weak one: a free, shippable +0.080.
  The +0.22 headline implies a reachable 0.872 we **cannot reach by choice.**
- **Negative interaction** — the levers are partially redundant; with a rich target, going rich on the query
  buys only +0.045.

### The operating curve is a step, not a gradient
AUC by target-description-length decile (rich/rich cell, n=377, under TF-IDF) is **flat within the rich range**
(Pearson r=0.04): 0.81 at 171–515 chars, saturating ~0.87–0.91 above ~900 chars. The gain is a **threshold**,
not a ramp — titles (~40 chars) → 0.655; descriptions >150 chars → ~0.81; then flat. (This also softens the
"TF-IDF mechanically rewards length" worry: length stops helping once past the threshold.)

**Production sits below the step.** DoD's USAspending `desc` is median **42 chars, 88% under 150** — DoD
targets are in title-length territory (~0.65–0.81), **not** the saturated 0.87. Detection degrades exactly
where descriptions are empty — the *same* root cause as Phase III miscoding. Mandating the description field
(a §638 mechanism) would move both the reporting failure and the detection failure at once.

### Negative provenance (the real threat to the table — checked)
The 2×2 negatives are `rng.choice(others)`: **uniformly random within the same register** (all non-SBIR NASA
projects), **seed-fixed so the identical negative set is used across all four cells**, and **never
similarity-mined under any representation.** So the artifact of "hard negatives mined under thin text separate
trivially under rich text" **cannot apply** — the cross-cell deltas are clean by construction. Honest flip
side: random-within-register negatives are *easier* than metadata-hard negatives (same agency/year/NAICS,
different firm), so the **absolute** AUCs are optimistic; only the **deltas** are trustworthy. Metadata-hard
negatives are the right upgrade before any absolute number ships.

**Built and run** (`--negatives metadata`: same NASA TX taxonomy area + year ±2, different firm — the
NAICS-analogue; true-hard for 310/375 firms). **This is a robustness check under harder negatives, NOT an
artifact refutation** — the similarity-mining artifact was dead on arrival last turn (negatives are
`rng.choice`, seed-fixed, never mined), so no experiment was needed for it. All four cells, both regimes:

| cell | random | metadata-hard | metadata, 310 true-hard only |
|---|--:|--:|--:|
| thin_query / thin_target | 0.658 | 0.618 | 0.610 |
| thin_query / rich_target | 0.829 | 0.783 | 0.770 |
| rich_query / thin_target | 0.766 | 0.710 | 0.688 |
| rich_query / rich_target | 0.872 | 0.815 | 0.796 |
| **target main effect** | +0.139 | +0.135 | **+0.134** |
| query main effect | +0.076 | +0.062 | **+0.052** |
| interaction | −0.066 | −0.059 | −0.053 |

- **Target richness is robust to negative *difficulty*** — +0.139 → +0.134 (clean 310). Firm-clustered
  **paired bootstrap** of the difference (same 375 firms in both conditions, so correlated errors cancel):
  Δtarget = **+0.004, 95% CI [−0.008, +0.016]** — straddles 0, so "essentially unchanged" is defensible, not
  eyeballed.
- **The query effect moved, and I under-flagged it.** +0.080 → +0.062 (all) → **+0.052** on the clean 310 —
  down ~30%. The controllable, shippable lever is worth **+0.052**, not +0.080. Still free; quote the honest
  number. (The 65 fallback firms — rare TX × thin year, still on random negatives — carried an inflated query
  effect of +0.114; the target effect held there too, so de-blending only cost the query number.)
- **Absolute level:** random negatives were ~0.06–0.08 optimistic (rich/rich 0.872 → **0.796** on clean 310).
  Trustworthy absolute rich/rich ≈ **0.80**.
- **Text-reuse ruled out.** Longest contiguous shared word-run, positive (query, own target) vs negative
  pairs: median **2 vs 2**, ≥8-word runs **1% vs 0%**. Positives do not share copied spans that negatives
  lack — the signal is distributed technical vocabulary, not plagiarism, so it is *not* the fragile
  string-overlap result and should survive an embedding model / rewrite. (Caveat retained: TX areas are
  coarse; a finer taxonomy control could still lower the absolute a little.)

### The binding constraint (DoD) — the spine
`scripts/phase3_benchmark/dod_transition_inventory.py`. Everything above ran on NASA (rich text). The memo's
subject is DoD. The count:

- **DoD Phase II→III positives: 5,091 contracts across 974 firms — abundant, not scarce.**
- **Target text (Phase III `desc`) is empty: median 43 chars, 87.5% below the 150-char floor, 12.5% usable.**

The wall is not positive scarcity — it is that DoD does not write contract descriptions. This is the *same*
empty field that produces the Phase III miscoding: **the reporting failure and the detection failure share
one root cause.** A §638 mandate to populate the description field moves both. (The measurement is pointed at
NASA only because NASA writes the text; the DoD number stands as the finding, not a gap to be closed with
more modeling.)

### Reproducible scripts
- `text_richness_2x2.py --negatives {random,metadata}` — the ablation; `longest_shared_word_run`,
  `paired_bootstrap` are the reuse + CI probes.
- `auc_by_target_length.py` — the operating curve (step, not gradient).
- `dod_transition_inventory.py` — the DoD positive count + description emptiness.
- Pure cores tested in `tests/unit/scripts/test_eval_validity.py` (13 passed).

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
- ~~"we fixed the ranker, AUC went 0.5→0.85"~~ → "under TF-IDF, text richness is sufficient; the *exogenous*
  target-description effect (+0.138) dominates the controllable query effect (+0.080); DoD descriptions sit
  below the richness threshold, so real DoD operating AUC is ~0.65–0.81, not 0.87. Absolute values await
  metadata-hard negatives; only cross-cell deltas are trustworthy today."
- ~~"median transition lag ~6–9y"~~ → "unconditional median undefined (13% ever transition); conditional lag
  ≥9y, right-censored."

Pure cores (`firm_retrieval_auc`, `kaplan_meier`) are covered by `tests/unit/scripts/test_eval_validity.py`.
The remaining trust artifact — precision/recall/unsure/self-agreement from the blind hand-adjudication — is
in flight (`~/Documents/phase3_adjudication_*`); see the methodology memory for the standing rules.
