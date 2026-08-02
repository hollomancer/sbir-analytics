# GitHub Actions Composite Actions

This directory contains reusable composite actions for GitHub workflows. These actions standardize common patterns and reduce duplication across workflows.

`ci.yml` is the only workflow in the repository — it runs lint, type checks, and
tests. Everything else (data extraction, enrichment, reporting, image
publishing) runs on the Mac mini as Dagster schedules or cron, so actions that
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
    cache-venv: "true"              # Optional, default: "true"
    cache-pytest: "false"           # Optional, default: "false"
    install-pyreadstat: "false"     # Optional, default: "false"
```

**Features:**

- Installs UV package manager
- Caches virtual environment and pytest cache
- Optionally installs pyreadstat for Stata file support

---

### `start-neo4j`

Starts a Neo4j Docker container and waits for it to be ready.

**Usage:**

```yaml
- name: Start Neo4j
  uses: ./.github/actions/start-neo4j
  with:
    container-name: "test-neo4j"    # Optional, default: "test-neo4j"
    neo4j-image: "neo4j:5"          # Optional, default: "neo4j:5"
    neo4j-user: "neo4j"             # Optional, default: "neo4j"
    neo4j-password: "password"      # Optional, default: "password"  # pragma: allowlist secret
    timeout: "60"                   # Optional, default: "60"
```

**Outputs:**

- `neo4j-uri`: Neo4j bolt URI (bolt://localhost:7687)

**Features:**

- Starts Neo4j container with specified credentials
- Waits for Neo4j to be ready using TCP health check (via `wait-for-neo4j`)
- Sets NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD environment variables

**Note:** Use `stop-neo4j` action for cleanup (see below).

---

### `stop-neo4j`

Stops and removes a Neo4j Docker container.

**Usage:**

```yaml
- name: Stop Neo4j
  if: always()
  uses: ./.github/actions/stop-neo4j
  with:
    container-name: "test-neo4j"    # Optional, default: "test-neo4j"
```

---

### `wait-for-neo4j`

Waits for a Neo4j container to be ready. Called by `start-neo4j`; use it
directly only when starting Neo4j some other way.

**Usage:**

```yaml
- name: Wait for Neo4j
  uses: ./.github/actions/wait-for-neo4j
  with:
    method: "tcp"                   # Optional, default: "http"
    uri: "http://localhost:7474"    # Optional (for http method)
    port: "7687"                    # Optional (for tcp method), default: "7687"
    timeout: "120"                  # Optional, default: "120"
    check-interval: "5"             # Optional, default: "5"
```

**Features:**

- Supports HTTP and TCP health checks
- Automatic retry with configurable timeout
- Installs netcat for TCP checks if needed

---

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

`ci.yml` uses `setup-python-uv` in every job, and `start-neo4j` / `stop-neo4j`
around the full test run on `main`.
