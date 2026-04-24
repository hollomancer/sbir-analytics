# Phase III Solicitation & Award Candidate Alerts — Design

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
         |  + reuse score_text_similarity   |
         |    (similarity computed upstream)|
         |  + score_lineage_language (new)  |
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

4. **Scorer extension** — minimal, consistent with existing patterns.
   The existing `TransitionScorer`
   (`packages/sbir-ml/sbir_ml/transition/detection/scoring.py`) exposes
   five public signal methods: `score_agency_continuity`,
   `score_timing_proximity`, `score_competition_type`,
   `score_patent_signal`, `score_cet_alignment`, plus
   `score_text_similarity` which accepts a pre-computed similarity
   float and applies `self.text_config["weight"]`.

   - **Topical similarity reuses `score_text_similarity`.** The asset
     factory computes a similarity float externally (v1: NAICS overlap
     + PSC overlap + Jaccard token overlap over title/abstract vs.
     target description) and passes it into the existing method. No
     new method, no duplicated weight plumbing.
   - **One new method: `score_lineage_language`**, added to
     `TransitionScorer` following the same pattern as the existing five
     scoring methods. Reads weight from `self.lineage_config["weight"]`
     (new scoring-config key; defaults to 0). Regex + phrase match
     over target description with two phrase lists:
     - **Phase III lineage**: "Phase III", "Phase 3", "derives from",
       "extends", "completes", "prototype transition", "follow-on
       production", "continuation of".
     - **Data-rights lineage** (signals a Phase III / data-rights
       review is warranted, not evidence of a violation): "technical
       data package", "interface control document", "source code",
       "government purpose rights", "unlimited rights".
     Returns a capped max-match score scaled by the configured weight.

   One scorer instance is constructed per signal class with its own
   per-class config dict — identical pattern to the existing transition
   presets. No special API carve-outs, no explicit `weight` kwargs.
   Existing six methods and their weight-reading pattern are untouched.

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

Live as plain constants in `assets.py`, not YAML. Each constant is a
scoring-config dict with weights for the seven signals the scorer
actually exposes: the existing five (`agency_continuity`,
`timing_proximity`, `competition_type`, `patent_signal`,
`cet_alignment`), the existing `text_similarity`, and the new
`lineage_language`. Weights sum to 1.0; unit-test asserts.

Vendor match is **not** a scorer signal — UEI overlap is a pair-filter
gate in `pair_filter_s1` and `pair_filter_s2`, so a non-matching pair
is never scored. (The existing scorer has a `vendor_config` key but no
`score_vendor_match` method; it is inert in today's code path and this
spec does not change that.)

```python
# Illustrative; per-signal-class scoring-config dicts (sum to 1.0).
WEIGHTS_RETROSPECTIVE = {
    "agency_continuity": 0.25,
    "timing_proximity":  0.15,
    "competition_type":  0.20,
    "patent_signal":     0.05,
    "cet_alignment":     0.15,
    "text_similarity":   0.10,
    "lineage_language":  0.10,
}
WEIGHTS_DIRECTED = { ..., "competition_type": 0.30, ... }  # sole-source dominant
WEIGHTS_FOLLOWON = { ..., "text_similarity": 0.45, "cet_alignment": 0.20, ... }
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

- **Unit (scorer additions)**: table-driven tests for the new
  `score_lineage_language` and for the external topical-similarity
  computation (NAICS / PSC / Jaccard) feeding `score_text_similarity`.
  Lineage phrase-match corpus includes positives (real Phase III
  justification text) and adversarial negatives (Phase I abstracts
  mentioning "phase III of combustion", "prototype" in non-transition
  context).
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
