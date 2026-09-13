# M&A Discovery Integration — Tasks

- [x] 1. Fail-closed search default (`none`); `mock` explicit; live backends require a key
  - Verify: `tests/unit/enrichers/ma_discovery/test_search.py` and orchestrator CLI test
  - Requirements: fail-closed operated path

- [x] 2. Dedup one confirmed row per `(company, acquirer)` and honor YAML client settings
  - Verify: `test_process_batch_dedupes_four_query_rows_for_one_pair`, factory timeout test

- [x] 3. LLM pair-name match via `RECIPIENT_V1`; `source_url` is the citation
  - Verify: `tests/unit/enrichers/ma_discovery/test_extractor.py`

- [x] 4. C3 collision join and design confidence table
  - Verify: `tests/unit/enrichers/ma_discovery/test_collision.py`

- [x] 5. Frozen-snippet search backend and sample-run / review-queue CLI
  - Verify: snippet factory test; `scripts/data/run_ma_discovery_sample.py --help`

- [x] 6. Licensed snippet cut of the Form-D-missing population (human source/ToS + keys)
  - Verify: hashed JSONL recorded in the study run summary
  - Note: pilot freeze is private/gitignored (`run-manifest.json`). Confirmatory
    freeze is private/gitignored (`confirmatory-run-manifest.json`).

- [x] 7. Held-out confirmatory run (pairs 501–1500, strict recall, stop-until-dated)
  - Spec: `studies/ma-discovery-recall/confirmatory-design.md` (hashed before capture)
  - Complete 2026-09-07: strict recall 13>=10; cost ~$0.0186/pair; 20 medium
    labels 19 true / 0 false / 1 ambiguous (FP = 0).
  - Verify: `confirmatory-run-manifest.json`; `confirmatory-labels.jsonl`

- [ ] 8. Promote `studies/ma-discovery-recall` only after the confirmatory design passes
  - Verify: evidence-auditor; `evidence_status` remains `exploratory` until then
  - Do not edit `docs/research-questions.md`
