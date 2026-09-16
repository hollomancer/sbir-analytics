# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
under the repository policy in [docs/steering/versioning.md](docs/steering/versioning.md).
The root project and all packages under `packages/` release as one synchronized
version.

## [Unreleased]

### Changed

- Company-name normalization now has one implementation. Eight functions that
  carried their own rule (`ot_consortium.registry.normalize_cmf_name`,
  `models.uspto_models._normalize_name`,
  `transformers.patent_transformer._normalize_name`, and the normalizers in
  `pull_techport_nasa`, `text_richness_2x2`, `sbir_ma_signal_counts_by_fy`,
  `bootstrap_form_d_leverage_ci` and `assets/transition/utils`) now call
  `sbir_etl.identity.normalize_company_name` with a named profile. Five new
  profiles record the behavior that no existing profile covered: `cmf-v1`,
  `uspto-assignee-v1`, `benchmark-firm-key-v1`, `lower-join-v1` and
  `patent-assignee-v1`.
- Three join keys now collapse interior whitespace runs, which changes 31 of
  34,459 distinct award company names (0.090%): `bootstrap_form_d_leverage_ci`,
  `sbir_ma_signal_counts_by_fy` and `assets/transition/utils`. Names such as
  `"aPeak  Inc."` and `"aPeak Inc."` become one key instead of two. Blank and
  `None` names now key to `""` rather than `"NONE"` in the TechPort puller.
- `assets/transition/utils._norm_name` now case-folds rather than lower-cases,
  because it shares `lower-join-v1` with `sbir_ma_signal_counts_by_fy`, which
  already case-folded. The two differ only outside ASCII — `"Straße GmbH"` keys
  to `strasse gmbh` instead of `straße gmbh`. No company name in the current
  award data is affected: `.lower()` and `.casefold()` agree on all 34,459
  distinct values.
- The 14 library digest functions now delegate to the shared SHA-256 helpers.
  Digest values do not change: each migrated function was checked against
  `hashlib.sha256` over a multi-chunk payload, so frozen manifest SHAs still
  match. Digests of serialized structures (`_row_sha256`,
  `ordered_columns_sha256`, `_ordered_columns_sha256`) are a different concern
  and are left alone.
- The Form D candidate ledger is unchanged by default. With
  `--include-legal-form-variants` off the output is byte-identical to the
  previous ledger, verified against the `2026-08-30` study index, and with it on
  the exact rows are unchanged, so filtering to
  `match_rationale == "exact_form_d_join_v1_name_key"` reproduces the frozen cut
  exactly.

### Added

- `check_identity_boundaries.py` rejects a company-name normalizer that does not
  reach `sbir_etl.identity.company_names`. Person-name and state-name
  normalizers are listed as reviewed exceptions; `scripts/archive/` stays
  unscanned so published numbers keep the normalizer that produced them.
- `sbir_etl.utils.data.file_io` gains `file_sha256`, `file_sha256_or_none` and
  `sha256_bytes`. Source-provenance digests were written from scratch in 14
  library call sites under seven different names, with no shared helper to
  import.
- `build_sbir_ma_form_d_candidates.py` gains `--include-legal-form-variants`,
  which also emits candidates whose names meet only after legal designators are
  stripped (`recipient-v1`). A legal-form difference is what defeats most
  SBIR-to-EDGAR name matches: against the full Form D filer universe the widened
  key raises the share of SBIR firms finding a filer from 5.46% to 12.28%
  (2,349 more firms). On the `2026-08-30` study index it adds 6,356 candidate
  rows to the 5,744 the exact key finds.
- `build_sbir_ma_form_d_identity_review_queue.py` now normalizes the Form D
  issuer name with the candidate's own `name_key_profile` instead of always the
  exact profile, and names the key that produced the candidate in
  `prefilled_evidence_codes` (`exact_key_candidate` or
  `legal_form_variant_candidate`). Comparing a widened candidate under the
  exact profile disagreed on the legal suffix alone — the difference the
  widened key exists to tolerate — silently denying it the alias-agreement
  prefill.
- Widened Form D rows carry the fields needed to adjudicate them:
  `name_key_ambiguous` and `form_d_cik_count` when one key reaches several CIKs
  (136 of 6,356 rows), and `sbir_exact_key_count` / `sbir_exact_keys` when
  several SBIR spellings collapse onto one widened key. A widened row is a
  candidate, not a resolution.

## [0.16.0] — 2026-09-15

### Breaking

- `validated_phase_iii_contracts` now also emits task orders placed under an IDV
  that explicitly declares SBIR/STTR Phase III, so `phase_iii_contracts.parquet`
  gains rows and every rate derived from it moves. Inheritance is fail-closed:
  the parent must resolve to one unambiguous IDV, and a general-purpose vehicle
  that happens to carry a single Phase III order does not confer status on its
  siblings. A PIID reused by different IDVs is omitted from the lookup rather
  than guessed at.
- `PhaseIIIContract` gains a required `phase_iii_evidence` field, alongside
  optional `parent_contract_id` and `phase_iii_inherited`. Code that constructs
  the model directly must now state how the row was identified — `direct_10q`,
  `direct_sbir_phase`, `direct_research`, or `parent_declared`. A validator
  rejects rows where `phase_iii_inherited` and `phase_iii_evidence` disagree, so
  a consumer can filter on either one.

### Added

- The C4 allocation transaction-cost study
  (`studies/allocation-transaction-costs/`,
  `scripts/data/allocation_transaction_costs.py`,
  `docs/research/allocation-transaction-costs.md`) compares NIH SBIR against an
  R01-equivalent baseline. It reports the break-even reviewer-hour count as the
  identified result and records the directional efficiency claim as
  underidentified. Hours per award, dollars per award, and cost per awarded
  dollar stay separate rather than collapsing into one efficiency score.
  Reviewer hours are anchored in Gallo 2019 with the NSF 2021 Merit Review
  Survey as a second anchor, the UK full-system estimate as an external
  benchmark, and the FDP activity decomposition recorded from the primary
  reports. The total-cost break-even is reported beside the applicant-only one,
  and the sweep shocks one side at a time.
- The R16 permutation-separation validation design for `phase-iii-census`:
  `assets/phase_iii_negative_controls/permutation.py` and
  `scripts/data/build_phase_iii_placebo_permutation.py` compare the actual frame
  against 500 seeded placebo frames and report an exceedance share with a Wilson
  95% interval for the primary statistic and each secondary cell. The design is
  frozen in `studies/phase-iii-census/validation-design.md` under SHA pinning.
  `build_placebo_assignment` and `permute_prior_end_dates_across_firms` take an
  optional `seed`; `criteria.summarize_survivors` and
  `criteria.build_sensitivity_grid_from_full` are public aliases for the frozen
  per-stage summaries.
- Two study-claim CI guards, run by `make lint-boundaries` and the CI quality
  job. `check_study_artifact_roundtrip.py` requires a rendered deliverable to
  reproduce from its committed sidecar, and every renderer to be registered or
  waived with a reason. `check_deterministic_as_of.py` refuses a wall-clock
  as-of default in the three places that fix a data cut, including the semantic
  form — a `None` default that the body resolves with `as_of or clock()`, a
  ternary, or an `if as_of is None:` branch. Neither guard accepts a blank
  exemption reason: a waiver or allowlist entry with no reason is reported and
  exempts nothing. Three pre-existing paths are recorded on the as-of burndown
  allowlist, including `supply_chain/release_validation.py`, where release age
  moved with the clock.
- A `named-reader-reviewer` agent role that checks what a declared outside
  reader would quote from a packet and whether that sentence is licensed. It
  routes on packet type rather than header presence, so a packet missing its
  reader header still reaches the check; inventory edits to
  `docs/research-questions.md` are exempt from the header rule and resolve their
  reader from the enclosing policy area.

### Fixed

- `validated_phase_iii_contracts` emitted `parent_contract_id` as `NaN` rather
  than `None` on rows with no parent, because `DataFrame.apply` infers a string
  dtype over mixed `str`/`None` and rewrites the missing entries. `NaN` is
  truthy, so `if row["parent_contract_id"]:` was true for every parentless row.
- The consultant-hours arithmetic in the allocation transaction-cost study was
  corrected, and an assumption that had been presented as an anchor no longer
  claims to be one.
- Pinned study CSVs are stored with LF endings and pinned against normalisation
  via `.gitattributes`, so a checkout on another platform does not change the
  bytes a manifest records.

### Changed

- The SBIR-versus-R01 contrast is recorded as an allocation-mechanism
  comparison, not a performer comparison.
- Two C4 citations moved off reserved research-question slots, and the new
  sources were added to the inventory.

## [0.15.0] — 2026-09-14

### Breaking

- A promotion-intended discovery capture now fails closed instead of recording
  that it should not have run. When a protocol declares `intended_rank` above
  `exploratory`, `run_ma_discovery_sample.py` refuses to start from a checkout
  with uncommitted changes, and refuses when git is unusable, because silence is
  not evidence of cleanliness. `_code_version` had always computed the dirty
  flag and nothing gated on it; that is how 948 of 1000 pairs in one held-out
  cut were captured by code whose state is not recoverable from git. Exploratory
  runs make no rank claim and are unaffected.
- `validate_study_manifests.py` now fails when a frozen run manifest records a
  `protocol_sha256` that disagrees with `validation_result.design_sha256`. The
  protocol pin is checked before a run and nothing stopped it being edited and
  re-pinned afterwards, which is how one design came to be pinned about ten
  hours after the replay it was supposed to have preregistered with every
  run-time check passing. Manifests predating the field are not flagged.
- `StudyManifest` gains an optional `reproduction` block, and a study that
  declares one must satisfy it: each `LiveSource` names a `retrieval_manifest`
  that has to appear in `frozen_artifacts`, and each `ReproductionTolerance`
  must name a quantity that is either a declared `upstream_measure` or
  mentioned in the study's estimand, permitted claims, or limitations. A band on
  a quantity nothing reports cannot be breached.
- `classify_rebuild` requires an `identity_grain` argument and carries it into
  the verdict, because a comparison that does not say what "the same rows" meant
  cannot be audited.

### Added

- `sbir_etl/quality/reproduction.py` classifies a rebuild against a live
  upstream into exact, upstream drift, pipeline regression, identity
  divergence, or outside tolerance. Row identity is checked before counts: an
  upstream can revise a record in place, so equal counts over different rows is
  the case a count-only comparison silently passes.
- `run_ma_discovery_sample.py` records `protocol_sha256` and
  `protocol_yaml_sha256` in its run manifest, so the design a result names can
  be compared mechanically against the design the run actually read.
- `specs/upstream-drift-reproduction/` specifies how `reproducible` stays
  checkable when an input is a live public source that its publisher updates.
- `studies/sbir-ma-dated-signal-study/` adds a prospective F1 signal protocol at
  `exploratory`, with sources acquired privately and uncommitted.

### Changed

- `transition-scoring` moves from `exploratory` to `reproducible`. Its fusion
  corpus rebuilt from committed scripts to 828 rows, 138 positives, and 101
  firms, matching the frozen figures, and the retrieval manifest for that pull
  is committed and pinned. An earlier rebuild in the same session produced 822
  and 137 and was read as archive drift; it was a truncated fetch, which is the
  distinction the reproduction contract exists to make.
- `ma-discovery-recall` stays `exploratory` and now records its held-out result
  rather than leaving the outcome unstated: 4 strict medium/high pairs of 307
  strict-eligible, Wilson 95% [0.0051, 0.0330], against a preregistered floor of
  10, with `threshold_met` and `confirmatory` both false and five
  `post_hoc_analyses` entries. An evidence audit established the pinned design
  postdates the evaluated run, so the study cannot promote on this cut.
- `docs/research-questions.md` and `studies/README.md` state that the inventory
  rank `Validated` requires `validation_result.threshold_met: true`, since a
  manifest at `validated` no longer implies the threshold was met.

## [0.14.0] — 2026-09-13

### Breaking

- `validated` now means the preregistered validation design was run as written
  and its result is recorded with uncertainty; it no longer implies the
  threshold was met. `citable` additionally requires `threshold_met: true`.
  `StudyManifest` gains a `validation_result` block (numerator, denominator,
  interval, method, `threshold_met`, `confirmatory`, `post_hoc_analyses`),
  required at `validated` and above. Its `design_path` and `design_sha256` must
  match one `frozen_artifacts` entry exactly, so a result cannot cite the hash of
  some other pinned file as its design, and its `confirmatory` flag must be true
  to promote. `confirmatory` asserts the design was frozen before the run; the
  schema does not verify that ordering and the auditor checks it against git.
  `ValidationDesign` gains `threshold_basis` and `threshold_value` (both
  required at `validated` and above) and `frozen_population_artifact`
  (required for count thresholds and checked against `frozen_artifacts`).
  `decision_threshold` stays prose, so `threshold_value` restates the same
  threshold as a number the basis is checked against: a count floor can no
  longer be filed under `threshold_basis: proportion`. The inventory guard
  now demotes a `validated` manifest whose `threshold_met` is false to
  `computable`, so a recorded miss cannot surface as a `Validated` answer in
  `docs/research-questions.md`. Existing manifests below `validated`
  load unchanged. Documented post-hoc analyses are reportable and are no
  longer an audit BLOCK by themselves; presenting one as confirmatory still is.
  (`studies/README.md`, `docs/steering/epistemic-tiers.md`,
  `.claude/agents/evidence-auditor.md`.)

## [0.13.0] — 2026-09-12

### Breaking

- Removed the press-wire enrichment stage from M&A discovery. Deleted
  `sbir_etl/enrichers/ma_discovery/press.py`; `enrich_ma_events` and
  `merge_press_signals` are gone from the package's public exports. All 18 of
  the stage's matches were false positives, so no true signal is lost.
- Changed the Form D high-tier rule. A person-name score of at least 0.7 no
  longer reaches `high` on its own; it now needs an exact ZIP or a state
  overlap. The historical rule is retired as `person-or-zip-v1` and the current
  one is `corroborated-person-v2`. Every `match_confidence` object must persist
  `rule_version`; unversioned or mixed-version inputs fail before analysis.
- `build_ma_events` no longer emits rows whose `acquirer` is empty. A row that
  cannot name a counterparty cannot support an exit claim, and a consumer could
  not tell unknown-acquirer from firm-was-the-buyer.
- Study manifests at `validated` or `citable` now require a `validation_design`
  block naming the addressable population, expected yield, decision threshold,
  and how that threshold was derived. Manifests below that status are
  unaffected.

### Added

- `sbir_etl/capital_events/cross_enrichment.py`: a provenance layer that links
  Form D and M&A candidate records and reports whether M&A evidence is
  independent of the Form D filing it came from. M&A metadata now carries
  `candidate_status`, `legal_event_validated`, and `cross_enrichment`.
- Fail-closed M&A discovery with a confirmatory recall floor, a blocking
  coverage gate, and freeze/replay support for sample runs.
- Artifact-boundary tests that assert what M&A consumers rely on: every emitted
  event names a counterparty, `signal_count` matches the signals it reports,
  and a missing input yields `[]` rather than an error.
- Adversarial must-not-match cases for the company-matching functions, drawn
  from real production attribution errors, alongside DUNS-confirmed positives.
- An audited Form D control-identity universe and an exploratory supplier-share
  census.
- Exploratory NASA, Air Force, and DOE post-Phase-II commercialization outcomes
  analysis.
- Automated GitHub release publishing from a pushed tag.

### Fixed

- Press-wire watchlist matching used unanchored substring comparison, so every
  match it produced was a false positive. Matching is now word-boundary
  anchored with a four-character floor, and each hit records where it matched.
- Restored the press-wire feeds. BusinessWire's feed returns an error envelope
  and is dropped until a replacement URL exists; PR Newswire and GlobeNewsWire
  poll normally.
### Fixed

- Versioned the Form D tier rule as `corroborated-person-v2`, added a
  deterministic atomic offline rescorer, and made current downstream consumers
  reject unversioned or mixed-rule detail rows.
- Retired the historical `person-or-zip-v1` fundraising result and dependent
  cohort reports because their local inputs cannot be pinned or fully rebuilt;
  the replacement study now fails closed on filing/CIK and amendment-chain
  aggregation gates.
- Corrected the v0.12.0 Form D amendment shortcut's interpretation: without a
  filing-number chain key it is an interim heuristic, not a proven lower bound.

## [0.12.0] — 2026-08-31

### Fixed

- `validated_phase_iii_contracts` and the `phase_transition_pairs`/survival
  assets now write their parquet unconditionally, including when the frame
  is empty. Skipping the write on an empty result left the previous parquet
  on disk beside a freshly written `checks.json` reporting `total_rows: 0`,
  so a legitimate zero-row run looked like a stale one (#692).
- `load_form_d_control_universe` refuses Form D control-universe staging
  products (a `.provisional.jsonl`/`.identity-staging.jsonl` filename,
  staging-shaped records, or a sibling manifest reporting an unready gate)
  instead of loading them silently on a mismatched identity key (#692).
- Form D amendment filings no longer inflate `total_form_d_raised` and
  `offering_count` by being summed alongside the filing they amend. The fix
  is a documented lower bound, not exact chain collapse — that is blocked on
  locating the SEC file number that links an amendment to its original (#692).
- The phase-transition report read latency from `pairs` (one row per matched
  contract) while reading the transition rate and agency counts from
  `survival` (one row per Phase II award), mixing two denominators under one
  transition vocabulary. All three now read `survival` (#692).

### Changed

- Consolidated three reviewed spec proposals into the specs that already own
  the surface they touch, rather than three new registry entries:
  `specs/phase-iii-source-materialization/tasks.md` gained the transition
  source/lineage work, and a new `specs/sec-source-fidelity/` spec covers
  EDGAR event-date and Form D source fidelity (#692).

## [0.11.0] — 2026-08-26

### Added

- Exploratory, non-citable headcount-at-award readout over the canonical
  SBIR.gov bulk materialization: schema and agency-year coverage, cap-slackness,
  near-cap firms, mechanical >500 anomaly buckets, and award-history
  repeat-award proxies. Uses `PRELOAD_V1` firm merge. Not a cap-removal
  policy estimate and not a study promotion (#668).

### Changed

- GitHub Action `peter-evans/create-pull-request` 7 → 8 (#670).

## [0.10.0] — 2026-08-19

### Added

- Weekly literature-map refresh: `OpenAlexClient.search_works`,
  `make literature-map`, and a Monday GitHub Action that opens a PR for
  new OpenAlex works plus GAO/NAP/CRS/ITIF RSS items. Authored memos and
  `[L#]` entries are not rewritten (#666).
- Exploratory, non-citable A-CP7 notebook for top-10 incumbent
  repeat-winner displacement (descriptive slot counts, not causal
  crowd-out) (#665).

## [0.9.0] — 2026-08-19

### Added

- Importable M&A discovery toolkit at `sbir_etl.enrichers.ma_discovery`
  (query generation, keyword verifier, mock search, press-wire merge, and
  optional CLIs). Name cleaning goes through `sbir_etl.identity`. Search
  backends and the LLM extractor are not in this release (#661).

### Changed

- `make ci-local` now reproduces pull-request CI (lint, guards, Dagster
  validate, compose, Bandit, pinned `detect-secrets`, unit `-m "not slow"`,
  hermetic e2e) instead of the post-merge coverage suite (#660).
- Phase III PR canary no longer claims to be the ≥85% HIGH-precision
  benchmark. A mixed-signal slice fails if retrospective weights are
  swapped; the S3-corpus number stays a manual run (#660).

## [0.8.0] — 2026-08-18

### Added

- Reserved inventory Status ranks (`Computable`, `Validated`, `Citable`) now
  require a matching `studies/*/study.yaml`. CI enforces the pairing
  (`scripts/ci/check_research_question_status.py`) (#654, #657).
- `studies/form-d-fundraising` at `reproducible`: frozen Form D leverage
  estimand, restored `scripts/data/bootstrap_form_d_leverage_ci.py`, and
  F3 Status may say Computable. Not validated or citable (#658).

### Changed

- Audience start-here lists only reserved Status ranks or explicit refusals.
  F3 is split into the Form D leverage estimand and causal questions that
  design cannot answer. E4–E6 are marked operational. Unbacked F1 M&A point
  estimates were removed from the inventory (#657).
- Phase III census research-outputs index now treats `study.yaml` as the
  clock: August identity, matching, outcomes, and placebo memos are
  recorded; hand-labeled validation remains open (#656).

## [0.7.1] — 2026-08-18

### Added

- Hermetic end-to-end coverage for `core_refresh_job` (#649).
- Job-level execution tests for `phase_transition_latency_job`,
  `cet_full_pipeline_job`, and `cet_drift_job` (#650).
- Unit tests for the previously untested Neo4j categorization, SEC EDGAR,
  organization, and patent-loading paths, plus weekly-report LLM digest
  builders (#651).

### Changed

- Specs that declared `evidence` without the four-item contract were
  retiered; `phase-iii-census` remains the only evidence target, and CI now
  requires amendments SHA paperwork plus a declared estimand (#635).
- The evidence-tier checker fence-strips `amendments.md` before the SHA
  scan. The new job tests pin `core_refresh_job` membership, the production
  `cet_drift_job` selection, and the CET pipeline skip path (#652).

### Fixed

- `OrganizationLoader.create_subsidiary_relationships` kept an invalid pair
  (with a `None` child) and dropped a later valid pair when a mixed batch
  contained a hole (#652).

## [0.7.0] — 2026-08-18

### Added

- `SourceAdapter` protocol and `SourceRefreshRunner`, with `USAspendingAPIClient`
  wrapped as the reference adapter, restoring `uv run refresh-enrichment
  --source usaspending` (#619).
- Pipelines-tier `AnalysisSpec` / `AnalysisRun` platform with a registry-driven
  runner, snapshot compare, and `scripts/data/run_analysis.py --profile`; the
  prior hard-coded tech-area builder CLIs remain as deprecated shims (#619).
- STTR spinout-linkage exploratory kernel: identity resolution, generic-token
  guard, typed dimension-absence reasons, and the frozen Order 0–4 linkage
  cascade (#623), its D1 award-spine loader and design freeze-hash guard
  (#627), and a D4 money/paper-trail scorer scoring the subcontract and
  spinout signals as two independent directions (#632).
- STTR spinout-linkage partner-type seed lists: FFRDC, IPEDS, new-model-org,
  fiscal-sponsor, and IRS nonprofit-registry data captured; the
  research-hospitals list is left honestly pending on two dead-end sources
  (#624).
- `evidence-auditor` and `deployment-safety-reviewer` specialist review
  agents, cross-checked against the actual evidence-tier contract and
  self-hosted server runbook they enforce (#646).
- A crosswalk from the canonical 21-area CET taxonomy to the 14 national
  security CET areas in Appendix A of the August 2026 National Security
  Science and Technology Strategy, with Appendix B's priority-need alignment
  and a `docs/nssts-2026-alignment.md` explainer of what the strategy does
  and does not license (#647).

### Changed

- `specs/sttr-spinout-linkage` frozen as Revision 1: all 12 open design
  questions resolved, including a second research pass confirming no public
  or paid source directly supplies Bayh-Dole research-institution-to-SBC
  license records (#620, #626).
- `make lint-boundaries` now runs the same eight guard scripts as the CI
  quality job, including two that were previously CI-only (#633).
- Remaining `(str, Enum)` classes migrated to `StrEnum`, enforced by a
  targeted `UP042` check in `make lint` and CI; Python version wording
  unified to 3.11–3.12 throughout (#634).
- CLAUDE.md and agent role instructions deduplicated behind a single shared
  pointer (#636).
- The steering glossary and requirements template point confidence bands at
  their owning config or doc instead of restating them, and disambiguate
  enrichment "evidence" from the epistemic `evidence` tier (#637).
- Steering checklists that read as CI gates but were not enforced anywhere
  are relabeled as guidance, with the genuinely CI-enforced contracts kept
  in their own table (#638).
- Per-spec glossaries scrubbed of confidence bands they never owned;
  archived specs keep only glossary terms still used in their own
  requirements text (#639).

### Fixed

- The USAspending refresh pipeline: requests carried only `award_id` and
  could never match an award, the runner checkpoint was never cleared so an
  award refreshed once was skipped forever, and NaN identifiers reached the
  API as the literal string `"nan"` (#621).
- The analysis platform: `run_analysis.py --profile` wrote no census
  artifacts, the calibration-drift gate was unreachable from the CLI, and a
  malformed analysis registry could crash the entire Dagster definitions
  load instead of just the affected cohort assets (#622).
- The STTR linkage kernel: a generic-token guard bypass on the exact-match
  identity path, a guard failure that collapsed into a measured negative
  instead of blocking the label, `D4MoneyTrail`'s single shared status
  letting one direction's typed absence suppress the other's real signal,
  and an unreachable cascade branch (#628).
- `D4MoneyTrail` construction after the kernel's status-field split, which
  had been failing `Fast Tests` on every open pull request (#647).

## [0.6.0] — 2026-08-15

### Added

- OpenAlex and PubMed enricher clients with sync facades and mocked unit tests
  (#616).
- STTR spinout–subcontract linkage Phase 0 spec (exploratory, gated), dedicated
  B1/B2 inventory questions, and an exploratory partner-type commercialization
  notebook (#615).
- Bayh-Dole / D3 license-source research as O-12: no public microdata for
  research-institution-to-SBC licenses (#617).
- A blocking hygiene check that every top-level spec declares a
  research-question anchor (#612).

### Changed

- Outside-reader Status lines and Form D / Massachusetts report leads now use
  plain language while staying inside study boundaries (#613).

### Fixed

- Corrected the live-server health check to use production Neo4j variables and
  dependencies instead of E2E-only assumptions (#611).
- Made the Tailscale route helper runnable with the macOS system Python used by
  host preflight checks (#611).
- Made server rebuilds remove services retired from the Compose definition
  (#611).
- Restored the non-root `sbir` runtime contract for all three Dagster services,
  including one-time ownership migration for existing persistent directories
  (#611).

## [0.5.1] — 2026-08-12

### Added

- A weekly comprehensive test and branch-coverage lane with a 70% floor, plus
  hermetic end-to-end tests on every pull request (#602, #603).
- Operated-path coverage for CET analytics and validation, weekly enrichment,
  and congressional-district fiscal allocation (#605).

### Changed

- Lint now runs over the whole repository, including exploratory `scripts/` and
  `notebooks/`; formatting remains scoped to the primitives and pipelines trees.
  `make lint` runs the same three steps as the CI job.
- Reframed the README around what is verifiable, promoted epistemic tiers into
  the reading path, and added a "Verifying a checkout" gate list.
- Normalized spec and document naming to kebab-case, and added an index for
  `examples/`.
- Relocated the generated `pytest-split` timing file to `tests/.test_durations`.
- Reclassified component-level tests into unit and integration suites, leaving
  the E2E suite to execute two production Dagster workflows with hermetic inputs
  and explicit network rejection (#604).
- Removed environment-variable skips that silently prevented slow ML tests from
  running in the comprehensive suite (#603).

## [0.5.0] — 2026-08-12

### Added

- NSF private-capital Phase 1 gate: a repaired, horizon-bounded Phase I→II
  graduation estimand with connected-component identity resolution, and a
  pinned exploratory review artifact with a deterministic manifest (#577).
- Fail-closed FY M&A signal counts, replacing the incoherent match-rate spec
  with a count diagnostic that refuses to publish without a real input (#588).

### Fixed

- Neo4j load summaries report canonical graph labels and distinguish rows
  submitted from nodes written, so an idempotent re-run no longer reads as a
  failure and a partial load no longer reads as a success (#574).

## [0.4.0] — 2026-08-12

### Added

- **Epistemic tier system.** A four-tier contract (`primitives`, `pipelines`,
  `evidence`, `exploratory`) governing what each artifact may claim, documented in
  `docs/steering/epistemic-tiers.md`, declared across `sbir_etl`, `packages/`, and
  the analysis scripts, and enforced by a blocking import guard
  (`scripts/ci/check_tier_boundaries.py`) wired into CI and `make lint-boundaries`.
- **Study contracts** under `studies/` for reproducible, citable research, with
  manifest validation in CI. Transition scoring is the first contract.
- **Notebook-first research workflow** — `notebooks/` workbench, template,
  backlog, and companion notebooks over the canonical script artifacts.
- **Tech-area cohort reporting** parameterized by technology area, with a
  reproducible composition emitter and figure audit.
- **Repository guards**: large-file blocking at 5 MiB, configuration-boundary
  checks that route YAML loading through `read_yaml_mapping`, spec-registry
  coverage, and dead documentation-link detection.
- End-to-end coverage for the weekly report render and the Neo4j graph
  round-trip.

### Changed

- Promoted source-download pipelines, jurisdiction identity, exact award
  identity, and the SBIR award grain out of scripts into library modules.
- Consolidated the seven production `yaml.safe_load` call sites behind a single
  loader with an explicit `allow_empty` policy.
- Declared `sbir-graph` loaders as `pipelines` tier and `sbir_etl` config,
  models, and company-name handling as `primitives` tier.

### Fixed

- CI coverage reporting no longer implies a coverage gate that was not enforced.
- Corrected precision-gate documentation: the ≥85% Phase III HIGH-precision
  benchmark is enforced on PRs by a fixture-level canary, not by a full-corpus
  CI run.
- Repaired rotted end-to-end and functional tests, and wired the health check
  into server operations.

### Removed

- The phantom ML vectorizer API — a zero-byte module plus documentation for five
  classes that were never implemented.
- The private analytics API and the stale API map.

## [0.3.0] — 2026-08-04

### Changed

- Generalized the self-hosted server runbook so host-specific paths and
  materialization state live in an untracked local file.
- Improved developer onboarding.

### Removed

- Private analytics API.

## [0.2.0] — 2026-08-04

First release under the synchronized versioning policy, with versions aligned
across the root project and the three packages under `packages/`.

## Earlier tags

`0.1` and `v0.11` predate the versioning policy and do not follow the
`vMAJOR.MINOR.PATCH` form it requires. Per that policy published tags are never
moved or reused, so they remain as historical markers.

[Unreleased]: https://github.com/hollomancer/sbir-analytics/compare/v0.16.0...HEAD
[0.16.0]: https://github.com/hollomancer/sbir-analytics/compare/v0.15.0...v0.16.0
[0.15.0]: https://github.com/hollomancer/sbir-analytics/compare/v0.14.0...v0.15.0
[0.14.0]: https://github.com/hollomancer/sbir-analytics/compare/v0.13.0...v0.14.0
[0.13.0]: https://github.com/hollomancer/sbir-analytics/compare/v0.12.0...v0.13.0
[0.12.0]: https://github.com/hollomancer/sbir-analytics/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/hollomancer/sbir-analytics/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/hollomancer/sbir-analytics/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/hollomancer/sbir-analytics/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/hollomancer/sbir-analytics/compare/v0.7.1...v0.8.0
[0.7.1]: https://github.com/hollomancer/sbir-analytics/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/hollomancer/sbir-analytics/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/hollomancer/sbir-analytics/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/hollomancer/sbir-analytics/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/hollomancer/sbir-analytics/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/hollomancer/sbir-analytics/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/hollomancer/sbir-analytics/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/hollomancer/sbir-analytics/releases/tag/v0.2.0
