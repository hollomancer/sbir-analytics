# Source Extractors

## Public SBIR/STTR awards

`sbir_public_awards.py` is the canonical pipeline for SBIR.gov's
`award_data.csv`. It reads identifiers as text in bounded chunks, materializes
the versioned `sbir-source-v2` award key from `sbir_etl.identity.sbir_awards`,
and collapses revised source editions only after all chunks are normalized.
Technology censuses, technology-area cohorts, and the procurement-transition
packet consume this same materialization rather than defining their own award
grain.

The public `award_id` remains a readable lineage field. Joins, counts,
deduplication, and snapshot comparisons use `award_key`; tracking or contract
number alone is not award-grain.

## Federal contracts

`ContractExtractor` streams federal procurement transactions from a USAspending
PostgreSQL directory archive and retains rows matching the configured SBIR vendor frame.
It produces the canonical `FederalContract` parquet used by transition assets.

## Authoritative source

The contract source is `rpt.transaction_search_fpds`, the `is_fpds = TRUE` physical
partition of `rpt.transaction_search`. If an older archive stores data on the unpartitioned
parent, the extractor reads the parent and applies the same `is_fpds` gate row by row. It
never scans the FABS assistance partition.

USAspending's official data dictionary maps:

- `research_code` to `transaction_fpds.research`, with `SR1`/`SR2`/`SR3` and
  `ST1`/`ST2`/`ST3` values;
- `naics_code` to `transaction_fpds.naics`; and
- `product_or_service_code` to `transaction_fpds.product_or_service_code`.

See the [USAspending data dictionary](https://api.usaspending.gov/api/v2/references/data_dictionary/)
and the official
[`TransactionSearch` model](https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/search/models/transaction_search.py).

## Schema verification

PostgreSQL directory-archive member numbers change between snapshots. The extractor does
not guess a member from file size, row shape, a historical number, or Django model order.
It instead:

1. runs `pg_restore --list` against `toc.dat` and resolves the unique FPDS `TABLE DATA`
   entry;
2. verifies the FPDS partition relationship from archive schema metadata;
3. obtains the exact serialized field order from the archive's explicit `COPY (...)`
   statement using a metadata-only restore; and
4. validates all required fields before reading any transaction rows.

Row width is checked against the verified `COPY` list. A schema mismatch, missing member,
ambiguous table entry, malformed FPDS gate, or missing stable key fails extraction. There
is no positional fallback.

`pg_restore` is therefore a runtime prerequisite. Debian images install it through
`postgresql-client`. On macOS with Homebrew's keg-only `libpq`, add
`$(brew --prefix libpq)/bin` to `PATH`.

## Preserved census fields

The parquet carries these source values at top level:

- `transaction_unique_id` — stable transaction key;
- `generated_unique_award_id` — stable contract grouping key;
- `research` — raw FPDS research code;
- `naics_code` — raw transaction NAICS;
- `product_or_service_code` — raw transaction PSC; and
- signed `obligation_amount`, including genuine zeroes and deobligations.

No `sbir_phase` value is inferred from `research`. Missing or malformed obligations remain
null so downstream census validation can fail explicitly; they are never converted to
zero.

## Usage

```python
from pathlib import Path

from sbir_etl.extractors.contract_extractor import ContractExtractor

extractor = ContractExtractor(
    vendor_filter_file=Path("data/transition/sbir_vendor_filters.json"),
    batch_size=10_000,
)
rows = extractor.extract_from_dump(
    dump_dir=Path("data/transition/pruned_data_store_api_dump"),
    output_file=Path("data/transition/contracts_ingestion.parquet"),
)
print(rows)
print(extractor.source_provenance)
```

When `table_files` is configured for selective S3 synchronization, it must name exactly
the member resolved from the archive TOC. A mismatch fails instead of silently reading a
different table.

## Vendor frame

The filter JSON supports UEI, legacy DUNS, and exact normalized company names:

```json
{
  "uei": ["UEI123456789"],
  "duns": ["123456789"],
  "company_names": ["ACME CORPORATION"]
}
```

UEI is preferred. Name matching remains an ingestion compatibility fallback; the Phase III
census pair universe itself is still an exact normalized UEI join.

## Output and cache integrity

Writes are atomic, including an empty schema-bearing parquet when no vendors match, so a
refresh cannot retain stale rows. The Dagster producer records the table/member, ordered
column fingerprint, dump-TOC fingerprint, vendor-frame fingerprint, and parquet checksum
in the adjacent checks manifest. Cache reuse requires those values to match.

Negative obligations are preserved according to
[ADR-001](../../docs/decisions/ADR-001-negative-obligations.md). Transactions remain at
their source grain; this extractor does not aggregate modification chains or infer Phase
III status.
