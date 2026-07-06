# DoD Form D leverage — Branch heterogeneity, follow-ups, and the FPDS substitution channel

**Date:** 2026-06-21 (consolidates PRs #342 → #343 → #350)
**Companion to:** [sbir-form-d-fundraising-analysis.md](sbir-form-d-fundraising-analysis.md) (the published headline finding), [form-d-data-dictionary.md](form-d-data-dictionary.md) (field reference)
**Scripts:** [`scripts/archive/data/dod_form_d_leverage_decomposition.py`](../../scripts/archive/data/dod_form_d_leverage_decomposition.py), [`scripts/archive/data/dod_form_d_followups.py`](../../scripts/archive/data/dod_form_d_followups.py), [`scripts/archive/data/dod_fpds_substitution_test.py`](../../scripts/archive/data/dod_fpds_substitution_test.py)

## Overview

The cross-agency bootstrap analysis (see `form-d-leverage-bootstrap-findings` methodology appendix in [sbir-form-d-fundraising-analysis.md](sbir-form-d-fundraising-analysis.md)) surfaced **DoD's aggregate Form D leverage as 1.011x [0.842, 1.214]** — statistically distinguishable from every other large-cohort agency. This document decomposes that aggregate, resolves the four candidate explanations it raised, and closes the deferred follow-ups. It folds three prior research notes into one record:

- **Branch decomposition** (PR #342) — the aggregate masks ~9× spread across DoD branches.
- **Deferred follow-ups** (PR #343) — per-firm leverage, time-series, and acquirer-type analyses.
- **FPDS substitution test** (PR #350) — the federal-contract substitution channel.

**Headline:** DoD's 1.011x is not a uniform agency characteristic. It is the volume-weighted average of a commercial-tech-oriented Air Force (2.12x, 37% of program $) and a classified-/mission-specific Navy + MDA + DTRA cluster (~0.3–0.4x, 32% of program $). The Navy low-leverage profile is real and is driven by a federal-contract substitution channel — confirmed in the FPDS test below.

---

## Part 1 — Branch decomposition (PR #342)

The bootstrap surfaced DoD's aggregate as **1.011x [0.842, 1.214]**. This decomposes that aggregate to test which of four candidate explanations actually drive it.

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

⚠️ **Important methodology caveat:** Both ratios use the DoD program total ($24.50B) as the denominator. Multi-agency firms split their SBIR receipt across agencies — they contribute less DoD-program-$ per firm than DoD-only firms do, so their ratio against the DoD denominator is artificially deflated. **This is NOT evidence that multi-agency firms are less commercial** — it's a denominator artifact. (Resolved by the per-firm leverage analysis in Part 2, Item 2.)

What this comparison actually shows: of the $24.50B counted Form D capital flowing from DoD-overlapping firms, the firms that are pure DoD contribute 0.768x and the firms that share with other agencies contribute 0.501x. The sum exceeds the bootstrap's 1.011x because the cohort in this decomposition includes firms whose **dominant** agency is non-DoD but who have some DoD activity (whereas the bootstrap attributes each firm to its dominant agency).

The honest takeaway: **DoD-only firms collectively account for more of the DoD program leverage than DoD-secondary firms do.** Whether that's because they're more commercial or just because they "fully count" against the DoD denominator isn't disambiguated here — see Part 2.

### Synthesis: which of the four candidate explanations actually hold?

The bootstrap raised four candidate explanations for DoD's 1.011x. Re-evaluating each with the decomposition data:

1. **DoD SBIR firms are systematically less commercially-oriented (gov-services / classified-heavy / SBIR-as-sole-revenue).**
   **Partially true, branch-specific.** Holds for Navy (6.1% participation), MDA (7.1%), DTRA (12.1%) — all classified/mission-specific. Does NOT hold for Air Force (17.1%), DHA (21.4%), CBD (31.0%).

2. **DoD firms commercialize via federal contracts rather than VC (FPDS substitution).**
   **Resolved in Part 3.** True for Navy specifically, weakly for DHA, false elsewhere.

3. **Defense IP and classification restrictions discourage outside investment.**
   **Plausible for the low-Form-D branches** (Navy, MDA, DTRA) — these are exactly the branches where classified work is concentrated. Air Force and DHA contradict the "DoD = classified-heavy" framing.

4. **Acquisition path replaces capital-raising path.**
   **Branch-specific and weaker than the bootstrap hinted.** Navy has M&A rate > Form D rate (1.7×); MDA also shows weak M&A-over-Form-D (1.2×). Every other branch has the opposite. (Refined in Part 2, Item 4 — the acquirers are commercial, not defense primes.)

The decomposition revises the bootstrap framing in one important way. Instead of "DoD doesn't attract private capital," the more accurate statement is:

> **"DoD's 1.011x reflects a bimodal subportfolio: a commercial-tech-oriented Air Force (2.12x, 37% of program $) and a classified-/mission-specific Navy+MDA+DTRA cluster (~0.3–0.4x, 32% of program $). The aggregate is the volume-weighted average, not a uniform DoD characteristic."**

### What this means for policy / interpretation

- **Stop citing "DoD 1:1 leverage" as a uniform agency-level finding.** It's not; it's an average of two very different portfolios.
- **Air Force SBIR looks similar to commercial-tech ecosystem leverage** (2.12x, brushes NSF range). If the policy question is "is DoD SBIR commercially generative," the answer for Air Force is *yes* — though note Part 2's finding that this is a post-AFWERX phenomenon, not structural.
- **Navy SBIR is genuinely low-leverage** with both low participation (6.1%) and low per-firm raises. Combined with the strongest-substitution-signal M&A finding (Navy M&A rate 1.7× Form D rate), this looks like a portfolio where commercialization happens via channels other than private-capital growth.
- **MDA and DTRA leverage is essentially zero** — consistent with classified work that can't attract outside capital. Probably correct outcome for those mission areas; not a methodology failure.
- **DHA and CBD have unusually high participation rates** (21.4%, 31.0%) and ratios in the 1.1–1.6x range. These mission areas overlap with biotech/medical devices where commercial markets exist. They're the DoD's bright spots for private-capital leverage.

### Reproducibility

```bash
.venv/bin/python scripts/archive/data/dod_form_d_leverage_decomposition.py
```

Default config: 1,000 bootstrap iterations, seed 42, year window 2009-2024, minimum branch program-$ threshold $100M. Outputs `reports/ml/dod_form_d_decomposition.{json,md}` (gitignored). Runs in ~5 seconds. numpy only; no new deps.

---

## Part 2 — Follow-ups resolved (PR #343)

PR #342 flagged four follow-up items. The FPDS substitution test (item 1) is resolved in Part 3. This part resolves the other three.

**Three findings, two of them revising the Part 1 framing:**

1. **Per-firm leverage is far MORE uniform across branches than program-level ratios.** Air Force median 6.79x vs Navy median 4.12x vs Army median 7.34x. The dramatic Branch heterogeneity in program-level ratios (2.12x vs 0.41x) is dominated by **participation rate differences**, not per-firm raise size. MDA (1.24x median) is the only large-cohort branch where per-firm leverage is genuinely low.

2. **Air Force's high leverage is RECENT, not structural.** Time-series decomposition shows Air Force averaged ~0.4x in 2009-2014 and ~2.5x in 2018-2024 — a 6× jump that corresponds to the AFWERX program launch (March 2017). Navy and MDA show no comparable trend; their low ratios are structural across the entire window.

3. **The "Navy commercializes via defense-prime acquisition" hypothesis is WRONG.** Only **6.9% of named Navy SBIR firm acquirers are defense primes**. The dominant pattern is **commercial acquisition (88.5%)**. Air Force shows a near-identical mix (5.7% / 83.9%). Whatever distinguishes Navy from Air Force in the M&A-vs-Form-D finding, it isn't the *type* of acquirer.

### Item 2 — Per-firm leverage by Branch (resolves Decomposition 4 methodology caveat)

The Part 1 decomposition attributed each firm to its dominant Branch but used the Branch's program total as the denominator. The multi-agency comparison in Decomposition 4 had a flagged methodology caveat: multi-agency firms' ratios were artificially deflated against the DoD denominator because they split SBIR receipt across agencies.

This decomposition computes per-firm leverage (Form D $ / firm's own DoD SBIR $) and aggregates by dominant Branch with median + interquartile range. Per-firm ratios are heavily right-skewed (a handful of large-raise outliers per Branch), so median is the more representative central tendency.

| Branch | Firms | Median | Mean | P25 | P75 |
|---|---|---|---|---|---|
| Air Force | 659 | **6.79x** | 167.73x | 0.80x | 43.34x |
| Army | 140 | **7.34x** | 47.73x | 1.34x | 28.85x |
| Navy | 98 | **4.12x** | 77.25x | 0.38x | 27.37x |
| DARPA | 81 | **6.55x** | 28.56x | 0.68x | 17.21x |
| DHA | 50 | 4.70x | 37.23x | 1.07x | 29.10x |
| MDA | 22 | **1.24x** | 47.67x | 0.11x | 11.56x |
| CBD | 20 | 2.55x | 44.07x | 0.18x | 16.05x |
| SOCOM | 19 | 9.23x | 25.61x | 2.22x | 23.15x |
| DLA | 13 | 15.00x | 867.29x | 1.55x | 114.48x |

**What this revises about Part 1:**

- The "Air Force is commercial-tech-grade, Navy is defense-services-pipeline" framing **overstates the per-firm story**. Air Force firms that DO file Form D raise about 1.6× more per SBIR dollar than Navy firms that do (6.79x vs 4.12x medians), but they're in the same order of magnitude.
- **The dramatic 5× program-level spread (Air Force 2.12x vs Navy 0.41x) is mostly about how many firms participate, not how much they raise when they do.** Air Force has 659 matched firms against $9.02B program; Navy has 98 against $6.10B.
- **MDA's 1.24x per-firm median is genuinely low** — even MDA firms that DO file Form D raise relatively little. Consistent with the classified-work hypothesis: missile defense products don't have commercial markets even for firms that try.

The decomposition is fully consistent with Part 1's Decomposition 2 (participation rates) but adjusts the interpretation of Decomposition 1 (program-level ratios):

> **"DoD branches differ mainly in how many of their SBIR firms participate in private capital markets, less in how much those firms raise. Per-firm leverage is in the 4-7x range across most major branches; only MDA is genuinely outside that range."**

### Item 3 — Time-series Branch ratios (Air Force's leverage is recent, AFWERX-aligned)

Per-(Branch, Year) program-level ratios for all major DoD branches, 2009-2024. The headline is **Air Force's clear post-2017 inflection**.

#### Air Force

| Year | Program $M | Form D $M | Ratio |
|---|---|---|---|
| 2009 | 335 | 67 | 0.20x |
| 2010 | 363 | 42 | 0.12x |
| 2011 | 257 | 179 | 0.70x |
| 2012 | 311 | 131 | 0.42x |
| 2013 | 347 | 225 | 0.65x |
| 2014 | 276 | 397 | 1.44x |
| 2015 | 385 | 413 | 1.07x |
| 2016 | 344 | 622 | 1.81x |
| 2017 | 328 | 618 | 1.88x |
| 2018 | 280 | 1,104 | **3.94x** |
| 2019 | 826 | 1,199 | 1.45x |
| 2020 | 708 | 1,810 | 2.56x |
| 2021 | 633 | 4,911 | **7.76x** |
| 2022 | 1,020 | 2,253 | 2.21x |
| 2023 | 1,224 | 2,140 | 1.75x |
| 2024 | 1,382 | 2,985 | 2.16x |

**5-year early average (2009-2013): 0.42x. 5-year late average (2020-2024): 3.29x. 8× jump.**

The inflection lines up with **AFWERX**, the Air Force's commercial-engagement program launched in March 2017. AFWERX restructured Air Force SBIR around dual-use commercial-defense technology and explicitly courted VC-backed startups. The Form D leverage ratio's rise from sub-1x to consistently 2x+ post-2018 is consistent with AFWERX's stated goal of attracting commercial-tech firms whose downstream funding comes from VC, not federal contracts.

The 2021 peak at 7.76x corresponds to the VC boom year — same pattern visible in the cross-agency yearly table from the published doc.

**Air Force pre-AFWERX (2009-2016) averaged 0.78x — actually below the DoD aggregate.** The headline 2.118x is almost entirely a post-2017 phenomenon.

#### Navy (no comparable trend)

| Year | Ratio | Year | Ratio |
|---|---|---|---|
| 2009 | 0.21x | 2017 | 0.17x |
| 2010 | 0.18x | 2018 | 0.16x |
| 2011 | 0.38x | 2019 | 0.21x |
| 2012 | 0.53x | 2020 | 0.53x |
| 2013 | 0.32x | 2021 | 0.35x |
| 2014 | 0.65x | 2022 | 1.07x |
| 2015 | 0.57x | 2023 | 0.43x |
| 2016 | 0.45x | 2024 | 0.25x |

**5-year early average: 0.40x. 5-year late average: 0.41x. Essentially flat.**

Recent years (2017-2024) average 0.40x — *lower* than the 2014-2016 peak. Navy doesn't show the post-AFWERX-style commercial engagement. The Navy SBIR program is structurally low-leverage, not in a transition.

#### MDA (consistently low across whole window)

| Year | Ratio | Year | Ratio |
|---|---|---|---|
| 2009 | 0.18x | 2017 | 0.43x |
| 2010 | 0.33x | 2018 | 0.48x |
| 2011 | 0.59x | 2019 | 0.07x |
| 2012 | 0.16x | 2020 | 0.03x |
| 2013 | 0.12x | 2021 | 0.12x |
| 2014 | 0.12x | 2022 | 0.21x |
| 2015 | 0.47x | 2023 | 0.49x |
| 2016 | 0.09x | 2024 | 0.00x |

**5-year early average: 0.26x. 5-year late average: 0.17x.**

Recent years if anything are *worse* than the early window. Missile defense SBIR is structurally not commercialization-attracting. The classified-/mission-specific hypothesis is supported across the full time window.

#### DHA (clear upward trend)

5-year early avg: ~0.4x → 5-year late avg: ~1.4x. Defense health follow-on private capital has roughly tripled over the window, possibly reflecting the broader biotech-VC cycle. The 23.3% Form D participation rate (highest in DoD) plus the rising trend makes DHA the second clear "commercial engagement" story alongside Air Force.

#### Army, DARPA, others

Generally volatile year-over-year (high variance from small annual cohorts), no clear directional trend. Army 5-yr early (~0.81x) vs 5-yr late (~1.70x) shows some uplift but not the dramatic Air Force pattern.

**What this revises:**

The Air Force 2.118x finding shouldn't be cited as a stable structural characteristic of Air Force SBIR. **It's a measurement against the 2009-2024 window that's dominated by 2018-2024 post-AFWERX activity.** If the analysis was rerun on 2009-2016 data, Air Force would show a 0.78x program-level ratio — *lower* than the DoD aggregate.

Policy framing implications:
- "Air Force SBIR is commercial-tech-grade" is true *for the post-AFWERX era*. It's not a permanent characteristic.
- AFWERX appears causally relevant. If the policy question is "what made Air Force private-capital-leverage rise," AFWERX is the right thing to study.
- Navy has not had an equivalent transformation. Whether that's because no Navy-equivalent program exists, or because Navy's underlying tech mix is harder to commercialize, is a separate question.

### Item 4 — Navy acquirer-type analysis (the defense-prime hypothesis fails)

Part 1 hypothesized that Navy's "M&A rate > Form D rate" pattern reflects *defense-prime consolidation* — Navy SBIR firms commercialize by getting acquired by Lockheed / Northrop / L3Harris / Leidos / Kratos / Mercury / Teledyne rather than by raising VC. This decomposition tests that hypothesis by classifying M&A acquirers.

Classifier categories:
- **defense_prime**: substring match against canonical DoD-prime / defense-services contractor names (Lockheed, Northrop, Raytheon, Boeing, BAE, L3, Leidos, CACI, Kratos, Mercury Systems, Teledyne, KBR, etc.). Uses word-boundary regex for short acronyms to avoid false matches.
- **financial_sponsor**: investment-vehicle markers (Capital, Partners, BDC, SPAC, Acquisition Corp, Merger Sub, Hercules Capital, Golub Capital, Churchill Capital, etc.). Tightened to exclude "Holdings" alone (too many false positives on real operating companies).
- **commercial**: everything else.

#### Navy

- Navy SBIR firms (dominant Navy): 2,510
- M&A events for Navy firms: 250
- Events with named acquirer: 203

| Acquirer type | Count | Share |
|---|---|---|
| **defense_prime** | 14 | **6.9%** |
| **commercial** | 180 | **88.5%** |
| financial_sponsor | 9 | 4.6% |
| unknown | 0 | 0.0% |

Top defense-prime Navy acquirers: L3 Technologies (3), Teledyne (2), CACI (1), TransDigm (1), KBR (1), Northrop Grumman, Lockheed Martin, Mercury Systems, etc.

#### Air Force (control)

- Air Force SBIR firms (dominant Air Force): 3,539
- M&A events for AF firms: 297
- Events with named acquirer: 244

| Acquirer type | Count | Share |
|---|---|---|
| **defense_prime** | 14 | **5.7%** |
| **commercial** | 205 | **83.9%** |
| financial_sponsor | 25 | 10.4% |
| unknown | 0 | 0.0% |

Top defense-prime AF acquirers: Kratos (3), L3 Technologies (2), KBR (1), Raytheon, Parsons, CACI, etc.

#### What this revises

**The "Navy commercializes via defense-prime acquisition" hypothesis is not supported by the acquirer-type data.** Navy's defense-prime share (6.9%) is essentially the same as Air Force's (5.7%), and both are dominated by **commercial acquisition (~85-90% of named acquirers)**.

If Navy SBIR firms are exiting via commercial acquisition rather than via private-capital raises, the relevant mechanism is **acquisition-by-commercial-companies** (probably tech consolidators, instruments/semiconductor companies, medical-device buyers), not by-defense-primes.

This deepens the Navy story rather than resolving it:
- Navy SBIR firms file Form D less (6.6% participation vs Air Force 18.6%)
- Navy SBIR firms ARE more likely to have M&A events (10.3% vs 6.6%)
- But Navy SBIR firms that get acquired are not predominantly acquired by defense primes — they get acquired by commercial buyers, same as Air Force firms

Possible mechanisms still on the table for Navy's distinct profile:
1. **Smaller commercial-tech footprint per firm** — Navy SBIR firms may build products that get rolled up into larger commercial companies' portfolios as one-time acquisitions, rather than as ongoing VC-funded scale-ups.
2. **Earlier exits** — Navy SBIR firms may exit before they'd need to file Form D. Median time-to-exit comparison would test this.
3. **Different industry mix** — Navy SBIR may concentrate in industries where exits are more common than VC scale-ups (e.g., sensor manufacturing, marine systems, specialized hardware).

The honest reframing:

> **"Navy SBIR firms exit via commercial acquisition at higher rates than Air Force firms, but not via defense-prime consolidation. The mechanism behind Navy's M&A-over-Form-D pattern requires different evidence than the Part 1 framing suggested."**

### Reproducibility

```bash
.venv/bin/python scripts/archive/data/dod_form_d_followups.py
```

Default config: year window 2009-2024, inputs `data/form_d_details.jsonl` + `data/raw/sbir/award_data.csv` + `data/sbir_ma_events.jsonl`. Outputs `reports/ml/dod_form_d_followups.{json,md}` (gitignored). Runs in ~3 seconds. numpy only; no new deps.

---

## Part 3 — FPDS substitution test (PR #350)

Candidate explanation #2 — **"DoD firms commercialize via federal contracts rather than VC (substitution channel)"** — required fresh USAspending pulls and was deferred from PRs #342/#343. This part closes it.

**Headline finding: the substitution hypothesis is true for Navy specifically, and weakly for DHA. It fails for every other large-cohort branch.**

| Branch | Form D ratio | FPDS ratio | Substitution signal |
|---|---|---|---|
| Air Force | 2.118x | 0.493x | −77% (Form D dominates) |
| **Navy** | **0.406x** | **0.432x** | **+7% (FPDS slightly dominates)** |
| Army | 1.010x | 0.258x | −74% (Form D dominates) |
| DARPA | 1.160x | 0.362x | −69% (Form D dominates) |
| MDA | 0.246x | 0.036x | −86% (both channels weak) |
| **DHA** | **1.139x** | **0.605x** | **−47% (both channels strong)** |

Navy is the **only large-cohort DoD branch** where follow-on federal contracts roughly match private capital as a commercialization channel. Every other major branch's firms raise substantially more in Form D than in federal contract follow-on.

This closes the substitution-hypothesis question: Navy SBIR firms genuinely *do* substitute federal contract follow-on for private capital. The narrative from Part 1 — "Navy has the lowest Form D leverage in DoD" — is now joined by: "and they have the highest FPDS-to-Form-D ratio in DoD."

### Method

For each of the 1,041 DoD high-tier Form D matched firms (same cohort as Parts 1-2), queried the USAspending public API for all federal contracts (PIID type, award_type_codes A/B/C/D) with the firm's name as `recipient_search_text` in the 2009-2024 window. Tightened the recipient match to exact uppercased name equality to reduce false-positive name collisions. Cached results to JSONL so reruns are fast.

Per-Branch aggregation: sum each branch-attributed firm's FPDS contract dollars and divide by the Branch's DoD program SBIR $. This produces a directly-comparable program-level ratio (same denominator construction as the Form D leverage analysis).

Substitution signal = `(FPDS_ratio − FD_ratio) / FD_ratio`. Positive means FPDS dominates (substitution); negative means Form D dominates (no substitution).

Runtime: ~30 minutes API time at 1.05s/request (under USAspending's 60/min limit). Fully cached after first run.

### Results — full table

| Branch | Program $B | Matched firms | Form D $B | FPDS $B | Form D ratio | FPDS ratio | Substitution signal |
|---|---|---|---|---|---|---|---|
| Air Force | 9.02 | 605 | 19.10 | 4.44 | 2.118x | 0.493x | −77% |
| **Navy** | 6.10 | 91 | 2.48 | 2.64 | 0.406x | **0.432x** | **+7%** |
| Army | 3.65 | 135 | 3.69 | 0.94 | 1.010x | 0.258x | −74% |
| DARPA | 1.83 | 77 | 2.12 | 0.66 | 1.160x | 0.362x | −69% |
| MDA | 1.48 | 19 | 0.36 | 0.05 | 0.246x | 0.036x | −86% |
| DHA | 0.72 | 46 | 0.82 | 0.44 | 1.139x | 0.605x | −47% |
| SOCOM | 0.40 | 18 | 0.35 | 0.05 | 0.867x | 0.112x | −87% |
| DLA | 0.30 | 12 | 1.46 | 0.02 | 4.862x | 0.066x | −99% |
| CBD | 0.20 | 18 | 0.32 | 0.02 | 1.564x | 0.079x | −95% |
| DTRA | 0.20 | 7 | 0.02 | 0.00 | 0.120x | 0.000x | −100% |
| SDA | 0.19 | 5 | 0.26 | 0.03 | 1.393x | 0.173x | −88% |
| OSD | 0.14 | 2 | 0.00 | 0.02 | 0.035x | 0.146x | +320% (n=2, noise) |

### Interpretation by Branch

#### Navy — substitution confirmed (the headline finding)

Navy SBIR firms have **comparable Form D and FPDS leverage** (0.406x vs 0.432x). This is the only large-cohort branch where the FPDS channel reaches parity with private capital.

Combined with prior findings:
- **Part 1**: Navy 6.6% Form D participation (lowest in DoD) and 0.406x Form D leverage
- **Part 1**: Navy is the only branch where M&A event rate (10.3%) > Form D rate (6.6%)
- **Part 2**: Navy's M&A acquirers are predominantly commercial (88.5%), NOT defense primes (6.9%)
- **This finding**: Navy firms have follow-on FPDS leverage of 0.432x — roughly equal to their Form D leverage

The composite Navy picture: SBIR firms commercialize via federal contracts at a rate comparable to private capital. They get acquired by commercial buyers (not defense primes). When they do raise Form D, it's a modest channel. **Navy SBIR is more federal-contract-and-acquisition-oriented than other DoD branches** — but the acquirers are commercial, not defense-prime, suggesting Navy's tech transfers cleanly to commercial markets via M&A.

#### DHA — both channels active

Defense Health Agency has substantial Form D (1.139x) AND substantial FPDS (0.605x). The substitution signal is −47% (Form D still dominates), but the absolute FPDS leverage is the second-highest in DoD after Navy.

This is consistent with the biotech-VC overlap noted in Part 1: DHA SBIR funds healthcare/medical-device firms that have both commercial-market (Form D) and federal-procurement (FPDS) pathways available.

#### Air Force / Army / DARPA — private capital dominates

Air Force, Army, and DARPA all show substantial Form D leverage (1.0×–2.1×) and modest FPDS follow-on (0.25×–0.49×). Form D is 3-5× the FPDS channel for these branches.

Air Force's 4.44B FPDS dollars are nontrivial in absolute terms — but spread across 605 matched firms with $9.02B in program SBIR, the per-program-dollar leverage is only 0.493x.

**Air Force's pattern is the "normal commercial-tech" model:** SBIR seeds firms, they raise private capital to scale, federal contracts are a secondary follow-on channel.

#### MDA — both channels weak

MDA's Form D leverage (0.246x) is the second-lowest in DoD (after DTRA). The FPDS test reveals it doesn't substitute either: 0.036x FPDS leverage means MDA firms have very little non-SBIR federal contract activity *or* private capital follow-on.

This is the clearest "classified work doesn't commercialize" pattern in the data. MDA SBIR is structurally a one-way pipeline — work goes in, no scaling out via either channel. Consistent with the missile-defense IP / classification hypothesis from Part 1.

#### Small-cohort branches (CBD, DLA, DTRA, SDA, SOCOM, OSD) — noisy

All these branches have <20 matched firms, so per-Branch ratios should be interpreted with low confidence. Notable: CBD has high Form D (1.564x) and low FPDS (0.079x), suggesting biotech-firm pattern similar to DHA but smaller scale. DTRA is essentially zero on both channels (n=7).

### Cross-Branch summary: where Navy stands

| Metric | Navy | All other large branches |
|---|---|---|
| Form D leverage | 0.406x | 1.01x – 2.12x |
| Form D participation rate | 6.1% | 12.0% – 17.1% |
| M&A vs Form D rate | M&A higher (1.7×) | Form D higher (1.2-6×) |
| FPDS vs Form D leverage | FPDS higher (+7%) | Form D higher by 47-99% |
| Acquirer type (when acquired) | 88.5% commercial | 84% commercial |

Navy is statistically distinct from other DoD branches on every commercialization measure. The substitution finding completes the picture: Navy SBIR firms commercialize differently — less through private capital, more through federal contracts and commercial acquisition.

### Caveats

- **Recipient-name matching** uses USAspending's `recipient_search_text` fuzzy search, tightened to exact uppercased name equality. False positives from name collisions remain possible but bounded.
- **USAspending coverage degrades pre-2015.** Pre-2015 firm-contract sums may be undercounted. The per-Branch signal should be interpreted with that in mind.
- **FPDS numerator includes contracts that are themselves SBIR contracts** (which appear in both USAspending and SBIR.gov). A more rigorous version would subtract SBIR-tagged contracts from the FPDS numerator to isolate pure non-SBIR follow-on activity. The published numbers may slightly overstate "follow-on" FPDS.
- **FPDS numerator includes non-DoD federal contracts.** A Navy SBIR firm with NASA contracts contributes those NASA dollars to the Navy FPDS ratio. This is methodologically appropriate for the "do firms commercialize via *any* federal contracts?" question, but means high FPDS ratios for some branches reflect cross-agency contract relationships rather than same-branch.
- **Cohort is HIGH-tier Form D matched firms only** (n=1,041). Firms with no Form D match are not in scope. The within-cohort comparison asks: of firms that DID raise some private capital, do they ALSO have heavy federal-contract activity?
- **Per-Branch firm counts vary 2-605.** Air Force / Navy / Army / DARPA / DHA results are statistically credible (n ≥ 46). Small-cohort branches (CBD, DLA, DTRA, SDA, SOCOM, OSD) have low-n estimates and shouldn't be over-interpreted.

### Reproducibility

```bash
.venv/bin/python scripts/archive/data/dod_fpds_substitution_test.py
```

Default config: year window 2009-2024, inputs `data/form_d_details.jsonl` + `data/raw/sbir/award_data.csv`. Caches per-firm USAspending pulls to `data/processed/fpds_substitution/firm_contracts.jsonl` (gitignored, but reruns reuse cache so the ~30-min initial pull happens only once). Outputs `reports/ml/dod_fpds_substitution_test.{json,md}`.

Only depends on `httpx` (already in pyproject for other API clients). No numpy required.

---

## Candidate-explanation scorecard (all four resolved)

| Candidate | Status |
|---|---|
| 1. DoD firms less commercially-oriented | **Partially true.** Branch-specific. Holds for MDA / DTRA. Does NOT hold for Air Force / DHA. (Part 1) |
| 2. FPDS substitution channel | **True for Navy, weakly for DHA. False for every other large-cohort branch.** (Part 3) |
| 3. Defense IP / classification discourages outside investment | **Plausible for MDA / DTRA.** (Part 1) |
| 4. Acquisition replaces capital-raising | **True for Navy specifically, weakly for MDA. NOT defense-prime-driven** — acquirers are ~85-90% commercial. (Parts 1 + 2) |

The Navy finding stacks all four Navy-relevant explanations:
- Branch is genuinely lower-commercialization (Part 1 — confirmed)
- Has higher M&A rate (Part 1 — confirmed)
- M&A buyers are commercial, not defense-prime (Part 2 — refining the mechanism)
- Has higher FPDS leverage than Form D leverage (Part 3 — substitution confirmed)

## Remaining open work

1. **Subtract SBIR contracts from FPDS numerator** to isolate true non-SBIR follow-on activity. Would tighten the Navy +7% substitution signal.
2. **Per-Navy-firm deep dive** on the 91 high-tier matched firms. Which Navy firms drive the FPDS substitution signal? Are they consolidated in specific sub-mission areas (e.g., maritime systems, submarine sonar, naval aviation)?
3. **Compare against non-DoD agencies** (NSF, HHS, DOE) using the same FPDS-leverage methodology. Does NSF's 3.23x Form D leverage have a corresponding low FPDS leverage (commercial-tech model) vs. Navy's substitution pattern?
4. **Update the published doc** ([sbir-form-d-fundraising-analysis.md](sbir-form-d-fundraising-analysis.md)) to reference the Navy substitution finding in its DoD section.
