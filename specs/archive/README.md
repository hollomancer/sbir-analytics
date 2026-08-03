# Archived Specifications

Archived specifications preserve implementation history and rationale. They are
provenance, not current commands or architecture guidance. Start with the
[status registry](../status.md) and [specification workflow](../../docs/development/spec-workflow-guide.md)
before reviving any archived work.

## Categories

| Directory | Meaning |
| --- | --- |
| [`completed-features/`](completed-features/) | Delivered feature specifications and completion records |
| [`completed-migrations/`](completed-migrations/) | Finished repository or workflow migrations |
| [`superseded/`](superseded/) | Designs replaced by a different approach or intentionally dropped |

Other directories are historical snapshots retained for context. Their paths,
commands, dependencies, and task states may describe the repository at the time
they were written. Use current documentation under `docs/` to operate the system.

When archiving a spec, add a completion or supersession record, update
`specs/status.md`, and repair inbound links in the same change.
