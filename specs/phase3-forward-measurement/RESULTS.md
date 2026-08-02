# Abstract→Notice Candidate-Substrate Control (superseded as "forward" by #484 A)

> **CORRECTION (2026-08-02).** This was framed as the "forward" measurement, but it is
> **abstract → notice**, not the packet's forward task. It keeps the *contract-ranking
> orientation* (query = firm abstract; candidate = the firm's transition **award/intent
> notice** text; rank the true notice among decoy notices). The packet's real forward job is
> **firm-ranking** (query = opportunity; candidates = rich firm abstracts), measured in
> **#484 (Lever A)** at 0.54–0.71 — materially higher. So the honest scope of this result is
> narrow: *a notice is no richer a **candidate** than a contract (both ~0.47)*. It does NOT
> measure the forward packet task. Two residual caveats: the candidates here are **award/intent
> notices**, not open **Sources Sought** solicitations (the packet's literal forward input); and
> the true forward task (rank firms vs an open solicitation) is still unlabeled — Sources Sought
> don't name a firm. See #484 `T3_RESULTS.md` for the actual forward/firm-ranking measurement.

---

# (original) Forward-Representative Measurement of the Frozen Phase III Detector

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
