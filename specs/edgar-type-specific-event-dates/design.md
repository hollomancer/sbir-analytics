# EDGAR Type-Specific Event Dates — Design

## Current flow

Inbound searches return dated `EdgarMAEvent` objects. `enrich_company` then keeps only the latest
event per filer and serializes a company profile containing all-time mention types plus one latest
date across those retained events. The filing-grain objects are not the authoritative persisted
interface.

## Proposed flow

```text
EDGAR hits → normalized Edgar mention events → event artifact
                                          ↘ deterministic profile aggregation
```

The event artifact is canonical. Its identity should include target company identity, accession
number, and mention type; if one accession legitimately yields multiple classified contexts, add a
stable context ordinal or source locator rather than collapsing them by filer. Profile summaries
are derived conveniences and never replace the event rows.

## Schema

At minimum preserve:

- target canonical name/identifier;
- filer CIK and name;
- accession number and form type;
- filing date;
- mention type and existing noise/classification metadata;
- source query cut or manifest fingerprint.

Add `latest_mention_date_by_type` only if the serialization format supports a stable typed mapping;
otherwise publish a separate long-form type summary. Keep `latest_mention_date` as an explicitly
generic compatibility field during migration.

## Failure and migration behavior

Duplicate byte-equivalent events collapse deterministically. Same-identity conflicts are emitted
to a quarantine/check table and block profile publication. Existing profiles are not assigned
synthetic type dates: consumers must either join the new event artifact or mark the dated branch
unavailable until regeneration.

## Testing strategy

- One target with an older acquisition-related filing and a newer unrelated filing.
- Two distinct accessions from the same filer, both retained.
- Duplicate and conflicting event identities.
- Round-trip provenance from profile type/date back to accession.
- Compatibility test naming latest-any-mention semantics explicitly.
