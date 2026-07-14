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

## Negative veto + negation diagnostic (2026-07-13)

**Change:** the negative-keyword list was previously loaded but inert — `build_keyword_cohort`
discarded it (`del negatives`) and admission was purely positive-gated, so the taxonomy
negatives (quantum dot/well/mechanics/chemistry/field theory) and pack negatives
(`supersonic`) rejected nothing. They now **veto soft-only admissions**: a `soft_corroborated`
award is dropped if any negative pattern fires. **Core admits are never vetoed** — a specific
positive (qubit, `quantum information`, scramjet) is strong enough to survive an incidental
`quantum well` mention.

Also added `negation_spotcheck`: a diagnostic (not a veto) that flags admitted awards where a
positive is negated in context (e.g. "does not involve quantum information"). Regex cannot read
negation; the count is reported in `overlap_summary.json` and stdout so the false-positive class
is quantified rather than silent.

**Confirmed effect on cohort sizes (2026-07-13, real `award_data.csv` run):**

| Area | `soft_requires` | Veto reachable? | Result |
|---|---|---|---|
| `nanotechnology` | n/a (`soft_patterns: []`) | no | **2,849 unchanged** (no soft admits) — not re-run here, unaffected by construction |
| `hypersonics` | `core_cooccur` | no (soft-only never admits) | **813 unchanged** by construction, confirmed; `supersonic` co-occurs with 76 Method A awards (spot-check flag, 0 pure-negative admissions) |
| `quantum_information_science` | `title_or_multi` | **yes** | **138 unchanged** — the veto ran (5 soft/core awards co-occur with a negative) but 0 of the 17 `soft_corroborated` admits actually hit one in this data; the veto is real and tested, it just didn't trigger here. Method A stays 121 core + 17 soft_corroborated = 138 |

Engine coverage: `tests/unit/scripts/test_build_tech_area_cohort.py` now exercises
`resolve_method_a`, both soft-gating modes, the veto, `overlap_stats`, and `negation_spotcheck`.

---

## Reproducible composition + figure audit (2026-07-13)

**Problem:** the Finding 1 / Finding 2 tables (agency×dollar×firms, program split, decade
distribution, censoring, firm concentration, no-UEI) were hand-authored and had no automated
derivation or check — and the reports anchored them to the raw **row** count (138 / 813) while
overlap stats used **unique** IDs, a row-vs-unique inconsistency.

**Change:**

- `build_tech_area_cohort.py` now emits `data/reports/<area>/composition.json` via
  `aggregate_composition()`, which **deduplicates first** (so composition is unique-award-based)
  and computes every headline composition figure.
- `scripts/data/verify_tech_area_figures.py --area <id>` recomputes composition from the cohort
  CSV and diffs it against `EXPECTED` tables transcribed from the published findings docs — the
  generalized analogue of `nano_verify_report_figures.py`.
- Tests: `test_build_tech_area_cohort.py` (dedupe + `aggregate_composition`) and
  `test_verify_tech_area_figures.py` (diff logic: match, tolerance, mismatch, missing agency).

**Bug found on the real data-bearing run (2026-07-13):** the original `dedupe_by_award_id` keyed
on bare `award_id` alone. Checking the actual "duplicate" rows against real `award_data.csv`
showed this was wrong, not just row-vs-unique noise: of QIS's 3 repeated `award_id` values, only
1 was a true duplicate row (identical company/year/amount) — the other 2 were genuinely different
awards (a DOE Phase II continuation in a later year; a successor-company change) sharing a base
contract number, the same `award_id`-is-not-a-key trap documented for nanotech in
[[fpds-piid-not-a-key]] / `docs/steering/data-quality.md`. Bare-ID dedup was silently dropping
real awards. Of hypersonics' 3 repeated IDs, **none** were true duplicates (2 DOE continuations,
1 same-year pair with different dollar amounts) — the predicted 813→810 gap does not hold at all
once you check what's actually being dropped.

**Fix:** `dedupe_by_award_id` now keys on `(award_id, company, award_year, award_amount)` — a row
is a true duplicate only if all four agree. Regression test added:
`test_dedupe_keeps_same_award_id_different_award`.

**Confirmed composition (2026-07-13, real `award_data.csv` run, post-fix):**

| Area | Rows | True duplicates | Unique awards (composition basis) |
|---|---:|---:|---:|
| `quantum_information_science` | 138 | 1 | **137** |
| `hypersonics` | 813 | 0 | **813** (unchanged) |

`verify_tech_area_figures.py --area quantum_information_science` and `--area hypersonics` both
report **ALL CHECKS PASSED** against the reconciled findings/brief docs. Hypersonics needed no
prose changes at all — its published figures were already correct (no true duplicates to drop).
QIS Finding 1/2 tables, program split, decade distribution, censoring, and firm concentration were
updated to the 137-unique-award basis across both `quantum_information_science_sbir_transition_findings.md`
and `quantum_information_science_sbir_policy_brief.md`. Method A's row-matching count (138) and the
Method A/B overlap statistics (which compare bare `award_id` **sets**, 135 distinct values for QIS
— a different, coarser question than "unique awards") are unaffected and still reported as before.

---

## Acceptance checklist

| Criterion | Result |
|---|---|
| Area YAML + CLI | Done |
| Size gap explained (domain prevalence) | Done (this doc) |
| Quantum precision pass | Done (203→138) |
| Hypersonics TPS/Mach co-occurrence | Done (886→813) |
| Nanotech ±5% of 2,849 | PASS (exact) |
| Negative veto (data-bearing run) | Done — real-data confirmed: QIS 138 unchanged (veto ran, found 0 vetoable), hypersonics 813 unchanged by construction |
| Composition dedup + figure audit (data-bearing run) | Done — bare-`award_id` dedup bug found and fixed (compound key); QIS 137 / hypersonics 813 unique awards confirmed; `verify_tech_area_figures.py` passes both areas; findings/brief docs reconciled |

---

## Follow-ups

1. Re-run with prospect digest / Form D / M&A for channel enrichment.
2. Optional: demote soft title-only quantum admits that are clearly tool/supply-chain (CFD, inventory) via a denylist on title patterns.
3. Optional Method C for quantum (`G06N10`) once CPC extract is generalized (T8).

## Provisional findings reports (2026-07-12)

Cohort + triangulation + agency composition (no pathway rates — signal artifacts absent):

- [`docs/nanotech_sbir_policy_brief.md`](../../docs/nanotech_sbir_policy_brief.md) — full channel headline table (nanotech)
- [`docs/quantum_information_science_sbir_policy_brief.md`](../../docs/quantum_information_science_sbir_policy_brief.md) — Method A **138**, provisional cohort brief
- [`docs/hypersonics_sbir_policy_brief.md`](../../docs/hypersonics_sbir_policy_brief.md) — Method A **813**, provisional cohort brief

Technical appendices: `docs/*_sbir_transition_findings.md`. Format spec: `specs/tech-area-transition-report/publication-format.md`.

Regenerate underlying CSVs with `build_tech_area_cohort.py --area <id>` (outputs under gitignored `data/reports/<id>/`).
