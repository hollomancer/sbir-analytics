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

## Spike (ran the deeper-FPDS + solicitation check — both dead ends)

Fetched the **full USASpending award record** (`/api/v2/awards/`) for 12 sparse GT
contracts (DLA/MDA/DHA/DTRA/SOCOM), live API:

1. **Deeper award text — dead end.** The API `description` is *identical* to our cached
   terse one (14–40 chars). The only field ≥80 chars anywhere in the record is
   `naics_description` = "RESEARCH AND DEVELOPMENT IN THE PHYSICAL, ENGINEERING, AND LIFE
   SCIENCES" — the generic 541715 label, **the same string on all 12**. No richer
   intrinsic contract text exists at the award level.
2. **Contract solicitation — dead end (the pointer is missing).** The solicitation *is* a
   rich source, but `solicitation_identifier` is populated on **1 of 12 (~8%)** — FPDS
   does not record which solicitation these Phase III awards were let under (most are
   SBIR set-aside "full-and-open after exclusion of sources" or sole-source). The one
   with an ID (`HDTRA111R0026`) would need a separate, uncertain 2011-era SAM.gov pull.
   Reaching a solicitation any *other* way routes through the firm's prior SBIR topic —
   which is **leakage** and is the *wrong* solicitation (the Phase I/II topic, trivially
   similar to the firm's own abstract). Intrinsic + rich + covered: not achievable.

**J&A justification documents** — the remaining theoretical prose source — would be
external scraping with the same missing-pointer problem (no captured solicitation/J&A
reference on the contract). Not pursued.

**Spike verdict: STOP confirmed on both the award-text and solicitation angles.**

## Population insight (why the solicitation source is structurally unavailable)

A solicitation pointer lives on **competed** procurement actions; a canonical Phase III is
sole-source (SBIR-derived, no re-competition), so it has none. Measured across 35 GT
contracts: **sole-source 0% pointer**, SBIR-set-aside 17%, overall 17%. The deeper
consequence: our ground-truth set was built by matching the **"SBIR PHASE III" marker**,
so it is the *marked, mostly-sole-source* population — which is exactly the population that
**lacks** a solicitation. The solicitation-rich transitions are the **competed / unmarked
(dark)** ones, which a text-marker label method structurally excludes. So the two
populations — *text-rich* and *text-labelable* — are nearly disjoint. Enrichment cannot be
rescued for the marked set, and the unmarked/dark set is a **separate detection target**
needing a different label source (solicitation→award genealogy), not text enrichment.
This bounds the deadline-primary verdict to the *marked* Phase III population validated in
#481.

## Decision → pivot to T3

The primary lever is **description-independent lineage features (T3)**, not text.
Critically, T3 must pass the *same* leakage test: each feature has to be computable at
packet time from `(firm abstract) × (open solicitation)` — e.g. agency continuity, NAICS
ancestry between the firm's SBIR and the solicitation, timing gap, prior-award count —
**not** from knowing the transition occurred. T2 (assembler) is shelved unless a spike on
option #1/#2 shows real, leakage-safe, discriminating coverage on the sparse cells.
