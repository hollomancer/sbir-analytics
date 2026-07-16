# Phase III Undercount — Validation Plan (50-case precision review)

> **Status:** Frame frozen; sample drawn; awaiting human review.
> Frozen frame: **168 flags, $308.1M, frame_hash `a776e08617cb`** (DoD 141 exact + 11 text-scan;
> NASA 16). Regenerate frame + sample: `scripts/phase3_benchmark/freeze_and_sample.py` (seed
> `20260715`) → `data/derived/phase3_undercount_flags_frozen.csv` +
> `data/derived/phase3_undercount_validation_sample_50.csv` (gitignored; the frame_hash locks them).

## Purpose
Estimate the **precision** of the automated status-denial flags before the 168 count (or ~$308M) is
cited. The flag rule ("described 'SBIR PHASE III', no SR3/ST3 code") has false-positive modes a human
must adjudicate:
- description names Phase III but the action is Phase I/II, a *future* Phase III option, or a negation;
- a key/join artifact made a coded contract look uncoded;
- the contract isn't genuinely SBIR Phase III despite the words.

## The frozen frame
168 flags, locked (hash `a776e08617cb`) so the sample is reproducible and a reviewer can re-draw it.
Columns: `flag_id, agency, sub_agency, firm, award_id, gen_id, amount_usd, layer, action_date,
description, usaspending_url, disposition`.

## The sample (50 cases)
Stratified random by **agency × dollar band** (≥$5M / $1–5M / <$1M), seed `20260715`, NASA oversampled
to ~9 to validate the smaller agency (DoD 41 / NASA 9). Each row carries `_design_weight` (= stratum
population ÷ sampled) so precision can be reweighted to the 168-flag population, not just the sample.

## Reviewer instructions
For each case: open `usaspending_url`, read the description + award, set **`disposition`**:
- `confirmed_uncoded_phase3` — genuinely SBIR/STTR Phase III with no SR3/ST3 code;
- `false_positive` — not Phase III, or actually coded (note why);
- `unclear` — insufficient info.
Record `reviewer` and `notes` (esp. the failure mode for false positives).

## Computing precision
- **Unweighted:** confirmed ÷ 50, Wilson 95% CI.
- **Weighted (population estimate):** Σ(confirmed × design_weight) ÷ Σ(design_weight) → apply to the
  168 confirmed flags: "N ± CI genuinely uncoded Phase III (~$X M)."
- Dispositions feed back into the frame's `disposition` column as **labels** for a future classifier.

## Scope note
Validates the **confirmed / text-evidenced** layer only (168). The **modeled dark ~1,073** is
unenumerable (see [dark-undercount-analysis.md](./dark-undercount-analysis.md)) and cannot be sampled —
its uncertainty is the extrapolation's, not a precision question.
