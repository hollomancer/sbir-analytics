# USAspending Multi-FY Contract Archive Union — Design

## Current flow

The transition asset calls `find_latest_local_contract_archive`, which sorts all matching archive
filenames by update date and returns one path. The extractor and manifest consequently model the
source as a scalar even when the local directory contains multiple fiscal partitions.

## Proposed flow

1. Resolve the configured fiscal-year set before extraction.
2. Group valid `Contracts_Full` filenames by fiscal year and choose the latest revision inside
   each group.
3. Stream each selected archive through `AwardArchiveContractExtractor` in deterministic order.
4. Reconcile repeated transaction IDs across archives, retaining identical repeats and rejecting
   conflicts.
5. Publish one Parquet output and one manifest bound to the complete ordered archive set.

The resolver should return a typed sequence carrying fiscal year, revision date, and path rather
than infer those values repeatedly from strings. The asset should accept an explicit fiscal-year
configuration; implicit "all files currently present" behavior would make the cut unstable.

## Failure behavior

- Missing requested fiscal year: fail before scanning.
- Multiple same-date revisions for one year: require byte identity or fail as ambiguous.
- Repeated transaction ID with different canonical content: fail and emit the conflicting archive
  names and transaction identifier.
- Existing scalar-cache manifest: invalidate and rebuild; do not reinterpret it as a set.

## Provenance and migration

The manifest schema gains an ordered `award_archives` collection and an archive-set SHA-256.
During one compatibility release, the existing singular `award_archive_file` may be emitted only
when the set contains one item. Consumers must use the set-level fingerprint for cache validity.

## Testing strategy

- Resolver fixtures with two fiscal years and multiple revisions within one year.
- Missing-year and ambiguous-revision failure tests.
- Two tiny ZIP fixtures containing a repeated identical transaction and a conflicting transaction.
- Asset test proving input order does not change output bytes or manifest order.
