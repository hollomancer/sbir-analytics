# Tech-Area Transition Report — Design (v1)

**Status:** in progress. See `requirements.md` for goals/constraints.

## Goal

Generalize the PR #428 nanotech *pattern* (multi-method cohort → shared transition
signals → deficiency labels → methodology stub) so any `cet_id` can run Method A with
optional Method B/C, without inventing a parallel taxonomy or requiring nanotech-only
inputs (NNI, B82).

## Architecture

```text
config/cet/taxonomy.yaml          # cet_id, keywords, negative_keywords
config/transition_reports/<id>.yaml   # optional keyword_pack, cpc, metadata
        │
        ▼
scripts/data/build_tech_area_cohort.py
        │
        ├─ Method A: keyword_pack OR taxonomy keywords (+ negatives)
        ├─ Method B: taxonomy keywords for same cet_id (triangulation)
        ├─ Method C: optional CPC prefixes (empty if unset)
        └─ enrich_cohort_with_signals()  # reuse nano helpers when artifacts exist
                │
                ▼
data/reports/<cet_id>/
  cohort_keyword.csv
  cohort_cet.csv
  overlap_summary.json
  methodology_stub.md
```

## Config schema

```yaml
area_id: quantum_information_science  # path slug under data/reports/
display_name: Quantum Information Science
audience: null                        # optional report header

# Link to taxonomy.yaml for Method B + default negatives. Null for report areas
# that are not a single CET (e.g. nanotechnology spans materials/manufacturing).
cet_id: quantum_information_science

# Method A — optional richer pack. If omitted AND cet_id is set, taxonomy keywords
# are used. If both omitted, config is invalid.
keyword_pack:
  patterns:                           # regexes OR plain phrases
    - 'quantum comput'
    - 'qubit'
  negative_patterns: []               # extra negatives beyond taxonomy

# Method B override when cet_id is null (nanotech-style multi-CET proxy terms)
method_b_terms: null                  # map {phrase: label} or null

# Optional Method C
cpc_prefixes: []                      # e.g. [B82Y, B82B] for nanotech; empty OK

# Optional plugs — absent means unused
external_reference: null
sector_registries: null
```

**ID rule:** prefer `area_id == cet_id` when the report area is a CET. Nanotechnology
is the documented exception (`area_id: nanotechnology`, `cet_id: null`).

**Config ownership rule:** do not duplicate taxonomy keyword lists unless Method A needs
a *richer or stricter* pack than taxonomy (nanotech, quantum contamination control,
hypersonics dropping bare `supersonic`).

## Keyword matching rules

1. Positives: title + abstract; case-insensitive.
2. Negatives: if *any* negative pattern matches and *no* positive remains after
   excluding spans that are only negative hits, drop the award.
   Practical v1 rule (simple, testable): require ≥1 positive match; **reject** if the
   text matches a negative phrase that is *not* subsumed by a more specific positive
   (e.g. "quantum computing" may contain "quantum" but negatives are full phrases like
   "quantum dot"). Implementation: reject when a negative phrase matches AND no
   positive pattern matched. (Positives are specific; bare "quantum" is not a positive.)
3. Provenance: each cohort row records `keyword_matches` and `keyword_source`
   (`keyword_pack` | `taxonomy`).

## Signal enrichment

Reuse functions from `build_nano_cohort.py` (import or thin shared module later):
`load_phase3_digest`, `load_ma_signals`, `load_form_d_signals`,
`enrich_cohort_with_signals`, `classify_deficiency`.

Missing artifacts → print `signals_absent: [...]` in `overlap_summary.json`; do not
write a methodology claiming 0% channels as measured rates.

## Ownership vs dark-majority-resolution

| Concern | Owner |
|---|---|
| Area YAML, Method A/B/C, overlap, stub methodology | **this spec** |
| WS1–WS6, survey frame, dark capture-recapture | **dark-majority-resolution** |
| Existing `nano_*` scripts / findings prose | PR #428 reference; migrate later |

## Test areas

| Area | Method A source | Risks |
|---|---|---|
| `nanotechnology` | keyword_pack ported from `build_nano_cohort.py` | Regression vs 2,849 |
| `quantum_information_science` | keyword_pack + taxonomy negatives | quantum-dot / well contamination |
| `hypersonics` | keyword_pack **without** bare `supersonic` | sparsity; taxonomy Method B still has `supersonic` for contrast |

## Non-goals (design)

No Dagster, no API refresh layer, no auto findings narrative, no required CPC or
external reference table.
