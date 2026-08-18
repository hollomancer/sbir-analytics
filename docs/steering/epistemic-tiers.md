# Epistemic Tiers

Every artifact in this repository sits in one of four tiers. The tier declares
how much weight the artifact can carry, and each tier's contract states what it
costs to sit there.

This is the axis the work actually varies on. Technical role — extract, enrich,
transform, load — describes what code does; it says nothing about whether a
number it produces can be quoted to a program officer. Two artifacts with
identical technical roles can differ completely in how much they can be trusted,
and the repository has to make that difference visible.

See the [architecture evidence boundary](../architecture/detailed-overview.md#evidence-boundary)
for how this relates to the current directory layout.

## Why this exists

The cost that grows fastest as research questions accumulate is not lines of
code. It is the maintenance obligation attached to those lines. A repository
with one undifferentiated standard has to hold everything to the standard of its
most rigorous artifact, so every throwaway cohort-builder either gets tests it
does not need or quietly erodes the standard.

Tiering caps that cost by making it **legitimate to not maintain most of the
code**. `exploratory/` work is allowed to be untested, unrefactored, and stale,
because it is labeled non-citable and nothing downstream depends on it. In
exchange, `evidence/` is small, expensive, and genuinely trustworthy.

The tiers are admission control, not a filing system. If a tier's contract is
not enforced, the tier is decoration.

## The four tiers

### 1. `primitives`

Identity resolution, configuration loading, schemas.

| | |
|---|---|
| **Depends on** | Nothing in the repository |
| **Depended on by** | Everything |
| **Contract** | One implementation per concept. Comprehensive tests. Versioned behavior — a change in output is a new named version, never an edit in place. |
| **Reviewed as** | Load-bearing. Assume every downstream number moves when this changes. |

The one-implementation rule is about *contract*, not uniformity. A primitive may
legitimately expose several named, versioned behaviors —
`sbir_etl/identity/` exposes one `company_name_similarity` interface over many
`CompanyNameProfile` policies, because different matching tasks genuinely want
different recall. What is forbidden is a second, unnamed implementation
somewhere else in the tree. Divergent behavior is fine when it is declared;
invisible divergence is the defect.

### 2. `pipelines`

Extraction and materialization.

| | |
|---|---|
| **Contract** | Deterministic. Reproducible from a declared data cut. Re-running on the same inputs produces the same outputs. |
| **Must not** | Perform inference, estimation, or scoring that a reader could mistake for a finding |
| **Reviewed as** | Infrastructure. Correctness means faithfulness to the source, not plausibility of the result. |

Pipelines move and reshape data. The moment a stage starts *deciding* something
contestable, it is doing evidence-tier or exploratory-tier work and needs the
matching contract.

### 3. `evidence`

Artifacts that can be cited outside this repository.

All four of these are required. There is no partial admission:

1. **Frozen spec** — a design note fixed at a content hash, describing the
   method before the run.
2. **SHA enforcement** — inputs pinned by hash; a manifest recording input
   hashes, sizes, row counts, and output hash.
3. **Blocking asset checks** — quality gates that fail the materialization
   rather than warn.
4. **Declared estimand** — a written statement of what quantity is being
   estimated, and what would make the estimate wrong.

Reference implementation for the required machinery: the Phase III census
(`specs/phase-iii-census/`, `packages/sbir-analytics/sbir_analytics/assets/phase_iii_census/`).
Its frozen specification, SHA enforcement, declared estimand, and blocking
asset check are the pattern to compare against directly. The census itself is
currently `reproducible`, not citable: its study manifest keeps results
non-citable until complete audit tables and post-write checks have passed.

Entering this tier is meant to be expensive and visibly so. The correct default
answer to "should this be evidence-tier?" is no.

### 4. `exploratory`

Everything else.

| | |
|---|---|
| **Contract** | Labeled non-citable. That is the whole contract. |
| **Permitted** | No tests, no interface stability, no cleanup, going stale |
| **Forbidden** | Being depended on by any other tier, except an approved temporary migration bridge; producing numbers that leave the repository without relabeling |

Most of `scripts/` belongs here and there is no shame in it. Exploratory work
answering a question once is the normal mode of research. The failure is not
writing it — it is leaving it indistinguishable from work that earned a stronger
claim.

#### Temporary migration bridges

An approved dependency from a package into `scripts/` is a migration bridge,
not a fifth tier and not an implicit promotion of the script. It must be named
in the architecture guard, limited to a compatibility wrapper, and have a
removal condition: move the implementation behind a package API while retaining
the CLI as an entry point. No new bridge may be added without those conditions,
and an `evidence` artifact may not depend on one. See
[structure.md](structure.md#transitional-script-dependencies) for the current
bridge policy; no transitional bridges are currently active.

#### Two populations: workbench and operated

The exploratory tier deliberately holds two different kinds of artifact, and
only one of them gets the tier's full permissions.

**Workbench** work — `notebooks/`, one-off analyses in `scripts/`, cohort
builders run once — carries the whole contract and every permission that comes
with it: no tests, no interface stability, allowed to rot.

**Operated** work is exploratory code reachable from a Dagster job or schedule:
the recurring reports, fiscal estimation, CET classification, transition
scoring. Operated status is derived from job wiring, never declared, and it is
not a fifth tier. An operated artifact keeps the tier's non-citability — and
must emit `citable: false` metadata on anything that leaves the repository —
but loses rot tolerance: code that runs on a schedule has to keep working, so
tests and upkeep on operated exploratory code are maintenance, not
overbuilding. The rest of the contract stands unchanged: nothing above
exploratory may import it, and its numbers stay non-citable no matter how well
tested it is.

The promotion runway for operated inference is a study contract, not more
tests: a `studies/<id>/study.yaml` entering at `exploratory` or `reproducible`,
created only when a research question needs the number to carry citable
weight. Transition scoring — already precision-benchmarked, with frozen
coefficients from `phase3-notice-corpus-fusion` — is the named first
candidate; fiscal estimation waits on the `fiscal-tax-impact-v2` gate.

## Classifying an artifact

Work the questions in order and stop at the first yes:

1. Does anything else in the repository import it? → at least `primitives` or `pipelines`
2. Will a number from it be quoted outside the repository? → `evidence`, and it needs all four contract items
3. Does it move data without deciding anything contestable? → `pipelines`
4. Otherwise → `exploratory`

Two rules make this stick:

- **Tier is declared, not inferred.** Every spec states its target tier in
  `requirements.md`. Every new asset or module states its tier. Unstated means
  `exploratory`.
- **Promotion is explicit work.** Moving up a tier is its own change, with the
  new contract satisfied in that change. Nothing gets promoted by being useful,
  by being imported, or by accumulating callers.

### Assigning spec targets

A spec's declaration is the contract for its next authorized implementation
slice. It is neither a claim that current code already satisfies that contract
nor an aspirational label for every possible future phase. Review
[`specs/status.md`](../../specs/status.md) first, then apply these rules:

- Target `primitives` only when the deliverable is the single shared,
  versioned implementation of a repository-wide concept.
- Target `pipelines` when the authorized work is deterministic extraction,
  materialization, or operational plumbing. A gated or deferred spec may use
  this target to permit data preparation, but it does not authorize any
  contestable analysis in that spec; that phase requires an explicit retier.
- Target `evidence` only when a selected active or maintenance deliverable is
  an externally reportable finding, benchmark, or validation and the
  implementation must satisfy all four evidence-contract items.
- Target `exploratory` for open-ended prototypes and contestable work without
  an approved evidence contract.

The initial declaration sweep therefore capped gated and deferred analytical
specs at their deterministic preparation stage and retained `evidence` only
where the requirements already named the reportable result or validation as a
selected deliverable. Determinism alone never turns classification, imputation,
ranking, or another contestable decision into a pipeline.

## Relationship to the research questions

[research-questions.md](../research-questions.md) is the inventory of what the
repository exists to answer, and its reserved **Status** ranks are a public
API backed by [study contracts](../../studies/README.md), not by directory
tier labels:

| research-questions.md says | Required `studies/*/study.yaml` |
|---|---|
| `Citable` | `evidence_status: citable` |
| `Validated` | `validated` or `citable` |
| `Computable` / `Partially computable` | `reproducible` or higher |
| Exploratory / partial / inventory target | none required |

A question cannot be marked `Computable` on the strength of exploratory-tier
work or an exploratory study. `scripts/ci/check_research_question_status.py`
enforces the pairing. An `evidence`-tier spec is the implementation contract
for building that study; it is not itself a Status rank.

## Current status

The tiers are a target, not a description of the tree as it stands. There are no
`primitives/`, `pipelines/`, `evidence/`, or `exploratory/` directories today.

What already holds:

- `sbir_etl/` is a clean foundation layer — 141 imports inbound from
  `packages/`, zero outbound.
- `sbir_etl/identity/` meets the `primitives` contract, with a boundary checker
  at `scripts/ci/check_identity_boundaries.py` enforced by `make lint-boundaries`
  and the CI quality job.
- Active specs declare a target tier in `requirements.md`;
  `scripts/ci/check_epistemic_tiers.py` rejects missing, duplicate, and
  invalid declarations in `make lint-boundaries` and CI. Specs that declare
  `evidence` must also carry paperwork for SHA-256 freeze enforcement (a
  recorded digest or explicit raw-byte freeze language in `amendments.md`)
  plus a `**Declared estimand:**` field. That gate is paperwork-only; it does
  not prove runtime SHA or blocking asset-check enforcement.
- The tier dependency lattice is executable: `scripts/ci/check_tier_boundaries.py`
  (in `make lint-boundaries` and CI) resolves each module's effective tier and
  blocks imports below it. Its `TIER_IMPORT_ALLOWLIST` is empty — every seeded
  edge from the T1.2 triage has been retired (canonical company merge promoted
  into `sbir_etl.identity`, the NSF CET screen inverted out of the pipelines
  release, the opportunity scorer and NAICS text-inference registration moved
  behind exploratory composition points), so any new cross-tier import fails the
  build outright (`specs/epistemic-tier-enforcement/`).
- The Phase III census implements the evidence-tier mechanisms: frozen
  artifacts, SHA enforcement, a declared estimand, and a blocking asset check.
- Production YAML mapping reads route through the configuration loader or the
  shared strict-mapping reader. `scripts/ci/check_config_boundaries.py` makes
  that single-reader contract executable while preserving explicit
  `allow_empty=True` policy at permissive call sites.

What does not:

- `scripts/phase3_groundtruth/` and `scripts/validation/` now carry explicit
  `exploratory` labels, but their analytical weight — T6/T7 groundtruth
  results feeding the evidence-target `phase3-transition-groundtruth` spec —
  still exceeds their tier. The remaining issue is that tension, not missing
  labels.
- Module-level declaration is now the standard — subpackages carry package
  defaults and divergent modules carry per-file `EPISTEMIC_TIER` constants —
  but coverage is not yet universal. The remaining gaps are whatever
  `rg --files-without-match '^EPISTEMIC_TIER'` reports, not a fixed list, and
  an undeclared module is still exploratory until an explicit promotion
  satisfies its target contract.

The first useful step is labeling, not moving directories. Directory
reorganization is the last step, and optional.
