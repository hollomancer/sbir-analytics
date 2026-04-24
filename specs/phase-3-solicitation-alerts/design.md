# Phase 3 Solicitation & Award Candidate Alerts — Design

## Architecture

Two new signal methods on the existing `TransitionScorer`. One parameterized
Dagster asset factory that emits three materializations (one per signal
class). One new extractor for SAM.gov Opportunities. One new parquet output
plus evidence NDJSON. No new scorer class, no new config tree, no weekly
digest, no feedback plumbing.

### Data flow

```
                                           +-----------------------------+
validated_phase_ii_awards (existing) ----> |   prior_award_universe      |
                                           |  (UEI, CET, abstract,       |
                                           |   POP_end, agency/sub-tier/ |
                                           |   office, NAICS)            |
                                           +-------+---------------------+
                                                   |
                                                   v
+----------------+   +----------------+   +----------------+
|  S1 source:    |   |  S2 source:    |   |  S3 source:    |
|  FPDS /        |   |  SAM.gov Opps  |   |  SAM.gov Opps  |
|  USAspending   |   |  notice_type   |   |  notice_type   |
|  contracts     |   |  in {sole-src, |   |  == solicit-   |
|  (existing)    |   |   justif,      |   |  ation         |
|                |   |   NOI, award}  |   |  + SBIR.gov    |
+-------+--------+   +--------+-------+   +--------+-------+
        |                     |                    |
        +---------+-----------+-----+--------------+
                  | pair_filter_for_s1/s2/s3()
                  v
         +----------------------------------+
         |  build_candidate_asset(          |
         |    signal_class, pair_filter,    |
         |    weights, threshold )          |
         +----------------+-----------------+
                          |
                          v
         +----------------------------------+
         |  TransitionScorer (existing)     |
         |  + score_topical_similarity      |
         |  + score_lineage_language        |
         +----------------+-----------------+
                          |
                          v
         +----------------------------------+
         |  phase_iii_candidates.parquet    |
         |  phase_iii_evidence.ndjson       |
         +----------------------------------+
```

### Key components

1. **`SamGovOpportunitiesExtractor`** — `sbir_etl/extractors/sam_gov_opportunities.py`.
   Parquet-first, API-fallback. Mirrors `docs/SAM_GOV_INTEGRATION.md`.

2. **`Opportunity` model** — `sbir_etl/models/opportunity.py`. Pydantic row
   contract (see requirements §3 for fields).

3. **`sam_gov_opportunities_ingestion`** — Dagster asset parallel to
   `sam_gov_ingestion.py`. Daily cadence. Output:
   `data/raw/sam_gov_opportunities/opportunities.parquet`.

4. **Two new methods on existing `TransitionScorer`**
   (`packages/sbir-ml/sbir_ml/transition/detection/scoring.py`):

   - `score_topical_similarity(prior_award, target, *, weight: float) -> float`
     — v1 implementation combines NAICS-code overlap, PSC-code overlap,
     and Jaccard token overlap over title + abstract vs. target
     description. No embeddings.
   - `score_lineage_language(target_description: str, *, weight: float) -> float`
     — regex + phrase match. Two phrase lists:
     - **Phase III lineage**: "Phase III", "Phase 3", "derives from",
       "extends", "completes", "prototype transition", "follow-on
       production", "continuation of".
     - **Data-rights lineage** (signals that a Phase III / data-rights
       review is warranted; not evidence of violation): "technical data
       package", "interface control document", "source code",
       "government purpose rights", "unlimited rights".
     Returns a capped max-match score scaled by weight.

   Existing six signal methods are untouched. The scorer still reads
   weights from the config dict it is already handed; the new methods
   accept a `weight` kwarg explicitly (they do not rely on the
   `self.*_config` pattern) so they can be called with per-signal-class
   weights passed in by the asset factory.

5. **`build_candidate_asset`** — factory in
   `packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates/assets.py`.
   Signature:

   ```python
   def build_candidate_asset(
       *,
       signal_class: SignalClass,
       pair_filter: Callable[[DataFrame, DataFrame], DataFrame],
       weights: dict[str, float],
       high_confidence_threshold: float,
   ) -> AssetsDefinition: ...
   ```

   Produces three asset definitions:
   - `phase_iii_retrospective_candidates` (S1)
   - `phase_iii_directed_candidates` (S2)
   - `phase_iii_followon_candidates` (S3)

   All three write rows to the same `phase_iii_candidates.parquet` with
   distinguishing `signal_class`. Factory-generated assets are standard
   Dagster pattern; this is not an abstraction for its own sake.

6. **Pair filters** — three module-level functions in
   `packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates/pairing.py`:

   - `pair_filter_s1(prior, contracts)` — `contract.recipient_uei IN
     prior.uei_set` AND hierarchical agency match
     (agency → sub-tier → office, finest available) AND NOT
     `contract.phase_iii_already_coded`.
   - `pair_filter_s2(prior, opps)` — `opp.notice_type IN
     {sole_source, justification, notice_of_intent, award}`; match by
     `awardee_uei IN prior.uei_set` when present, else fall back to
     agency + NAICS match.
   - `pair_filter_s3(prior, opps)` — `opp.notice_type == "solicitation"`
     AND (NAICS overlap OR PSC overlap) AND token-overlap Jaccard ≥ 0.10
     on title tokens. Cheap pre-filter to keep cross-product manageable.

   No class, no generator, no strategy pattern. Three functions.

### Signal-class weight constants

Live as plain constants in `assets.py`, not YAML. Eight-entry dicts per
class. Sum to 1.0; unit-test asserts.

```python
WEIGHTS_S1 = {
    "agency_continuity": 0.20,
    "timing_proximity": 0.15,
    "competition_type": 0.20,
    "patent_signal":    0.05,
    "cet_alignment":    0.10,
    "vendor_match":     0.20,
    "topical_similarity": 0.05,
    "lineage_language":   0.05,
}
WEIGHTS_S2 = { ... "competition_type": 0.25, ... }  # sole-source dominant
WEIGHTS_S3 = { ... "topical_similarity": 0.40, "cet_alignment": 0.15, ... }
```

If a consumer needs to tune a weight, they edit a constant and open a PR —
same mechanism that governs the existing transition detection defaults.
YAML config tree is earned after that happens more than once.

### Confidence thresholds (v1: one per class)

- **S1**: HIGH ≥ 0.85
- **S2**: HIGH ≥ 0.75
- **S3**: HIGH ≥ 0.60

v1 emits `is_high_confidence: bool` and `candidate_score: float`. LIKELY /
POSSIBLE buckets are added if/when a query asks for them.

### Precision gate — backtest script, not asset check

A backtest script `scripts/phase_iii_precision_backtest.py`:

1. Loads DoD-coded Phase III contracts (treating them as ground-truth
   positives).
2. Runs the scorer over them.
3. Asserts S1 HIGH precision ≥ 0.85.
4. Exits non-zero on failure.

Wired into CI as a release gate, not a Dagster asset check. The
materialization of the asset does not depend on a human-maintained audit
ledger.

S2 and S3 precision are tracked via a simple CSV at
`reports/phase_iii/audit/<signal_class>.csv` with columns
`candidate_id,audited_at,auditor,verdict,note`. The same backtest script
reads the CSVs and prints current precision for each class. No parquet
ledger, no asset check, no dagster.materialize() gated on an HR process.

### Output formats

- `phase_iii_candidates.parquet` — canonical row store (all three
  signal classes).
- `phase_iii_evidence.ndjson` — per-candidate evidence bundles mirroring
  `transitions_evidence.ndjson` shape.
- `reports/phase_iii/audit/*.csv` — hand-audit precision tracking.
- `reports/phase_iii/backtest.json` — output of the precision backtest
  script (latest run).

No weekly markdown digest. No review cards. No triage action labels.

## Asset boundaries (what does NOT change)

- Existing six `TransitionScorer` signals and their weight-reading
  pattern are untouched. The two new methods sit alongside them and
  accept an explicit `weight` kwarg.
- `validated_phase_ii_awards` is not modified.
- `validated_phase_iii_contracts` is not modified. No additive column,
  no env-var gate, no feedback plumbing in v1.
- No existing Pydantic model is changed. New models are purely additive.
- No existing Dagster asset is renamed.

## Config shape (minimal)

Only the extractor gets new YAML — everything else is in-code constants.

```yaml
extraction:
  sam_gov_opportunities:
    parquet_path: data/raw/sam_gov_opportunities/opportunities.parquet
    parquet_path_s3: null
    use_s3_first: true
    api_rate_limit_per_minute: 60
    api_key_env_var: SAM_GOV_API_KEY
```

No `phase_iii_candidates:` config block. If needed later, it's additive.

## Testing strategy

- **Unit (scorer additions)**: table-driven tests for
  `score_topical_similarity` and `score_lineage_language`. Lineage
  phrase-match corpus includes positives (real Phase III justification
  text) and adversarial negatives (Phase I abstracts mentioning
  "phase III of combustion", "prototype" in non-transition context).
- **Unit (pair filters)**: three tests, one per filter, each with a
  small synthetic prior-award frame + target frame.
- **Integration**: one test that materializes all three assets against a
  100-row fixture (mixed known positives / known negatives) and asserts
  schema, evidence-NDJSON structure, and score bounds.
- **Precision backtest**: S1 against DoD-coded Phase III (production
  data, offline). HIGH precision ≥ 0.85 gate.
- **Hand-audit CSVs**: 100-row sample per class; committed under
  `reports/phase_iii/audit/` when the first run is produced.

## Deferred (explicitly)

- Delivery channels (email, Slack, webhooks).
- Weekly markdown digest / review-card output format.
- Triage action labels ("letter of concern" etc.).
- YAML weight presets + Pydantic config tree.
- `paecter_embeddings_opportunities` asset. S3 v1 uses NAICS / PSC /
  Jaccard filters; embeddings return only if precision < 0.60.
- `validated_phase_iii_contracts` reclassification feedback column.
- Multi-band confidence (LIKELY / POSSIBLE) — single HIGH flag for v1.
