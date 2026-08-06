# Epistemic Tier Enforcement — Requirements

**Target epistemic tier:** `pipelines`

- **Research question:** none directly. Operational obligation: the tier system in
  [docs/steering/epistemic-tiers.md](../../docs/steering/epistemic-tiers.md) protects the
  citability of every answered question, and its own doctrine is that an unenforced
  contract is decoration. The 2026-08 labeling sweep (PRs #550, #551, #552) made module
  tiers machine-readable; nothing yet enforces the dependency rules those labels imply,
  and the sweep surfaced live violations.
- **Status:** active. Implementation starts after PRs #550–#552 merge, since the guard
  reads the `EPISTEMIC_TIER` declarations they introduce.
- **Out of scope:** a fifth tier; directory reorganization; data-level lineage or
  tier-tracking inside Neo4j; study manifests for analytics not named here; runtime
  import hooks; labeling or policing `notebooks/` and the unlabeled remainder of
  `scripts/` (unstated-means-exploratory remains the design there).
- **Verification that proves completion:** the new guard runs in `make lint-boundaries`
  and CI with an empty allowlist, all existing tests pass, and the doctrine section in
  the tiers doc describes the enforced state.

## Problem

The exploratory tier is carrying two orthogonal properties as if they were one: whether
an artifact's outputs may be cited, and whether anyone is obligated to keep it working.
For notebooks the two coincide. For operated inference (fiscal, CET, transition scoring,
the recurring reports) they diverge, and the divergence leaks: pipelines-tier modules
import exploratory modules today, which the exploratory contract forbids. Known edges:

1. `packages/sbir-analytics/sbir_analytics/assets/sbir_neo4j_loading.py` imports
   `sbir_etl.utils.company_canonicalizer` (exploratory fuzzy pre-load deduplication).
2. `sbir_etl/supply_chain/defense_release.py` imports
   `sbir_etl.supply_chain.nsf_screen` (exploratory CET-relevance screening).
3. `sbir_etl/supply_chain/__init__.py` (pipelines package default) re-exports
   `nsf_screen` symbols, so importing the package imports the exploratory module.

The seed list is provisional: the first full-repository guard run (T1.2) is the
authoritative census, and every hit must be either fixed or allowlisted with a removal
condition before the guard merges.

## R1 — Tier-aware import guard

A static checker, `scripts/ci/check_tier_boundaries.py`, following the structure of
`check_architecture_boundaries.py` (AST-based, no module execution).

1.1 THE guard SHALL resolve an effective tier for every first-party module: the module's
    own `EPISTEMIC_TIER` constant if present; otherwise the nearest ancestor package
    `__init__.py` declaration within the same package root; otherwise `exploratory`.

1.2 THE guard SHALL extract absolute imports, literal dynamic imports, and
    package-relative imports (resolving `ImportFrom.level > 0` against the importing
    module's package path), and SHALL evaluate each first-party edge against this
    dependency policy:

    | Importer tier | May import |
    |---|---|
    | `primitives` | `primitives` |
    | `pipelines` | `primitives`, `pipelines` |
    | `evidence` | `primitives`, `pipelines`, `evidence` |
    | `exploratory` | any tier |

1.3 WHEN an edge violates the policy and is not allowlisted, THE guard SHALL exit
    non-zero and print `path:line: <tier> module may not import <tier> module <name>`.

1.4 THE allowlist SHALL be an in-file mapping from importer path to permitted imported
    modules, where each entry carries a comment stating the reason and a concrete
    removal condition — the same doctrine as the retired transitional script bridges in
    `check_architecture_boundaries.py`. IF an edge is allowlisted but no longer present,
    THEN THE guard SHALL fail, so stale entries cannot linger.

1.5 THE guard SHALL run in `make lint-boundaries` and in the CI job that runs
    `check_epistemic_tiers.py`, as a blocking check, and SHALL be covered by unit tests
    exercising tier resolution (own constant, inherited package default, undeclared),
    relative-import resolution, each policy row, allowlisting, and stale-entry failure.

1.6 Declarations remain voluntary per module (package defaults suffice); the guard
    enforces only the dependency consequences of whatever is declared. It SHALL NOT
    require any module to add a declaration.

## R2 — Retire edge 1 by promoting canonical company merge into identity

`canonicalize_companies_from_awards` is fuzzy identity resolution (90/75 thresholds over
self-matching) — the concept `sbir_etl.identity` exists to own. The fix is promotion
under the primitives contract, not extraction of a "deterministic core" that does not
exist.

2.1 THE identity package SHALL expose a named, versioned canonical-merge policy (e.g.
    `build_canonical_company_map(awards, policy=CanonicalMergePolicy.PRELOAD_V1)`) whose
    frozen behavior — key preference UEI > DUNS > normalized name, thresholds, tie
    handling — reproduces the current mapping byte-identically on a committed fixture
    corpus. Behavior changes require a new named policy version.

2.2 THE implementation SHALL satisfy the primitives contract: comprehensive tests, no
    imports from any lower tier. IF equivalence cannot be achieved without importing
    `sbir_etl.enrichers.company_fuzzy_matcher`, THEN the promotion stops, the edge stays
    allowlisted with that finding recorded, and R2 is re-scoped rather than silently
    weakened.

2.3 WHEN the policy lands, `sbir_neo4j_loading.py` SHALL import only `sbir_etl.identity`
    for canonicalization, `company_canonicalizer` SHALL be deleted or reduced to an
    exploratory deprecation shim with no package importers, and the allowlist entry
    SHALL be removed.

## R3 — Retire edges 2 and 3 by dependency inversion

`nsf_screen` decides contestable CET relevance and is correctly exploratory; the fix
moves the composition up, not the screen's tier.

3.1 `defense_release.py` SHALL accept screened-award input as a parameter instead of
    importing `nsf_screen`; the call SHALL move to the exploratory-labeled asset layer
    that already orchestrates the NSF/defense lineage flow.

3.2 `sbir_etl/supply_chain/__init__.py` SHALL stop re-exporting `nsf_screen` symbols;
    remaining callers import the module directly, making every exploratory dependency
    explicit at its use site.

3.3 WHEN 3.1 and 3.2 land, both allowlist entries SHALL be removed, and any output
    column derived from the screen SHALL carry a screen-version attribute so downstream
    readers can tell the signal's provenance.

## R4 — Doctrine: two populations, one tier

4.1 THE tiers doc SHALL gain a short section distinguishing *workbench* exploratory
    (notebooks, one-off scripts — full rot tolerance) from *operated* exploratory
    (anything reachable from a Dagster job or schedule — keeps non-citability, loses rot
    tolerance, and must emit `citable: false` metadata on outputs that leave the
    repository). Operated status is derived from job wiring, never declared, and creates
    no new tier.

4.2 THE same section SHALL state the promotion runway for operated inference: a
    per-artifact `studies/<id>/study.yaml` entering at `exploratory` or `reproducible`,
    created only when a research question needs the number citable — transition scoring
    is the named first candidate; fiscal waits on the `fiscal-tax-impact-v2` gate.

4.3 THE "Current status" list in the tiers doc SHALL be updated to reflect module-level
    enforcement once R1 merges.
