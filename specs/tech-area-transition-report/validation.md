# Tech-Area Transition Report — Validation (v1)

**Date:** 2026-07-12  
**Universe:** 68,077 Phase II awards from SBIR.gov `award_data.csv`  
**CLI:** `python scripts/data/build_tech_area_cohort.py --area <area_id>`  
**Signal artifacts:** absent in this environment (cohort + overlap only; channel rates not claimed)

---

## Summary table

| Area | Method A | Method B | ∩ | Jaccard | A⊆B | Notes |
|---|---:|---:|---:|---:|---:|---|
| `nanotechnology` | **2,849** | 650 | 426 | 0.141 | 0.152 | Exact regression vs PR #428 Method A |
| `quantum_information_science` | **203** | 158 | 153 | 0.777 | 0.777 | High A↔B agreement; negatives effective |
| `hypersonics` | **886** | 962 | 804 | 0.774 | 0.911 | Dropped bare `supersonic` / `ramjet` / `aerothermal` from Method A |

---

## Nanotechnology (regression)

- Method A size **2,849** matches PR #428 / `build_nano_cohort.py` keyword cohort on the same CSV vintage (±0).
- Method B (ported `method_b_terms` including carbon fiber) size **650** matches the nano reference.
- Low Jaccard (0.141) is expected — same carbon-fiber divergence documented in the nano methodology.

**Gate T5:** PASS.

---

## Quantum Information Science

### Sizes
- Method A keyword pack: 203 awards (~0.30% of Phase II).
- Method B taxonomy keywords: 158 awards.
- Jaccard 0.777 — packs are largely aligned; Method A is a modest recall extension (post-quantum, NV-center, etc.).

### Contamination control (Requirement 3)
- **Pure-negative admissions:** 0 (awards matching only taxonomy negatives never enter Method A).
- **Quantum-dot / quantum-well awards with no QIS positive:** 185 correctly excluded from Method A.
- **Negative co-occurrence inside Method A:** 7 awards — all also match a genuine QIS positive (e.g. entangled-photon quantum-dot source for space QKD; quantum computing + quantum mechanics language). Keeping these is correct under the mixed-abstract rule.

### Random sample (n=15, seed 20260712) — precision notes
Most rows are clearly QIS (QKD, qubits, dilution refrigerators, entangled photon sources, PQC). Borderline / possible false friends to watch in a follow-up pack tune:
- “Providing AI and Data Analytics Skills Assessment…” (matched `quantum computing` in body — verify context)
- “Magnetic Resonance Force Microscopy” (2003; may be weak)
- “Extended SWIR Single Photon Avalanche…” (sensing-adjacent; `quantum sensing` hit)

**Gate:** PASS for non-empty cohort + negative control. Pack may need a precision pass before policy publication.

---

## Hypersonics

### Sizes
- Method A (no bare `supersonic` / `ramjet` / `aerothermal`): **886** awards.
- Method B (taxonomy, still includes `supersonic`): **962** awards.
- A⊆B = 0.911 — Method A is largely a stricter subset, as intended.

### Quality notes
- Dominant match token is `hypersonic*` (~732+).
- **125 awards** lack a `hypersonic*` token in `keyword_matches` (mostly `thermal protection system`, `scramjet`, `Mach 5–9`). Spot samples are mixed: many are on-topic (scramjet panels, CAV TPS, Mach 7–8 fuels); some TPS rows are generic cryogenic/reusable heat-shield work.
- Recommendation for Phase 2: require TPS/Mach hits to co-occur with a hypersonic/scramjet/boost-glide cue, or move TPS to a soft tier.

**Gate:** PASS for non-empty cohort + no bare `supersonic` in Method A.

---

## Acceptance checklist (requirements.md)

| Criterion | Result |
|---|---|
| Area YAML under `config/transition_reports/` | Done (3 areas) |
| CLI `--area` writes `data/reports/<area_id>/` | Done (local; gitignored under `/data/*`) |
| Method A / B sizes + Jaccard | Done (`overlap_summary.json`) |
| Missing signals stated, not silent 0% | Done |
| Quantum non-empty + negative spot-check | PASS |
| Hypersonics non-empty + no bare `supersonic` in Method A | PASS |
| Nanotech ±5% of 2,849 | PASS (exact) |

---

## Follow-ups

1. Re-run with prospect digest / Form D / M&A artifacts to exercise channel enrichment.
2. Quantum pack precision pass on the borderline titles above.
3. Hypersonics TPS co-occurrence rule.
4. Optional Method C for quantum (`G06N10`) once CPC extract is generalized (T8).
