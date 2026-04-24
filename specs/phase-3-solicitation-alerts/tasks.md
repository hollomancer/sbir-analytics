# Phase III Solicitation & Award Candidate Alerts — Tasks

Ordered so each phase produces a standalone deliverable. S1 first (highest
ROI, clearest precision benchmark, no new data source). S2 adds the
Opportunities API. S3 adds the competitive-follow-on path. Each phase can
ship independently.

## Phase 1: Scorer extension + models

- [ ] 1.1 Add `PhaseIIICandidate` Pydantic model in
      `sbir_etl/models/phase_iii_candidate.py`.
- [ ] 1.2 Add `SignalClass` StrEnum (`RETROSPECTIVE`, `DIRECTED`,
      `FOLLOWON`) next to it.
- [ ] 1.3 Add a `topical_similarity` helper module (e.g.
      `packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates/similarity.py`)
      that computes a float similarity score from (prior_award, target)
      using NAICS overlap + PSC overlap + Jaccard token overlap. The
      asset factory passes the result into the existing
      `TransitionScorer.score_text_similarity`. No new scorer method
      for this signal.
- [ ] 1.4 Add `score_lineage_language` method to existing
      `TransitionScorer` in
      `packages/sbir-ml/sbir_ml/transition/detection/scoring.py`,
      reading its weight from `self.lineage_config["weight"]` to match
      the existing `score_*` pattern. Regex + phrase match for
      Phase III lineage phrases and data-rights lineage phrases (see
      design §4).
- [ ] 1.5 Unit tests for the topical-similarity helper and for
      `score_lineage_language`, including adversarial negatives.

## Phase 2: S1 — retrospective reclassification

- [ ] 2.1 Create
      `packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates/`
      package with `__init__.py`, `assets.py`, `pairing.py`.
- [ ] 2.2 Implement `pair_filter_s1` in `pairing.py` (structural filter:
      UEI overlap + hierarchical agency match + NOT already-Phase-III-coded).
- [ ] 2.3 Implement `build_candidate_asset` factory in `assets.py`.
      Instantiate `phase_iii_retrospective_candidates` from the factory
      with `WEIGHTS_RETROSPECTIVE` constants and `HIGH_THRESHOLD_RETROSPECTIVE = 0.85`.
- [ ] 2.4 Emit one row per candidate into `phase_iii_candidates.parquet`
      and one JSON line into `phase_iii_evidence.ndjson`.
- [ ] 2.5 Create `scripts/phase_iii_precision_backtest.py` that loads
      DoD-coded Phase III contracts as positives, runs the scorer, asserts
      `RETROSPECTIVE` HIGH precision ≥ 0.85, writes
      `reports/phase_iii/backtest.json`, exits non-zero on failure.
- [ ] 2.6 Wire the backtest script into the existing CI workflow that
      already runs other release gates (reuse — do not add a new workflow).
- [ ] 2.7 Integration test: 100-row fixture with known positives and
      negatives; assert schema, evidence NDJSON structure, precision gate.

## Phase 3: S2 — directed / sole-source notice alerts

- [ ] 3.1 Add `Opportunity` Pydantic model in
      `sbir_etl/models/opportunity.py`.
- [ ] 3.2 Create `SamGovOpportunitiesExtractor` in
      `sbir_etl/extractors/sam_gov_opportunities.py`. Reuse the existing
      `BaseAsyncAPIClient` for rate-limiting, retry, and
      `X-Api-Key` auth. **Add** cursor-based pagination over
      `postedFrom`/`postedTo` date windows — the existing Entity client
      pages by UEI lookup, so the date-window iteration is new code,
      not a shared helper. Mirror the parquet-first, API-fallback
      structure of `SAMGovExtractor`.
- [ ] 3.3 Create `sam_gov_opportunities_ingestion` Dagster asset parallel
      to `sam_gov_ingestion.py`. Daily cadence.
- [ ] 3.4 Add `extraction.sam_gov_opportunities` config block in
      `config/base.yaml` with parquet path, S3 path, rate limit, API key
      env var.
- [ ] 3.5 Implement `pair_filter_s2` in `pairing.py` (notice-type gate +
      UEI match, else agency + NAICS fallback).
- [ ] 3.6 Instantiate `phase_iii_directed_candidates` from
      `build_candidate_asset` with `WEIGHTS_DIRECTED` and
      `HIGH_THRESHOLD_DIRECTED = 0.75`.
- [ ] 3.7 Integration test on fixture of synthetic SAM.gov notices
      (include real-world justification text as positives).
- [ ] 3.8 Write an initial 100-row hand-audit CSV at
      `reports/phase_iii/audit/directed.csv` once the first production
      run has output.

## Phase 4: S3 — competitive solicitation follow-on candidates

- [ ] 4.1 Implement `pair_filter_s3` in `pairing.py` (solicitation
      notice-type + NAICS/PSC overlap + token-Jaccard ≥ 0.10).
- [ ] 4.2 Instantiate `phase_iii_followon_candidates` from
      `build_candidate_asset` with `WEIGHTS_FOLLOWON` and
      `HIGH_THRESHOLD_FOLLOWON = 0.60`. Column naming uses "follow-on
      candidate", not "Phase III".
- [ ] 4.3 Integration test on a fixture of open solicitations (mix of
      topically-adjacent and unrelated).
- [ ] 4.4 Initial 100-row hand-audit CSV at
      `reports/phase_iii/audit/followon.csv`. If HIGH precision < 0.60,
      either narrow the pre-filter or revisit embeddings (defer the latter
      to a follow-on spec).

## Phase 5: Docs + sign-off

- [ ] 5.1 Short runbook `docs/phase-iii-candidates.md`: how to run the
      pipeline, how to read the evidence bundles, how to add to an audit
      CSV, how to interpret the backtest output. One page.
- [ ] 5.2 Update `docs/research-questions.md` to link this spec from B3,
      B4, and E5's checklist entries.
- [ ] 5.3 Run full pipeline end-to-end on production data. Record counts
      per signal class and per agency in
      `reports/phase_iii/v1_acceptance.json`.
- [ ] 5.4 Compare `agencies_with_zero_phase_iii` before and after the S1
      HIGH population is exposed (as a read-only query against the
      candidate parquet — no modification of
      `validated_phase_iii_contracts` in v1).
- [ ] 5.5 Fill in the gate-condition statement from `requirements.md`
      into `reports/phase_iii/v1_acceptance.md` with actual numbers.
- [ ] 5.6 `test-fixer` pass on any failing tests.
- [ ] 5.7 `quality-sweep` pass.

## Explicit non-tasks (deferred to future specs)

- Email / Slack / webhook delivery.
- Weekly markdown digest or review-card output.
- Triage action labels ("letter of concern", "PCR inquiry").
- YAML weight-preset config tree.
- Per-user subscription / filter UI.
- Non-federal solicitation corpora.
- Direct agency-page scraping.
- `paecter_embeddings_opportunities` asset (S3 uses cheaper filters in
  v1; embeddings re-enter only if precision falls short).
- `validated_phase_iii_contracts` reclassified-column feedback loop.
- Predictive model of Phase II completion likelihood (belongs in B4).
- Multi-band confidence (LIKELY / POSSIBLE) buckets.
