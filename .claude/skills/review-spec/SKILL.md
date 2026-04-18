---
name: review-spec
description: Review a specification's current relevance and implementation status
argument-hint: "[spec-name or 'all']"
---

Review the implementation status of specification(s) against the actual codebase.

## If reviewing a specific spec ($ARGUMENTS):

1. Read `specs/$ARGUMENTS/tasks.md` to find incomplete tasks
2. For each incomplete task:
   - Check if the referenced files/modules already exist
   - Check if the described functionality is already implemented elsewhere
   - Assess whether the task is still relevant
3. Report:
   - **STILL RELEVANT**: Task needs work, code doesn't exist
   - **PARTIALLY STALE**: Some work done but task not updated
   - **FULLY STALE**: Code exists or spec is superseded

## If reviewing all specs:

1. Read all `specs/*/tasks.md` files
2. For each spec, provide a summary table:
   - Spec name
   - Total / Done / Pending tasks
   - Relevance verdict
   - Top priority remaining task
3. Recommend which specs should be archived

## Output Format

Provide a markdown table summarizing findings, then detailed notes for any spec that needs attention.
