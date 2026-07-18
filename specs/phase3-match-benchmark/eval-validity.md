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

The wall is not positive scarcity — it is that DoD does not write contract descriptions.

**Provenance caveat, up front (not in a limitations footnote):** those 5,091 positives are FPDS element-10Q
**SR3/ST3-coded** (5,565 SR3 + 786 ST3). The eval population **is the coded population** — the *complement*
of the claim, which is about the *uncoded* dark Phase III. So every within-DoD AUC below is an **upper bound
on a population we cannot sample.** If minimal data entry correlated across fields, uncoded Phase IIIs would
be even emptier and the detector would do worse in the wild.

**The actual within-DoD number (not a NASA extrapolation), `dod_within_retrieval.py`:**
- Rich Phase II abstract → Phase III `desc` target, metadata-hard negatives (same PSC + FY, different firm):
  **AUC 0.714** on 968 firms (thin target, median 78 chars) — squarely the thin-target regime, as the NASA
  step predicted. The rich-desc subset (≥515 chars, n=21) reaches 0.833. This is the number the memo needs;
  the NASA work exists to establish the step-function that explains *why* it's 0.714 and not 0.87.

**§638 drafting number — the floor is ~900, not 150.** DoD Phase III descriptions clearing each length:
40c → 53.6%, 150c → 11.5%, 515c → 1.0%, **900c → 0.0%**. A 150-char mandate buys only the bottom of the step
(~+0.04); the plateau (~0.89) needs **~900 chars of substantive technical scope, which 0% of DoD currently
meet.** Lobby for the character count, not "a description."

**Mechanism test — the two facts are NOT yet one mechanism.** Within coded Phase III, description emptiness
does *not* correlate with sparsity in other fields: NAICS/PSC are ~always present (0% missing) regardless of
description length; corr(desc-len, missing NAICS|IDV) = 0.01. So it is **not** generalized "sloppy CO data
entry" — the structured/enforced fields are filled; only the free-text description is empty because it is an
**unenforced optional field.** That reframes (and arguably strengthens) the §638 ask — *make the description
mandatory like the codes already are* — but it means the "reporting failure and detection failure share one
root cause" claim is **not proven at the contract level** (I cannot run the direct test — it needs the
uncoded population's descriptions, the very thing I can't sample). State it as a strong hypothesis, not a
finding.

### Reproducible scripts
- `text_richness_2x2.py --negatives {random,metadata}` — the ablation; `longest_shared_word_run`,
  `paired_bootstrap` are the reuse + CI probes.
- `auc_by_target_length.py` — the operating curve (step, not gradient).
- `dod_transition_inventory.py` — the DoD positive count + description emptiness.
- `dod_within_retrieval.py` — the real within-DoD AUC (0.714), the §638 floor table, the mechanism test.
- `dense_vs_sparse_2x2.py` — the model axis (ModernBERT-Embed vs TF-IDF; requires a torch venv, not repo .venv).
- Pure cores tested in `tests/unit/scripts/test_eval_validity.py` (14 passed).

### The model axis — now run (`dense_vs_sparse_2x2.py`, ModernBERT-Embed on MPS)
The richness gradient is **TF-IDF-specific.** Identical NASA firms + seed-0 negatives, under ModernBERT-Embed:

| cell | TF-IDF | ModernBERT-Embed |
|---|--:|--:|
| thin/thin | 0.658 | **0.759** |
| thin/rich | 0.829 | 0.831 |
| rich/thin | 0.766 | 0.757 |
| rich/rich | **0.872** | 0.806 |
| target main effect | +0.139 | **+0.060** |
| query main effect | +0.076 | **−0.013** |

Two flips, both consequential:
- **On thin text the dense model wins (0.759 vs 0.658)** — it reads meaning from a ~40-char title where the
  lexical model has nothing to overlap. So #423's 0.56 was **not** "dense models fail on thin text"
  (ModernBERT gets 0.76 on thin titles here); it was the classification framing / even-thinner agreement
  text. The model swap was never the villain.
- **On rich text the sparse model wins (0.872 vs 0.806)** — jargon-lexical overlap dominates when text is
  abundant (the earlier "sparse beats dense" result). So the two models are complementary: dense for thin,
  sparse for rich.
- **The richness main effects nearly vanish under dense** (target +0.139 → +0.060; query +0.076 → −0.013).
  "Text richness is a sufficient cause" holds **only under TF-IDF** — the scope caveat the review demanded
  was load-bearing.

**This complicates the §638 story honestly:** a dense model is far more thin-text-robust, so "mandate longer
descriptions" is not the only lever — "use embeddings" competes, and would lift thin-DoD detection toward
~0.76 on its own. Caveat: the thin text here is *descriptive titles* ("Additive Manufacturing of Refractory
Metal…"); DoD contract boilerplate ("OFFICE FURNITURE") carries even less meaning, so a dense model may not
fully rescue it. The defensible ask pairs both: **a substantive description field _and_ a semantic model.**

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
