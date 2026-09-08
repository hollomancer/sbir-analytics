# Phase III Source Materialization — Tasks

**Target epistemic tier:** `pipelines`

**Research question anchor:** B1 (Phase III transition measurement)

The source and lineage layer is implemented; `specs/status.md` records it as
Maintenance and directs that it be kept aligned with the census and other
transition consumers rather than extended. These are the remaining alignment
tasks, folded in from two spec proposals reviewed in PRs #687 and #688 rather
than given their own registry entries.

## Contract source-field preservation (from #687)

The award-archive projection at `sbir_etl/extractors/usaspending_award_archive.py:36-67`
decodes a narrow column set, and that narrowness is a deliberate, commented
memory tradeoff — not an accident. The argument for widening it is that
`phase_ii.py:143` carries a lenient `\bPHASE\s+(III|II|I)\b` regex whose only
purpose is to recover a phase from the Element 10Q *label* because the *code*
was never projected. The goal is deleting that compensating fallback, not
repairing a live break: the fallback currently works, so nothing is miscounted
today.

- [ ] 1. Audit the real USAspending archive headers in a notebook.
  - The projection has never been checked against a genuine header row:
    `tests/unit/extractors/test_usaspending_award_archive.py:64` synthesizes the
    CSV header *from `CONTRACT_ARCHIVE_COLUMNS` itself*, and
    `usaspending_award_archive.py:347` verifies column presence only, never value
    semantics — so a code/label swap is currently undetectable.
  - Per CLAUDE.md's notebook-first rule, resolve this before writing the
    downstream tasks; the header names are an open question, not a settled input.
  - Verify: a fixture derived from a real archive member, carrying distinct
    research code and label values.

- [ ] 2. Extend the canonical contract model for the audited fields.
  - Verify: model serialization preserves each optional field without fallback.

- [ ] 3. Expand the archive projection and row mapping, and state the memory cost.
  - The existing comment claims narrowness keeps Arrow record batches small for
    multi-GB members. Measure the change rather than silently reversing it.
  - Verify: CSV→model tests preserve every added field after normalization, and
    the projection's memory footprint is recorded.

- [ ] 4. Bind projection and coverage metadata into source checks.
  - Verify: missing headers fail closed; coverage is emitted per added field.

- [ ] 5. Remove the lenient phase-label regex once the code is projected.
  - This is the task that justifies the work. Do not add fields without it.
  - Verify: `phase_ii.py` classifies from the code, and the label fallback is
    deleted rather than left as dead alternative logic.

## Materialization output integrity (from #688)

The reviewed proposal was framed as a cache-validity problem, but these assets
have no cache: `phase_iii.py`, `phase_ii.py`, and `pairs.py` all recompute
unconditionally on every materialization. The fingerprint framework it proposed
would also have been a second implementation of the manifest already built at
`packages/sbir-analytics/sbir_analytics/assets/phase_transition/sbir_gov_source.py:290-449`,
which already carries source SHA, output SHA, ordered-column SHA, and a
validator that rejects mismatches. Only the empty-output defect was real, and it
is fixed.

- [x] 1. Write transition parquets unconditionally, including when empty.
  - The assets wrote the parquet only when the frame was non-empty while writing
    `checks.json` unconditionally, so a legitimate zero-row run left the previous
    parquet on disk beside a checks file reporting `total_rows: 0`.
  - Verify: `tests/unit/phase_transition/test_empty_output_write.py` covers both
    the stale-overwrite and first-write cases. Done.

- [ ] 2. Extend the existing `sbir_gov_source` manifest to the Phase II/III assets.
  - Reuse that manifest rather than introducing a parallel fingerprint utility.
  - Verify: changing a source input invalidates the dependent output; no second
    canonical-JSON or hashing helper is added.
