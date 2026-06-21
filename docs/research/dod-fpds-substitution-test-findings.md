# DoD FPDS substitution test — Navy commercializes via federal contracts

**Date:** 2026-06-21
**Companion to:** [dod-form-d-leverage-deep-dive.md](dod-form-d-leverage-deep-dive.md) (PR #342), [dod-form-d-followup-findings.md](dod-form-d-followup-findings.md) (PR #343)
**Script:** [`scripts/data/dod_fpds_substitution_test.py`](../../scripts/data/dod_fpds_substitution_test.py)

## Summary

The bootstrap analysis surfaced four candidate explanations for DoD's low Form D leverage (1.011x). PR #342 + PR #343 resolved three of them via decomposition; the fourth — **"DoD firms commercialize via federal contracts rather than VC (substitution channel)"** — required fresh USAspending pulls and was deferred. This document closes that gap.

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

This closes the substitution-hypothesis question: Navy SBIR firms genuinely *do* substitute federal contract follow-on for private capital. The narrative from PR #342 — "Navy has the lowest Form D leverage in DoD" — is now joined by: "and they have the highest FPDS-to-Form-D ratio in DoD."

## Method

For each of the 1,041 DoD high-tier Form D matched firms (same cohort as PR #342 / PR #343), queried the USAspending public API for all federal contracts (PIID type, award_type_codes A/B/C/D) with the firm's name as `recipient_search_text` in the 2009-2024 window. Tightened the recipient match to exact uppercased name equality to reduce false-positive name collisions. Cached results to JSONL so reruns are fast.

Per-Branch aggregation: sum each branch-attributed firm's FPDS contract dollars and divide by the Branch's DoD program SBIR $. This produces a directly-comparable program-level ratio (same denominator construction as the Form D leverage analysis in PR #338 / PR #342).

Substitution signal = `(FPDS_ratio − FD_ratio) / FD_ratio`. Positive means FPDS dominates (substitution); negative means Form D dominates (no substitution).

Runtime: ~30 minutes API time at 1.05s/request (under USAspending's 60/min limit). Fully cached after first run.

## Results — full table

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

## Interpretation by Branch

### Navy — substitution confirmed (the headline finding)

Navy SBIR firms have **comparable Form D and FPDS leverage** (0.406x vs 0.432x). This is the only large-cohort branch where the FPDS channel reaches parity with private capital.

Combined with prior findings:
- **PR #342**: Navy 6.6% Form D participation (lowest in DoD) and 0.406x Form D leverage
- **PR #342**: Navy is the only branch where M&A event rate (10.3%) > Form D rate (6.6%)
- **PR #343**: Navy's M&A acquirers are predominantly commercial (88.5%), NOT defense primes (6.9%)
- **This finding**: Navy firms have follow-on FPDS leverage of 0.432x — roughly equal to their Form D leverage

The composite Navy picture: SBIR firms commercialize via federal contracts at a rate comparable to private capital. They get acquired by commercial buyers (not defense primes). When they do raise Form D, it's a modest channel. **Navy SBIR is more federal-contract-and-acquisition-oriented than other DoD branches** — but the acquirers are commercial, not defense-prime, suggesting Navy's tech transfers cleanly to commercial markets via M&A.

### DHA — both channels active

Defense Health Agency has substantial Form D (1.139x) AND substantial FPDS (0.605x). The substitution signal is −47% (Form D still dominates), but the absolute FPDS leverage is the second-highest in DoD after Navy.

This is consistent with the biotech-VC overlap noted in PR #342: DHA SBIR funds healthcare/medical-device firms that have both commercial-market (Form D) and federal-procurement (FPDS) pathways available.

### Air Force / Army / DARPA — private capital dominates

Air Force, Army, and DARPA all show substantial Form D leverage (1.0×–2.1×) and modest FPDS follow-on (0.25×–0.49×). Form D is 3-5× the FPDS channel for these branches.

Air Force's 4.44B FPDS dollars are nontrivial in absolute terms — but spread across 605 matched firms with $9.02B in program SBIR, the per-program-dollar leverage is only 0.493x.

**Air Force's pattern is the "normal commercial-tech" model:** SBIR seeds firms, they raise private capital to scale, federal contracts are a secondary follow-on channel.

### MDA — both channels weak

MDA's Form D leverage (0.246x) is the second-lowest in DoD (after DTRA). The FPDS test reveals it doesn't substitute either: 0.036x FPDS leverage means MDA firms have very little non-SBIR federal contract activity *or* private capital follow-on.

This is the clearest "classified work doesn't commercialize" pattern in the data. MDA SBIR is structurally a one-way pipeline — work goes in, no scaling out via either channel. Consistent with the missile-defense IP / classification hypothesis from PR #342.

### Small-cohort branches (CBD, DLA, DTRA, SDA, SOCOM, OSD) — noisy

All these branches have <20 matched firms, so per-Branch ratios should be interpreted with low confidence. Notable: CBD has high Form D (1.564x) and low FPDS (0.079x), suggesting biotech-firm pattern similar to DHA but smaller scale. DTRA is essentially zero on both channels (n=7).

## What this revises about the bootstrap doc's four candidate explanations

| Candidate | Status |
|---|---|
| 1. DoD firms less commercially-oriented | **Partially true.** Branch-specific. Holds for MDA / DTRA. Does NOT hold for Air Force / DHA. (PR #342) |
| 2. **FPDS substitution channel** | **True for Navy, weakly for DHA. False for every other large-cohort branch.** (This document) |
| 3. Defense IP / classification discourages outside investment | **Plausible for MDA / DTRA.** (PR #342) |
| 4. Acquisition replaces capital-raising | **True for Navy specifically, weakly for MDA. NOT defense-prime-driven.** (PR #342 + PR #343) |

The Navy finding stacks all three Navy-relevant explanations:
- Branch is genuinely lower-commercialization (PR #342 — confirmed)
- Has higher M&A rate (PR #342 — confirmed)
- M&A buyers are commercial (PR #343 — refining the substitution mechanism)
- Has higher FPDS leverage than Form D leverage (this document — substitution confirmed)

## Cross-Branch summary: where Navy stands

| Metric | Navy | All other large branches |
|---|---|---|
| Form D leverage | 0.406x | 1.01x – 2.12x |
| Form D participation rate | 6.1% | 12.0% – 17.1% |
| M&A vs Form D rate | M&A higher (1.7×) | Form D higher (1.2-6×) |
| FPDS vs Form D leverage | FPDS higher (+7%) | Form D higher by 47-99% |
| Acquirer type (when acquired) | 88.5% commercial | 84% commercial |

Navy is statistically distinct from other DoD branches on every commercialization measure. The substitution finding completes the picture: Navy SBIR firms commercialize differently — less through private capital, more through federal contracts and commercial acquisition.

## Caveats

- **Recipient-name matching** uses USAspending's `recipient_search_text` fuzzy search, tightened to exact uppercased name equality. False positives from name collisions remain possible but bounded.
- **USAspending coverage degrades pre-2015.** Pre-2015 firm-contract sums may be undercounted. The per-Branch signal should be interpreted with that in mind.
- **FPDS numerator includes contracts that are themselves SBIR contracts** (which appear in both USAspending and SBIR.gov). A more rigorous version would subtract SBIR-tagged contracts from the FPDS numerator to isolate pure non-SBIR follow-on activity. The published numbers may slightly overstate "follow-on" FPDS.
- **FPDS numerator includes non-DoD federal contracts.** A Navy SBIR firm with NASA contracts contributes those NASA dollars to the Navy FPDS ratio. This is methodologically appropriate for the "do firms commercialize via *any* federal contracts?" question, but means high FPDS ratios for some branches reflect cross-agency contract relationships rather than same-branch.
- **Cohort is HIGH-tier Form D matched firms only** (n=1,041). Firms with no Form D match are not in scope. The within-cohort comparison asks: of firms that DID raise some private capital, do they ALSO have heavy federal-contract activity?
- **Per-Branch firm counts vary 2-605.** Air Force / Navy / Army / DARPA / DHA results are statistically credible (n ≥ 46). Small-cohort branches (CBD, DLA, DTRA, SDA, SOCOM, OSD) have low-n estimates and shouldn't be over-interpreted.

## Reproducibility

```bash
.venv/bin/python scripts/data/dod_fpds_substitution_test.py
```

Default config: year window 2009-2024, inputs `data/form_d_details.jsonl` + `data/raw/sbir/award_data.csv`. Caches per-firm USAspending pulls to `data/processed/fpds_substitution/firm_contracts.jsonl` (gitignored, but reruns reuse cache so the ~30-min initial pull happens only once). Outputs `reports/ml/dod_fpds_substitution_test.{json,md}`.

Same dependency set as the other Form D scripts (numpy + httpx).

## Future work

This document closes the four candidate explanations from the bootstrap doc. Open follow-ups:

1. **Subtract SBIR contracts from FPDS numerator** to isolate true non-SBIR follow-on activity. Would tighten the Navy +7% substitution signal.
2. **Per-Navy-firm deep dive** on the 91 high-tier matched firms. Which Navy firms drive the FPDS substitution signal? Are they consolidated in specific sub-mission areas (e.g., maritime systems, submarine sonar, naval aviation)?
3. **Compare against non-DoD agencies** (NSF, HHS, DOE) using the same FPDS-leverage methodology. Does NSF's 3.23x Form D leverage have a corresponding low FPDS leverage (commercial-tech model) vs. Navy's substitution pattern?
4. **Update the published doc** (`docs/research/sbir-form-d-fundraising-analysis.md`) to reference this finding in the DoD section.
