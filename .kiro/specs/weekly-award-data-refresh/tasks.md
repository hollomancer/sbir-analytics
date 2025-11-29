# Implementation Plan – Weekly SBIR Award Data Refresh

- [ ] 1. Establish data validation utilities
  - [ ] 1.1 Create `scripts/data/awards_refresh_validation.py` to stream-validate the CSV (row count, column schema, checksum)
  - [ ] 1.2 Add canonical column schema reference (JSON) in `docs/data/` for validation
  - [ ] 1.3 Implement metadata writer that emits `reports/awards_data_refresh/<DATE>.json` and Markdown summary

- [ ] 2. Author GitHub Actions workflow
  - [ ] 2.1 Add `.github/workflows/weekly-award-data-refresh.yml` with cron + manual triggers
  - [ ] 2.2 Implement download, validation, metadata, and diff guard steps
  - [ ] 2.3 Integrate `peter-evans/create-pull-request` to open PRs with standardized branch naming and labels
  - [ ] 2.4 Upload raw CSV + metadata as run artifacts for observability

- [ ] 3. Wire up commit/PR conventions
  - [ ] 3.1 Configure git author env vars (`GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`) inside workflow
  - [ ] 3.2 Add CODEOWNERS entry or assign reviewers for `data/raw/sbir/awards_data.csv`
  - [ ] 3.3 Create PR template snippet (optional) or leverage auto-generated Markdown summary

- [ ] 4. Documentation & runbook
  - [ ] 4.1 Document the workflow usage and manual override instructions in `docs/data/awards-refresh.md`
  - [ ] 4.2 Update `README.md` (or relevant data sourcing doc) to mention the automation
  - [ ] 4.3 Note validation + artifact expectations for on-call rotation
