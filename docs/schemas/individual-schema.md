# Neo4j Individual Schema

## Overview

The unified Individual node type consolidates Researcher and PatentEntity (INDIVIDUAL) entities into a single node type. This simplifies entity resolution, reduces duplication, and enables unified queries across all individual persons in the graph.

## Node Type

### Individual Node

Represents any individual person: researchers/principal investigators, and patent assignees/assignors.

**Label**: `:Individual`

### Properties

```yaml
individual_id: String (UNIQUE, PRIMARY KEY)
  # Unique individual identifier
  # Format varies by source:
  #   - Researchers: "ind_researcher_{researcher_id}"
  #   - Patent individuals: "ind_patent_{entity_id}"
  # Example: "ind_researcher_jane.smith@university.edu"

name: String
  # Individual's full name
  # Example: "Dr. Jane Smith"

normalized_name: String (nullable)
  # Normalized name for matching (uppercase)
  # Example: "DR. JANE SMITH"

email: String (nullable, INDEXED)
  # Email address
  # Example: "jane.smith@university.edu"

phone: String (nullable)
  # Phone number
  # Example: "+1-555-123-4567"

address: String (nullable)
  # Street address (from patent assignments)
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

individual_type: String
  # Type of individual: RESEARCHER, PATENT_ASSIGNEE, PATENT_ASSIGNOR
  # Example: "RESEARCHER"

source_contexts: List<String>
  # Source contexts: ["SBIR"], ["PATENT"], or combinations
  # Example: ["SBIR", "PATENT"]

# Researcher-specific (nullable)
researcher_id: String (nullable, INDEXED)
  # Legacy Researcher identifier for backward compatibility
  # Example: "jane.smith@university.edu"

institution: String (nullable)
  # Academic/research institution
  # Example: "University of Technology"

department: String (nullable)
  # Department within institution
  # Example: "Computer Science"

title: String (nullable)
  # Professional title
  # Example: "Professor"

expertise: String (nullable)
  # Research expertise/keywords
  # Example: "Machine Learning, AI"

bio: String (nullable)
  # Researcher biography
  # Example: "Dr. Smith is a leading researcher..."

website: String (nullable)
  # Personal/academic website
  # Example: "https://janesmith.university.edu"

orcid: String (nullable)
  # ORCID identifier
  # Example: "0000-0001-2345-6789"

linkedin: String (nullable)
  # LinkedIn profile URL
  # Example: "https://linkedin.com/in/janesmith"

google_scholar: String (nullable)
  # Google Scholar profile URL
  # Example: "https://scholar.google.com/citations?user=..."

# Patent-specific (nullable)
entity_id: String (nullable, INDEXED)
  # Legacy PatentEntity identifier
  # Example: "entity_xyz789"

entity_type: String (nullable)
  # ASSIGNEE or ASSIGNOR (from patent context)
  # Example: "ASSIGNEE"

num_assignments_as_assignee: Integer (nullable)
  # Number of patent assignments as assignee
  # Example: 5

num_assignments_as_assignor: Integer (nullable)
  # Number of patent assignments as assignor
  # Example: 2

# Metadata
created_at: DateTime
  # When node was created
  # Example: 2025-01-15T10:30:00Z

updated_at: DateTime
  # When node was last updated
  # Example: 2025-01-15T10:30:00Z
```

### Constraints

- `individual_id` UNIQUE

### Indexes

```cypher
CREATE INDEX idx_individual_id FOR (i:Individual) ON (i.individual_id);
CREATE INDEX idx_individual_name FOR (i:Individual) ON (i.name);
CREATE INDEX idx_individual_normalized_name FOR (i:Individual) ON (i.normalized_name);
CREATE INDEX idx_individual_type FOR (i:Individual) ON (i.individual_type);
CREATE INDEX idx_individual_email FOR (i:Individual) ON (i.email);
CREATE INDEX idx_individual_researcher_id FOR (i:Individual) ON (i.researcher_id);
CREATE INDEX idx_individual_entity_id FOR (i:Individual) ON (i.entity_id);
CREATE FULLTEXT INDEX idx_individual_name_fulltext FOR (i:Individual) ON (i.name);
```

## Relationship Types

### Existing Relationships (Updated)

- `PARTICIPATED_IN`: (Individual {individual_type: "RESEARCHER"}) → (Award)
  - Unified relationship replacing RESEARCHED_BY and WORKED_ON
  - Properties: `role: "RESEARCHER"`, `created_at`
- `WORKED_AT`: (Individual {individual_type: "RESEARCHER"}) → (Organization)
- `ASSIGNED_TO`: (PatentAssignment) → (Individual {individual_type IN ["PATENT_ASSIGNEE"]})
- `ASSIGNED_FROM`: (PatentAssignment) → (Individual {individual_type IN ["PATENT_ASSIGNOR"]})

## Migration from Legacy Node Types

### Researcher → Individual

- All Researcher nodes migrated with `individual_type = "RESEARCHER"`
- `source_contexts = ["SBIR"]`
- `researcher_id` preserved for backward compatibility

### PatentEntity (INDIVIDUAL) → Individual

- Only PatentEntity nodes with `entity_category = "INDIVIDUAL"` migrated
- Merged with existing Individuals when matches found (by normalized_name + email, or normalized_name + address)
- `source_contexts` includes "PATENT"
- `entity_id` preserved for backward compatibility
- `individual_type` set based on `entity_type` (ASSIGNEE → PATENT_ASSIGNEE, ASSIGNOR → PATENT_ASSIGNOR)

## Query Patterns

### Find Researchers

```cypher
MATCH (i:Individual {individual_type: "RESEARCHER"})
WHERE "SBIR" IN i.source_contexts
RETURN i
```

### Find Individuals with Patents

```cypher
MATCH (i:Individual)-[:ASSIGNED_TO]->(pa:PatentAssignment)
RETURN i.name, count(pa) as assignment_count
ORDER BY assignment_count DESC
```

### Find Researchers Working on Awards

```cypher
MATCH (i:Individual {individual_type: "RESEARCHER"})-[:PARTICIPATED_IN]->(a:Award)
RETURN i.name, count(a) as award_count
ORDER BY award_count DESC
```

### Find Individuals Across Multiple Contexts

```cypher
MATCH (i:Individual)
WHERE size(i.source_contexts) > 1
RETURN i.name, i.individual_type, i.source_contexts
```

## Backward Compatibility

- Legacy properties (`researcher_id`, `entity_id`) preserved on Individual nodes
- Old node types (Researcher, PatentEntity) remain in database until explicitly removed
- Queries can filter by `individual_type` to maintain type-specific behavior

