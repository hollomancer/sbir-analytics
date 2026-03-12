---
name: autodev-run
description: Start an autonomous development session working through pending project tasks
argument-hint: "[max-tasks] [--scope spec|quality|all]"
context: fork
agent: general-purpose
---

Start an autonomous development session for the SBIR Analytics project.

## Overview

You will systematically work through pending tasks from multiple sources:
1. Kiro specification tasks (`.kiro/specs/*/tasks.md`)
2. Failing tests
3. Lint and type errors
4. Code TODOs

## Discovery Phase

First, discover what needs to be done:

1. Run `uv run sbir-cli autodev specs --root .` to see spec completion status
2. Run `uv run sbir-cli autodev discover --root .` to see all work items
3. Run `uv run pytest tests/unit/ -x --tb=line -q -m "not slow"` to find test failures

## Execution Phase

Work through tasks in this priority order:

1. **Test failures** (unblocks everything)
2. **Lint/type errors** (quick wins)
3. **Near-complete spec tasks** (finish what's started)
4. **New spec tasks by risk** (low -> medium -> high)

For each task:
1. Read relevant context (source files, specs, steering docs)
2. Implement the change
3. Run `uv run ruff check` on changed files
4. Run `uv run pytest tests/unit/ -x -q -m "not slow"`
5. If tests pass: commit with message `autodev: [description]`
6. If tests fail: fix or revert, then continue
7. Move to next task

## Stop Conditions

- After completing $ARGUMENTS tasks (default: 10)
- If you hit 3 consecutive failures
- Before any HIGH risk task (credentials, deployment, schema changes) — ask the user
- After every 5 tasks — brief status update to the user

## Commit Convention

```
autodev: [spec-name or category] brief description of change
```
