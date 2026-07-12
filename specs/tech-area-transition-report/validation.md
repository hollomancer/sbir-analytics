# Tech-Area Transition Report — Validation (v1)

**Date:** 2026-07-12 (precision pass)  
**Universe:** 68,077 Phase II awards from SBIR.gov `award_data.csv`  
**CLI:** `python scripts/data/build_tech_area_cohort.py --area <area_id>`  
**Signal artifacts:** absent in this environment (cohort + overlap only)

---

## Why quantum and hypersonics are much smaller than nanotech

This is mostly **domain prevalence**, not a broken filter.

| Probe (title+abstract, Phase II) | Awards | % of Phase II |
|---|---:|---:|
| `nano*` prefix | 3,479 | 5.11% |
| Nanotech Method A (52-pattern pack) | 2,849 | 4.18% |
| bare `quantum` | 1,102 | 1.62% |
| …of which quantum dot/well (not QIS) | ~185+ | — |
| QIS Method A after precision pass | **138** | **0.20%** |
| `hypersonic*` | 763 | 1.12% |
| Hypersonics Method A after TPS rule | **813** | **1.19%** |

Nanotech is a broad materials/process umbrella (nanoparticles, MEMS, graphene, ALD, biomed nano) spanning DoD/HHS/DOE/NSF/NASA. Quantum information science is a narrow, newer instrument set; most “quantum” SBIR text is quantum dots/wells or passing mentions. Hypersonics is real but DoD/NASA-concentrated and ~¼ the nano footprint even before precision cuts.

---

## Summary table (after precision pass)

| Area | Method A | Method B | ∩ | Jaccard | A⊆B | vs prior pack |
|---|---:|---:|---:|---:|---:|---|
| `nanotechnology` | **2,849** | 650 | 426 | 0.141 | 0.152 | unchanged |
| `quantum_information_science` | **138** | 158 | 118 | 0.694 | 0.874 | was 203 |
| `hypersonics` | **813** | 962 | 795 | 0.815 | 0.981 | was 886 |

---

## Quantum precision pass

**Change:** split pack into `patterns` (core) vs `soft_patterns` with `soft_requires: title_or_multi`.

- **Core** (any hit admits): qubit, quantum information/communication/cryptography/entanglement/algorithm/network/QKD/anneal/memory/repeater/metrology, superconducting/ion-trap qubit, NV-center.
- **Soft** (title hit or ≥2 soft hits): `quantum comput*`, `quantum sens*`, `post-quantum`, `PQC`.

**Effect:** 203 → **138** (−65 abstract-only market-name-drops: helium-3 supply chain, workforce AI training, cryocoolers, generic semiconductor tooling that namedrop “for quantum computing”).

| Check | Result |
|---|---|
| Pure-negative admissions | 0 |
| Quantum-dot/well-only correctly excluded | 185 |
| `admitted_by` | core 121 / soft_corroborated 17 |
| Prior weak titles (skills assessment, Helium-3, LEAP semiconductor, BNNT damping) | gone |
| Residual soft edge cases | CFD-for-quantum-computers; inventory forecasting on a quantum computer (title is literal — kept) |

---

## Hypersonics TPS / Mach rule

**Change:** `hypersonic*` / `scramjet*` / `boost-glide` stay **core**. `thermal protection system` and `Mach 5–19` move to **soft** with `soft_requires: core_cooccur` (never admit alone).

**Effect:** 886 → **813** (−73 TPS/Mach-only aerospace rows). All 813 are core-admitted; 51 also carry a TPS tag alongside hypersonic/scramjet language. Rows without hypersonic/scramjet/boost in matches: **0**.

---

## Nanotechnology regression

Method A remains **2,849** (exact vs PR #428). Soft-pattern machinery is unused (`soft_patterns: []`).

---

## Acceptance checklist

| Criterion | Result |
|---|---|
| Area YAML + CLI | Done |
| Size gap explained (domain prevalence) | Done (this doc) |
| Quantum precision pass | Done (203→138) |
| Hypersonics TPS/Mach co-occurrence | Done (886→813) |
| Nanotech ±5% of 2,849 | PASS (exact) |

---

## Follow-ups

1. Re-run with prospect digest / Form D / M&A for channel enrichment.
2. Optional: demote soft title-only quantum admits that are clearly tool/supply-chain (CFD, inventory) via a denylist on title patterns.
3. Optional Method C for quantum (`G06N10`) once CPC extract is generalized (T8).

## Provisional findings reports (2026-07-12)

Cohort + triangulation + agency composition (no pathway rates — signal artifacts absent):

- [`docs/quantum_information_science_sbir_transition_findings.md`](../../docs/quantum_information_science_sbir_transition_findings.md) — Method A **138**, 82 firms, ~$150M; DoD 59% / DOE 23%
- [`docs/hypersonics_sbir_transition_findings.md`](../../docs/hypersonics_sbir_transition_findings.md) — Method A **813**, 355 firms, ~$968M; DoD 88% / NASA 11%

Regenerate underlying CSVs with `build_tech_area_cohort.py --area <id>` (outputs under gitignored `data/reports/<id>/`).
