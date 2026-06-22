# DoD Form D leverage — deferred follow-ups from PR #342

**Date:** 2026-06-21
**Companion to:** [dod-form-d-leverage-deep-dive.md](dod-form-d-leverage-deep-dive.md) (PR #342)
**Script:** [`scripts/data/dod_form_d_followups.py`](../../scripts/data/dod_form_d_followups.py)

## Summary

PR #342 surfaced **DoD's 1.011x [0.842, 1.214]** as a bimodal subportfolio — Air Force at 2.12x, Navy at 0.41x, MDA at 0.25x — and flagged four follow-up items. The FPDS substitution test (item 1) requires fresh USAspending pulls and is left for a separate PR. This document resolves the other three.

**Three findings, two of them revising PR #342's framing:**

1. **Per-firm leverage is far MORE uniform across branches than program-level ratios.** Air Force median 6.79x vs Navy median 4.12x vs Army median 7.34x. The dramatic Branch heterogeneity in program-level ratios (2.12x vs 0.41x) is dominated by **participation rate differences**, not per-firm raise size. MDA (1.24x median) is the only large-cohort branch where per-firm leverage is genuinely low.

2. **Air Force's high leverage is RECENT, not structural.** Time-series decomposition shows Air Force averaged ~0.4x in 2009-2014 and ~2.5x in 2018-2024 — a 6× jump that corresponds to the AFWERX program launch (March 2017). Navy and MDA show no comparable trend; their low ratios are structural across the entire window.

3. **The "Navy commercializes via defense-prime acquisition" hypothesis from PR #342 is WRONG.** Only **6.9% of named Navy SBIR firm acquirers are defense primes**. The dominant pattern is **commercial acquisition (88.5%)**. Air Force shows a near-identical mix (5.7% / 83.9%). Whatever distinguishes Navy from Air Force in PR #342's M&A-vs-Form-D finding, it isn't the *type* of acquirer.

## Item 2 — Per-firm leverage by Branch (resolves Decomposition 4 methodology caveat)

The DoD decomposition in PR #342 attributed each firm to its dominant Branch but used the Branch's program total as the denominator. The multi-agency comparison in Decomposition 4 had a flagged methodology caveat: multi-agency firms' ratios were artificially deflated against the DoD denominator because they split SBIR receipt across agencies.

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

**What this revises about PR #342:**

- The "Air Force is commercial-tech-grade, Navy is defense-services-pipeline" framing **overstates the per-firm story**. Air Force firms that DO file Form D raise about 1.6× more per SBIR dollar than Navy firms that do (6.79x vs 4.12x medians), but they're in the same order of magnitude.
- **The dramatic 5× program-level spread (Air Force 2.12x vs Navy 0.41x) is mostly about how many firms participate, not how much they raise when they do.** Air Force has 659 matched firms against $9.02B program; Navy has 98 against $6.10B.
- **MDA's 1.24x per-firm median is genuinely low** — even MDA firms that DO file Form D raise relatively little. Consistent with the classified-work hypothesis: missile defense products don't have commercial markets even for firms that try.

The decomposition is fully consistent with PR #342's Decomposition 2 (participation rates) but adjusts the interpretation of Decomposition 1 (program-level ratios). The "DoD has different commercial DNAs by Branch" framing should be:

> **"DoD branches differ mainly in how many of their SBIR firms participate in private capital markets, less in how much those firms raise. Per-firm leverage is in the 4-7x range across most major branches; only MDA is genuinely outside that range."**

## Item 3 — Time-series Branch ratios (Air Force's leverage is recent, AFWERX-aligned)

Per-(Branch, Year) program-level ratios for all major DoD branches, 2009-2024. The headline finding is **Air Force's clear post-2017 inflection**.

### Air Force

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

### Navy (no comparable trend)

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

### MDA (consistently low across whole window)

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

### DHA (clear upward trend)

5-year early avg: ~0.4x → 5-year late avg: ~1.4x. Defense health follow-on private capital has roughly tripled over the window, possibly reflecting the broader biotech-VC cycle. The 23.3% Form D participation rate (highest in DoD) plus the rising trend makes DHA the second clear "commercial engagement" story alongside Air Force.

### Army, DARPA, others

Generally volatile year-over-year (high variance from small annual cohorts), no clear directional trend. Army 5-yr early (~0.81x) vs 5-yr late (~1.70x) shows some uplift but not the dramatic Air Force pattern.

**What this revises about PR #342:**

The Air Force 2.118x finding shouldn't be cited as a stable structural characteristic of Air Force SBIR. **It's a measurement against the 2009-2024 window that's dominated by 2018-2024 post-AFWERX activity.** If the analysis was rerun on 2009-2016 data, Air Force would show a 0.78x program-level ratio — *lower* than the DoD aggregate.

This has implications for policy framing:
- "Air Force SBIR is commercial-tech-grade" is true *for the post-AFWERX era*. It's not a permanent characteristic.
- AFWERX appears causally relevant. If the policy question is "what made Air Force private-capital-leverage rise," AFWERX is the right thing to study.
- Navy has not had an equivalent transformation. Whether that's because no Navy-equivalent program exists, or because Navy's underlying tech mix is harder to commercialize, is a separate question.

## Item 4 — Navy acquirer-type analysis (the defense-prime hypothesis fails)

PR #342 hypothesized that Navy's "M&A rate > Form D rate" pattern reflects *defense-prime consolidation* — Navy SBIR firms commercialize by getting acquired by Lockheed / Northrop / L3Harris / Leidos / Kratos / Mercury / Teledyne rather than by raising VC. This decomposition tests that hypothesis by classifying M&A acquirers.

Classifier categories:
- **defense_prime**: substring match against canonical DoD-prime / defense-services contractor names (Lockheed, Northrop, Raytheon, Boeing, BAE, L3, Leidos, CACI, Kratos, Mercury Systems, Teledyne, KBR, etc.). Uses word-boundary regex for short acronyms to avoid false matches.
- **financial_sponsor**: investment-vehicle markers (Capital, Partners, BDC, SPAC, Acquisition Corp, Merger Sub, Hercules Capital, Golub Capital, Churchill Capital, etc.). Tightened from initial version to exclude "Holdings" alone (too many false positives on real operating companies).
- **commercial**: everything else.

### Navy

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

### Air Force (control)

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

### What this revises about PR #342

**The "Navy commercializes via defense-prime acquisition" hypothesis is not supported by the acquirer-type data.** Navy's defense-prime share (6.9%) is essentially the same as Air Force's (5.7%), and both are dominated by **commercial acquisition (~85-90% of named acquirers)**.

If Navy SBIR firms are exiting via commercial acquisition rather than via private-capital raises, the relevant mechanism is **acquisition-by-commercial-companies** (probably tech consolidators, instruments/semiconductor companies, medical-device buyers), not by-defense-primes.

This actually deepens the Navy story rather than resolving it:
- Navy SBIR firms file Form D less (6.6% participation vs Air Force 18.6%)
- Navy SBIR firms ARE more likely to have M&A events (10.3% vs 6.6%)
- But Navy SBIR firms that get acquired are not predominantly acquired by defense primes — they get acquired by commercial buyers, same as Air Force firms

Possible mechanisms still on the table for Navy's distinct profile:
1. **Smaller commercial-tech footprint per firm** — Navy SBIR firms may build products that get rolled up into larger commercial companies' portfolios as one-time acquisitions, rather than as ongoing VC-funded scale-ups. The Navy firm structure may not support standalone scaling.
2. **Earlier exits** — Navy SBIR firms may exit before they'd need to file Form D. Median time-to-exit comparison would test this.
3. **Different industry mix** — Navy SBIR may concentrate in industries where exits are more common than VC scale-ups (e.g., sensor manufacturing, marine systems, specialized hardware).

The acquirer-type analysis closes one specific hypothesis from PR #342 and opens a few more. The honest reframing:

> **"Navy SBIR firms exit via commercial acquisition at higher rates than Air Force firms, but not via defense-prime consolidation. The mechanism behind Navy's M&A-over-Form-D pattern requires different evidence than PR #342 suggested."**

## What's still deferred (Item 1 — FPDS substitution)

The substitution-via-federal-contracts hypothesis from the bootstrap doc's candidate explanation #2 still cannot be evaluated without USAspending pulls. Three followup items would close it:

1. **DoD non-SBIR federal contract activity for matched firms**, by Branch. If Navy firms have high follow-on FPDS activity (relative to Air Force / NSF firms), the "Navy commercializes via federal contracts not VC" hypothesis is confirmed.
2. **Repeat this per-Branch**, since Air Force may show a different substitution profile.
3. **Compare against NASEM's 4:1 non-SBIR-federal benchmark** for DoD specifically, decomposed by Branch.

Each requires USAspending API pulls and per-firm contract matching — bigger scope than the computational follow-ups above.

## Reproducibility

```bash
.venv/bin/python scripts/data/dod_form_d_followups.py
```

Default config: year window 2009-2024, inputs `data/form_d_details.jsonl` + `data/raw/sbir/award_data.csv` + `data/sbir_ma_events.jsonl`. Outputs `reports/ml/dod_form_d_followups.{json,md}` (gitignored). Runs in ~3 seconds on a development laptop.

Same dependency set as the other Form D scripts (numpy only; no new deps).
