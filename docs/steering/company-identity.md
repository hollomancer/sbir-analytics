# Company identity contract

Company identity is an evidence-producing decision, not generic string cleanup. Live
callers use `sbir_etl.identity` for company-name normalization and similarity. The shared
API has two guarantees:

1. every normalization policy is explicitly named and versioned; and
2. every similarity score uses a `0..1` scale, even when a compatibility adapter exposes
   RapidFuzz's historical `0..100` convention.

## Decision order

Identity resolution remains identifier-first:

1. exact validated UEI;
2. exact validated CAGE or DUNS when the source and study permit it;
3. exact name under the declared profile;
4. fuzzy name candidate generation under declared thresholds; and
5. human or study-specific adjudication where required.

Name similarity alone must not establish a negative claim such as “this firm never
received an SBIR award.” Absence claims require a study-specific coverage contract over
the identifiers, aliases, source universe, and data cut being searched. The Phase III
census study manifest therefore keeps `negative_evidence_allowed: false` until that
contract exists.

## Compatibility profiles

The initial profiles preserve existing behavior so migration cannot silently change
research outputs:

| Profile | Current consumer |
|---|---|
| `matching-v1` | local company-master matching |
| `recipient-v1` | USAspending recipient matching |
| `entity-resolution-v1` | Phase 0 cross-source resolver |
| `groundtruth-v1` | Phase III success-story award resolution |
| `vendor-crosswalk-v1` | transition vendor crosswalk persistence |
| `vendor-resolver-v1` | transition vendor resolver |
| `form-d-join-v1` | agency/private-capital join keys |
| `ucc-v1` | UCC debtor matching |
| `sec-edgar-v1` | SEC company lookup and mention filtering |
| `sec-edgar-trailing-v1` | single-suffix SEC mention/noise filtering |
| `notice-key-v1` | Phase III notice attribution |
| `phase3-ranking-v1` | Phase III firm-ranking benchmark |

These profiles intentionally do not imply equivalent recall. Consolidating two profiles
requires a versioned change, a before/after output comparison on the relevant corpus,
and review of every changed auto-link and dropped candidate. Compatibility shims may keep
old import paths temporarily, but the implementation belongs in `sbir_etl.identity`.

Person-name matching, grant-number matching, and storage-only display cleanup are separate
domains and do not use company-name profiles merely because their old helper was also
called `normalize_name`.
