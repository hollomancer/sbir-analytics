# Award Export Source Pipeline — Design

## Current flow

The Phase II path owns an exact CSV reader and then constructs canonical award
identities. The SBA study uses Pandas directly and counts source rows. A broad
loader collapses source editions for other uses. These are different contracts.

## Proposed flow

```text
pinned export + source sidecar
            |
            v
verify bytes, row count, and ordered schema
            |
            v
exact 42-column raw frame (EXPORT_ROW_V1)
            |
            +--> Phase II canonicalization (existing behavior)
            |
            +--> SBA study view (Award Year + jurisdiction rules)
```

Move the exact parser and ordered schema to a canonical extractor module. Keep
Phase II canonicalization in its current pipelines package and import the raw
reader there. This preserves its output contract while removing parser
ownership from a study-specific asset.

## Verification order

The verified entry point performs these steps:

1. Parse and validate the source sidecar.
2. Resolve its repository-relative input path against an explicit root.
3. Check SHA-256 and bytes.
4. Read the exact CSV.
5. Check raw row count and ordered-schema fingerprint.
6. Return the raw frame and a deterministic verification record.

No step searches a directory for a newer file.

## Source capture

The capture interface writes to a new dated directory. It stages bytes and
metadata before an atomic rename. This spec defines behavior for new captures
only. Existing files remain in place.

## SBA study view

The study owns state and territory inclusion, fiscal-year selection, and count
grouping. It passes versioned profile values to the loader and writes them to
its result manifest. The loader never interprets a row as an official award.

## Compatibility

Golden tests compare current and migrated SBA analytical values. Phase II tests
compare parser output, canonicalized output, and provenance fields before and
after the refactor.

## Failure behavior

Missing sidecars, mutable paths, invalid metadata, mismatched bytes, wrong
headers, malformed rows, and count mismatches are hard failures. Errors name the
declared vintage and failed check.

## Evidence consequence

This pipeline proves which bytes and transformations were used. It does not
validate a comparison band or authorize an external claim.
