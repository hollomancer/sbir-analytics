# Agent Instructions

This file routes; it does not carry rules of its own. Everything below lives
canonically somewhere else, so there is nothing here to drift out of sync.

**Read [CLAUDE.md](CLAUDE.md) first.** It is the canonical source for project
conventions, epistemic tiers, testing requirements, code standards, scope rules,
and the live-deployment constraints. Those instructions apply to all coding
agents regardless of runtime; only the tool-specific agent definitions in
`.claude/agents/` vary.

Then, depending on the work:

| Doing | Read |
|---|---|
| Anything at all | [CLAUDE.md](CLAUDE.md) |
| Deployment, server operations, or live Dagster materialization | [the Mac mini runbook](docs/deployment/mac-mini-server.md#live-instance-on-this-mac-mini) — **before** acting, not after — plus the live-deployment section of CLAUDE.md |
| Implementing a spec | [docs/steering/epistemic-tiers.md](docs/steering/epistemic-tiers.md) for the tier contract, then the spec directory in `specs/` |
| Judging whether work is in scope | [docs/research-questions.md](docs/research-questions.md) |
| Architecture context | [docs/architecture/detailed-overview.md](docs/architecture/detailed-overview.md), patterns in `docs/steering/` |

If guidance appears to conflict, CLAUDE.md wins for conventions and the runbook
wins for anything touching the live host. If you find a rule stated here rather
than referenced, that is a bug in this file — move it to CLAUDE.md.
