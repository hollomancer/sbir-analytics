# Neo4j Organization Schema

## Overview

The unified Organization node type consolidates Company, PatentEntity, ResearchInstitution, and Agency entities into a single node type. This simplifies entity resolution, reduces duplication, and enables unified queries across all organizational entities.

## Node Type

### Organization Node

Represents any organizational entity: companies, universities, government agencies, and patent entities.

**Label**: `:Organization`

### Properties

```yaml
organization_id: String (UNIQUE, PRIMARY KEY)
  # Unique organization identifier
  # Format varies by source:
  #   - Companies: "org_company_{company_id}" or "org_{uei}"
  #   - Patent entities: "org_patent_{entity_id}"
  #   - Agencies: "org_agency_{agency_code}"
  # Example: "org_company_abc123"

name: String
  # Organization name
  # Example: "Acme AI Inc."

normalized_name: String (nullable)
  # Normalized name for matching (uppercase, special chars removed)
  # Example: "ACME AI INC"

address: String (nullable)
  # Street address
  # Example: "123 Main St"

city: String (nullable)
  # City name
  # Example: "Arlington"

state: String (nullable)
  # State or province code (2-letter)
  # Example: "VA"

postcode: String (nullable)
  # Postal/ZIP code
  # Example: "22201"

country: String (nullable)
  # Country code (default: "US")
  # Example: "US"

organization_type: String
  # Type of organization: COMPANY, UNIVERSITY, GOVERNMENT, AGENCY
  # Example: "COMPANY"

source_contexts: List<String>
  # Source contexts: ["SBIR"], ["PATENT"], ["RESEARCH"], ["AGENCY"], or combinations
  # Example: ["SBIR", "PATENT"]

# SBIR-specific (nullable)
uei: String (nullable, UNIQUE)
  # Unique Entity Identifier (SAM.gov)
  # Example: "ABC123DEF456"  # pragma: allowlist secret

cage: String (nullable, UNIQUE)
  # CAGE code (5 characters)
  # Example: "1A2B3"

duns: String (nullable, UNIQUE)
  # DUNS number (9 digits)
  # Example: "123456789"

business_size: String (nullable)
  # SMALL_BUSINESS or OTHER
  # Example: "SMALL_BUSINESS"

company_id: String (nullable)
  # Legacy SBIR company_id for backward compatibility
  # Example: "company_abc123"

naics_primary: String (nullable)
  # Primary NAICS code
  # Example: "541511"

# Patent-specific (nullable)
entity_id: String (nullable)
  # Legacy PatentEntity identifier
  # Example: "entity_xyz789"

entity_category: String (nullable)
  # COMPANY, INDIVIDUAL, UNIVERSITY, GOVERNMENT (from patent context)
  # Example: "COMPANY"

num_assignments_as_assignee: Integer (nullable)
  # Number of patent assignments as assignee
  # Example: 15

num_assignments_as_assignor: Integer (nullable)
  # Number of patent assignments as assignor
  # Example: 3

num_patents_owned: Integer (nullable)
  # Current patent portfolio size
  # Example: 42

is_sbir_company: Boolean (nullable)
  # True if this organization matches an SBIR company
  # Example: true

# Agency-specific (nullable)
agency_code: String (nullable)
  # Agency code (e.g., "17" for DoD, "47" for NSF)
  # Example: "17"

agency_name: String (nullable)
  # Full agency name
  # Example: "Department of Defense"

sub_agency_code: String (nullable)
  # Sub-agency code (e.g., "5700" for Air Force)
  # Example: "5700"

sub_agency_name: String (nullable)
  # Sub-agency name
  # Example: "Department of the Air Force"

# Transition metrics (nullable, computed from transitions)
transition_total_awards: Integer (nullable)
  # Total SBIR awards for this company
  # Example: 5

transition_total_transitions: Integer (nullable)
  # Total detected transitions
  # Example: 3

transition_success_rate: Double (nullable)
  # Transition success rate (transitions / awards)
  # Example: 0.60

transition_avg_likelihood_score: Double (nullable)
  # Average likelihood score across transitions
  # Example: 0.72

transition_profile_updated_at: DateTime (nullable)
  # When transition metrics were last updated
  # Example: 2025-01-15T10:30:00Z

# Metadata
created_at: DateTime
  # When node was created
  # Example: 2025-01-15T10:30:00Z

updated_at: DateTime
  # When node was last updated
  # Example: 2025-01-15T10:30:00Z
```

### Constraints

- `organization_id` UNIQUE
- `uei` UNIQUE (where not null)
- `cage` UNIQUE (where not null)
- `duns` UNIQUE (where not null)

### Indexes

```cypher
CREATE INDEX idx_organization_id FOR (o:Organization) ON (o.organization_id);
CREATE INDEX idx_organization_name FOR (o:Organization) ON (o.name);
CREATE INDEX idx_organization_normalized_name FOR (o:Organization) ON (o.normalized_name);
CREATE INDEX idx_organization_type FOR (o:Organization) ON (o.organization_type);
CREATE INDEX idx_organization_uei FOR (o:Organization) ON (o.uei);
CREATE INDEX idx_organization_duns FOR (o:Organization) ON (o.duns);
CREATE INDEX idx_organization_agency_code FOR (o:Organization) ON (o.agency_code);
CREATE INDEX idx_organization_transition_success_rate FOR (o:Organization) ON (o.transition_success_rate);
CREATE INDEX idx_organization_transition_total_transitions FOR (o:Organization) ON (o.transition_total_transitions);
CREATE INDEX idx_organization_transition_total_awards FOR (o:Organization) ON (o.transition_total_awards);
CREATE FULLTEXT INDEX idx_organization_name_fulltext FOR (o:Organization) ON (o.name);
```

## Relationship Types

### Existing Relationships (Updated)

- `RECIPIENT_OF`: (FinancialTransaction) → (Organization)
  - Unified relationship replacing `AWARDED_TO` (awards) and `AWARDED_CONTRACT` (contracts)
  - Links financial transactions to recipient organizations
  - Properties: `transaction_type: "AWARD" | "CONTRACT"`, `role`, `created_at`
- `ASSIGNED_TO`: (PatentAssignment) → (Organization {organization_type IN ["COMPANY", "UNIVERSITY", "GOVERNMENT"]})
- `ASSIGNED_FROM`: (PatentAssignment) → (Organization {organization_type IN ["COMPANY", "UNIVERSITY", "GOVERNMENT"]})
- `OWNS`: (Organization {organization_type: "COMPANY"}) → (Patent)
- `SPECIALIZES_IN`: (Organization {organization_type: "COMPANY"}) → (CETArea)
- Transition metrics are now stored directly on Organization nodes (no separate TransitionProfile node)

### New Relationships

- `FUNDED_BY`: (FinancialTransaction) → (Organization {organization_type: "AGENCY"})
  - Links financial transactions (awards and contracts) to their funding/awarding agencies
  - Unified relationship replacing separate `AWARDED_BY` for contracts
  - Properties: `transaction_type: "AWARD" | "CONTRACT"`, `role: "FUNDING_AGENCY" | "AWARDING_AGENCY"`, `created_at`

- `SUBSIDIARY_OF`: (Organization) → (Organization)
  - Links organizations to their parent organizations
  - Used for:
    - Company subsidiaries (child company → parent company) via `parent_uei` from contracts
    - Agency hierarchies (sub-agency → parent agency) via `agency_code` and `sub_agency_code`
  - Properties:
    - `source`: String - Source of relationship ("CONTRACT_PARENT_UEI" or "AGENCY_HIERARCHY")
    - `created_at`: DateTime - When relationship was created
  - Direction: `(child)-[SUBSIDIARY_OF]->(parent)`

## Migration from Legacy Node Types

### Company → Organization

- All Company nodes migrated with `organization_type = "COMPANY"`
- `source_contexts = ["SBIR"]`
- `company_id` preserved for backward compatibility

### PatentEntity → Organization

- Only non-individual PatentEntity nodes migrated (`entity_category IN ["COMPANY", "UNIVERSITY", "GOVERNMENT"]`)
- Merged with existing Organizations when matches found (by normalized_name + state + postcode, or uei)
- `source_contexts` includes "PATENT"
- `entity_id` preserved for backward compatibility

### ResearchInstitution → Organization

- All ResearchInstitution nodes migrated with `organization_type = "UNIVERSITY"`
- `source_contexts = ["RESEARCH"]`
- Merged with existing Organizations when matches found

### Agency → Organization

- Created from unique `(agency_code, agency_name, sub_agency_code, sub_agency_name)` combinations in Award/Contract data
- `organization_type = "AGENCY"`
- `source_contexts = ["AGENCY"]`
- `organization_id = "org_agency_{agency_code}"`

## Query Patterns

### Find SBIR Companies

```cypher
MATCH (o:Organization {organization_type: "COMPANY"})
WHERE "SBIR" IN o.source_contexts
RETURN o
```

### Find Organizations with Patents

```cypher
MATCH (o:Organization)-[:OWNS]->(p:Patent)
RETURN o.name, count(p) as patent_count
ORDER BY patent_count DESC
```

### Find Funding Agencies

```cypher
MATCH (a:Award)-[:FUNDED_BY]->(o:Organization {organization_type: "AGENCY"})
RETURN o.agency_name, count(a) as award_count
ORDER BY award_count DESC
```

### Find Organization Subsidiaries

```cypher
// Find all subsidiaries of a company
MATCH (parent:Organization {uei: "ABC123DEF456"})<-[:SUBSIDIARY_OF]-(child:Organization)  # pragma: allowlist secret
RETURN child.name, child.uei, child.organization_type

// Find parent company of a subsidiary
MATCH (child:Organization {uei: "XYZ789GHI012"})-[:SUBSIDIARY_OF]->(parent:Organization)
RETURN parent.name, parent.uei

// Find all sub-agencies of DoD
MATCH (parent:Organization {agency_code: "17", organization_type: "AGENCY"})<-[:SUBSIDIARY_OF]-(sub:Organization)
WHERE sub.organization_type = "AGENCY"
RETURN sub.name, sub.sub_agency_code, sub.sub_agency_name

// Count subsidiaries per parent
MATCH (parent:Organization)<-[:SUBSIDIARY_OF]-(child:Organization)
RETURN parent.name, count(child) as subsidiary_count
ORDER BY subsidiary_count DESC
```

### Find Organizations Across Multiple Contexts

```cypher
MATCH (o:Organization)
WHERE size(o.source_contexts) > 1
RETURN o.name, o.organization_type, o.source_contexts
```

### Find Companies by Transition Success Rate

```cypher
MATCH (o:Organization {organization_type: "COMPANY"})
WHERE o.transition_success_rate IS NOT NULL
RETURN o.name, o.transition_total_awards, o.transition_total_transitions, o.transition_success_rate
ORDER BY o.transition_success_rate DESC
LIMIT 10
```

## Backward Compatibility

- Legacy properties (`company_id`, `entity_id`) preserved on Organization nodes
- Old node types (Company, PatentEntity, ResearchInstitution) remain in database until explicitly removed
- Queries can filter by `organization_type` to maintain type-specific behavior


