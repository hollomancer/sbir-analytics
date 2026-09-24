# Research status

This file is the public status index. The machine-readable `study.yaml` in each
study directory is authoritative when this summary and a contract disagree.

## Approved evidence

None. The SBA annual-report structural comparison is validated and may be
cited as a validated result from an immutable release, but its substantive
claims are not yet repository-approved evidence.

## Validated, not approved

| Study | Validation result | Why it is not approved evidence |
| --- | --- | --- |
| [SBA annual-report structural comparison](docs/public/sba-structural-comparison.md) | A separate blinded-role implementation reproduced 1,264/1,264 count operands; exact point interval `[1.0, 1.0]` | One final pinned review must approve the exact manifest claim boundary |

## Reproducible research, not validated

| Study | What can be rerun | Why it is not validated |
| --- | --- | --- |
| [SBA annual-report tables](studies/sba-annual-report-tables/) | The original current-data structural check and post-hoc extensions | It cannot reproduce the unavailable publication-era exports; its bands are post hoc |
| [Phase III census](studies/phase-iii-census/) | The declared census and negative-control workflow | Labeled validation and interpretation gates remain open |
| [Transition scoring](studies/transition-scoring/) | The declared scoring reproduction contract | It reproduces scores, not transition truth |
| [Allocation transaction costs](studies/allocation-transaction-costs/) | The bounded NIH SBIR/STTR versus R01-equivalent break-even analysis | Directional ranking remains underidentified |

## Exploratory systems and datasets

These paths support candidate discovery, measurement development, study design,
or analysis that is not approved evidence:

- M&A discovery and dated-signal work, including entity and event-date review.
- Form D and other private-capital matching.
- NASA and NIH comparative-outcome designs.
- Marginal-award identification and social-return break-even design.
- Notebooks unless their header and a study contract explicitly state a higher
  status.

The live exploratory study contracts are indexed in
[the research outputs guide](docs/research/README.md).

## Archived or retired

- [Form D fundraising](studies/form-d-fundraising/) is retired. Its former
  numerical claims are suppressed pending a governed rebuild.
- [The graph projection](archive/neo4j/) is retired. Governed Parquet and DuckDB
  records remain authoritative.
- `docs/archive/`, `specs/archive/`, and `scripts/archive/` preserve historical
  decisions and selected provenance. Archived material is not a maintained
  capability.

## Status meanings

| Status | Meaning |
| --- | --- |
| **Approved evidence** | Passed prospective validation plus one pinned review approving the manifest's bounded claims |
| **Validated, not approved** | Frozen prospective validation was run and recorded; claim approval remains absent |
| **Reproducible, not validated** | Declared inputs and code can rerun; validation remains incomplete |
| **Exploratory** | Hypothesis generation, candidate discovery, design work, or unverified data linkage |
| **Archived / retired** | Preserved for history or provenance; not maintained as an active evidence path |
