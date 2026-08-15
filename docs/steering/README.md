# Steering

Durable engineering contracts and guidance. Several contracts are enforced by
guards in `scripts/ci/`; others are conventions for reviewers and operators and
are **not** CI gates.

## CI-enforced contracts

| Contract | Gate |
|---|---|
| [Epistemic tiers](epistemic-tiers.md) | `check_epistemic_tiers.py` |
| [Company identity](company-identity.md) | `check_identity_boundaries.py` |
| [Repository structure](structure.md) | `check_architecture_boundaries.py` |
| [Versioning and releases](versioning.md) | `check_versioning.py` (+ release workflow) |
| [Data quality](data-quality.md) | Dagster asset checks |

## Guidance (not CI)

| Doc | Status |
|---|---|
| [Enrichment patterns](enrichment-patterns.md) | Convention |
| [Pipeline orchestration](pipeline-orchestration.md) | Convention |
| [Neo4j patterns](neo4j-patterns.md) | Convention / ops guidance |
| [ML methodology review](ml-methodology-review.md) | Recommended PR review notes |

Reference: [product scope](product.md), [technology decisions](tech.md),
[glossary](glossary.md).
