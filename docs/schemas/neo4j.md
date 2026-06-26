---

Type: Reference
Owner: data@project
Last-Reviewed: 2026-06-26
Status: active

---

# Neo4j Schema (Canonical Index)

This is the canonical index for the graph schema written by the SBIR ETL loaders.
It lists the node labels and relationship types that the loaders actually create,
and links to the per-node reference docs.

- **SBIR award loading** (authoritative): `packages/sbir-analytics/sbir_analytics/assets/sbir_neo4j_loading.py`
- **Other loaders:** `packages/sbir-graph/sbir_graph/loaders/neo4j/`
  (`transitions.py`, `profiles.py`, `cet.py`, `patents.py`, `organizations.py`)
- Writes are MERGE-based and idempotent.
- Changes here must be reflected in loader code (and vice versa) in the same PR.

## Node Labels

| Label | Key | Created by | Reference |
|-------|-----|------------|-----------|
| `FinancialTransaction` | `transaction_id` | `sbir_neo4j_loading.py` (`transaction_type` = `AWARD`; `CONTRACT` from contract loading) | [financial-transaction-schema.md](financial-transaction-schema.md) |
| `Organization` | `organization_id` | `sbir_neo4j_loading.py`, `patents.py`, `cet.py` (companies, universities, agencies, patent assignees/assignors) | [organization-schema.md](organization-schema.md) |
| `Individual` | `individual_id` | `sbir_neo4j_loading.py`, `patents.py` (researchers/PIs, patent individuals) | [individual-schema.md](individual-schema.md) |
| `Transition` | `transition_id` | `transitions.py` | below |
| `TransitionProfile` | `profile_id` | `profiles.py` | below |
| `CETArea` | `cet_id` | `cet.py` | below |
| `Patent` | `grant_doc_num` | `patents.py` | [uspto-patents.md](uspto-patents.md) |
| `PatentAssignment` | `rf_id` | `patents.py` | [uspto-patents.md](uspto-patents.md) |

> **Not in the graph.** Earlier drafts referenced `:Award`, `:Contract`, `:Company`,
> and `:PatentEntity` nodes. These are **not** written by the loaders. Awards and
> contracts are unified as `FinancialTransaction`; companies/universities/agencies/
> patent organizations are unified as `Organization`; researchers and patent
> individuals are unified as `Individual`. (Some loader helper methods still carry
> legacy `:Award`/`:Company` constraints and CET-enrichment paths for backward
> compatibility, but the active asset graph uses the unified labels above.)

## Relationship Types

| Type | Direction | Created by |
|------|-----------|------------|
| `RECIPIENT_OF` | `FinancialTransaction` → `Organization` | `sbir_neo4j_loading.py` |
| `CONDUCTED_AT` | `FinancialTransaction` → `Organization` (research institution) | `sbir_neo4j_loading.py` |
| `FUNDED_BY` | `FinancialTransaction` → `Organization` (agency) | `sbir_neo4j_loading.py` |
| `PARTICIPATED_IN` | `Individual` → `FinancialTransaction` | `sbir_neo4j_loading.py` |
| `WORKED_AT` | `Individual` → `Organization` | `sbir_neo4j_loading.py` |
| `SUBSIDIARY_OF` | `Organization` → `Organization` | `sbir_neo4j_loading.py`, `organizations.py` |
| `FOLLOWS` | `FinancialTransaction` → `FinancialTransaction` (phase progression) | `sbir_neo4j_loading.py` |
| `TRANSITIONED_TO` | `FinancialTransaction` (AWARD) → `Transition` | `transitions.py` |
| `RESULTED_IN` | `Transition` → `FinancialTransaction` (CONTRACT) | `transitions.py` |
| `ENABLED_BY` | `Transition` → `Patent` | `transitions.py` |
| `INVOLVES_TECHNOLOGY` | `Transition` → `CETArea` | `transitions.py` |
| `ACHIEVED` | `Organization` (COMPANY) → `TransitionProfile` | `profiles.py` |
| `APPLICABLE_TO` | `Award` → `CETArea` (CET classification; legacy node target) | `cet.py` |
| `SPECIALIZES_IN` | `Organization` (COMPANY) → `CETArea` | `cet.py` |
| `OWNS` | `Organization` (COMPANY) → `Patent` | `patents.py` |
| `ASSIGNED_VIA` | `Patent` → `PatentAssignment` | `patents.py` |
| `ASSIGNED_TO` | `PatentAssignment` → `Organization` / `Individual` | `patents.py` |
| `ASSIGNED_FROM` | `PatentAssignment` → `Organization` / `Individual` | `patents.py` |
| `CHAIN_OF` | `PatentAssignment` → `PatentAssignment` | `patents.py` |
| `GENERATED_FROM` | `Patent` → `Award` (SBIR-funded patents) | `patents.py` |

> `GENERATED_FROM` targets an `award_id` key; in the unified model an SBIR award is a
> `FinancialTransaction` with `transaction_type = "AWARD"` (key `transaction_id =
> "txn_award_<award_id>"`).

## Transition, TransitionProfile, and CETArea nodes

These three labels do not have a dedicated per-node doc; they are summarized here.

### `:Transition`

Source: `transitions.py`. Key: `transition_id` (UNIQUE).

| Property | Notes |
|----------|-------|
| `transition_id` | Unique detection identifier |
| `award_id`, `contract_id` | Source award / target contract references |
| `likelihood_score` | Composite score (0.0–1.0) |
| `confidence` | e.g. `high`, `likely`, `possible` |
| `signals` | Serialized signal contributions |
| `evidence` | Serialized evidence bundle |
| `detected_at`, `updated_at` | Detection / update timestamps |
| `vendor_match_score` | Vendor resolution confidence |

Indexes: `transition_id`, `confidence`, `likelihood_score`, `detection_date`.

### `:TransitionProfile`

Source: `profiles.py`. Key: `profile_id` (UNIQUE). Company-level aggregate metrics.
Linked to its company via `(:Organization {organization_type:"COMPANY"})-[:ACHIEVED]->(:TransitionProfile)`.

| Property | Notes |
|----------|-------|
| `profile_id` | Unique profile identifier |
| `company_id` | Company reference |
| `total_awards`, `total_transitions` | Counts |
| `success_rate` | transitions / awards |
| `avg_likelihood_score` | Mean transition score |
| `high_confidence_count`, `likely_confidence_count` | Confidence breakdown |
| `last_transition_date` | Most recent detection |
| `avg_time_to_transition_days` | Mean days award→transition |
| `created_at`, `updated_at` | Timestamps |

Indexes: `profile_id`, `company_id`, `success_rate`.

### `:CETArea`

Source: `cet.py`. Key: `cet_id` (UNIQUE). Critical & Emerging Technology taxonomy area.

| Property | Notes |
|----------|-------|
| `cet_id` | Unique CET identifier |
| `name` | CET area name |
| `definition` | Optional description |
| `keywords` | Optional list of detection keywords |
| `taxonomy_version` | Taxonomy version string |

Indexes: `cet_id` (constraint), `name`, `taxonomy_version`.
CET classifications are also written as enrichment properties on `Organization` (companies)
and `Award` nodes, and as `SPECIALIZES_IN` / `APPLICABLE_TO` relationships.

## Per-node reference docs

- [Organization Schema](organization-schema.md) — companies, universities, agencies, patent organizations
- [Individual Schema](individual-schema.md) — researchers/PIs, patent individuals
- [Financial Transaction Schema](financial-transaction-schema.md) — awards and contracts
- [USPTO Patents](uspto-patents.md) — Patent / PatentAssignment nodes and USPTO source/field reference

## Identifiers

- Use stable domain identifiers (UEI, DUNS, grant document number) when available.
- Synthetic ids are namespaced by source/type, e.g. `txn_award_<id>`,
  `org_company_<id>`, `org_agency_<code>`, `ind_researcher_<id>`, `org_patent_<id>`.

## Update policy

- Additions must be backward compatible; deprecations require a migration note.
- Update this index and the relevant loader(s) in the same PR.
- Document architectural changes in `docs/decisions/`.

For queries/examples, see `docs/queries/` and integration tests under `tests/`.
