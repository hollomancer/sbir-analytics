# Contract Source-Field Preservation — Design

## Field contract

The source layer should carry these concepts independently:

| Concept | USAspending archive field | Canonical destination |
|---|---|---|
| Research code | `research_code` | `research_code` |
| Research label | `research` | existing `research` during migration |
| Awarding top tier | `awarding_agency_name` | existing `agency` |
| Awarding sub-tier | `awarding_sub_agency_name` | existing `sub_agency` |
| Funding top tier | `funding_agency_name` | `funding_agency` |
| Funding sub-tier | `funding_sub_agency_name` | `funding_sub_agency` |
| Transaction narrative | `transaction_description` | existing `description` |
| Base-award narrative | `prime_award_base_transaction_description` | `base_award_description` |

Exact source headers must be verified against the schema-extraction fixture before implementation;
aliases must be explicit rather than fuzzy header matching.

## Component changes

1. Expand `CONTRACT_ARCHIVE_COLUMNS` and `_map_row` with the required raw fields.
2. Extend `FederalContract` with stable optional fields where they are broadly consumed. Critical
   scope fields should not be buried in an opaque metadata blob.
3. Update Parquet serialization and source-provenance checks to carry the expanded schema.
4. Add named compatibility accessors only where an existing consumer cannot migrate atomically.

## Failure and migration behavior

An archive governed by the new contract fails schema verification when a required header is
absent. An older cached Parquet without the new schema must be invalidated, not padded with copied
values. Existing fields keep their current definitions until downstream consumers have migrated;
the change must not redefine `description` as the base-award description in place.

## Testing strategy

- One-row CSV fixture with deliberately different values in every paired field.
- Round-trip test through `FederalContract` and Parquet.
- Null fixture proving no cross-field fallback.
- Schema-drift test for a missing required header.
- Downstream compatibility tests for existing contract consumers.
