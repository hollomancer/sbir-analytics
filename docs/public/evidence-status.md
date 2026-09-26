# Evidence status

The repository uses five public evidence-status labels. These labels govern
which substantive claims the repository endorses. They also set one citation
rule: a study result may be cited from an immutable release only when the study
is reproducible or higher, and only with its actual status attached. Exploratory
and retired studies may not be cited.

## Approved evidence

The study passed its prospectively frozen validation threshold and has one
final, pinned claim-boundary review. Only the claims listed in the manifest are
approved. Publication metadata, repository-owner merge authority, and
operational materialization are separate release controls.

## Validated, not approved

The frozen validation design was run as written, and its result and uncertainty
are recorded. A validated result can still fail its threshold. Even when the
threshold passes, the final claim-boundary review may remain incomplete.

## Reproducible, not validated

The declared inputs and implementation can rerun. One or more validation or
source-recovery requirements remain incomplete. Reproducibility does not
establish truth or authorize a substantive finding.

## Exploratory

The work supports hypothesis generation, candidate discovery, measurement
development, design, or unverified linkage. It can inform the next study. It
must not be presented as a validated result.

## Archived or retired

The work is kept for history, provenance, or migration context. It is not a
maintained evidence path.

The `evidence_status` field in each study manifest is the machine-checked
authority for claim approval. The independent `materialization` field controls
whether an operation may run. Directory names, test counts, dashboards, fresh
timestamps, citation metadata, and an open materialization gate are not
evidence-status signals.
