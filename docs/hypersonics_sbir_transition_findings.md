# Hypersonics SBIR/STTR Phase II: Technical Findings (Provisional)

**Prepared for:** Analysts and reproducibility reviewers  
**Policy brief:** [`hypersonics_sbir_policy_brief.md`](hypersonics_sbir_policy_brief.md)  
**Status:** Provisional — cohort and triangulation only; channel rates not computed  
**Data through:** FY2025 SBIR.gov Phase II universe  
**CLI:** `python scripts/data/build_tech_area_cohort.py --area hypersonics`  
**Config:** `config/transition_reports/hypersonics.yaml`

---

## Background: Why Hypersonics Needs a Narrow Net

"Hypersonic" in SBIR abstracts co-occurs with adjacent aerospace language — thermal protection systems (TPS), Mach numbers, and especially **supersonic** flight — that is necessary for hypersonic vehicles but also appears in unrelated aero work. A bare `hypersonic*` probe hits ~763 Phase II awards; expanding with ungated TPS/Mach language inflated the prior pack to 886. Requiring TPS/Mach to co-occur with core hypersonic/scramjet/boost-glide language lands at **813**, with **zero** Method A awards lacking a core match.

Unlike nanotech (no authoritative NNI-style public table used here) or QIS (heavy quantum-dot contamination), the main precision risk for hypersonics is **aerospace adjacency**, not a different technology using the same token.

Commercialization measurement is dominated by the federal customer:

- Most awards are DoD contracts; FPDS Phase III coding (and its known DoD-centric coverage) will matter more than Form D.
- Private-raise and pharma-style acquisition pathways that featured in nanotech Findings 1–2 are expected to be rare — again, a prediction from agency mix, not a measured rate.

---

## Cohort Definition

### Method A — keyword pack (primary)

| Tier | Patterns | Admission rule |
|------|----------|----------------|
| Core | `hypersonic*`, hypersonic flight/weapon/vehicle/missile, `scramjet*`, `boost-glide` | Any hit admits |
| Soft | `thermal protection system`, `Mach 5–9`, `Mach 10–19` | Only with **core co-occurrence** (`soft_requires: core_cooccur`) |
| Negative | `\bsupersonic\b` | Flagged for contamination spot-check; Method A never admits on soft alone |

Effect of the TPS/Mach rule: **886 → 813** (−73 TPS/Mach-only aerospace rows). All 813 are core-admitted; 51 also carry a TPS tag alongside hypersonic/scramjet language. Rows without hypersonic/scramjet/boost in matches: **0**. Pure-negative admissions: **0**. Spot-check: **76** Method A awards co-occur with the `supersonic` negative token (expected in hypersonic aero abstracts; not used as an automatic reject).

SBIR.gov carries **3** duplicate `award_id` rows (813 rows → **810** unique IDs). Overlap uses unique IDs; headline Method A size matches validation (**813**).

### Method B — CET / taxonomy triangulation

Nine taxonomy terms (including `supersonic`, which Method A deliberately omits) produce **962** award rows (**960** unique IDs).

| Metric | Value |
|--------|------:|
| Method A (rows / unique) | 813 / 810 |
| Method B (rows / unique) | 962 / 960 |
| Intersection (unique) | 795 |
| Union (unique) | 975 |
| Jaccard | 0.815 |
| Containment A⊆B | 0.981 |
| Containment B⊆A | 0.828 |

**Interpretation:** Method A is nearly a **subset** of Method B (98% containment). The ~165 Method-B-only unique awards are the main precision risk in the CET label — likely `supersonic`-driven or other taxonomy terms without hypersonic/scramjet language. For program monitoring, Method A is the defensible "hypersonics" cohort; Method B is an upper envelope that still mixes adjacent aero.

### Method C — CPC patents

`cpc_prefixes` is empty. No patent-classification cohort in this report.

---

## Finding 1: A Near-Pure Defense Procurement Market

| Agency | Hypersonics Phase II awards | Share | Phase II $ (M) | Unique firms |
|--------|----------------------------:|------:|---------------:|-------------:|
| Department of Defense | 713 | 87.7% | 900.3 | 319 |
| NASA | 87 | 10.7% | 54.4 | 64 |
| Department of Energy | 12 | 1.5% | 12.3 | 9 |
| National Science Foundation | 1 | 0.1% | 1.0 | 1 |
| **Total** | **813** | **100%** | **~968** | **355** |

DoD alone is **88%** of awards and **93%** of Phase II dollars. NSF is a single award. Relative to nanotech (DoD 50%, HHS/NSF/DOE/NASA all material) and QIS (DoD 59%, DOE 23%), hypersonics is the most procurement-concentrated of the three areas.

Program split: **682 SBIR / 131 STTR** (16% STTR).

**Implication for the missing pathway table:** When FPDS and Form D artifacts are restored, expect:

- Higher baseline FPDS Phase III coding than nanotech NSF/HHS slices (DoD coding culture — with GAO caveats still applying inside DoD).
- Low Form D rates relative to nanotech's NSF-heavy private pathway.
- Dark-majority analysis dominated by **continued federal activity under primes / subawards / uncoded contracts**, not venture disappearance.

---

## Finding 2: Scale, Concentration, and a Long Tail of Recency

**Scale.** ~$968M Phase II obligations across 355 firms — roughly **6×** the QIS Method A dollar total and about **¼–⅓** of nanotech's award count. Firm count (355) is large enough for agency-level descriptive statistics; still thin for rare events (prime acquisitions, high-confidence M&A).

**Firm concentration.** Top 10 firms hold **24%** of awards. Leading counts: Spectral Energies (32), CFD Research (31), Physical Sciences Inc. (25), Combustion Research & Flow Technology (25), Materials Research & Design (16), ATA Engineering (15), Ultramet (15). Several of these are multi-decade aero S&T shops — composition that favors **repeat federal customers** over venture exits.

**Temporal structure.**

| Decade | Awards |
|--------|-------:|
| 1980s | 20 |
| 1990s | 67 |
| 2000s | 136 |
| 2010s | 188 |
| 2020s | 402 |

**558** awards have award year ≤ 2022; **255** are ≥ 2023. Half the cohort is 2020s activity — consistent with the post-2018 U.S. hypersonics rebuild — so any transition rate that ignores censoring will mix a long mature tail with a large immature mass.

**Entity resolution.** **68** awards (8.4%) lack a UEI — higher than QIS (2.9%), lower than nanotech's dark-majority no-UEI share. WS2 name resolution will matter for a non-trivial slice once signals exist.

---

## Finding 3: Measurement Limits — Same Stack Gap as Quantum

| Artifact | Role in nanotech report | Status here |
|----------|-------------------------|-------------|
| `fy25_phase3_prospect_digest.csv` | FPDS Phase III + federal obligation flags | **Absent** |
| Form D high-conf / details JSONL | Private-raise pathway | **Absent** |
| `enriched_sbir_ma_events.jsonl` | M&A channel | **Absent** |

`deficiency_class` on the cohort CSV is not interpretable as firm disappearance until the digest is present. This report does not publish dark-majority bucket shares.

**Next commands** (when artifacts exist):

```bash
python scripts/data/nano_form_d_temporal.py --area hypersonics
python scripts/data/nano_ws1_contract_evidence.py --area hypersonics
python scripts/data/nano_ws2_resolve_no_uei.py --area hypersonics
```

Outputs: `data/reports/hypersonics/`. Remaining dark-majority scripts (liveness, trademarks, WS5a, aliases) still need `--area` migration (T14–T16).

---

## What Is Not Visible (Yet)

- Coded and uncoded federal follow-on (including same-agency non-SBIR contracts — the WS1 strong tier in nanotech Finding 4)
- Subaward absorption into primes (nanotech Finding 3 / Policy 5) — especially salient for a DoD-heavy cohort
- Private capital and M&A (expected small, still worth measuring as a floor)
- Patent/trademark liveness without a hypersonics-specific CPC pack

---

## What This Says About Hypersonics SBIR (Bounded)

1. **Hypersonics is a real, mid-sized SBIR domain** (~1.2% of Phase II) — larger than QIS, smaller than nanotech — concentrated in DoD/NASA.
2. **Method A is nearly nested in CET Method B**, but Method B is the looser envelope (`supersonic` and related). Use Method A for "hypersonics" counts; treat B−A as contamination risk, not bonus recall, until spot-checked.
3. **TPS/Mach gating is load-bearing.** Without it, the cohort silently absorbs non-hypersonic aero materials and facility work.
4. **Composition predicts a procurement-first measurement problem.** The nanotech dual-pathway narrative should not be copy-pasted; Form D may be a minor channel here.
5. **Recent awards dominate.** Any evaluation window shorter than several years will classify a large share of the 2020s surge as "failed" by calendar alone.

---

## Policy Implications (Provisional)

1. **Publish Method A vs Method B with the number** — 813 vs 962 is a definitional choice, not measurement error.
2. **Prioritize FPDS + contract-level recovery (WS1) and subaward (WS5a) over Form D** for this area once signals are restored — match instruments to the DoD/NASA customer.
3. **Right-censor 2023–2025 awards** in any transition dashboard.
4. **Do not treat CET `supersonic` hits as hypersonics** without core co-occurrence — the Method A negative and soft rules exist for that reason.
5. **Restore shared signal artifacts before pathway rates** — cohort definition is ready.

---

## Methodological Notes

- **Universe:** 68,077 Phase II awards from `data/raw/sbir/award_data.csv`.
- **Outputs:** `data/reports/hypersonics/{cohort_keyword,cohort_cet}.csv`, `overlap_summary.json`, `methodology_stub.md` (under gitignored `/data/*`; regenerate via CLI).
- **Duplicate award IDs:** 3 row-level duplicates; overlap uses unique IDs.
- **Soft-pattern rule:** `soft_requires: core_cooccur` — TPS/Mach never admit alone.
- **Negative `\bsupersonic\b`:** Contamination flag; 76 co-occurrences in Method A (not auto-rejects).
- **Signal enrichment:** All three artifacts absent → no channel rates.
- **Comparison caveat:** Award-level rates are not comparable to firm-level rates without de-graining; multi-award aero shops will dominate award-level federal follow-on if/when measured.

---

## Roadmap to Nanotech-Parity Depth

| Step | Unlocks |
|------|---------|
| Prospect digest + Form D + M&A | Pathway table (expect procurement-heavy) |
| Form D temporal + WS1/WS2 `--area` | Coding-gap and no-UEI recovery |
| Migrate WS5a subawards early for this area | Prime-supply pathway (high prior) |
| Optional CPC prefixes for aero/materials | Method C validation |
| Area-specific prime list (defense OEM) | Acquisition narrative analogous to nanotech Finding 2 |

Until those land, this document is the defensible hypersonics deliverable: a **precision cohort, triangulation, and composition report** — not a commercialization-rate report.
