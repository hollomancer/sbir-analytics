---
Type: Decision
Owner: data@project
Last-Reviewed: 2026-08-04
Status: accepted
---

# ADR-004: Retire the Private Analytics API

## Context

The repository added a private FastAPI service to expose curated Neo4j queries and analytical
snapshots. It has no current consumer tied to an active research question, but it adds a separate
runtime, authentication secret, dependency set, deployment health check, and Tailscale ingress
route. Maintaining those surfaces is not justified by the current research workflow.

## Decision

Retire the private analytics API and its API-only snapshot publishing path. Dagster, command-line
tools, studies, and direct operator access to Neo4j remain the supported execution surfaces.

Do not require an HTTP API before adding another adapter. Any future externally callable interface
must start from a current consumer and an active research or operational need, then define its own
least-privilege data, provenance, and deployment contract.

## Consequences

- The server profile no longer runs or exposes an analytics API.
- FastAPI, Uvicorn, bearer-token configuration, API-specific snapshots, and their tests are removed.
- The live stack has fewer dependencies, secrets, health checks, and ingress routes.
- A future API or MCP adapter requires a new decision based on a concrete consumer rather than the
  retired API-first rule.

## Alternatives considered

- **Keep the API dormant:** rejected because unused code still carries maintenance and security
  costs.
- **Keep snapshot publishing without HTTP:** rejected because the snapshot contract has no current
  non-API consumer.
- **Replace the API immediately:** rejected because no active consumer establishes a replacement
  contract.

## Links

- Supersedes [ADR-003: Establish APIs Before MCP Adapters](ADR-003-api-before-mcp.md)
- [Research questions](../research-questions.md)
