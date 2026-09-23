# Evidence status

The repository uses five public status labels.

## Citable

A tagged study release has exact source identity, a frozen contract, an
executable result, prospective validation, an open publication gate, an
evidence audit, and an outside-reader review. Only the claim listed in that
release is authorized.

## Validated, not citable

The frozen validation design was run as written, and its result and uncertainty
are recorded. A validated result can still fail its threshold. Even when the
threshold passes, publication, outside-reader, materialization, or release
gates can keep the result non-citable.

## Reproducible, not citable

The declared inputs and implementation can rerun. One or more validation,
review, source-recovery, or release gates remain closed. Reproducibility does
not establish truth or authorize a public finding.

## Exploratory

The work supports hypothesis generation, candidate discovery, measurement
development, design, or unverified linkage. It can inform the next study. It
must not be presented as a validated result.

## Archived or retired

The work is kept for history, provenance, or migration context. It is not a
maintained evidence path.

The `evidence_status` and `materialization` fields in each study manifest are
the machine-checked authority. Directory names, test counts, dashboards, and
fresh timestamps are not evidence-status signals.
