# Allocation transaction costs — Tasks

- [x] 1. Add C4 to the research-question inventory and literature entries
  - Verify: `uv run python scripts/ci/check_research_question_status.py`
  - Requirements: 5

- [x] 2. Commit NIH RePORT / Data Book CSVs with `sources.yaml` hashes
  - Verify: loader SHA check in unit tests
  - Requirements: 2, 4

- [x] 3. Implement the calculator, break-even, and sensitivity CLI
  - Verify: `uv run pytest tests/unit/scripts/test_allocation_transaction_costs.py`
  - Requirements: 1, 2, 3, 4

- [x] 4. Add the study contract, FOA complexity YAML, and research note
  - Verify: study manifest validation; note ends with an allowed conclusion
  - Requirements: 5

- [x] 5. Register the spec in `specs/status.md`
  - Verify: repository hygiene coverage of the new spec directory
  - Requirements: 5
