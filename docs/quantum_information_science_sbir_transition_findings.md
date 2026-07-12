# Quantum Information Science SBIR/STTR Phase II: Technical Findings (Provisional)

**Prepared for:** Analysts and reproducibility reviewers  
**Policy brief:** [`quantum_information_science_sbir_policy_brief.md`](quantum_information_science_sbir_policy_brief.md)  
**Status:** Provisional — cohort and triangulation only; channel rates not computed  
**Data through:** FY2025 SBIR.gov Phase II universe  
**CLI:** `python scripts/data/build_tech_area_cohort.py --area quantum_information_science`  
**Config:** `config/transition_reports/quantum_information_science.yaml`

---

## Background: Why QIS Is Harder Than Nanotech to Census

There is no single authoritative tag for "quantum information science" on SBIR.gov. Abstracts freely use "quantum" for quantum dots, quantum wells, quantum mechanics, and market-name drops ("for quantum computing") on cryocoolers, lasers, and workforce projects. A naive `quantum` probe over Phase II text hits ~1,100 awards; after QIS-positive filters and quantum-dot/well exclusion, Method A retains **138**.

Commercialization measurement faces the same dual-pathway problem as nanotech (FPDS procurement vs private capital), compounded by:

1. **Small N** — 138 awards / 82 firms cannot support the agency×pathway crosstabs that nanotech's 2,849 awards allowed without large confidence intervals.
2. **Young cohort** — nearly two-thirds of awards are 2020s; private-raise and acquisition windows of 2–7 years (nanotech Finding 1–2) have not elapsed for much of the population.
3. **Missing shared signals in this run** — FPDS Phase III digest, Form D details, and EDGAR M&A enrichment were not available, so channel rates are withheld rather than imputed as zeros.

---

## Cohort Definition

### Method A — keyword pack (primary)

Patterns are split into **core** (any hit admits) and **soft** (title hit or ≥2 soft hits in title+abstract):

| Tier | Examples |
|------|----------|
| Core | qubit(s), quantum information / communication / cryptography / entanglement / algorithm / network, QKD, quantum anneal*, ion-trap / superconducting qubit, NV-center, quantum memory / repeater / metrology |
| Soft | `quantum comput*`, `quantum sens*`, `post-quantum`, `PQC` |

Taxonomy negatives (quantum dot, quantum well, quantum mechanics, …) are loaded via `cet_id: quantum_information_science`. Soft gating removed **65** abstract-only market-name-drop awards (203 → 138). Of the 138: **121** core-admitted, **17** soft-corroborated. Pure-negative admissions: **0**. Quantum-dot/well awards with no QIS positive (correctly excluded): **185**.

SBIR.gov carries **3** duplicate `award_id` rows in this cohort (138 rows → **135** unique IDs). Overlap statistics below use unique IDs; headline Method A size matches the row count used in validation (**138**).

### Method B — CET / taxonomy triangulation

Ten taxonomy terms for the `quantum_information_science` CET category produce **158** award rows (**153** unique IDs). This is a deterministic keyword heuristic, not a trained classifier.

| Metric | Value |
|--------|------:|
| Method A (rows / unique) | 138 / 135 |
| Method B (rows / unique) | 158 / 153 |
| Intersection (unique) | 118 |
| Union (unique) | 170 |
| Jaccard | 0.694 |
| Containment A⊆B | 0.874 |
| Containment B⊆A | 0.771 |

**Interpretation:** Unlike nanotech — where Method B (CET) was largely orthogonal and later retired by patent validation — QIS Method A and Method B substantially agree. **87%** of the keyword cohort sits inside the CET set. The residual Method-B-only awards are the main place to hunt false taxonomy positives (or Method A false negatives) in a follow-up precision pass.

### Method C — CPC patents

`cpc_prefixes` is empty for this area. A quantum CPC extract (e.g. `G06N10`) is a planned follow-up (`specs/tech-area-transition-report` T8), not part of this report.

---

## Finding 1: A DoD/DOE Spine, Not a Five-Agency Mix

| Agency | QIS Phase II awards | Share | Phase II $ (M) | Unique firms |
|--------|--------------------:|------:|---------------:|-------------:|
| Department of Defense | 82 | 59.4% | 90.9 | 51 |
| Department of Energy | 32 | 23.2% | 39.9 | 29 |
| NASA | 13 | 9.4% | 9.9 | 9 |
| National Science Foundation | 6 | 4.3% | 4.9 | 6 |
| Department of Commerce | 3 | 2.2% | 0.9 | 3 |
| HHS | 2 | 1.4% | 3.4 | 2 |
| **Total** | **138** | **100%** | **~150** | **82** |

DoD + DOE account for **82.6%** of awards and **~87%** of Phase II dollars. NSF — the private-capital-heavy agency in the nanotech pathway split — is only six awards here. That composition predicts (but does not yet measure) a procurement-skewed commercialization profile once FPDS/Form D signals are restored: there is little NSF mass for a Form-D-dominant pathway of the kind seen in nanotech Finding 1.

Program split: **81 SBIR / 57 STTR** (41% STTR — high relative to hypersonics, consistent with university-adjacent quantum hardware and algorithms work).

---

## Finding 2: Concentration and Recency Shape What Can Be Learned

**Firm concentration.** The top 10 firms account for **38%** of Method A awards. Leading award counts: AdvR (12), NuCrypt (9), Physical Sciences Inc. (7), Streamline Automation (5), ColdQuanta / Infleqtion (4), Hypres (4). Small-N pathway rates will be sensitive to a handful of multi-award firms; firm-level and award-level headlines should be reported side by side (as the nanotech report does).

**Temporal structure.**

| Decade | Awards |
|--------|-------:|
| 1990s | 1 |
| 2000s | 12 |
| 2010s | 36 |
| 2020s | 89 |

**97** awards have award year ≤ 2022 (mature enough for a first look at follow-on activity); **41** are ≥ 2023 and should be treated as right-censored in any future survival analysis — not as commercialization failures.

**Entity resolution.** Only **4** awards (2.9%) lack a UEI — far below nanotech's ~23% no-UEI share of the indeterminate population. Identity resolution (WS2) is a smaller blocker here than for nanotech; the binding constraints are signal artifacts and calendar time.

---

## Finding 3: Measurement Limits — What Nanotech Had That This Run Lacks

The nanotech report's headline pathway table required three shared inputs:

| Artifact | Role in nanotech report | Status here |
|----------|-------------------------|-------------|
| `fy25_phase3_prospect_digest.csv` | FPDS Phase III + federal obligation flags | **Absent** |
| `form_d_high_conf_cohort.jsonl` / `form_d_details.jsonl` | Private-raise pathway + temporal filter | **Absent** |
| `enriched_sbir_ma_events.jsonl` | M&A channel | **Absent** |

Without them, `deficiency_class` values written on the cohort CSV reflect *missing digest*, not firm disappearance. Publishing those bucket counts as "dark majority" composition would be misleading. This report therefore stops at cohort definition and composition.

**Scripts already area-aware for the next step** (once artifacts exist):

```bash
python scripts/data/nano_form_d_temporal.py --area quantum_information_science
python scripts/data/nano_ws1_contract_evidence.py --area quantum_information_science
python scripts/data/nano_ws2_resolve_no_uei.py --area quantum_information_science
```

Outputs land under `data/reports/quantum_information_science/`. Dark-firm liveness, trademarks, subawards, and alias expansion remain nano-path-locked pending T14–T16 in `specs/tech-area-transition-report/tasks.md`.

---

## What Is Not Visible (Yet)

- **Government procurement follow-on** (FPDS Phase III and uncoded contracts)
- **Private capital** (Regulation D offerings after Phase II end)
- **M&A and prime absorption**
- **Patent / trademark / subaward liveness** for procurement-dark firms
- **CPC Method C** validation of the keyword pack

None of these absences imply failed commercialization. They are instrument gaps.

---

## What This Says About QIS SBIR (Bounded)

1. **QIS is a thin slice of SBIR Phase II** (~1/20th of nanotech's share). Program evaluation cannot borrow nanotech's sample-size assumptions.
2. **Text matching without soft-pattern gating badly overstates QIS.** Quantum-dot/well and market-name-drop contamination are first-order; the precision pass is load-bearing, not cosmetic.
3. **CET triangulation is unusually aligned** (87% A⊆B). That is good news for using either instrument for monitoring — and a reason to inspect the B-only residual carefully before treating CET as interchangeable with Method A.
4. **Composition predicts a DoD/DOE measurement problem**, not an NSF private-capital story: when channel rates arrive, expect procurement coding (and its FPDS gaps) to dominate the narrative.
5. **Recency censors outcomes.** Any near-term "transition rate" that does not right-censor 2023–2025 awards will understate QIS commercialization by construction.

---

## Policy Implications (Provisional)

1. **Publish the instrument with the count.** "Quantum SBIR" is 138 (Method A), 158 (CET), or ~1,100 (bare `quantum`) depending on the filter — same lesson as nanotech Policy Implication 8.
2. **Do not use FPDS Phase III alone for cross-agency QIS comparison** once rates exist — GAO-24-106398 still applies, and DOE/NASA/NSF shares are material enough to distort a DoD-coded metric.
3. **Evaluation windows must match a young deep-tech cohort** — four to seven years for private and acquisition pathways (nanotech Finding 4 timing), with explicit censoring of recent awards.
4. **Restore shared signal artifacts before claiming pathway rates** — the cohort definition is ready; the measurement stack is not yet wired for this area in this environment.

---

## Methodological Notes

- **Universe:** 68,077 Phase II awards from `data/raw/sbir/award_data.csv`.
- **Outputs:** `data/reports/quantum_information_science/{cohort_keyword,cohort_cet}.csv`, `overlap_summary.json`, `methodology_stub.md` (gitignored under `/data/*`; regenerate with the CLI above).
- **Duplicate award IDs:** 3 row-level duplicates in Method A; overlap uses unique IDs.
- **Soft-pattern rule:** `soft_requires: title_or_multi` — see YAML and `validation.md`.
- **Negatives:** Via CET taxonomy; pure-negative admissions = 0 in this run.
- **Signal enrichment:** Attempted; all three artifacts absent → no channel rates.
- **Small-N:** Treat percentages below as descriptive of this cohort, not precise population parameters.

---

## Roadmap to Nanotech-Parity Depth

| Step | Unlocks |
|------|---------|
| Rebuild prospect digest + Form D + M&A JSONL | Pathway table analogous to nanotech Finding 1 |
| `nano_form_d_temporal.py --area …` | Temporally filtered private-raise rates |
| WS1 / WS2 `--area` | Coding-gap recovery + no-UEI resolution |
| Migrate liveness / TM / WS5a (any-class, no B82) | Dark-majority floor |
| Optional CPC `G06N10` extract | Method C validation |

Until those land, this document is the defensible QIS deliverable: a **precision cohort, triangulation, and composition report** — not a commercialization-rate report.
