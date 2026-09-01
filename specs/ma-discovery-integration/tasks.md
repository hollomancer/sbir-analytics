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

- [ ] 6. Licensed snippet cut of the Form-D-missing population (human source/ToS + keys)
  - Verify: hashed JSONL recorded in the study run summary

- [ ] 7. Sample run + 20-row human medium-row review (validation design in the study note)
  - Verify: kill-gate fields in `sample_run_summary.json`; labeled `review_queue.jsonl`

- [ ] 8. Promote `studies/ma-discovery-recall` only after the validation design passes
  - Verify: evidence-auditor; `evidence_status` remains `exploratory` until then
