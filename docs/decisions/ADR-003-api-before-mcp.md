---

Type: Decision
Owner: data@project
Last-Reviewed: 2026-07-12
Status: accepted

---

# ADR-003: Establish APIs Before MCP Adapters

## Context

The repository produces analytical evidence for dashboards, notebooks, partner applications, and
AI assistants. If each transport implements its own queries or orchestration, business rules,
authorization, provenance, and safety controls drift. The superseded MCP design also exposed raw
Cypher and pipeline execution before a stable application interface existed.

## Decision

New externally callable functionality follows this dependency direction:

```text
domain and analytics code → transport-neutral service → private/versioned API → optional MCP adapter
```

- Domain calculations and curated data access live outside HTTP and MCP modules.
- The private API is the first supported transport and defines validation, provenance, errors, and
  authorization for a capability.
- An MCP tool may be added only after the underlying service and API contract exist. It delegates
  to the same service method and cannot gain raw Cypher, filesystem, Dagster, or other privileges
  absent from the API capability.
- MCP-specific response shaping and tool descriptions may live in the adapter; analytical logic,
  queries, and side-effect policy may not.
- Exceptions require a superseding ADR. Local developer-only diagnostics that are not product
  functionality are outside this rule.

## Consequences

- Dashboards, notebooks, integrations, and AI assistants receive consistent answers and provenance.
- MCP remains inexpensive to add because it is a protocol adapter rather than a second backend.
- API contracts must be designed and tested before an MCP tool ships.
- Some local-only AI experiments may take longer to productize, but they cannot silently become a
  privileged production interface.

## Alternatives considered

- **MCP-first:** rejected because it couples domain behavior to one class of clients.
- **Independent API and MCP implementations:** rejected because query and security behavior drift.
- **Raw graph gateway:** rejected because it bypasses curated semantics and least privilege.

## Links

- [Private analytics API](../architecture/private-analytics-api.md)
- Superseded design: `specs/archive/superseded/mcp_interface/`
