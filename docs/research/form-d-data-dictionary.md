# Form D Data Dictionary

## Lifecycle and version boundary

`form_d_details.jsonl` is a local, gitignored exploratory artifact. Each current
`match_confidence` object must carry
`rule_version: "corroborated-person-v2"`. Unversioned rows are historical
`person-or-zip-v1` rows and must be rescored before a current consumer uses their
tier. A deterministic offline migration is available at
`scripts/data/rescore_form_d_details.py`.

Versioning makes the Boolean tier rule auditable. It does not validate the
underlying company match.

## Fundraising fields

The Form D XML contains three fundraising amount fields:

| Field | Meaning | Safe treatment |
|---|---|---|
| `totalOfferingAmount` | Amount the issuer intended to offer | Do not treat as capital sold |
| `totalAmountSold` | Cumulative amount reported sold for that offering | Self-reported; requires amendment-chain handling |
| `totalRemaining` | Reported amount remaining | Do not treat as capital sold |

The historical fetcher stored `total_raised` as a sum of
`totalAmountSold` across every attached filing. That field is not an exact
capital-flow total: a D/A amendment can restate cumulative amounts, and a
company record can contain multiple filings or CIKs. Current research must use a
declared accession/file-number and amendment-chain policy before aggregating
dollars. The retired Form D fundraising study does not authorize a current
numerical result.

## Match-confidence fields

| Field | Meaning |
|---|---|
| `rule_version` | Named rule used to assign `tier` |
| `tier` | `high`, `medium`, or `low` under that named rule |
| `score` | Weighted composite retained for ordering; it does not assign the tier |
| `name_score` | Fuzzy company-name score supplied by index matching |
| `person_score` | Best fuzzy SBIR PI to Form D related-person score |
| `person_match_detail` | Human-readable best-person comparison |
| `state_score` | Whether the SBIR state appears among pooled Form D states |
| `address_score` | Whether the SBIR ZIP appears among pooled Form D ZIPs |
| `temporal_score` | Form D timing relative to earliest SBIR award |
| `year_of_inc_score` | Incorporation-year plausibility |

### Current tier rule: `corroborated-person-v2`

| Tier | Record-level rule |
|---|---|
| High | Exact ZIP, or `person_score >= 0.7` together with exact state overlap |
| Medium | Person hit without corroboration, state overlap alone, or missing state evidence |
| Low | No person/ZIP hit and an observed state mismatch |

The historical `person-or-zip-v1` rule promoted a person hit or exact ZIP to
high. It remains available only so old materializations can be interpreted and
migrated; it is not the current default.

An exact ZIP or person-plus-state conjunction satisfies the record-level v2
rule, but neither is proof that the issuer is the SBIR firm. Common-person
collisions, reused addresses, and pooled filing evidence still require review.

## Signal-scope metadata

Current records also expose `match_confidence_scope`:

| Field | Meaning |
|---|---|
| `unit` | `company-record`; confidence was not scored per filing |
| `offering_count` | Number of attached filing records supplying signals |
| `distinct_ciks` | Normalized CIKs represented among those filings |
| `signals_may_span_filings` | More than one filing supplied the pooled evidence |
| `signals_may_span_ciks` | More than one CIK supplied the pooled evidence |

These flags disclose aggregation scope; they do not identify which filing
supplied each score. Until scoring is rebuilt at a declared filing/issuer grain,
no high-tier record should be described as trustworthy solely because it passes
the v2 Boolean rule.

## Temporal and incorporation signals

These are stored as metadata but do not assign the tier:

- `temporal_score`: Form D date vs SBIR award date proximity
  (`1.0` within two years, `0.5` within two to five years, `0.0` later).
- `year_of_inc_score`: `1.0` when incorporation precedes the earliest SBIR
  award, `0.0` otherwise, and null when unavailable.
