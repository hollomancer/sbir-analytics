# Materialization Semantic Fingerprints — Design

## Fingerprint payload

Each stage emits a canonical JSON payload with:

```text
stage_name
transformation_contract
transformation_version
normalized_config
upstream[{name, output_sha256, semantic_fingerprint}]
direct_sources[{name, sha256}]
```

The semantic fingerprint is SHA-256 over canonical UTF-8 JSON with sorted keys and compact
separators. Stage code owns a named version constant; a Git SHA and package version can be emitted
as diagnostics but do not replace that contract.

## Validation flow

1. Resolve and validate every upstream manifest.
2. Build the expected canonical payload from current configuration and contract versions.
3. Compare its SHA-256 with the stored fingerprint before accepting a cached output.
4. Verify the output bytes against the stored output SHA-256.
5. If any check fails, report the mismatched payload component and require rematerialization.

The validator should be a small shared pipeline utility so stages do not reimplement canonical
JSON or mismatch reporting. The first consumers are `validated_phase_ii_awards`,
`validated_phase_iii_contracts`, pair construction, and the survival frame.

## Version-change discipline

Focused tests should pin representative transformation behavior to its declared version. A test
must fail when a fixture output changes without the expected version bump. This is narrower and
more reviewable than hashing implementation source files, which would invalidate on comments and
miss behavior imported from elsewhere.

## Migration and failure behavior

Legacy manifests without a semantic fingerprint are stale by definition. Migration is a local
rematerialization, not an in-place manifest rewrite. Empty artifacts still publish an output (or
an explicitly hashed empty representation) and a complete manifest so zero-row results cannot
escape lineage checks.

## Testing strategy

- Canonical-payload stability across key order and non-semantic path changes.
- Invalidation on contract version, normalized config, source hash, or upstream fingerprint change.
- Legacy/missing manifest rejection.
- Empty-output lineage test.
- End-to-end fixture across all four transition stages.
