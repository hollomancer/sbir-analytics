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
