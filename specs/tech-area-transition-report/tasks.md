# Tech-Area Transition Report — Tasks

## Phase 1 — Spec + v1 cohort CLI (this PR)

- [x] T1 Write `requirements.md`, `design.md`, `tasks.md`
- [x] T2 Add `config/transition_reports/` YAMLs for
      `nanotechnology`, `quantum_information_science`, `hypersonics`
- [x] T3 Implement `scripts/data/build_tech_area_cohort.py`
      (`--area`, Method A/B, negatives, overlap, optional signal enrichment note, stub doc)
- [x] T4 Run quantum + hypersonics; record sizes / Jaccard / spot-check in `validation.md`
- [x] T5 Nanotech smoke: Method A size exact match to 2,849 with ported keyword pack

## Phase 2 — Follow-ups (out of this PR unless cheap)

- [ ] T6 Extract shared enrichment helpers from `build_nano_cohort.py` into
      `sbir_etl/` (stop importing from a script)
- [ ] T7 Point `nano_*` dark-majority scripts at `data/reports/<cet_id>/` via `--area`
- [ ] T8 Optional Method C for quantum (`G06N10` etc.) once CPC extract is generalized
- [ ] T9 Dagster asset wrapper (only after CLI is stable across ≥3 areas)
- [ ] T10 Quantum pack precision pass; hypersonics TPS co-occurrence rule (see `validation.md`)
