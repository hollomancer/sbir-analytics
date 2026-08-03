# Epistemic Tiers

Every artifact in this repository sits in one of four tiers. The tier declares
how much weight the artifact can carry, and each tier's contract states what it
costs to sit there.

This is the axis the work actually varies on. Technical role — extract, enrich,
transform, load — describes what code does; it says nothing about whether a
number it produces can be quoted to a program officer. Two artifacts with
identical technical roles can differ completely in how much they can be trusted,
and the repository has to make that difference visible.

See [architecture/detailed-overview.md §10](../architecture/detailed-overview.md)
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
bridge.

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

## Relationship to the research questions

[research-questions.md](../research-questions.md) is the inventory of what the
repository exists to answer, and its **Status** lines already speak in
epistemic terms — what is answerable today, what is a lower-bound proxy, what
is contested. The tiers are the supply side of that same distinction:

| research-questions.md says | Backing tier |
|---|---|
| Answerable today, citable | `evidence` |
| Answerable but lower-bound proxy | `evidence`, with the bound in the declared estimand |
| Partial or contested | `pipelines` + `exploratory` |
| Design target, not built | none yet |

A question cannot be marked answerable on the strength of exploratory-tier
work. If the inventory claims an answer, something in `evidence` has to stand
behind it.

## Current status

The tiers are a target, not a description of the tree as it stands. There are no
`primitives/`, `pipelines/`, `evidence/`, or `exploratory/` directories today.

What already holds:

- `sbir_etl/` is a clean foundation layer — 141 imports inbound from
  `packages/`, zero outbound.
- `sbir_etl/identity/` meets the `primitives` contract, with a boundary checker
  at `scripts/ci/check_identity_boundaries.py`.
- The Phase III census implements the evidence-tier mechanisms: frozen
  artifacts, SHA enforcement, a declared estimand, and a blocking asset check.

What does not:

- The identity boundary checker is enforced by the CI quality job, but no
  tier-declaration check exists yet.
- Nine direct `yaml.safe_load` call sites remain outside the configuration
  loader and the shared strict-mapping reader; several intentionally use
  permissive empty-file behavior.
- `scripts/` carries analytical weight from `phase3_groundtruth/` and
  `validation/` with no contract at all.
- No existing specs, assets, or modules declare one of these four tiers, so the
  declaration rule is not yet observable or mechanically enforced.

The first useful step is labeling, not moving directories. Directory
reorganization is the last step, and optional.
