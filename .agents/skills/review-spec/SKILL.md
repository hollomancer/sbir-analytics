---
name: review-spec
description: Review a specification's current relevance and implementation status
argument-hint: "[spec-name or 'all']"
---

Review specification(s) against their lifecycle status, research purpose, tier,
and the actual codebase. Follow `docs/development/spec-workflow-guide.md`.

## If reviewing a specific spec ($ARGUMENTS):

1. Find the entry in `specs/status.md`. If it is missing, report a registry error.
2. Read the spec's requirements, design, and tasks when present. A standalone
   top-level Markdown file may be the complete spec.
3. Identify the research-question ID or operating duty, target epistemic tier,
   status, explicit exclusions, and completion checks. Report missing fields.
4. Compare every open task and claimed result with current code, tests, studies,
   and documentation.
5. Report one lifecycle verdict:
   - **CURRENT**: Status, scope, and remaining tasks match the repository.
   - **PARTLY STALE**: Some work landed or changed without spec reconciliation.
   - **STALE**: The implementation or design has been superseded.
   - **GATED**: The work remains valid but its stated prerequisite is unmet.
   - **ARCHIVE READY**: Completion or supersession is documented and no active
     work should continue from the top-level spec.

## If reviewing all specs:

1. Use `specs/status.md` as the inventory. Confirm that each top-level spec
   directory and standalone spec file appears exactly once.
2. Review each registered spec using the specific-spec process above.
3. Provide a summary table with:
   - Spec name
   - Registry status
   - Research question or operating duty
   - Target tier
   - Done / pending tasks when a task list exists
   - Lifecycle verdict
   - Next gate or smallest relevant task
4. Recommend archiving only when the lifecycle evidence supports it; unchecked
   tasks alone do not make a spec current, and checked tasks alone do not prove
   that it is ready to archive.

## Output Format

Provide a Markdown table, then detailed notes for registry errors, stale claims,
unmet gates, tier problems, and archive candidates. Separate implementation
status from evidence status: working code does not by itself make a result
validated or citable.
