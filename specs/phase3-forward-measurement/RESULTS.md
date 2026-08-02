# Forward-Representative Measurement of the Frozen Phase III Detector

**Question:** the T6 number (~0.467) is the *retrospective* task — rank a past transition
*contract* (terse FPDS text) among decoys. The packet's real job is *forward* — rank a firm
against an open *solicitation* (government-written notice text). Is forward performance secretly
higher, because the candidate finally has content? This closes that open question.

## Method

`scripts/phase3_benchmark/measure_forward.py` (self-contained; fully local, no API). Query =
firm's SBIR Phase I/II abstract (`award_data.csv`). Candidate = the government-written text of a
self-labeled SBIR Phase III notice naming that firm (SAM Contract Opportunities bulk extract,
materialized at `data/derived/phase3_selflabeled/`). Decoys = 9 other such notices. Scored with
the **frozen fusion detector** (word + char TF-IDF cosine, frozen `#467` coefficients). Firms
joined to abstracts by name-key prefix (SAM `Awardee` carries trailing address tokens).

## Result

| task | substrate | p@1 | p@3 | n |
|---|---|---|---|---|
| retrospective (T6) | terse FPDS contract text | 0.467 | 0.556 | 45 |
| **forward (this)** | **government-written notice text** | **0.469** | **0.656** | **32** |

**Forward = retrospective.** The detector on forward-grain solicitation/notice text scores
0.469@1 — statistically identical to 0.467. The forward task is **not** higher; the richer-looking
government notice text does not rescue it (p@3 is modestly higher, 0.656 vs 0.556).

## Interpretation

This settles the last open hope from the detector-ceiling analysis. Combined with the earlier
findings — terse contracts 0.467, boilerplate notices 0.429, self-authored grant abstracts
0.81–0.97 (a mirage), NOFOs generic/sparse — the picture is complete: **~0.47 is the detector's
real performance on both the retrospective and forward tasks, because no government-written
substrate is firm-specific *and* rich.** The ceiling is data-structural, not the model.
Deadline-primary + top-3 aid stands as the operating decision.

The remaining lever is **non-text lineage features** (separate effort, #484 T3) — signals that
don't depend on candidate text at all.
