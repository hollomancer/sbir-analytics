# FinancialTransaction Node Schema

## Overview

The `FinancialTransaction` node type unifies `Award` and `Contract` nodes into a single node type, simplifying the graph model and enabling unified queries across all financial transactions.

## Node Type

**Label**: `:FinancialTransaction`

## Properties

### Core Identification

```yaml
transaction_id: String (UNIQUE, PRIMARY KEY)
  # Unique transaction identifier
  # Format: "txn_award_{award_id}" or "txn_contract_{contract_id}"
  # Example: "txn_award_SBIR-2020-PHASE-II-001"

transaction_type: String (REQUIRED)
  # Type of transaction: "AWARD" or "CONTRACT"
  # Example: "AWARD"
```

### Common Properties

```yaml
agency: String (nullable)
  # Awarding agency code
  # Example: "17"

agency_name: String (nullable)
  # Full agency name
  # Example: "Department of Defense"

sub_agency: String (nullable)
  # Sub-agency code
  # Example: "5700"

sub_agency_name: String (nullable)
  # Sub-agency name
  # Example: "Air Force"

recipient_name: String (nullable)
  # Recipient/vendor company name
  # Example: "Acme AI Inc."

recipient_uei: String (nullable)
  # Recipient/vendor UEI
  # Example: "ABC123DEF456"

recipient_duns: String (nullable)
  # Recipient/vendor DUNS number
  # Example: "123456789"

recipient_cage: String (nullable)
  # Recipient/vendor CAGE code
  # Example: "ABC12"

amount: Float (REQUIRED)
  # Transaction amount in USD
  # Example: 150000.0

base_and_all_options_value: Float (nullable)
  # Total potential value including options (contracts)
  # Example: 1000000.0

transaction_date: Date (REQUIRED)
  # Transaction date (award_date or action_date)
  # Example: 2021-09-15

start_date: Date (nullable)
  # Period of performance start
  # Example: 2021-09-15

end_date: Date (nullable)
  # Period of performance end
  # Example: 2023-01-15

completion_date: Date (nullable)
  # Completion date (awards)
  # Example: 2023-01-15

title: String (nullable)
  # Transaction title
  # Example: "Advanced neural network optimization"

description: String (nullable)
  # Transaction description/abstract
  # Example: "Development of federated learning techniques..."

naics_code: String (nullable)
  # NAICS code
  # Example: "541511"

naics_description: String (nullable)
  # NAICS description
  # Example: "Custom Computer Programming Services"
```

### Award-Specific Properties

```yaml
award_id: String (nullable)
  # Legacy Award identifier for backward compatibility
  # Example: "SBIR-2020-PHASE-II-001"

phase: String (nullable)
  # Award phase: PHASE_I, PHASE_II, PHASE_IIB, PHASE_III
  # Example: "PHASE_II"

program: String (nullable)
  # Program type: SBIR or STTR
  # Example: "SBIR"

principal_investigator: String (nullable)
  # Principal Investigator name
  # Example: "Dr. Jane Smith"

research_institution: String (nullable)
  # Research institution
  # Example: "MIT"

cet_area: String (nullable)
  # Critical Emerging Technology area
  # Example: "AI & Machine Learning"

award_year: Integer (nullable)
  # Award year
  # Example: 2020

fiscal_year: Integer (nullable)
  # Fiscal year
  # Example: 2021
```

### Contract-Specific Properties

```yaml
contract_id: String (nullable)
  # Legacy Contract identifier for backward compatibility
  # Example: "FA1234-20-C-0001"

piid: String (nullable)
  # Procurement Instrument Identifier
  # Example: "FA1234-20-C-0001"

fain: String (nullable)
  # Federal Award Identification Number
  # Example: "FAIN123456"

competition_type: String (nullable)
  # Competition type: SOLE_SOURCE, LIMITED, FULL_AND_OPEN
  # Example: "SOLE_SOURCE"

psc_code: String (nullable)
  # Product/Service Code
  # Example: "D316"

place_of_performance: String (nullable)
  # Place of performance location
  # Example: "Arlington, VA"

contract_type: String (nullable)
  # Contract type code
  # Example: "C"
```

### Metadata

```yaml
created_at: DateTime (nullable)
  # Creation timestamp
  # Example: 2025-01-15T10:30:00Z

updated_at: DateTime (nullable)
  # Last update timestamp
  # Example: 2025-01-15T10:30:00Z
```

## Constraints

- `transaction_id` UNIQUE

## Indexes

- `transaction_id` (PRIMARY)
- `transaction_type` (for filtering by type)
- `transaction_date` (for time-based queries)
- `agency` (for agency breakdown)
- `award_id` (for backward compatibility lookups)
- `contract_id` (for backward compatibility lookups)
- `recipient_uei` (for vendor lookup)

## Relationship Types

### Outgoing Relationships

- `AWARDED_TO`: (FinancialTransaction) → (Organization)
- `FUNDED_BY`: (FinancialTransaction) → (Organization {agency})
- `CONDUCTED_AT`: (FinancialTransaction) → (Organization {research institution})
- `TRANSITIONED_TO`: (FinancialTransaction {AWARD}) → (Transition)
- `FOLLOWS`: (FinancialTransaction) → (FinancialTransaction) - Phase progressions
- `GENERATED_FROM`: (Patent) → (FinancialTransaction)

### Incoming Relationships

- `PARTICIPATED_IN`: (Individual) → (FinancialTransaction)
- `RESULTED_IN`: (Transition) → (FinancialTransaction {CONTRACT})

## Example Cypher Queries

### Create FinancialTransaction (Award)

```cypher
CREATE (ft:FinancialTransaction {
  transaction_id: "txn_award_SBIR-2020-PHASE-II-001",
  transaction_type: "AWARD",
  award_id: "SBIR-2020-PHASE-II-001",
  phase: "PHASE_II",
  program: "SBIR",
  agency: "17",
  transaction_date: date("2021-09-15"),
  amount: 150000,
  recipient_name: "Acme AI Inc.",
  recipient_uei: "ABC123DEF456"
})
```

### Create FinancialTransaction (Contract)

```cypher
CREATE (ft:FinancialTransaction {
  transaction_id: "txn_contract_FA1234-20-C-0001",
  transaction_type: "CONTRACT",
  contract_id: "FA1234-20-C-0001",
  piid: "FA1234-20-C-0001",
  agency: "17",
  transaction_date: date("2023-03-01"),
  amount: 500000,
  competition_type: "SOLE_SOURCE",
  recipient_name: "Acme AI Inc.",
  recipient_uei: "ABC123DEF456"
})
```

### Find All Awards for a Company

```cypher
MATCH (ft:FinancialTransaction {transaction_type: "AWARD"})-[:AWARDED_TO]->(o:Organization {organization_id: $org_id})
RETURN ft
ORDER BY ft.transaction_date DESC
```

### Find All Contracts for a Company

```cypher
MATCH (ft:FinancialTransaction {transaction_type: "CONTRACT"})-[:AWARDED_TO]->(o:Organization {organization_id: $org_id})
RETURN ft
ORDER BY ft.transaction_date DESC
```

### Find All Financial Transactions (Awards + Contracts)

```cypher
MATCH (ft:FinancialTransaction)-[:AWARDED_TO]->(o:Organization {organization_id: $org_id})
RETURN ft.transaction_type, ft.amount, ft.transaction_date
ORDER BY ft.transaction_date DESC
```

### Find Transition Pathway (Award → Transition → Contract)

```cypher
MATCH (award:FinancialTransaction {transaction_type: "AWARD"})-[:TRANSITIONED_TO]->(t:Transition)-[:RESULTED_IN]->(contract:FinancialTransaction {transaction_type: "CONTRACT"})
RETURN award, t, contract
```

## Migration Notes

- Legacy `Award` and `Contract` nodes are migrated to `FinancialTransaction` nodes
- `award_id` and `contract_id` properties are preserved for backward compatibility
- All relationships are updated to point to `FinancialTransaction` nodes
- Use `transaction_type` filter to query specific transaction types

## Related Documentation

- [Transition Graph Schema](./transition-graph-schema.md)
- [Organization Schema](./organization-schema.md)
- [Architecture Overview](../architecture/detailed-overview.md) - For migration context

