# Restore the unautomated repo checks

Tracking stub. Three checks that ran in the retired `weekly.yml` and now run
**nowhere**. None is in pre-commit. Nothing here is implemented yet.

Grouped because they share a shape: they check the repository, not the data, so
they want a host cron or a pre-commit hook rather than a Dagster job.

## 1. Nightly security scan — DONE, as a parallel CI job

Was `weekly.yml` · `security-scan`, cron `0 3 * * *`.

**Implemented here as a CI job rather than a host cron.** The stub originally
proposed host cron on the reasoning that it scans source, not data. That still
holds, but it misses the cheaper option: the scan is ~37s (bandit 10.7s,
detect-secrets 25.8s) and the CI critical path is the slowest test shard at
~65s, so a parallel `security` job costs **a runner and no wall-clock**. It also
gates pre-merge rather than telling you the morning after.

It is a separate job, not extra steps in `quality`. `quality` runs ~35-39s;
adding 37s to it would push it past the shards and make it the new critical
path. Parallel, it hides underneath.

Blocking on purpose — a non-blocking version would reproduce the state this
exists to fix.

**The four findings that made this red are fixed**, not suppressed wholesale:

| Finding | Resolution |
|---|---|
| `B324` SHA1 in `phase_iii_candidates/assets.py` | Real fix: `usedforsecurity=False`. It is a content hash for a short deterministic id, not a security primitive. |
| `B104` bind-all in `api/__main__.py` | False positive in this architecture. Binding `0.0.0.0` *inside a container* is required to accept from the compose network; the boundary is the host publish, which compose pins to `127.0.0.1` and `server-check` enforces. Suppressed with that rationale. |
| `B105` ×2 in `identity/company_names.py` | False positives. `token-set` / `token-sort` are matching-algorithm names in a StrEnum, not credentials. Suppressed with rationale. |

`bandit -r sbir_etl packages -c pyproject.toml` now exits 0 with "No issues
identified."

### Still open

- [ ] Nothing scans on a schedule — this gates PRs and `main`, but a dependency
      advisory published after a merge will not surface until the next push.
      Dependabot covers the dependency half; decide whether that is enough or
      whether a periodic scan is still wanted somewhere off-Actions.
- [ ] Verify by planting a known finding and confirming the job fails

## 2. Markdown lint

Was `weekly.yml` · `markdown-lint` (markdownlint-cli2 with `.markdownlint.yaml`).

- [ ] Add as a **pre-commit hook**, not CI — it is a formatting check and
      belongs where formatting checks already live
- [ ] Keep the existing ignores (archive, specs/archive, reports, venvs,
      node_modules)

## 3. Neo4j schema dry-run

Was `weekly.yml` · `neo4j-smoke`: build the runtime image, start Neo4j, run
`scripts/neo4j/apply_schema.py --dry-run`.

- [ ] Decide whether this is worth automating at all. The mini runs a real
      Neo4j continuously, so a dry-run against a throwaway container is weaker
      evidence than the live stack already provides.
- [ ] If yes: host cron or a documented manual step in the Neo4j runbook
