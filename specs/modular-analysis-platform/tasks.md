# Modular Analysis Platform — Tasks

- [x] 1. Add `sbir_etl/analysis/` contracts, registry loader, runner, and snapshot compare.
  - Verify: unit tests for registry load, hash pinning, and snapshot mismatch
- [x] 2. Seed `config/analysis_profiles/registry.yaml` from existing census and transition YAMLs.
  - Verify: registry lists drone, uas, unmanned_systems, nano, QIS, hypersonics
- [x] 3. Add `scripts/data/run_analysis.py`; deprecate the two builder CLIs as shims.
  - Verify: `--help` and a dummy-profile unit test (no new production Python module)
- [x] 4. Replace `TECH_AREAS` with registry-driven Dagster generation.
  - Verify: existing three transition assets still load; a temp registry row would mint a fourth
- [x] 5. Migrate the policy-brief stub to `EvidenceChannelStage` without changing the
  "Not computed — not zero" wording.
  - Verify: `test_policy_brief_stub_signals_absent_reports_not_computed`
- [x] 6. Keep calibration tests green.
  - Verify: `tests/unit/utils/test_tech_census.py` and
    `tests/unit/scripts/test_build_tech_area_cohort.py`
