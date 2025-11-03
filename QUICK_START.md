# Quick Start - Running Dagster

## Running Dagster UI

### ⚠️ IMPORTANT: Use Module Import Flag

**You MUST use the `-m` flag** because `definitions.py` uses relative imports:

```bash
poetry run dagster dev -m src.definitions
```

**DO NOT use `-f src/definitions.py`** - this will cause import errors.

### Alternative: Using workspace.yaml

If you prefer, you can use:

```bash
poetry run dagster dev
```

This should automatically read `workspace.yaml` which uses `python_module: src.definitions`.

**If you still see import errors**, explicitly use `-m src.definitions` as shown above.

### Option 3: Explicit File Path (For debugging)

If you need to use file path directly:

```bash

## First ensure PYTHONPATH includes project root

export PYTHONPATH="${PYTHONPATH}:$(pwd)"
poetry run dagster dev -f src/definitions.py
```

After starting, access the UI at: **http://localhost:3000**

## Viewing Assets

Once Dagster is running:

1. Open http://localhost:3000 in your browser
2. Navigate to the **Assets** tab in the left sidebar
3. You should see all your assets listed there
4. Click on any asset to see its details and materialize it

## Materializing Assets

### Via UI:

1. Go to the **Assets** tab
2. Select one or more assets
3. Click the **Materialize** button
4. Monitor progress in the **Runs** tab

### Via Command Line:

```bash

## Materialize a specific job

poetry run dagster job execute -m src.definitions -j sbir_etl_job

## Materialize a specific asset

poetry run dagster asset materialize -m src.definitions -s raw_sbir_awards
```

## Configuration Files

- **`workspace.yaml`**: Uses `python_module: src.definitions` (module-based import)
- **`pyproject.toml`**: Contains `[tool.dagster]` section with `python_module = "src.definitions"`

## Troubleshooting

If you see import errors about relative imports:

- Make sure you're using `-m src.definitions` instead of `-f src/definitions.py`
- The module-based approach is required because `definitions.py` uses relative imports (`. import assets`)

Some assets may have dependency issues that need to be fixed individually, but the UI should still start and show available assets.
