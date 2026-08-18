# Versioning and Releases

This repository follows [Semantic Versioning 2.0.0](https://semver.org/). A release version has
the form `MAJOR.MINOR.PATCH`; Git tags add the conventional `v` prefix, for example `v0.2.0`.

## Release unit

SBIR Analytics is versioned as a synchronized monorepo. These projects always carry the same
version:

- `sbir-etl` in the root `pyproject.toml`
- `sbir-analytics` in `packages/sbir-analytics/pyproject.toml`
- `sbir-graph` in `packages/sbir-graph/pyproject.toml`
- `sbir-ml` in `packages/sbir-ml/pyproject.toml`

`uv.lock` must record the same version for all four local packages. Independent package versions
are intentionally out of scope until the packages have separate release cadences or consumers.

Runtime release metadata must match that synchronized version as well. The authoritative Python
runtime marker is `sbir_etl.__version__`; pipeline defaults, HTTP User-Agents, and package-level
compatibility aliases derive from it. The `pipeline.version` value in `config/base.yaml` is also
release metadata because deployed configuration can override the Python default. The versioning
checker validates both static sources against the package metadata.

## Compatibility surface

Version decisions cover behavior on which a user, downstream script, or deployment can reasonably
depend:

- documented Python imports, functions, classes, and command-line entry points;
- configuration keys and their documented meaning;
- Dagster asset keys, job names, partitions, and materialization contracts;
- persisted DuckDB, Parquet, and Neo4j schemas and stable identifiers;
- documented inputs, outputs, and operational commands.

Research findings, internal implementation details, experimental scripts, and explicitly unstable
specs are not public API. They can still justify a minor release when their change is substantial or
user-visible.

## Increment rules

The project remains in initial development under major version zero. Until `1.0.0`, use:

- **PATCH** (`0.1.1` → `0.1.2`) for backward-compatible fixes, documentation corrections, and
  internal maintenance that does not add a compatibility surface.
- **MINOR** (`0.1.1` → `0.2.0`) for new capabilities, substantial research or pipeline features,
  deprecations, and breaking changes during initial development. Call out every breaking change in
  the release notes.
- **MAJOR** (`0.x.y` → `1.0.0`) when the public compatibility surface is deliberately declared
  stable. After `1.0.0`, incompatible public changes require a major increment.

When a release contains several change types, choose the largest required increment. Reset lower
components to zero when incrementing a higher component. Pre-release and build identifiers are
valid SemVer extensions, but this repository currently uses normal `MAJOR.MINOR.PATCH` releases
only. Introduce those identifiers only with a corresponding Python-packaging and checker update.

## Historical releases

The first two tag names predate this policy and remain immutable:

- `0.1` represents semantic version `0.1.0`.
- `v0.11` represents semantic version `0.1.1` (the patch separator was omitted).

Do not rename, move, or delete those published tags. All subsequent release tags must use the full
`vMAJOR.MINOR.PATCH` form.

## Release checklist

Steps run in this order. Each is labeled with whether it is machine-gated
(`check_versioning.py`, see `.github/workflows/versioning.yml`) or operator judgment.

1. **(Operator)** Review user-visible changes since the latest release and choose the required
   increment.
2. **(Required — CI)** Update all four `pyproject.toml` versions, `sbir_etl.__version__`, and
   `config/base.yaml`'s `pipeline.version` to the same `MAJOR.MINOR.PATCH` value.
3. **(Required — CI)** Run `uv lock` to update the four local-package entries in `uv.lock`; runtime
   defaults and User-Agents derive from `sbir_etl.__version__` and do not need separate edits.
4. **(Required — CI)** Run `uv run python scripts/ci/check_versioning.py --tag vMAJOR.MINOR.PATCH`.
5. **(Operator)** Confirm the relevant test and quality checks are green.
6. **(Operator)** Commit the release preparation before creating an annotated tag:

   ```bash
   git tag -a vMAJOR.MINOR.PATCH -m "Release vMAJOR.MINOR.PATCH"
   git push origin vMAJOR.MINOR.PATCH
   ```

7. **(Operator)** Create the GitHub release from that tag and include highlights, compatibility
   notes, and a full changelog link.

Published versions are immutable. If release notes or artifacts expose a defect, publish the fix
under a new version instead of changing the tagged contents.
