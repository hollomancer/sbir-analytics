# GitHub Actions Composite Actions

This directory contains reusable composite actions for GitHub workflows. These actions standardize common patterns and reduce duplication across workflows.

`ci.yml` is the only workflow in the repository — it runs lint, type checks, and
tests. Everything else (data extraction, enrichment, reporting, image
publishing) runs on the self-hosted server as Dagster schedules or cron, so actions that
existed to serve those workflows have been removed along with them.

## Available Actions

### `setup-python-uv`

Sets up Python with UV package manager and installs dependencies.

**Usage:**

```yaml
- name: Setup Python and UV
  uses: ./.github/actions/setup-python-uv
  with:
    python-version: "3.11"          # Optional, default: "3.11"
    install-dev-deps: "true"        # Optional, default: "true"
    cache-mypy: "false"             # Optional, default: "false"
```

**Features:**

- Installs UV package manager
- Caches the UV package cache (`~/.cache/uv`), from which `uv sync` hardlinks
  the virtual environment in about 0.2s
- Optionally caches `.mypy_cache` for the job that runs mypy

**Not cached, deliberately:** `.venv` itself. Restoring a ~300 MB venv tarball
costs far more than the 0.2s rebuild, and `uv sync` had to run afterwards
regardless. There is also no separate pyreadstat install — `uv sync --extra
stack-dev` already resolves it through the `uspto` extra.

## Best Practices

1. **Use composite actions for repeated patterns** - If you find yourself copying the same steps across workflows, create a composite action.

2. **Document inputs and outputs** - Always document what inputs are required vs optional, and what outputs are available.

3. **Keep actions focused** - Each action should do one thing well. Don't create monolithic actions that try to do everything.

4. **Test actions in workflows** - Test composite actions in real workflows before committing to ensure they work correctly.

5. **Version actions carefully** - If you need to make breaking changes, consider creating a new versioned action (e.g., `setup-python-uv-v2`).

## Creating New Composite Actions

1. Create a new directory under `.github/actions/`
2. Create an `action.yml` file with:
   - `name`: Action name
   - `description`: What the action does
   - `inputs`: Input parameters
   - `outputs`: Output values (if any)
   - `runs.using: composite`
   - `runs.steps`: The steps to execute

3. Reference the action in workflows:

   ```yaml
   - uses: ./.github/actions/your-action-name
     with:
       input1: "value1"
   ```

## Examples

`ci.yml` uses `setup-python-uv` in every Python job.
