# Agent Instructions

Read [CLAUDE.md](CLAUDE.md) for the repository's project conventions, testing
requirements, code standards, and scope rules. Those instructions apply to all
coding agents; tool-specific agent definitions may differ by runtime.

## Epistemic tiers

Before implementing anything, establish which tier the work targets —
`primitives`, `pipelines`, `evidence`, or `exploratory`. The contracts are in
[docs/steering/epistemic-tiers.md](docs/steering/epistemic-tiers.md) and summarized
in CLAUDE.md.

Build to the declared tier and no higher. Unstated tier means `exploratory`.
Promotion between tiers is explicit work that satisfies the destination contract —
never a side effect of code becoming useful or gaining callers.

## Live deployment

Before any deployment, server operation, or live Dagster materialization, read
[the Mac mini runbook](docs/deployment/mac-mini-server.md#live-instance-on-this-mac-mini).
On the live host, also read `docs/deployment/mac-mini-status.local.md` when it
exists. That ignored file is the source of truth for current materialization
state; never copy its host-specific contents into tracked documentation.

- The only live checkout is `/Users/conradhollomon/projects/sbir-analytics-server`.
  Never operate the live stack from the development checkout.
- Preserve `.env.server`, `/Volumes/SSDmini/sbir-analytics`, and the Docker
  `dagster_home` volume.
- Ingress must remain Tailscale Serve over tailnet-only HTTPS. Never enable
  Funnel or expose server ports to the LAN or public internet.
- Treat materialization as a live-data mutation. Confirm the SSD is mounted,
  the deployment checkout is clean, and the stack is healthy before running it.
- Keep schedules disabled until their jobs have completed successfully by hand
  with the inputs available on this host.
