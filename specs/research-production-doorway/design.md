# Research→Production Doorway — Design

> **Status:** Spec / design. No implementation.
> Requirements: [requirements.md](requirements.md).

## Shape

One YAML file, one loader helper, one CI check. Roughly 150 lines of implementation against
an artifact surface of one file — deliberately at the low end, per requirement 5.

```
contracts/
  registry.yaml            # the doorway: every research→production artifact
  __init__.py              # load_registry(), verify_artifact(), exemptions
scripts/ci/check_doorway.py  # the gate (requirement 3)
```

`contracts/` sits at repo root rather than inside a package because it describes a relationship
*between* the two worlds and belongs to neither.

## registry.yaml

```yaml
version: 1
artifacts:
  - path: packages/sbir-ml/sbir_ml/transition/detection/fusion_coefficients.json
    producer: scripts/phase3_benchmark/refit_fusion.py
    owner_spec: specs/phase3-notice-corpus-fusion/
    content_sha256: "<hash of the committed json>"
    frozen_at: "2026-08-01T15:04:53Z"
    reproducible: false
    reproducible_reason: >
      Fit on data/derived/phase3_notice_corpus.parquet, which is gitignored under *.parquet.
      corpus.manifest.json (frame_hash 4c4064f0…) is the only in-repo witness. Re-deriving the
      corpus requires GSA falextracts + FPDS access and is not reproducible from a checkout.
    inputs:
      - name: phase3_notice_corpus
        witness: specs/phase3-notice-corpus-fusion/corpus.manifest.json
        witness_field: frame_hash
        value: "4c4064f04d04ca2f0c4c96e50ce3be8b6169bfd7ff3d4c51b2a6c804782a7b84"
        durable: false

exempt_reads:
  # Static configuration and reference data — authored, not derived.
  - config/**/*.yaml
  - data/reference/*.csv
```

`reproducible: false` is a first-class value, not a failure. The point is that the gap is
declared in the one place someone will look, rather than discoverable only by noticing a
`.gitignore` line.

## Load-time verification

Requirement 2 is already implemented once, in `fusion_model.py` (PR #482): a
`FROZEN_CORPUS_FRAME_HASH` constant in the installed package, armed by default in
`score_pairs_with_fusion`, with `expected_corpus_hash=None` as the sole explicit opt-out.

Generalise it as a helper, not a framework:

```python
def verify_artifact(path: Path, expected_sha256: str) -> None:
    """Raise if a registered artifact's bytes do not match the registry."""
```

Consuming modules keep their own pinned constant. `contracts/` is **not** imported at runtime by
production code — that would make the packages depend on a repo-root directory that does not ship
in a wheel. The registry is the CI-time source of truth; the in-package constant is the runtime
one; the gate asserts they agree.

This is the one genuinely subtle decision in the design, and it is why requirement 2 says
"a constant in the installed package" rather than "read the registry."

## The gate (requirement 3)

`scripts/ci/check_doorway.py`, run in the `Code Quality` job:

1. AST-walk every module under `sbir_etl/` and `packages/`, collecting string literals and
   `Path(...)` expressions that resolve to a `.json` / `.parquet` / `.csv` path.
2. Drop anything matching `exempt_reads`, anything under a `tests/` path, and anything that
   resolves inside a temp or output directory.
3. For each survivor, require a registry entry whose `path` matches.
4. For each registry entry, require the committed file's SHA-256 to equal `content_sha256`,
   and each input witness field to equal the recorded `value`.
5. Exit non-zero listing every unregistered read and every stale hash.

Step 1 is deliberately syntactic. A dynamic `open(some_var)` will not be caught, and chasing that
would cost more than it returns — the gate exists to stop the ordinary case (someone commits a
new derived file and reads it) from happening silently, not to defeat an adversary.

## Verification

Prove the gate works by breaking it, as with the arm-blindness and hash-guard work:

1. Add a `.json` read to a production module without registering it → gate fails.
2. Mutate one byte of `fusion_coefficients.json` without updating `content_sha256` → gate fails.
3. Change `corpus.manifest.json`'s `frame_hash` → gate fails on the input witness.
4. Add a `config/*.yaml` read → gate passes (exemption works).
5. Revert all four → gate passes.

A gate that has never been made to fail is an assumption, not a control — which is exactly the
failure mode this whole spec exists to correct.

## What this does not do

It does not make the fusion coefficients reproducible. After this lands, a clean checkout still
cannot re-derive them; it can only detect that they changed. Closing that requires committing the
corpus or pinning it in durable storage — a storage decision, deliberately out of scope, and now
recorded as `reproducible: false` where the next person will find it.
