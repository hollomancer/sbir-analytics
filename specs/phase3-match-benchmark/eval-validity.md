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
- **Dense does NOT rescue DoD (ModernBERT-Embed, same 968 firms):** all positives **0.659** — *worse* than
  TF-IDF 0.714, because procurement boilerplate ("OFFICE FURNITURE") carries less meaning than a NASA title,
  so the semantic model has nothing to read.
- **The 0.945 "rich-desc subset" is a SELECTION ARTIFACT — do not use it.** The ≥515-char subset (n=21) hits
  0.945, but those 21 are not "the 947 with more text" — they are self-selected on *substance*: 81% R&D-PSC
  (A*) vs 67.5% in the rest. Someone wrote 515+ chars *because* the work was substantive R&D, which is exactly
  what matches a Phase II abstract. So 0.945 confounds "has a description" with "is the kind of contract worth
  describing"; the counterfactual "mandate descriptions → 0.66 → 0.95" is unsupported. (This is the third
  instance of the same error — evaluate on the population that *has* a property, generalize to the one that
  *lacks* it; see also coded-vs-uncoded and NASA-vs-DoD.) **Cut from the memo.**
- **The sturdy finding is `thin ≠ thin`:** dense wins thin *NASA* (0.759 vs 0.658) but loses thin *DoD*
  (0.659 vs 0.714) — same model, same length, opposite result. Length was never the variable; **information
  content was.** Length is a proxy that held within NASA and inverted across corpora.

**§638 instrument — mandate a LINKAGE FIELD, not a character floor.** An earlier draft here argued for
~900 chars of description; that is Goodhart bait — mandate characters and you get characters. The data
already shows the failure: the longest-description decile (4,111–18,791 chars) scores **0.834, *below* the
923–1,635 bin's 0.910** — padding degrades, and DoD's default register is boilerplate, so a length mandate
mass-produces filler. The correct ask is a **structured field: parent SBIR award ID on the Phase III
contract record.** Detection → ~1.0, no NLP, no prose, no Goodhart — a pointer, not an essay; a smaller,
cheaper, more passable ask. The detection work's honest role is to show the field is *needed*, not to be the
detector. (The MSE dark-count exists precisely *because* this field is absent — it measures its cost.)

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

**This complicates any text-based §638 story:** a dense model is thin-text-robust on *NASA* titles (~0.76)
but that did **not** transfer to DoD boilerplate (0.659 < 0.714 TF-IDF) — because the DoD "desc" is a
procurement category label, not compressed meaning (`thin ≠ thin`). So neither "mandate longer descriptions"
nor "use embeddings" is the right lever for DoD. The correct instrument is the **structured linkage field**
(parent SBIR award ID) — see the §638 section below; text mandates are Goodhart-exposed and corpus-dependent.

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
