---
name: fix-tests
description: Find and fix failing tests in the project
argument-hint: "[test-path or 'all']"
context: fork
agent: general-purpose
---

Find and fix failing tests in this project.

## Target

If `$ARGUMENTS` is provided, run tests at that path. Otherwise run `tests/unit/`.

## Steps

1. Run the tests:
   ```
   uv run pytest $ARGUMENTS -x --tb=short -q --no-header
   ```
   If no arguments: `uv run pytest tests/unit/ -x --tb=short -q --no-header -m "not slow"`

2. For each failing test:
   a. Read the test file to understand the assertion
   b. Read the source code being tested
   c. Determine if the test or source is wrong
   d. Fix the issue
   e. Re-run just that test file to verify

3. After fixing all failures, run the full suite to check for regressions:
   ```
   uv run pytest tests/unit/ -q --no-header -m "not slow"
   ```

4. Report: how many tests were failing, how many fixed, what the issues were

## Rules
- Fix root causes, don't weaken assertions
- If source code needs changing, fix source AND update test expectations
- Don't skip or disable tests unless genuinely irrelevant
