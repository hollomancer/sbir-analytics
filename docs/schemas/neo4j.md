---

Type: Reference
Owner: data@project
Last-Reviewed: 2025-10-30
Status: active

---

# Neo4j Schema (Canonical)

This is the canonical reference for the graph schema used by the SBIR ETL loader.

- Loader implementation: `src/loaders/` (MERGE-based idempotent writes)
- Schema docs (detailed): `docs/schemas/` (see Detailed Schema Documentation below)
- Changes here must be reflected in loader code and vice versa in the same PR.

## Detailed Schema Documentation

For comprehensive schema documentation, including field-level details, constraints, and examples:

- **[Organization Schema](../../schemas/organization-schema.md)** - Company and organization entities
- **[Individual Schema](../../schemas/individual-schema.md)** - Researcher and individual entities
- **[Financial Transaction Schema](../../schemas/financial-transaction-schema.md)** - Award and transaction entities
- **[Patent Assignment Schema](../../schemas/patent-assignment-schema.md)** - Patent assignment relationships
- **[Patent Neo4j Schema](../../schemas/patent-neo4j-schema.md)** - Patent entities and fields
- **[Patent Field Mapping](../../schemas/patent-field-mapping.md)** - USPTO to Neo4j field mapping
- **[Transition Graph Schema](../../schemas/transition-graph-schema.md)** - Technology transition detection schema

## Entities and Relationships

- Nodes: Company, Researcher, Award, Patent, SBIRAward
- Key relationships: `COMPANY_OWNS_AWARD`, `INDIVIDUAL_PARTICIPATED_IN`, `COMPANY_OWNS_PATENT`, `AWARD_FUNDED_PATENT`

## Identifiers

- Use stable domain identifiers (e.g., DUNS, UEI, patent number) when available.
- Synthetic ids are namespaced: `sbir:<id>`, `usaspending:<id>`, `uspto:<id>`.

## Constraints and Indexes

- Unique constraints on business keys (e.g., UEI for Company, patentNumber for Patent).
- Supporting indexes on frequent MATCH keys used by loaders.

## Update policy

- Additions must be backward compatible; deprecations require a migration note.
- Update `docs/references/schemas/neo4j.md` and the relevant loader(s) in the same PR.
- Document changes in `docs/decisions/` if they are architectural.

For queries/examples, see `docs/queries/` and integration tests under `tests/`.
