# Zed Configuration for SBIR Analytics

This directory contains Zed editor configuration for the SBIR Analytics project.

## Setup Complete ✓

The following has been configured:

### 1. Virtual Environment
- **Location**: `.venv/` (Python 3.11.13)
- **Setup**: Run via `uv sync --all-extras`
- **Status**: ✓ All dependencies installed (205 packages)
- **Dev Tools**: black, ruff, mypy, pytest, bandit

### 2. Pre-commit Hooks
- **Status**: ✓ Installed at `.git/hooks/pre-commit`
- **Activation**: Hooks run automatically on `git commit`
- **Manual Run**: `pre-commit run --all-files`

#### Hooks Configured:
- **black**: Code formatting (line length 100, Python 3.11)
- **ruff**: Linting and import sorting (with auto-fix)
- **mypy**: Type checking (standard mode)
- **bandit**: Security scanning
- **detect-secrets**: Secret detection with baseline
- **Standard hooks**: YAML validation, large file checks, trailing whitespace, EOF fixes

### 3. Zed Configuration Files

#### `.zed/settings.json`
Main Zed editor settings:
- Python venv path: `.venv/bin/python`
- Formatter: Black
- Format on save: Enabled
- LSP: Pyright with type checking in standard mode

#### `.zed/workspace.json`
Workspace-specific settings:
- Python linter: Ruff
- Python formatter: Black
- Tab size: 4 spaces
- Indent guides: Enabled
- Hot reload: Enabled

## Quick Start

### First Time Setup
```bash
# Already done, but for reference:
uv sync --all-extras
pre-commit install
```

### Daily Workflow

1. **Open project in Zed**:
   ```bash
   zed .
   ```

2. **Code formatting** (automatic on save, or manual):
   ```bash
   Cmd+Shift+I  # Format current file
   ```

3. **Check code quality** before commit:
   ```bash
   pre-commit run --all-files
   ```

4. **Run tests**:
   ```bash
   uv run pytest -v --cov=src
   ```

5. **Full code quality checks**:
   ```bash
   make check-all
   ```

## Command Reference

### Dependency Management
```bash
# Sync dependencies (after pyproject.toml changes)
uv sync --all-extras

# Add new dependency
uv add package_name

# Add dev dependency
uv add --dev package_name
```

### Pre-commit
```bash
# Run all checks on changed files (runs on commit)
pre-commit run

# Run all checks on all files
pre-commit run --all-files

# Run specific check
pre-commit run black --all-files
pre-commit run ruff --all-files
pre-commit run mypy --all-files

# Update pre-commit hooks
pre-commit autoupdate
```

### Code Quality
```bash
# Format code
uv run black .

# Lint with auto-fix
uv run ruff check . --fix

# Type checking
uv run mypy src/

# Security scanning
uv run bandit -r src/

# Run all tests
uv run pytest -v --cov=src

# Run specific test file
uv run pytest tests/unit/test_file.py -v
```

### Zed Features

- **Hover for type info**: Hover over variables/functions to see type hints
- **Go to definition**: Cmd+Click or Cmd+B
- **Find references**: Cmd+Shift+F
- **Find in project**: Cmd+Shift+P then search
- **Diagnostics panel**: View linting/type errors
- **Format on save**: Automatically runs Black

## Environment Variables

Create a `.env` file in the project root:
```bash
cp .env.example .env
# Edit .env with your settings:
# NEO4J_URI=...
# NEO4J_USER=...
# NEO4J_PASSWORD=...
```

## Troubleshooting

### Zed Not Finding Python
1. Verify `.venv` exists: `ls -la .venv`
2. Restart Zed: Close and reopen
3. Check settings: Open `.zed/settings.json` and verify paths

### Pre-commit Hooks Not Running
```bash
# Reinstall hooks
pre-commit install

# Verify installation
cat .git/hooks/pre-commit | head -5
```

### Permission Denied on File
```bash
chmod 644 path/to/file
```

### Module Not Found Errors
```bash
# Reinstall all dependencies
uv sync --all-extras

# Clear Python cache
find . -type d -name __pycache__ -exec rm -rf {} +
```

### Pre-commit Taking Too Long
This is normal on first run. Subsequent runs cache dependencies.

## Configuration Details

### Python Version
- **Required**: 3.11+
- **Current**: 3.11.13 (see `.python-version`)
- **pyproject.toml**: Configured for 3.11 target

### Black Formatting
- **Line length**: 100 characters
- **Target version**: Python 3.11

### Ruff Linting
- **Line length**: 100 characters
- **Rules**: E, W, F, I, B, C4, UP
- **Ignored**: E501 (line length), B008, B904, B017, C901, E402, I001

### MyPy Type Checking
- **Mode**: Standard (not strict)
- **Python version**: 3.11
- **Extra paths**: `src/`
- **Plugins**: Pydantic plugin enabled

### Bandit Security
- **Excluded**: `tests/` directory
- **Skipped checks**: B101, B601, B608, B110, B112, B603, B404, B105, B106

### Detect-Secrets
- **Baseline**: `.secrets.baseline` (for approved secrets)
- **Excluded patterns**: `.venv/`, `.git/`, `docs/`, data files, etc.

## Next Steps

1. ✓ Close any open terminals/Zed windows
2. ✓ Open the project fresh: `zed .`
3. ✓ Verify Python environment is recognized (look for Python version in status bar)
4. ✓ Create a test branch and make a small change to verify pre-commit hooks run
5. ✓ Review `.kiro/specs/` and `CONTRIBUTING.md` for additional guidance

## References

- **CONTRIBUTING.md**: Development standards and workflow
- **AGENTS.md**: Project architecture and key directories
- **docs/testing/index.md**: Complete testing commands
- **docs/development/**: Development guides and standards
- **.pre-commit-config.yaml**: Pre-commit hook definitions
- **pyproject.toml**: Project dependencies and tool configuration

## Support

For issues or questions:
1. Check `.kiro/steering/README.md` for architectural guidance
2. Review `docs/` folder for detailed guides
3. Open an issue on GitHub
4. Reach out to @hollomancer