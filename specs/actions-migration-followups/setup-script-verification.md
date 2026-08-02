# Verify the developer setup path

Tracking stub. Nothing here is implemented yet.

`scripts/setup_dev.sh` was checked by `ci.yml` · `verify-setup-script` until
GitHub Actions was rescoped to tests only. Nothing verifies it now, so the
onboarding path can rot silently — and it rots in the one place nobody
exercises daily, because everyone already has a working environment.

The old job ran the script on a clean runner, then confirmed the venv activated
and `pydantic` imported.

## Scope

- [ ] Decide where this belongs. It is genuinely a *test* — "does a clean
      checkout produce a working environment" — but it needs a clean machine,
      which is the one thing local runs never have.
- [ ] Options, roughly in order of preference:
  - A path-filtered CI job gated on `scripts/setup_dev.sh`, `pyproject.toml`,
    `uv.lock` — same shape as the `docker` job, near-zero cost, fires exactly
    when the setup path can break
  - A documented manual check in the contributing guide
  - Nothing, and accept the rot
- [ ] If CI: reuse the `docker-changes` filter pattern rather than adding a
      second detect job
- [ ] Keep the original assertions — venv activates, `pydantic` imports

## Related

`weekly.yml` also had `verify-local-workflow` (`make setup-local`,
`make sample-data`) and `verify-ml-workflow` (`make install-ml`,
`make setup-ml`, executing `notebooks/getting_started.ipynb`). Same category,
same question. Decide them together or explicitly drop them.
