# Steering

Durable engineering contracts. These describe rules that hold across features —
change them deliberately, not as a side effect of a feature branch. Several are
enforced by guards in `scripts/ci/`.

| Contract | Enforced by |
|---|---|
| [Epistemic tiers](epistemic-tiers.md) | `check_epistemic_tiers.py` |
| [Company identity](company-identity.md) | `check_identity_boundaries.py` |
| [Repository structure](structure.md) | `check_architecture_boundaries.py` |
| [Versioning and releases](versioning.md) | `check_versioning.py` |
| [Data quality](data-quality.md) | Asset checks |
| [Enrichment patterns](enrichment-patterns.md) | Convention |
| [Pipeline orchestration](pipeline-orchestration.md) | Convention |
| [Neo4j patterns](neo4j-patterns.md) | Convention |
| [ML methodology review](ml-methodology-review.md) | Review checklist |

Reference: [product scope](product.md), [technology decisions](tech.md),
[glossary](glossary.md).
