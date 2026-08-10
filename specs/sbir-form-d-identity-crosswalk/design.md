# SBIR ↔ Form D Identity Crosswalk — Design

## Data flow

```text
pinned control-universe manifest (expected SHA-256)
          ├── pins broad Form D issuer JSONL
          └── pins full-history SBIR award CSV
                         ↓ validate all pins and contracts
SBIR CSV ── exact valid UEI/DUNS graph ──→ SBIR firm identity ledger
       └── identifier-free exact name keys ───────────────┘
                         ↓ every component name
Form D issuer aliases/accessions ── ORGANIZATION_KEY_V1 exact equality
                         ↓
candidate edges at (sbir_firm_id, form_d_cik)
                         ↓
content-addressed JSONLs + deterministic audit manifest
                         ↓
atomic release-directory swap, or rollback to the prior release
```

The module declares `EPISTEMIC_TIER = "pipelines"`. It reshapes pinned source identity evidence
without scoring or accepting a match.

## Inputs

The CLI accepts:

- `--control-manifest`, defaulting to the materialized manifest beside the large
  untracked issuer JSONL at
  `data/processed/agency_private_capital/control_universe/form_d_control_universe.manifest.json`;
- required `--control-manifest-sha256`, the external pin for those manifest bytes;
- `--awards-csv`, defaulting to the full-history public SBIR award CSV;
- `--output-dir`, defaulting to
  `data/processed/agency_private_capital/identity_crosswalk`; and
- required `--code-version`, the full lowercase producer commit SHA recorded in the deterministic
  manifest.

The tracked `docs/research` copy is an audit record, not the runtime default because the large
product is not stored beside it. The materialized control manifest remains the authority for the
broad issuer filename and for the award CSV's hash, size, and row count. The producer does not
accept an unmanifested issuer path. It verifies
the upstream schema, closed quarter range, `complete=true`, `identity_only=true`, and the false
exclusion/covariate/matching gates. Paths recorded inside the manifest must be plain filenames so
they cannot escape the manifest directory. The release target must not contain any pinned input;
otherwise directory replacement would be destructive and the build fails before staging.

Each Form D issuer row must retain a unique normalized numeric CIK and filing-grain alias evidence.
Every alias used for matching is reconstructed from nested filings, so an emitted candidate can
name the exact raw alias and accession that created it. Aggregated aliases that cannot be traced to
a filing are rejected.

## SBIR component construction

The CSV is read with `csv.DictReader`; identifiers stay as strings. Header aliases are intentionally
small and reflect known source editions:

- company: `Company`, `company`, or `company_name`;
- UEI: `UEI`, `uei`, or `recipient_uei`;
- DUNS: `Duns`, `DUNS`, `duns`, or `recipient_duns`.

`source_record` means the one-based CSV data-record ordinal after the header, not a physical line
number; quoted multiline fields therefore still consume one record ordinal.

The shared identifier normalizers decide whether a value is valid. A disjoint-set structure groups
only exact `uei:<value>` and `duns:<value>` nodes observed together on a source row. Component IDs
are the SHA-256 of canonical sorted identifier material under `sbir-firm-id-v1`; the union-find root
itself never becomes an output ID.

Rows without a valid identifier are grouped only with other no-identifier rows sharing the exact
organization key. Their ID material has a separate `name_key` namespace, preventing an equal name
from attaching them to an identifier component. A no-identifier row whose organization key is
blank fails closed because it cannot satisfy the stable name-key contract.

All components are emitted. Components with more than one UEI, more than one DUNS, or malformed
nonblank identifier evidence use `component_status="quarantined_conflict"` and list stable reason
codes. Quarantine does not delete their source evidence or their exact-name candidates; downstream
gates remain closed for every edge regardless of component status.

## Candidate-edge construction

The issuer JSONL is streamed into an index keyed by exact organization key and then CIK. For every
ledger component name, the producer expands all matching CIKs. Evidence is accumulated only inside
one `(sbir_firm_id, form_d_cik)` bucket and canonicalized before serialization.

The `sbir-form-d-candidate-edge-v1` row contains:

- a stable pair-derived `edge_id`, `sbir_firm_id`, and `form_d_cik`;
- `match_method="exact_normalized_name"` and the normalizer version;
- exact matching names plus SBIR row/name and Form D accession/alias evidence;
- the SBIR component status;
- `decision="candidate_unreviewed"`, `same_legal_entity=null`; and
- false `identity_accepted`, `exclusion_eligible`, `matching_eligible`, and `rate_eligible` gates.

There is no first/best CIK policy. A shared CIK across components and a shared name across CIKs both
produce the full Cartesian set implied by exact equality. Offering amounts are not copied from the
upstream issuer rows.

## Outputs and publication

The release directory contains exactly:

- `sbir_firm_identity_ledger.v1.<sha256>.jsonl`;
- `sbir_form_d_candidate_edges.v1.<sha256>.jsonl`; and
- `sbir_form_d_identity_crosswalk.manifest.json`.

JSONL rows use sorted keys and compact UTF-8 JSON with one trailing newline per row. The fixed-name
manifest points at the content-addressed products and records input/output sizes, SHA-256 values,
row counts, contract versions, counts, invariants, and the producer source SHA-256. It contains no
timestamp.

The producer writes the entire new release to a sibling temporary directory. Publication renames
an existing release to a sibling backup, renames the staged directory into place, and only then
deletes the backup. If the second rename fails, it restores the backup. Because staging and target
share a filesystem, each directory rename is atomic.

## Failure behavior

`BuildError` is raised before publication for pin drift, unsafe or missing product paths, malformed
JSON/CSV contracts, duplicate CIKs, untraceable aliases, blank name-only identities, and invariant
failures. A publication exception is propagated after rollback. No partial output is considered a
release without the fixed-name manifest.

## Consequences

The product is a reproducible identity-review worklist, not validated evidence. It improves
traceability and prevents CIK-level aggregation from hiding ambiguity, but it does not close the
private-capital comparison's identity gate and cannot support exclusion or outcome claims.
