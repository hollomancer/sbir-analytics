---
name: spec-implement
description: Pick up and implement tasks from a Kiro specification
argument-hint: "[spec-name]"
context: fork
agent: general-purpose
---

Implement pending tasks from the Kiro specification: $ARGUMENTS

## Steps

1. Read the full spec from `.kiro/specs/$ARGUMENTS/`:
   - `requirements.md` — what needs to be built
   - `design.md` — how it should be built
   - `tasks.md` — specific implementation tasks

2. Identify all incomplete tasks (`- [ ]`) in tasks.md

3. For each incomplete task, in order:
   a. Read any existing code referenced in the task
   b. Read the relevant steering docs from `.kiro/steering/` if the task touches pipeline, Neo4j, enrichment, or config
   c. Implement the change following existing patterns
   d. Write or update tests in `tests/unit/`
   e. Run `uv run ruff check` on changed files
   f. Run `uv run pytest tests/unit/ -x -q -m "not slow"` to verify
   g. Update tasks.md to mark the task as `[x]`

4. After all tasks are done, report what was completed and what was skipped (with reasons)

## Quality Gates
- All changes must pass ruff lint
- All unit tests must pass
- Transition scoring changes must maintain >=85% precision benchmark
