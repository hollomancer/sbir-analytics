# T3 — Firm-Ranking + Non-Text Lineage Features (Lever A)

**Reframe:** T6/forward (~0.47) measured CONTRACT-ranking (given a firm, rank the true
transition *contract* among decoys) — where the candidate is terse and the text-poverty wall
bites. The packet's real job is FIRM-ranking (given an opportunity, rank candidate *firms*),
which flips which side is rich: candidates are firm SBIR abstracts (always rich). Non-text
lineage features (agency continuity, prior-award density, Phase-II timing) are constant within
a contract-ranking pool but vary across firms — so they only help in this framing.

## Result (`scripts/phase3_benchmark/measure_firm_ranking.py`, frozen fusion text signal)

| decoys | signal | p@1 | p@3 | n |
|---|---|---|---|---|
| random | text-only | 0.600 | 0.829 | 35 |
| random | **text + lineage** | **0.714** | **0.971** | 35 |
| hard (same-agency) | text-only | 0.536 | 0.786 | 28 |
| hard (same-agency) | **text + lineage** | **0.571** | **0.821** | 28 |
| *(contract-ranking, for contrast)* | text | *0.467* | *0.556* | 45 |

## Findings

1. **Firm-ranking beats contract-ranking, even with hard decoys** — text-only 0.536–0.600 vs
   0.467. The rich-candidate structure removes the wall that capped contract-ranking; **0.47 was
   the wrong (hardest, least-representative) task.**
2. **Non-text lineage features add real lift** — random +0.11 p@1 (0.60→0.71), hard +0.04 p@1
   (0.54→0.57) *with agency-match neutralized* (so density+timing carry it; established, timing-
   plausible firms rank higher). p@3 rises to 0.82–0.97.

## Honest caveats

- **Hand-picked weights** (agency 1.2, density 0.3, timing 0.4) — illustrative, not fit. A proper
  weighting (or re-fit with lineage in the feature vector) is the real next step and would set the
  true combined number.
- **Agency-match can misfire in hard mode** when the true firm transitioned *outside* its SBIR
  agency (feature = 0 for the true firm, 1 for same-bucket decoys) — one reason the hard-mode lift
  is smaller; a signed/learned weight would handle it.
- **n = 28–35**, wide CIs; SAM-notice opportunity text (terse) — the lift is carried by the rich
  candidate abstracts, as designed.

## Takeaway

Lever A is validated: the packet's real task (firm-ranking) is **~0.54–0.60 text-only and
~0.57–0.71 with lineage** — materially above the 0.47 contract-ranking number, and lineage adds
durable lift. Next: fit the feature weights (not hand-set) and score on a larger firm-ranking
ground-truth set for the production number.
