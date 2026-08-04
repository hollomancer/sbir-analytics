# Solicitation source coverage spike status

**Analysis date:** 2026-08-04

**Evidence status:** Reproducible initial award-linkage analysis; not solicitation-text evidence

## Adapter decisions

| Adapter | Decision | Authorized evidence | Remaining boundary |
| --- | --- | --- | --- |
| SBIR.gov bulk award linkage | `go` | Exact award-to-solicitation number and, when co-present, topic-code assertions | Award text is not solicitation text; historical identifier coverage is uneven |
| SBIR.gov solicitation records | `no_go` | None beyond the documentation-derived schema fixture | Endpoint unavailable; no source-native topic descriptions, nested subtopics, status, or agency URLs captured |
| NSF funding opportunities | `no_go` | Source contract and exact solicitation numbers from bulk awards can seed retrieval | No manifested page/document sample or attachment yield measurement |
| SAM.gov opportunities/documents | `no_go` | Existing metadata, description, and URL retention paths identified | No manifested attachment cohort measuring added text, MIME type, duplicates, or failures |
| Grants.gov opportunity detail | `no_go` | Source contract and context-only evidence boundary documented | No bounded adapter or manifested opportunity/version/attachment sample |

The bulk adapter's `go` decision applies only to exact identifier linkage. It does not authorize
solicitation-version, document, requirement, contract-use, or dependency claims.

## Pinned bulk award result

The full SBIR.gov bulk award snapshot was downloaded on 2026-08-03 and analyzed on 2026-08-04.

| Source property | Value |
| --- | --- |
| Source | `award_data.csv` with abstracts |
| Source URL | `https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv` |
| SHA-256 | `efdf7ca5a398703002ebb33345275b0f68e50af3c5db361d48a2456266a23628` |
| Bytes | 394,398,849 |
| Source rows | 219,503 |
| Reviewed columns | 42/42 matched |
| Exact link assertions | 115,147 unique rows |
| Assertion artifact SHA-256 | `85465dc541ba34f058be3c53aa2bc1beddc7e1622d739751ee7dad0527706d72` |

One duplicate source assertion was removed deterministically; all materialized assertion IDs are
unique. Generated Parquet and manifests remain outside version control.

## Award identifier coverage

| Cohort | Awards | Distinct company names | Solicitation ID | Topic code | Both | Funding |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| All agencies | 219,503 | 34,464 | 115,148 (52.5%) | 126,045 (57.4%) | 107,848 (49.1%) | $82.159B |
| NSF, all years | 15,544 | 7,535 | 4,144 (26.7%) | 8,922 (57.4%) | 4,143 (26.7%) | $3.822B |
| NSF, award years 2022–2025 | 1,614 | 1,401 | 1,613 (99.9%) | 1,614 (100.0%) | 1,613 (99.9%) | $824.1M |

The all-years NSF rate is not representative of current data. Coverage changes sharply across
source vintages:

| NSF award-year band | Awards | Solicitation ID | Topic code | Both |
| --- | ---: | ---: | ---: | ---: |
| 2022–2025 | 1,614 | 1,613 (99.9%) | 1,614 (100.0%) | 1,613 (99.9%) |
| 2011–2021 | 4,787 | 16 (0.3%) | 4,787 (100.0%) | 16 (0.3%) |
| 2004–2010 | 3,140 | 2,512 (80.0%) | 2,515 (80.1%) | 2,511 (80.0%) |
| 1983–2003 | 6,003 | 3 (0.0%) | 6 (0.1%) | 3 (0.0%) |

Therefore, an initial current-NSF analysis can use exact solicitation/topic identifiers with nearly
complete observed coverage for award years 2022–2025. Historical NSF analyses must either remain
topic-only where appropriate or retrieve authoritative NSF records; topic-only rows are not emitted
as exact award-to-solicitation assertions. Company counts are distinct source labels, not resolved
legal-entity counts.

## Reproduction

```bash
python scripts/data/build_sbir_bulk_solicitation_links.py \
  --source data/raw/sbir/award_data.csv \
  --source-metadata data/raw/sbir/award_data.meta.json \
  --schema docs/data/sbir_awards_columns.json \
  --analysis-date 2026-08-04
```

The command validates the source header and metadata hash, writes
`award_solicitation_link_assertions.parquet`, a JSON manifest, and a bounded Markdown summary under
`data/processed/solicitation_evidence/` by default. A missing or mismatched metadata sidecar closes
the gate.

## Interpretation boundary

- The bulk row's solicitation number supports an exact identifier link for that award.
- A topic is linked to the solicitation only when both fields occur in the same award row.
- `Award Title` and `Abstract` remain award text; they are not topic descriptions or requirement
  evidence.
- The bulk export contains no nested solicitation subtopics or attachment bodies.
- Exact identifiers do not establish technology use on a later contract or a physical supply-chain
  dependency.

## Next evidence collection

1. Use the 16 exact NSF solicitation numbers observed for award years 2022–2025 to retrieve and
   version the corresponding official NSF funding-opportunity publications.
2. Measure what authoritative NSF documents add beyond the 1,614 award titles and abstracts.
3. Build bounded SAM.gov and Grants.gov attachment manifests and reconcile them with existing GSA
   archive text before authorizing a requirement classifier.
