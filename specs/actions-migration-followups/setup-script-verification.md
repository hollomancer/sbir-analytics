# Verify the developer setup path

**Resolved.** Option 1 implemented in `ci.yml` — see the `detect-changes` /
`verify-setup-script` jobs.

`scripts/setup_dev.sh` was checked by `ci.yml` · `verify-setup-script` until
GitHub Actions was rescoped to tests only. Nothing verifies it now, so the
onboarding path can rot silently — and it rots in the one place nobody
exercises daily, because everyone already has a working environment.

The old job ran the script on a clean runner, then confirmed the venv activated
and `pydantic` imported.

## Decision

Option 1 chosen: a path-filtered CI job gated on `scripts/setup_dev.sh`,
`pyproject.toml`, and `uv.lock`, sharing the existing `detect-changes` filter
job (renamed from `docker-changes`). Near-zero cost on PRs that don't touch
those paths; fires exactly when the setup path can break. Original assertions
kept: venv activates, `pydantic` imports.

## Related

`weekly.yml` also had `verify-local-workflow` (`make setup-local`,
`make sample-data`) and `verify-ml-workflow` (`make install-ml`,
`make setup-ml`, executing `notebooks/getting_started.ipynb`). Same category,
same question. Decide them together or explicitly drop them.
