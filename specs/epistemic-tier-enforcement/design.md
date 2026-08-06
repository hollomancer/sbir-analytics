# Epistemic Tier Enforcement — Design

## Shape of the change

Three moves, ordered so each makes the next checkable:

1. **Enforce** (R1): a new static guard turns the `EPISTEMIC_TIER` labels from PRs
   #550–#552 into an executable dependency contract, with the known violations
   allowlisted so it lands green.
2. **Burn down** (R2, R3): the allowlist entries are retired by the repository's two
   established patterns — promotion behind a versioned identity policy, and dependency
   inversion at the asset layer.
3. **Describe** (R4): the tiers doc names the workbench/operated split so the enforced
   state and the promotion runway are doctrine, not tribal knowledge.

No new tier, no directory moves, no runtime machinery.

## R1 — `scripts/ci/check_tier_boundaries.py`

Sibling of `check_architecture_boundaries.py`; reuses its conventions (AST parse only,
frozen dataclass violations, sorted deterministic output, allowlist as in-file constant).

### Tier resolution

```
effective_tier(module_path):
    1. module's own `EPISTEMIC_TIER = "<literal>"` (top-level ast.Assign of a
       string constant — same strictness as the spec checker's regex)
    2. else nearest ancestor package __init__.py declaration, walking up to the
       package root (sbir_etl/, packages/*/<pkg>/, scripts/)
    3. else "exploratory"
```

Resolution is per-file and cached per run. An invalid tier string in a constant is
itself a violation (mirrors `check_epistemic_tiers.py` behavior for specs).

### Import extraction

Extends the architecture guard's `imported_modules()`:

- `ast.Import`, absolute `ast.ImportFrom`, and literal `importlib.import_module` /
  `__import__` calls, as today;
- **new:** relative imports (`ImportFrom.level > 0`) resolved against the importing
  module's dotted path — required because intra-package edges are exactly where tier
  violations live (`company_canonicalizer` reaches the fuzzy matcher via
  `from ..enrichers...`). The architecture guard skips these because cross-package
  imports cannot be relative; this guard cannot.
- Imports inside `if TYPE_CHECKING:` count. A type-only dependency is still an
  epistemic dependency; the allowlist is the escape hatch if this ever proves noisy.

An imported module that maps to no first-party file (third-party, stdlib) is ignored.
An import of a package resolves to that package's `__init__.py` tier.

### Policy and allowlist

```python
ALLOWED_TIER_IMPORTS = {
    "primitives":  frozenset({"primitives"}),
    "pipelines":   frozenset({"primitives", "pipelines"}),
    "evidence":    frozenset({"primitives", "pipelines", "evidence"}),
    "exploratory": frozenset({"primitives", "pipelines", "evidence", "exploratory"}),
}

# Each entry: importer path -> imported module names, with a reason and a
# removal condition. Stale entries (edge no longer present) fail the run.
TIER_IMPORT_ALLOWLIST: dict[str, frozenset[str]] = {
    "packages/sbir-analytics/sbir_analytics/assets/sbir_neo4j_loading.py": frozenset(
        {"sbir_etl.utils.company_canonicalizer"}  # removed by R2
    ),
    "sbir_etl/supply_chain/defense_release.py": frozenset(
        {"sbir_etl.supply_chain.nsf_screen"}  # removed by R3.1
    ),
    "sbir_etl/supply_chain/__init__.py": frozenset(
        {"sbir_etl.supply_chain.nsf_screen"}  # removed by R3.2
    ),
}
```

The seed list is written by T1.2's full-repository triage run, not copied from this
design; the three edges above are the ones known in advance. Triage rules: a hit caused
by a mislabeled module is fixed by correcting the label (with a one-line justification
in the PR); a real cross-tier edge is either fixed in place or allowlisted with a
removal condition. No silent third option.

### Failure modes

- Violation → non-zero exit, `path:line: pipelines module may not import exploratory
  module sbir_etl.supply_chain.nsf_screen`.
- Stale allowlist entry → non-zero exit naming the entry.
- Unparseable file → non-zero exit (same as the sibling guards; the tree must parse).

### Wiring

`make lint-boundaries` gains one line after the architecture check; CI runs it in the
same job as `check_epistemic_tiers.py` (`.github/workflows/ci.yml`). Tests live at
`tests/unit/scripts/test_tier_boundaries.py`, built on tmp-tree fixtures like
`test_epistemic_tiers.py`, covering: the three resolution branches, relative-import
resolution, every policy row, allowlist pass, stale-entry failure, invalid tier string.

## R2 — Canonical merge promotion into `sbir_etl.identity`

### Why promotion, not extraction

`canonicalize_companies_from_awards` (135 lines, `sbir_etl/utils/company_canonicalizer.py`)
builds company keys (UEI > DUNS > normalized name) and then merges candidates by fuzzy
self-matching at 90 (auto) / 75 (flag) thresholds via
`enrichers.company_fuzzy_matcher.enrich_awards_with_companies`. The merge decision *is*
the function; there is no deterministic core whose extraction would leave the loader
honest. Fuzzy identity under named, frozen policies is exactly what the primitives tier
already houses (`CompanyNameProfile`, `company_name_similarity`), so the correct move is
a new versioned policy, per the identity package's own rule: divergent behavior is fine
when declared.

### Interface

```python
# sbir_etl/identity/canonical_merge.py  (primitives; declares EPISTEMIC_TIER)
class CanonicalMergePolicy(StrEnum):
    PRELOAD_V1 = "preload-v1"   # frozen: current company_canonicalizer behavior

def build_canonical_company_map(
    awards: pd.DataFrame, *, policy: CanonicalMergePolicy
) -> dict[str, str]: ...
```

`PRELOAD_V1` freezes today's behavior: key preference, both thresholds, candidate
ordering, and tie handling. Any future tuning is `PRELOAD_V2`, never an edit.

### Equivalence gate and the honest exit

Promotion is conditional on byte-identical output: a committed fixture corpus (deduced
from awards data already used by loader tests, plus adversarial near-duplicate names)
and a golden `original_key -> canonical_key` mapping produced by the *current* code
before any rewrite. The new policy must reproduce it exactly.

The risk is that current behavior is only reachable through
`company_fuzzy_matcher`'s internal candidate generation. The implementation may
re-house that logic inside identity **only** if the equivalence gate stays green and the
moved code sheds its lower-tier imports. If not, R2 stops: the allowlist entry stays,
annotated with the finding, and the re-scope happens in the open (per requirement 2.2)
rather than by weakening the primitives contract.

`sbir_etl/utils/company_canonicalizer.py` is then deleted if the loader was its only
package importer (verify with the guard), or reduced to a deprecation shim that
delegates to the identity policy and keeps its exploratory label.

## R3 — NSF screen dependency inversion

Current: `defense_release.py` (pipelines) calls `screen_direct_nsf_awards` inline, and
the `supply_chain` package `__init__` re-exports it, so the exploratory module loads
with the package.

Target: the exploratory asset layer that already orchestrates NSF/defense lineage
(`nsf_defense_lineage_job` flow) calls the screen and passes the screened frame into
`defense_release` as data. `defense_release` keeps its pipelines label honestly: it
moves and reshapes what it is given. Screen-derived columns carry a `screen_version`
attribute (`nsf-screen-v1`) so provenance survives the handoff — faithfully recording
what a named policy said is data movement; presenting it as a finding is not, and the
attribute is what keeps that line visible downstream.

The `__init__` re-export is dropped; the one-line import moves to each caller. This is
an API narrowing inside the repo — the guard's full-repo run in T1.2 enumerates the
callers that need the direct import.

## Consequences for evidence and citability

None of this changes any materialized number. The census machinery is untouched (its
imports already conform — `pairing.py` carries a per-file pipelines label for exactly
this reason). The guard makes the census's protective moat structural: an evidence
artifact acquiring an exploratory dependency becomes a CI failure instead of a review
catch.

## Alternatives considered

- **Fifth tier ("operated"/"provisional")** — rejected: the tiers doc already refused a
  fifth tier for migration bridges; a comfortable middle tier is where inference would
  settle permanently; tier × operated × study-status already spans the space.
- **Rank-number comparison instead of an explicit policy map** — rejected: `evidence`
  is not "above" pipelines on an import axis (evidence may import pipelines, nothing
  imports evidence in practice); a map states the actual lattice.
- **Runtime import hooks** — rejected: CI-time static analysis matches the sibling
  guards, costs nothing at runtime, and the literal-import blind spots are already an
  accepted, documented limit of this family of checks.
- **Blanket study manifests for all operated inference** — rejected: manifest
  maintenance must be pulled by a research question needing a citable number, or the
  manifests rot into decoration themselves.
