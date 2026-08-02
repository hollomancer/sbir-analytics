# Restore the unautomated repo checks

Tracking stub. Three checks that ran in the retired `weekly.yml` and now run
**nowhere**. None is in pre-commit. Nothing here is implemented yet.

Grouped because they share a shape: they check the repository, not the data, so
they want a host cron or a pre-commit hook rather than a Dagster job.

## 1. Nightly security scan — highest priority

Was `weekly.yml` · `security-scan`, cron `0 3 * * *`.

The only item from the whole migration with **no fallback at all** — bandit and
detect-secrets are not pre-commit hooks, so the repo currently has no automated
security scanning.

Measured cost: bandit 10.7s + detect-secrets 25.8s ≈ **37s**. No runtime reason
to defer.

**It fails today.** `bandit -r sbir_etl packages -c pyproject.toml` exits 1:

| Severity | Finding | Location |
|---|---|---|
| High / High | `B324` weak SHA1 | `assets/phase_iii_candidates/assets.py:243` |
| Medium | `B104` bind all interfaces | `api/__main__.py:11` |
| Low ×2 | `B105` hardcoded password | `identity/company_names.py:49-50` |

- [ ] Triage the four findings. The two Low hits look like false positives —
      `token-set` / `token-sort` are token-matching algorithm names, not
      credentials. The SHA1 is probably a content hash wanting
      `usedforsecurity=False`.
- [ ] **Fix them before wiring the cron.** A gate that fails on its first run
      gets muted, which is how the previous scan came to be ignored.
- [ ] Host cron running both commands, output to a dated file
- [ ] Verify by planting a known finding and confirming it reaches a human

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
