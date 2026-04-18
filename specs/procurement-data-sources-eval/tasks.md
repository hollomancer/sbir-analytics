# Procurement Data Sources Evaluation — Tasks

Time-boxed investigation. Target: complete in one focused work cycle. No production
code changes.

## Phase 1 — Inventory

- [ ] 1.1 Re-fetch `github.com/makegov/awesome-procurement-data` README and transcribe
  every listed source into `specs/procurement-data-sources-eval/matrix.md` with the
  uniform-metadata columns defined in design §Step 1.
  → **verify**: Matrix row count equals upstream list entry count; no source
  missing.
- [ ] 1.2 Apply relevance labels (`imputation-critical`, `enrichment-upgrade`,
  `new-enrichment`, `tooling`, `orthogonal`) to every row.
  → **verify**: Every row has exactly one label; orthogonal rows cite why.
- [ ] 1.3 Flag sources that overlap with current integrations
  (`sbir_etl/enrichers/sam_gov/`, `usaspending/`, `fpds_atom.py`) and note whether
  the listed source is a superset, subset, or alternative encoding.

## Phase 2 — Deep evaluation (adopt-candidates)

- [ ] 2.1 **SAM.gov Entity Extracts** — confirm bulk-download availability, file
  format (CSV/JSON/Parquet), update cadence, auth requirements. Test against a
  100-company sample from our corpus missing UEI and report match rate.
  → **verify**: Evaluation doc at
  `specs/procurement-data-sources-eval/evaluations/sam_entity_extracts.md` with
  coverage number and diff proposal for
  `specs/data-imputation/design.md` §4.2.
- [ ] 2.2 **SAM.gov Opportunities API** — capture sample response for an SBIR
  solicitation; confirm fields: per-phase max amount, period of performance,
  NAICS, topic number. Test against 20 FY24 SBIR solicitations and report field
  coverage.
  → **verify**: Evaluation doc; sample payload saved as fixture; diff proposal
  for `specs/data-imputation/tasks.md` Task 4.3 prerequisite.
- [ ] 2.3 **FSCPSC API** — test NAICS prediction on 50 SBIR awards where ground
  truth exists (from USAspending-enriched subset); compare top-1 and top-3
  accuracy against our abstract-NN baseline (if any) or against a naive agency
  majority baseline.
  → **verify**: Accuracy comparison table; auth and pricing model documented.
- [ ] 2.4 **PSC Selection Tool** — confirm NAICS↔PSC crosswalk data is available
  via API; evaluate fit for `naics.solicitation_topic` (§4.8).
  → **verify**: Evaluation doc documents the crosswalk structure and completeness.
- [ ] 2.5 **DIIG CSIS Lookup Tables** — inventory what reference tables the repo
  provides; identify any that feed our NAICS hierarchy or agency-branch
  normalization.
  → **verify**: Evaluation doc lists each table and its relevance.
- [ ] 2.6 **procurement-tools (tandemgov)** — scan the Python library for helpers
  that would reduce boilerplate in our USASpending or FPDS extractors; decide
  adopt-as-dependency vs reference-only.
  → **verify**: Short eval; no adoption without a clear reduction in our own code.

## Phase 3 — Rejections and defers (documented briefly)

- [ ] 3.1 Write one-paragraph rejection rationale for each `orthogonal` source
  (CALC, FAR, Acquisition Gateway, Sec. 889, Pulse of GovCon, Slack bot, Google
  Sheets scraper) in `matrix.md`. No separate eval doc needed.
- [ ] 3.2 Write defer rationale for **AcquisitionInnovation** (R stack, reference
  only) and any other `defer` candidates.

## Phase 4 — Cross-reference and diff proposals

- [ ] 4.1 For every `adopt`-recommended source, write an inline diff proposal in
  `decisions.md` showing exactly which lines of
  `specs/data-imputation/design.md` or `specs/data-imputation/tasks.md` should
  change, and how.
- [ ] 4.2 Confirm that **SAM.gov Entity Extracts** proposal updates §4.2
  (`identifiers.cross_award_backfill`) to add Entity Extracts as the primary
  lookup, with sibling-row backfill as a fallback.
- [ ] 4.3 Confirm that **SAM.gov Opportunities API** proposal replaces the
  agency-page scraping plan in Task 4.3 of the imputation spec.

## Phase 5 — Decision record and follow-on specs

- [ ] 5.1 Produce `specs/procurement-data-sources-eval/decisions.md` with a table:
  `source`, `decision`, `target_method`, `follow_on_spec`, `effort`,
  `prerequisites`, `risks`.
  → **verify**: Every `adopt` row names a concrete follow-on spec directory.
- [ ] 5.2 For each follow-on spec, create
  `specs/<follow_on_name>/requirements.md` with introduction + scope pointing
  back to this investigation. Do **not** write design.md or tasks.md — those
  are that spec's own work.
  → **verify**: Each follow-on spec dir exists with at least a requirements.md.
- [ ] 5.3 Open a PR against the data-imputation branch (or main, depending on
  merge state) carrying the diff proposals from Phase 4. Keep that PR separate
  from the investigation PR so decisions are reviewable independently.

## Explicit non-tasks

- Do NOT write new extractors, enrichers, or config under
  `sbir_etl/` or `packages/` as part of this investigation.
- Do NOT modify `config/base.yaml` beyond what's necessary to record credentials
  for coverage tests (and even those should live in `.env.example`, not base
  config).
- Do NOT sign MOUs, accept ToS on behalf of the project, or commit credentials.
  If a source requires any of those to evaluate, label it `evaluate_further`
  and document the blocker.
