# Phase III transition — adjudication protocol

Written **before** labeling, so the rule doesn't drift toward the model. Frozen 2026-07-17.

## Files
- `specs/phase3-match-benchmark/adjudication/phase3_adjudication_blind.csv` — **90 cases** (regenerated 2026-07-18, reshuffled, new case_ids),
  **scores stripped**. Label these.
- `specs/phase3-match-benchmark/adjudication/phase3_adjudication_KEY.csv` — case_id → model_score / rank / link_evidence / stratum / prior label. **Do not open until labeling is done.**
- `specs/phase3-match-benchmark/adjudication/phase3_transition_leads_audit_v2.csv` — the score-visible source (your original 71 labels live here; treat as *provisional/anchored*).

## The unit and the question
One row = one **(firm, candidate-event)** pair. Candidate = a DoD notice, a NASA TechPort project, or a
**DoD contract** (see the dark-cell stratum). **Question:** does this candidate event represent a Phase III /
transition of *this firm's SBIR-funded technology*? Apply the same rule to every row regardless of type.

## The strata (hidden in the KEY — you can't tell which is which while labeling)
- **detector candidates** (60 DoD notices + 15 cross-agency NASA projects) — top-ranked by the model. Labeling
  these gives the detector's **precision/recall**.
- **dark-cell probe** (15 `dod_contract` rows) — a RANDOM sample of DoD contracts to SBIR firms that are
  **post-SBIR, un-flagged by both signals** (no SR3/ST3 code, no "SBIR PHASE III" text, not the SBIR award
  itself). **Purpose (reset 2026-07-18): an EXISTENCE SCAN + label-noise contribution — NOT a count-check.**
  We measured the frame these live in (~131,000 contracts); the 949 estimate implies a ~0.7% Phase-III rate,
  so 15 rows expect ~0.1 hits and **cannot** validate the 949 (that would need ~700 rows). So: finding even
  ONE confirmed uncoded Phase III here is a valuable existence proof; finding zero means nothing (it's the
  expected outcome either way — do not read "0/15" as "no dark cell"). **Expect this to be HARD** — these
  contracts have near-empty descriptions (median ~37 chars), so many will be honest "Unknown," and that high
  Unknown rate is itself a finding (the empty-field problem defeats *human* adjudication too). Judge on the
  firm's Phase II abstract + the contract's PSC/scope/timing/amount.

## Decision rule (decide these now, apply mechanically)
Answer **Y** only if BOTH hold:
1. **Same firm** — the candidate is performed by the same entity as the SBIR awardee. Same-firm includes:
   renamed firm; majority-acquired firm whose tech team/line continues; operating subsidiary; spin-off
   carrying the technology. **Not** same-firm: different UEI with only a name coincidence; a prime that
   merely subcontracts the firm.
2. **Same technology** — the candidate continues, commercializes, or matures the *specific* technology of an
   identifiable prior SBIR award (evidence: shared product name, technical continuity in the description, a
   cited contract/topic number).

Answer **N** if: different firm; OR same firm but a clearly unrelated technology/product line; OR the event
predates the firm's SBIR entry (`years_since_first_sbir` < 0 with no plausible earlier award).

Answer **Unknown** (do NOT force a binary) if: firm identity is ambiguous (name collision, unclear
acquisition); OR technical relatedness can't be judged from the text given; OR the dates conflict
irreconcilably. **The Unknown rate is a finding** — it measures irreducible ambiguity in the source data.

Also fill: `confidence_H_M_L`, `entity_same_firm` (Y/N/unsure — record the identity judgment separately from
the transition judgment), and `evidence_notes` (what decided it).

- **sibling stratum (C091–C105, appended 2026-07-18)** — unflagged task orders on **high-purity Phase III
  vehicles** (≥50% of the vehicle's enumerated orders are SR3/ST3-coded; the KEY records the vehicle and its
  coded-sibling count). These are direct-observation dark candidates — expected prevalence is HIGH (the
  vehicle exists for Phase III work), the opposite of the dark-cell probe. Their Y-rate = the precision of
  "sibling-of-coded" as a capture rule; each confirmed Y is an observed uncoded Phase III. **Blinding note:**
  appended mid-marking, so this block is knowably all-sibling (a reshuffle would have lost your in-progress
  labels). No model scores exist for these; judge tech continuity exactly as elsewhere. Note the firm shown
  is the VEHICLE holder's dominant coded vendor — verify same-firm as usual.

## Blinding (rule #1)
`model_score`, `rank`, `link_evidence`, `stratum`, and `data_flag` are removed from the sheet. Judge on the
text and dates. **Residual caveat:** the sheet still shows the model's *chosen* best-match award
(`match_award_*`) — that is a linkage *hypothesis*. You may reject it; if the candidate doesn't connect to
*any* SBIR work you'd recognize for this firm, it's N regardless of what the match column suggests. (If you
want maximal rigor, ask me for the variant that shows the firm's full award list instead of the model's pick.)

## Freeze & threshold (rule #2)
This 75-case set is frozen. Do **not** tune any score cutoff using these labels — a set used to pick a
threshold is training data, not a test set. Precision/recall get computed *after* labels are joined to the KEY.

## Self-agreement (rule #5)
11 of the 75 are **blind re-adjudications** of pairs you already labeled score-visible (you can't tell which).
After labeling, joining to the KEY gives two independent numbers:
- **Self-agreement** (blind vs blind, if any re-appear twice) and **anchoring delta** (blind label vs your
  prior score-visible label) → your **label-noise floor**. If you disagree with your past self 8% of the
  time, no model can be meaningfully scored above ~92% agreement. That ceiling is the point.

## What this produces (the trust artifact)
Precision, recall, Unknown rate, and self-agreement — per stratum (`dod_identity`, `dod_textonly`,
`cross_agency_dod_nasa`). The README line *"entity resolution is probabilistic and will include false
positives"* becomes a sentence with numbers in it. The cross-agency 15 specifically gate whether we build
the DoD non-SBIR puller.
