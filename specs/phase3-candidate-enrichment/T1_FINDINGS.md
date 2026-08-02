# T1 — Source Coverage + Leakage-Safety Inventory (the gate)

Ran on the 113 ground-truth transition contracts that matched `phase3_universe`
(57 sparse-description). **Verdict: STOP the cheap in-repo text-enrichment path (T2).
Pivot to non-text lineage features (T3).**

## Coverage × leakage class

| source | all | **sparse cells** | class |
|---|---|---|---|
| PSC code present | 100% | 100% | intrinsic (safe) |
| NAICS code present | 100% | 100% | intrinsic (safe) |
| Contract desc cites its own topic/sol # | 3% | **0%** | intrinsic (safe) |
| SBIR topic via prior award | 100% | 100% | **firm-linked (LEAKAGE)** |
| Firm has recovered notice text | 4% | 4% | intrinsic (safe) |

## The discrimination check (why coverage isn't enough)

A source only lifts ranking if it distinguishes the *true* contract from its
**same-agency decoys**. PSC/NAICS are universal but shared — `P(a random same-agency
mate shares the true contract's code)`:

| agency | PSC P(shared) | NAICS P(shared) |
|---|---|---|
| **DLA (logistics — the 0.21 cell)** | **0.92** | **0.92** |
| MDA | 0.26 | 0.60 |
| DHA | 0.30 | 0.33 |
| DTRA | 0.24 | 0.42 |

61% of all these contracts carry the *same* NAICS (541715, "R&D services"). So PSC/NAICS
enrichment would add **nearly identical category words to the true contract and its
decoys** — most severely in DLA, the exact cell that needs help. It cannot discriminate
where it matters.

## Why each lever fails the gate

- **PSC / NAICS** — safe + 100% coverage, but **non-discriminating** (DLA 0.92 shared).
  Adding them raises the true and decoy scores equally → ~zero ranking lift.
- **Contract cites its own topic/solicitation #** — the one rich *and* intrinsic signal,
  but present on **3% overall and 0% of the sparse cells**. Effectively absent.
- **SBIR topic description** — rich and discriminating, but **firm-linked**: reachable
  only through the firm→contract link the ranker is predicting. Using it plants the
  answer in the candidate (content leakage; `_scrub_identity` won't catch it).
  **Disqualified** per the T1 rule.
- **Recovered notice text** — rich + intrinsic, but **4% coverage** (the #481 grain wall).

**No leakage-safe source both covers the sparse cells and discriminates.** GO condition
not met → **STOP T2.**

## What survives (two expensive text options — flagged, not adopted)

1. **Deeper FPDS field pull** — the universe carries only the terse transaction
   description. A fuller FPDS/USASpending pull *might* expose richer intrinsic text
   (requirement descriptions, CLIN text). Uncertain; test coverage before building.
2. **J&A justification documents** — real prose, intrinsic — but retrieval for
   sole-source Phase III is uncertain and would be external scraping. Only if #1 fails
   and coverage looks real.

Neither is the primary path. Both are optional spikes.

## Decision → pivot to T3

The primary lever is **description-independent lineage features (T3)**, not text.
Critically, T3 must pass the *same* leakage test: each feature has to be computable at
packet time from `(firm abstract) × (open solicitation)` — e.g. agency continuity, NAICS
ancestry between the firm's SBIR and the solicitation, timing gap, prior-award count —
**not** from knowing the transition occurred. T2 (assembler) is shelved unless a spike on
option #1/#2 shows real, leakage-safe, discriminating coverage on the sparse cells.
