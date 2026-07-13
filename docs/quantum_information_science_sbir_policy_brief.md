# Quantum Information Science SBIR/STTR Phase II Outcomes: What Policy Leaders Can Safely Conclude (Provisional)

**Prepared for:** S&T policy leaders and CET / QIS program reviewers  
**Status:** Provisional — **cohort and triangulation only**; evidence-channel rates not yet computed  
**Data through:** FY2025 SBIR.gov Phase II universe  
**Technical appendix:** [`quantum_information_science_sbir_transition_findings.md`](quantum_information_science_sbir_transition_findings.md)  
**Publication standard:** [`specs/tech-area-transition-report/publication-format.md`](../specs/tech-area-transition-report/publication-format.md)

---

## Bottom line

Quantum information science (QIS) is a **small, young, and instrument-sensitive** slice of SBIR Phase II. Policy leaders can safely use the cohort counts and agency composition below for scoping and definitional discipline. **Do not** treat missing transition metrics as zero performance — shared signal artifacts were not loaded in this run.

For **137** Phase II awards (Method A keyword pack, deduplicated; 0.20% of the 68,077-award universe):

| Measure | Result | How to use it |
|---|---:|---|
| Method A cohort (keyword pack) | 137 unique awards, 81 firms, ~$149M | Primary defensible QIS count; state instrument in every headline |
| Share of all Phase II awards | 0.20% | Domain prevalence — not a filter error vs nanotech |
| Method A ⊆ Method B (CET) | 87.4% containment | CET and keyword pack largely agree; inspect B-only residual |
| DoD + DOE share of awards | 82.5% | Expect procurement-heavy outcomes once channels are computed |
| Awards from 2023 onward | 41 (30%) | Right-censored — not commercialization failures |
| FPDS / Form D / M&A channels | **Not computed** | Absent artifacts — do not report 0% |

*The keyword-matching step itself flags 138 award rows; 1 is a true duplicate (dropped here), 1 other award_id is shared by two real, distinct awards (both kept). See the technical appendix for the row-vs-unique-award distinction.*

**Policy interpretation.** QIS SBIR is too small and too recent for a single aggregate transition rate even after signals are restored. Future reporting should lead with channel-specific columns and explicit small-N caveats.

## What this provisional brief includes vs defers

This brief applies the nanotech **policy-leader format** (`publication-format.md`) at **cohort stage only**:

1. **Facts first** — cohort size, triangulation, agency mix, recency.
2. **Observable evidence language** — no “transition rate” claims without channel data.
3. **Operational uncertainty** — censoring (2023+), small N, missing digest/Form D/M&A called out explicitly.
4. **Deferred** — pathway findings, indeterminate taxonomy, dark-majority triage (requires same artifacts as nanotech PR #428).

## Finding 1: Definitional discipline matters more for QIS than for broader domains

A naive `quantum` text probe hits ~1,100 Phase II awards; **185** are quantum-dot/well-only and correctly excluded. Soft-pattern gating (title hit or ≥2 soft hits) removed **65** market-name-drop abstracts (203 → **138**).

| Metric | Value |
|--------|------:|
| Method A (keyword) | 138 awards / 135 unique IDs |
| Method B (CET taxonomy) | 158 / 153 unique |
| Intersection | 118 unique |
| Jaccard | 0.694 |

**Policy interpretation.** Publish **Method A with the instrument**. “Quantum SBIR” without a stated filter can mean 138, 158, or ~1,100 awards.

## Finding 2: Agency composition predicts measurement strategy, not outcomes (yet)

| Agency | Awards | Share | Phase II $ (M) |
|--------|-------:|------:|-----------------:|
| Department of Defense | 81 | 59.1% | 90.2 |
| Department of Energy | 32 | 23.4% | 39.9 |
| NASA | 13 | 9.5% | 9.9 |
| NSF | 6 | 4.4% | 4.9 |
| Other | 5 | 3.6% | 4.3 |

NSF is only six awards — too few for nanotech-style NSF vs DoD pathway splits. When channels exist, prioritize **FPDS + contract-level recovery (WS1)** over Form D for this cohort.

**Rigor caveat.** These are descriptive composition facts, not commercialization performance.

## Finding 3: Recency and small N constrain what leaders can ask next

- **65%** of awards are from the 2020s; **30%** are 2023+.
- Top 10 firms = **39%** of awards — pathway statistics will be firm-sensitive.

**Policy interpretation.** Use **4–7 year evaluation windows** (per nanotech policy brief) and right-censor recent awards before any QIS dashboard goes to leaders.

## What policy leaders should take away (now)

1. **Scope QIS SBIR honestly** — 137 awards, not “all quantum mentions.”
2. **Do not demand one QIS transition rate** when channel data arrive; report channels separately with small-N warnings.
3. **Restore shared signal artifacts** (prospect digest, Form D, M&A) before any outcome comparison to nanotech.
4. **State the instrument** beside every count shown to policy leaders or agency principals.

## Language to avoid (even in provisional form)

- Avoid: “QIS commercialization rate is unknown, therefore low.”  
  Use: “Evidence channels were not computed in this run; absence of metrics is not evidence of absence.”
- Avoid: “138 quantum computing awards.”  
  Use: “138 QIS Phase II awards under the Method A keyword pack (includes sensing, communications, PQC, etc.).”
- Avoid: “CET says 158, so the true count is 158.”  
  Use: “CET taxonomy yields 158; keyword pack yields 138; 87% of keyword awards sit inside CET.”

## Recommended publication structure (when channels land)

1. Executive summary + headline table (this brief, extended with channel rows).
2. Evidence-channel findings — expect procurement-heavy; Form D secondary.
3. Measurement limits — small N, censoring, FPDS cross-agency caveats (GAO-24-106398).
4. Agency reporting standard — channel columns, not one Phase III %.
5. Technical appendix — link to full findings + methodology stub.

---

## Technical detail

Cohort definitions, soft-pattern rules, spot-checks, and reproducibility CLI live in the technical appendix:

**[`quantum_information_science_sbir_transition_findings.md`](quantum_information_science_sbir_transition_findings.md)**
