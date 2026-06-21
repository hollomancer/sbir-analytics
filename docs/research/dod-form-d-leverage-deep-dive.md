# DoD Form D leverage decomposition — Branch heterogeneity is the headline

**Date:** 2026-06-21
**Companion to:** [sbir-form-d-fundraising-analysis.md](sbir-form-d-fundraising-analysis.md), [form-d-leverage-bootstrap-findings.md](form-d-leverage-bootstrap-findings.md)
**Script:** [`scripts/data/dod_form_d_leverage_decomposition.py`](../../scripts/data/dod_form_d_leverage_decomposition.py)

## Summary

The bootstrap analysis surfaced DoD's aggregate Form D leverage as **1.011x [0.842, 1.214]** — statistically distinguishable from every other large-cohort agency. This deep-dive decomposes that aggregate to test which of four candidate explanations actually drive it.

**The headline finding is that the DoD aggregate masks ~9× spread across Branches:**

| Branch | Program $B | Ratio (95% CI) | Read |
|---|---|---|---|
| **Air Force** | 9.02 (37%) | **2.118x [1.602, 2.666]** | Above cross-agency average; commercial-tech-grade leverage |
| Army | 3.65 (15%) | 1.010x [0.683, 1.421] | At the DoD aggregate |
| DARPA | 1.83 (7%) | 1.160x [0.740, 1.716] | Slightly above |
| **Navy** | 6.10 (25%) | **0.406x [0.242, 0.605]** | Statistically distinguishable from Air Force; drives the low aggregate |
| **MDA** | 1.48 (6%) | **0.246x [0.098, 0.423]** | Essentially no private capital; tight CI |
| DTRA | 0.20 (1%) | 0.120x [0.037, 0.243] | Lowest among large-enough cohorts |

**Re-reading the DoD 1.011x:** "DoD doesn't attract private capital" is *wrong* as a uniform agency statement. Air Force does (2.12x, brushes the NSF 3.23x range). The aggregate is dragged down by Navy + MDA + DTRA (combined $7.78B, 32% of DoD program $) — branches with classified-heavy or mission-specific portfolios.

Air Force vs Navy are statistically distinguishable at 95% (Air Force CI [1.60, 2.67] vs Navy CI [0.24, 0.61] don't overlap). The "DoD" finding is really two findings stacked: a healthy-leverage Air Force cohort and a low-leverage Navy/MDA cohort.

## What the four decompositions show

### 1 — Branch heterogeneity (the headline)

Full table from the decomposition script:

| Branch | Program $B | Matched firms | Form D $B | Ratio (95% CI) |
|---|---|---|---|---|
| Air Force | 9.02 | 659 | 19.10 | **2.118x** [1.602, 2.666] |
| Navy | 6.10 | 98 | 2.48 | **0.406x** [0.242, 0.605] |
| Army | 3.65 | 140 | 3.69 | **1.010x** [0.683, 1.421] |
| DARPA | 1.83 | 81 | 2.12 | **1.160x** [0.740, 1.716] |
| MDA | 1.48 | 22 | 0.36 | **0.246x** [0.098, 0.423] |
| DHA | 0.72 | 50 | 0.82 | **1.139x** [0.702, 1.672] |
| SOCOM | 0.40 | 19 | 0.35 | 0.867x [0.342, 1.682] |
| DLA | 0.30 | 13 | 1.46 | 4.862x [0.314, 12.523] |
| CBD | 0.20 | 20 | 0.32 | 1.564x [0.564, 2.857] |
| DTRA | 0.20 | 7 | 0.02 | 0.120x [0.037, 0.243] |
| SDA | 0.19 | 7 | 0.26 | 1.393x [0.161, 3.399] |
| OSD | 0.14 | 2 | 0.00 | 0.035x [0.004, 0.065] |

Methodological notes:
- Each firm is attributed to its **dominant DoD Branch** by award $.
- Bootstrap uses 1,000 firm-level resamples with seed 42 (same protocol as the cross-agency analysis).
- **DLA's 4.86x is essentially noise** — only 13 firms; CI [0.31, 12.52] spans an order of magnitude. Do not cite as a point estimate.
- The Air Force, Navy, Army, DARPA, MDA, and DHA results are credible (n ≥ 50 firms each).

### 2 — Form D participation rate by Branch

This separates "do DoD firms file Form D at all" from "what's the ratio when they do." A low ratio could come from either a low filer rate OR small per-filer raises.

| Branch | DoD firms | With high-tier Form D | Participation rate |
|---|---|---|---|
| **CBD** | 58 | 18 | **31.0%** |
| **SDA** | 21 | 5 | **23.8%** |
| **DHA** | 215 | 46 | **21.4%** |
| Air Force | 3,539 | 605 | **17.1%** |
| DARPA | 525 | 77 | 14.7% |
| SOCOM | 137 | 18 | 13.1% |
| DTRA | 58 | 7 | 12.1% |
| Army | 1,122 | 135 | 12.0% |
| DLA | 117 | 12 | 10.3% |
| OSD | 24 | 2 | 8.3% |
| MDA | 267 | 19 | 7.1% |
| **Navy** | 1,495 | 91 | **6.1%** |

Participation = firm has at least one high-tier Form D match AND positive in-window, non-excluded Form D raised dollars. (The "and positive raised after filters" condition was a Copilot review fix to PR #342; earlier rates were a couple of points higher because they counted firms whose only offerings were PIF-excluded or out-of-window.)

Key observations:

- **Navy's low ratio is driven by BOTH low participation AND low per-firm raises.** Only 6.1% of Navy SBIR firms have a high-tier Form D with positive in-window raises — less than half the Air Force rate. Of those 91 firms, they collectively raise just $2.48B against $6.10B of program SBIR.
- **CBD and DHA have the highest participation rates** (31.0% and 21.4%). Both are mission areas with high overlap with commercial biotech / pharma — exactly the verticals where VC funding is most active.
- **MDA's 7.1% participation** is consistent with the classified-/mission-specific hypothesis. Missile defense work doesn't generate VC-fundable products.
- **Air Force's 17.1%** is the highest large-cohort participation rate in DoD — and combined with its high per-firm ratio explains its 2.12x leverage.

### 3 — M&A event rate vs Form D participation

If DoD firms commercialize via *acquisition* instead of private capital, low-Form-D Branches should have high M&A rates. This tests the substitution hypothesis using M&A data from PR #286.

| Branch | DoD firms | Form D rate | M&A event rate | Read |
|---|---|---|---|---|
| **Navy** | 1,495 | 6.1% | **10.3%** | **M&A higher (1.7×) — strongest substitution signal** |
| **MDA** | 267 | 7.1% | **8.6%** | M&A higher (1.2×) — weak substitution signal |
| DLA | 117 | 10.3% | 9.4% | comparable |
| Army | 1,122 | 12.0% | 9.7% | Form D higher (1.2×) |
| DTRA | 58 | 12.1% | 8.6% | Form D higher (1.4×) |
| DARPA | 525 | 14.7% | 11.0% | Form D higher (1.3×) |
| OSD | 24 | 8.3% | 4.2% | Form D higher (2.0×) |
| SOCOM | 137 | 13.1% | 5.1% | Form D higher (2.6×) |
| Air Force | 3,539 | 17.1% | 6.6% | Form D higher (2.6×) |
| DHA | 215 | 21.4% | 8.4% | Form D higher (2.5×) |
| CBD | 58 | 31.0% | 5.2% | Form D higher (6.0×) |
| SDA | 21 | 23.8% | 0.0% | Form D only (no M&A) |

**The acquisition-substitution hypothesis holds for Navy and weakly for MDA.** In every other branch, Form D filings substantially outnumber M&A events — typically by 1.2–6×.

This is a methodologically significant finding: the "DoD firms commercialize via acquisition not private capital" hypothesis is **branch-specific, not DoD-wide**. Navy is the one branch where it has empirical support; Air Force and DHA actively contradict it.

### 4 — DoD-only vs multi-agency firms (with denominator caveat)

| Cohort | Firms | With Form D | Form D $B | Ratio (95% CI) |
|---|---|---|---|---|
| DoD-only firms (no other agencies) | 5,090 | 624 | 18.82 | 0.768x [0.594, 0.958] |
| Multi-agency firms (DoD + at least one other) | 2,559 | 417 | 12.29 | 0.501x [0.368, 0.646] |

⚠️ **Important methodology caveat:** Both ratios use the DoD program total ($24.50B) as the denominator. Multi-agency firms split their SBIR receipt across agencies — they contribute less DoD-program-$ per firm than DoD-only firms do, so their ratio against the DoD denominator is artificially deflated. **This is NOT evidence that multi-agency firms are less commercial** — it's a denominator artifact.

What this comparison actually shows: of the $24.50B counted Form D capital flowing from DoD-overlapping firms, the firms that are pure DoD contribute 0.768x and the firms that share with other agencies contribute 0.501x. The sum exceeds the bootstrap's 1.011x because the cohort in this decomposition includes firms whose **dominant** agency is non-DoD but who have some DoD activity (whereas the bootstrap attributes each firm to its dominant agency).

The honest takeaway from this decomposition: **DoD-only firms collectively account for more of the DoD program leverage than DoD-secondary firms do.** Whether that's because they're more commercial or just because they "fully count" against the DoD denominator isn't disambiguated here. A cleaner test would compute per-matched-firm leverage with each firm's DoD-only SBIR $ as denominator — flagged as future work.

## Synthesis: which of the four candidate explanations actually hold?

The bootstrap doc raised four candidate explanations for DoD's 1.011x. Re-evaluating each with the decomposition data:

1. **DoD SBIR firms are systematically less commercially-oriented (gov-services / classified-heavy / SBIR-as-sole-revenue).** 
   **Partially true, branch-specific.** Holds for Navy (6.1% participation), MDA (7.1%), DTRA (12.1%) — all classified/mission-specific. Does NOT hold for Air Force (17.1%), DHA (21.4%), CBD (31.0%).

2. **DoD firms commercialize via federal contracts rather than VC (FPDS substitution).**
   **Cannot evaluate without USAspending pulls.** Flagged as future work.

3. **Defense IP and classification restrictions discourage outside investment.**
   **Plausible for the low-Form-D branches** (Navy, MDA, DTRA) — these are exactly the branches where classified work is concentrated. Air Force and DHA contradict the "DoD = classified-heavy" framing.

4. **Acquisition path replaces capital-raising path.**
   **Branch-specific and weaker than the bootstrap doc hinted.** Navy has M&A rate > Form D rate (1.7×); MDA also shows weak M&A-over-Form-D (1.2×). Every other branch has the opposite. The acquisition-substitute hypothesis is concentrated in classified-mission branches, not DoD-wide.

The decomposition revises the bootstrap doc's framing in one important way: instead of "DoD doesn't attract private capital," the more accurate statement is:

> **"DoD's 1.011x reflects a bimodal subportfolio: a commercial-tech-oriented Air Force (2.12x, 37% of program $) and a classified-/mission-specific Navy+MDA+DTRA cluster (~0.3–0.4x, 32% of program $). The aggregate is the volume-weighted average, not a uniform DoD characteristic."**

## What this means for policy / interpretation

- **Stop citing "DoD 1:1 leverage" as a uniform agency-level finding.** It's not; it's an average of two very different portfolios.
- **Air Force SBIR looks similar to commercial-tech ecosystem leverage** (2.12x, brushes NSF range). If the policy question is "is DoD SBIR commercially generative," the answer for Air Force is *yes*.
- **Navy SBIR is genuinely low-leverage** with both low participation (6.1%) and low per-firm raises. Combined with the strongest-substitution-signal M&A finding (Navy M&A rate 1.7× Form D rate), this looks like a portfolio where commercialization happens via *prime contractor acquisition* rather than private-capital growth.
- **MDA and DTRA leverage is essentially zero** — consistent with classified work that can't attract outside capital. Probably correct outcome for those mission areas; not a methodology failure.
- **DHA and CBD have unusually high participation rates** (21.4%, 31.0%) and ratios in the 1.1–1.6x range. These mission areas overlap with biotech/medical devices where commercial markets exist. They're the DoD's bright spots for private-capital leverage.

## Future work

1. **FPDS substitution test.** Pull USAspending federal contract data for DoD SBIR firms and compute follow-on-federal-contract ratio per Branch. If Navy's low Form D is matched by high follow-on federal contracts, the substitution channel is confirmed.

2. **Per-firm leverage decomposition.** Compute each firm's leverage using its own SBIR $ as denominator (inner-join cohort, similar to the bootstrap doc's complementary view). This would disambiguate the multi-agency cohort interpretation in Decomposition 4.

3. **Time-series Branch decomposition.** The published doc shows the year-by-year ratio for the full cohort. Decomposing by Branch over time would surface whether Air Force's high leverage is recent (e.g., post-AFWERX) or persistent across the window.

4. **Acquirer-type analysis for Navy.** Of Navy SBIR firms that exit via M&A, who's acquiring them? If it's defense primes (Northrop, Lockheed, L3Harris, Leidos), the "Navy commercializes via acquisition not VC" framing is confirmed. If it's commercial buyers, a different story.

## Reproducibility

```bash
.venv/bin/python scripts/data/dod_form_d_leverage_decomposition.py
```

Default config: 1,000 bootstrap iterations, seed 42, year window 2009-2024, minimum branch program-$ threshold $100M. Outputs `reports/ml/dod_form_d_decomposition.{json,md}` (gitignored). Runs in ~5 seconds on a development laptop.

Same dependency set as the bootstrap script (numpy only; no new deps).
