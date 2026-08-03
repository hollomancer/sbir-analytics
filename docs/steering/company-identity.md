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

`organization-key-v1` is the durable suffixless comparison key for ordinary company
linkage. It folds case and accents, normalizes punctuation, and removes recognized legal
designators only at the end of a name. Removing designator-like words from the middle of
a name creates false collisions (for example, `PC Photonics` with `Photonics, Inc.`).

`vendor-key-v1` is the durable transition-vendor key. It preserves legal designators but
canonicalizes common long and short forms (`Corporation`/`Corp`, `Company`/`Co`, and
`Limited`/`Ltd`) because vendor records use those distinctions as matching evidence while
still needing spelling variants to share an index entry. Persisted canonical and alias
names remain display text; they are never replaced by the lowercase matching key.

The initial consumer-named profiles remain available as compatibility policies so
migration cannot silently change research outputs:

| Profile | Current consumer |
|---|---|
| `matching-v1` | local company-master matching |
| `recipient-v1` | legacy USAspending recipient normalization |
| `entity-resolution-v1` | Phase 0 cross-source resolver |
| `groundtruth-v1` | legacy Phase III success-story normalization |
| `vendor-crosswalk-v1` | transition crosswalk display cleanup only; never a match key |
| `vendor-resolver-v1` | legacy transition resolver key; equivalent to `vendor-key-v1` |
| `form-d-join-v1` | agency/private-capital join keys |
| `ucc-v1` | UCC debtor matching |
| `sec-edgar-v1` | SEC company lookup and mention filtering |
| `sec-edgar-trailing-v1` | single-suffix SEC mention/noise filtering |
| `notice-key-v1` | Phase III notice attribution |
| `phase3-ranking-v1` | legacy Phase III firm-ranking normalization |

These profiles intentionally do not imply equivalent recall. Consolidating two profiles
requires a versioned change, a before/after output comparison on the relevant corpus,
and review of every changed auto-link and dropped candidate. Compatibility shims may keep
old import paths temporarily, but the implementation belongs in `sbir_etl.identity`.

### First consolidation audit

USAspending and the Phase III ground-truth and ranking callers now use
`organization-key-v1`. Phase 0 remains on `entity-resolution-v1` because its normalized
name participates in stable canonical IDs and needs an explicit ID migration.

The new profile was compared with the three replaced policies over all 34,464 distinct
company names in `award_data.csv` (SHA-256
`efdf7ca5a398703002ebb33345275b0f68e50af3c5db361d48a2456266a23628`). It keeps the
same number of exact-name partitions as `recipient-v1` while changing two partitions:
it removes the false `Engineering Inc` / `Engineering Partnership, Ltd` collision and
joins the punctuated/unpunctuated `Pelletized Straw L.L.C.` variants. Relative to the
ground-truth profile, it adds the `Coherent Photonics` legal-name variants and removes
the false `PC Photonics` / `Photonics, Inc.` collision. Relative to the ranking profile,
it removes its broad `CORP\w*` behavior, which created false collisions among unrelated
names beginning with `Corp...`.

### Second consolidation audit

The transition vendor crosswalk and resolver now use `vendor-key-v1` for all name indices,
exact comparisons, and fuzzy-match inputs. Crosswalk persistence continues to retain
cleaned human-readable canonical and alias names, so an identity key cannot overwrite
source-facing display text.

The legacy crosswalk and shared vendor keys were compared over the same 34,464 distinct
awardee names and pinned `award_data.csv` SHA-256 used in the first audit. The shared key
reduces 34,459 legacy crosswalk partitions to 34,424 vendor-key partitions. All 35 newly
joined groups were reviewed. They consist exclusively of case, punctuation, ampersand,
or canonical legal-designator variants; no ambiguous firms were joined. Examples include
`Planetary Systems Corp.` / `PLANETARY SYSTEMS CORPORATION`, `Alme & Associates` /
`Alme and Associates`, and `I. C. Gomes...` / `I.C. Gomes...`.

Person-name matching, grant-number matching, and storage-only display cleanup are separate
domains and do not use company-name profiles merely because their old helper was also
called `normalize_name`.
