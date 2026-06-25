# Tasks — OT Consortium Sub-Award Attribution (FFATA/FSRS)

**Status:** spec only — not started. See `requirements.md` / `design.md`.

## Stage 1 — Sub-award model & index (no external deps)

- [ ] **T1.1** Add `sbir_etl/ot_consortium/subawards.py` with `SubawardRecord`
      (Pydantic, StrEnum/`datetime.UTC` conventions) and `SubawardIndex`
      (`members_of`, `attributed_amount(prime_piid, firm_uei)` — exact UEI sum).
- [ ] **T1.2** Pluggable `load_subawards(source)` (DataFrame / parquet / CSV /
      list[dict]) with column-alias tolerance, mirroring `claims_loader`.
- [ ] **T1.3** Unit tests: index build, exact-UEI sum, PIID normalization,
      empty/missing feed → empty index.

## Stage 2 — Classifier route (c)

- [ ] **T2.1** Add optional `subawards: SubawardIndex | None` param to
      `assign_tier`. Insert route (c) after (b), before T3: CMF (vendor or base)
      ∧ `attributed_amount` non-null ∧ PIID 9th ∈ {3,9} → T1,
      `resolution_method="subaward_uei"`.
- [ ] **T2.2** On a (c) hit, set `obligation_amount` to the sub-award amount and
      stash the prime rollup in `metadata["rollup_obligation"]`; emit evidence
      (subaward_number, subawardee UEI, amount).
- [ ] **T2.3** Tests: subaward UEI match → T1 + amount override; subaward for a
      different UEI → unchanged tier; no subaward → unchanged tier; below-PIID-rule
      → not T1.

## Stage 3 — Extractor & runner wiring

- [ ] **T3.1** `DuckDBUSAspendingExtractor.extract_subawards(prime_piids)` reading
      the `subaward` table, **restricted to the CMF/consortium prime PIIDs** (from
      the registry + detected OT records) to bound volume.
- [ ] **T3.2** `runner.classify_baseline` / `classify_claims`: build the
      `SubawardIndex` (when a feed is configured) and thread it into `assign_tier`;
      graceful no-op when absent.
- [ ] **T3.3** Tests: baseline run where a CMF-prime subaward recovers a firm
      (T2→T1) using the sub-award amount.

## Stage 4 — Magnitude report & config

- [ ] **T4.1** `MagnitudeReport`: add `recovered_from_rollup_count` /
      `recovered_from_rollup_usd`; compute in `aggregate` (records with
      `resolution_method="subaward_uei"`). Recompute unverifiable share after
      recovery; keep it first-class.
- [ ] **T4.2** `OTConsortiumConfig`: `subaward_path`, `ffata_threshold_usd`;
      `config/base.yaml` block; env override
      `SBIR_ETL__OT_CONSORTIUM__SUBAWARD_PATH`.
- [ ] **T4.3** `ot_consortium_verification_tiers` asset: build/pass the index when
      configured; stamp coverage caveat (partial OT sub-award reporting) in
      metadata.

## Stage 5 — Docs & verification

- [ ] **T5.1** Update `docs/ot-consortium/tiers.md`: document route (c), the
      amount-override semantics, and the "absence is not contradiction" caveat.
- [ ] **T5.2** Full gate: ≥85% coverage on new code; ruff/black/mypy clean;
      existing OT + transition suites green.
- [ ] **T5.3** Sanity run on a real CMF prime (e.g. an ATI/NSTXL PIID) to confirm
      sub-award rows resolve and the recovered-$ line is non-zero where expected.
