# Implementation Plan – Weekly SBIR Award Data Refresh

- [x] 1. Establish data validation utilities
  - [x] 1.1 Create `scripts/data/awards_refresh_validation.py` to stream-validate the CSV (row count, column schema, checksum)
  - [x] 1.2 Add canonical column schema reference (JSON) in `docs/data/` for validation
  - [x] 1.3 Implement metadata writer that emits `reports/awards_data_refresh/<DATE>.json` and Markdown summary

- [x] 2. Author GitHub Actions workflow
  - [x] 2.1 Add `.github/workflows/data-refresh.yml` with cron + manual triggers (includes SBIR awards refresh)
  - [x] 2.2 Implement download, validation, metadata, and diff guard steps
  - [ ] 2.3 Integrate `peter-evans/create-pull-request` to open PRs with standardized branch naming and labels
  - [x] 2.4 Upload raw CSV + metadata as run artifacts for observability

- [x] 3. Wire up commit/PR conventions
  - [x] 3.1 Configure git author env vars (`GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`) inside workflow
  - [x] 3.2 Add CODEOWNERS entry or assign reviewers for `data/raw/sbir/award_data.csv`
  - [ ] 3.3 Create PR template snippet (optional) or leverage auto-generated Markdown summary

- [x] 4. Documentation & runbook
  - [x] 4.1 Document the workflow usage and manual override instructions in `docs/data/awards-refresh.md`
  - [x] 4.2 Update `README.md` (or relevant data sourcing doc) to mention the automation
  - [x] 4.3 Note validation + artifact expectations for on-call rotation
