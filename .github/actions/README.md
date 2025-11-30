# GitHub Actions Composite Actions

This directory contains reusable composite actions for GitHub workflows. These actions standardize common patterns and reduce duplication across workflows.

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

### `setup-aws-credentials`

Configures AWS credentials using OIDC role assumption.

**Usage:**
```yaml
- name: Configure AWS credentials
  uses: ./.github/actions/setup-aws-credentials
  with:
    role-arn: ${{ secrets.AWS_ROLE_ARN }}    # Required
    aws-region: "us-east-2"                  # Optional, default: "us-east-2"
```

**Features:**
- Uses OIDC for secure credential management
- No long-lived AWS keys needed

---

### `setup-docker-buildx`

Sets up Docker Buildx for multi-platform builds and caching.

**Usage:**
```yaml
- name: Set up Docker Buildx
  uses: ./.github/actions/setup-docker-buildx
  with:
    setup-qemu: "true"              # Optional, default: "false"
```

**Features:**
- Optional QEMU setup for multi-arch builds (ARM64, etc.)
- Enables Docker Buildx caching

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
    username: "neo4j"               # Optional, default: "neo4j"
    password: "password"            # Optional, default: "password"  # pragma: allowlist secret
    timeout: "60"                   # Optional, default: "60"
```

**Outputs:**
- `neo4j-uri`: Neo4j bolt URI (bolt://localhost:7687)

**Features:**
- Starts Neo4j container with specified credentials
- Waits for Neo4j to be ready using TCP health check
- Sets NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD environment variables

**Note:** Remember to stop the container in a cleanup step:
```yaml
- name: Stop Neo4j
  if: always()
  run: |
    docker stop test-neo4j || true
    docker rm test-neo4j || true
```

---

### `setup-neo4j-service`

Sets up Neo4j environment variables for service containers.

**Usage:**
```yaml
- name: Setup Neo4j environment
  uses: ./.github/actions/setup-neo4j-service
  with:
    username: "neo4j"               # Optional, default: "neo4j"
    password: "password"            # Optional, default: "password"  # pragma: allowlist secret
    auth-mode: "password"           # Optional, default: "password"
    uri: "bolt://localhost:7687"    # Optional, default: "bolt://localhost:7687"
```

**Outputs:**
- `neo4j-uri`: Neo4j connection URI
- `neo4j-username`: Neo4j username
- `neo4j-password`: Neo4j password

**Note:** Service containers must be defined at the job level. See `wait-for-neo4j` for health checks.

---

### `wait-for-neo4j`

Waits for Neo4j service container to be ready.

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

### `prepare-env-file`

Prepares `.env` file from `.env.example` with optional secret injection.

**Usage:**
```yaml
- name: Prepare .env file
  uses: ./.github/actions/prepare-env-file
  with:
    neo4j-user: ${{ secrets.NEO4J_USER }}           # Optional
    neo4j-password: ${{ secrets.NEO4J_PASSWORD }}   # Optional
    source-file: ".env.example"                    # Optional, default: ".env.example"
```

**Features:**
- Copies from `.env.example` or creates empty file
- Injects Neo4j credentials if provided
- Sets `NEO4J_AUTH` automatically

---

### `setup-test-environment`

Consolidated setup for test environments including Neo4j service configuration,
environment variables, and common test settings.

**Usage:**
```yaml
- name: Setup test environment
  uses: ./.github/actions/setup-test-environment
  with:
    python-version: "3.11"          # Optional, default: "3.11"
    neo4j-image: "neo4j:5"          # Optional, default: "neo4j:5"
    neo4j-username: "neo4j"         # Optional, default: "neo4j"
    neo4j-password: "password"      # Optional, default: "password"  # pragma: allowlist secret
    default-timeout: "30"           # Optional, default: "30"
    performance-sample-size: "500"  # Optional, default: "500"
    aws-region: "us-east-2"         # Optional, default: "us-east-2"
    neo4j-health-retries: "12"      # Optional, default: "12"
```

**Outputs:**
- `neo4j-uri`: Neo4j connection URI
- `neo4j-username`: Neo4j username
- `neo4j-password`: Neo4j password

**Features:**
- Sets standardized environment variables for testing
- Reduces duplication across workflows
- Single source of truth for test configuration

---

### `detect-changes`

Detects which parts of the codebase changed using path filters.

**Usage:**
```yaml
- uses: actions/checkout@v4
- name: Detect changes
  uses: dorny/paths-filter@v2
  id: filter
  with:
    filters: |
      code-changed:
        - 'src/**'
        - 'tests/**'
      docs-only:
        - '**/*.md'
        - 'docs/**'
        - '!**/*.py'
```

**Outputs:**
- All filter outputs are available via `steps.filter.outputs.<filter-name>`
- Example: `steps.filter.outputs.code-changed`, `steps.filter.outputs.docs-only`

**Note:** This action is a convenience wrapper that includes checkout. For direct control, use `dorny/paths-filter@v2` directly. See [dorny/paths-filter](https://github.com/dorny/paths-filter) for filter syntax.

---

### `upload-artifacts`

Uploads workflow artifacts with common patterns.

**Usage:**
```yaml
# Upload on success
- name: Upload artifacts
  uses: ./.github/actions/upload-artifacts
  with:
    name: "test-results"            # Required
    path: |                         # Required (supports multi-line)
      reports/
      logs/
    retention-days: "7"             # Optional, default: "7"
    if-no-files-found: "warn"       # Optional, default: "warn"

# Upload on failure
- name: Upload artifacts on failure
  if: failure()
  uses: ./.github/actions/upload-artifacts
  with:
    name: "error-logs"
    path: logs/
```

**Features:**
- Supports multi-line path patterns
- Configurable retention and error handling
- Use `if: always()`, `if: success()`, or `if: failure()` for conditional uploads

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

See the workflow files in `.github/workflows/` for examples of how these actions are used:
- `ci.yml` - Uses `setup-python-uv`, `setup-docker-buildx`, `prepare-env-file`
- `lambda-deploy.yml` - Uses `setup-aws-credentials`, `setup-docker-buildx`
- `nightly.yml` - Uses `setup-python-uv`, `setup-neo4j-service`, `wait-for-neo4j`, `prepare-env-file`
