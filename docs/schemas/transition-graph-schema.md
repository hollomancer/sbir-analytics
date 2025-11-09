# Neo4j Transition Graph Schema

## Overview

The transition detection graph model represents SBIR awards, federal contracts, patents, and their relationships in Neo4j. It enables complex queries about commercialization pathways, technology transfer, and innovation impact.

### Graph Purpose

- **Represent Entities**: Awards, contracts, patents, companies, technology areas
- **Capture Relationships**: How awards lead to contracts (transitions)
- **Enable Analysis**: Pathways from research to commercialization
- **Support Queries**: Complex traversals across multiple entity types

### Core Model

```text
(Award)-[TRANSITIONED_TO]->(Transition)<-[RESULTED_IN]-(Contract)
         |                          |

         +--[FUNDED_BY]-->(Company) +--[ENABLED_BY]-->(Patent)

         |                          |

         +--[INVOLVES_TECHNOLOGY]->(CETArea)

(Company)-[ACHIEVED]->(TransitionProfile)
(Transition)-[INVOLVES_TECHNOLOGY]->(CETArea)
```

## Node Types

### 1. Award Node

Represents an SBIR award.

**Label**: `:Award`

### Properties

```yaml
award_id: String (UNIQUE, PRIMARY KEY)
  # Unique identifier for award
  # Example: "SBIR-2020-PHASE-II-001"

phase: String
  # Award phase: PHASE_I, PHASE_II, PHASE_IIB, PHASE_III
  # Example: "PHASE_II"

program: String
  # Program type: SBIR or STTR
  # Example: "SBIR"

agency: String
  # Awarding agency code
  # Example: "17" (DoD), "47" (NSF)

sub_agency: String
  # Sub-agency (e.g., service branch)
  # Example: "5700" (Air Force)

agency_name: String
  # Full agency name
  # Example: "Department of Defense"

award_date: Date
  # Date award was made
  # Example: 2021-09-15

completion_date: Date
  # Expected/actual completion date
  # Example: 2023-01-15

award_amount: Long
  # Award amount in dollars
  # Example: 150000

recipient_name: String
  # Recipient company name
  # Example: "Acme AI Inc."

recipient_uei: String
  # Unique Entity Identifier
  # Example: "ABC123DEF456"  # pragma: allowlist secret

recipient_duns: String (nullable)
  # DUNS number (legacy)
  # Example: "123456789"

cet_area: String (nullable)
  # Critical Emerging Technology area
  # Example: "AI & Machine Learning"

topic: String
  # Award topic/title
  # Example: "Advanced neural network optimization"

description: Text
  # Award description/abstract
  # Example: "Development of federated learning techniques..."

principal_investigator: String (nullable)
  # PI name
  # Example: "Dr. Jane Smith"

company_size: String
  # SMALL_BUSINESS or OTHER
  # Example: "SMALL_BUSINESS"

created_at: DateTime
  # When node was created in graph
  # Example: 2024-01-15T10:30:00Z

updated_at: DateTime
  # When node was last updated
  # Example: 2024-01-15T10:30:00Z
```

### Constraints

- `award_id` UNIQUE

### Indexes

- `award_id` (PRIMARY)
- `phase` (for phase analysis)
- `agency` (for agency breakdown)
- `completion_date` (for time-based queries)

### Example Cypher

```cypher
CREATE (a:Award {
  award_id: "SBIR-2020-PHASE-II-001",
  phase: "PHASE_II",
  program: "SBIR",
  agency: "17",
  award_date: date("2021-09-15"),
  completion_date: date("2023-01-15"),
  award_amount: 150000,
  recipient_name: "Acme AI Inc.",
  recipient_uei: "ABC123DEF456",  # pragma: allowlist secret
  cet_area: "AI & Machine Learning"
})
```

---

### 2. Contract Node

Represents a federal contract.

**Label**: `:Contract`

### Properties

```yaml
contract_id: String (UNIQUE, PRIMARY KEY)
  # Unique identifier (PIID or FAIN)
  # Example: "FA1234-20-C-0001"

piid: String (nullable)
  # Procurement Instrument Identifier
  # Example: "FA1234-20-C-0001"

fain: String (nullable)
  # Federal Award Identification Number (for grants)
  # Example: "FAIN123456"

agency: String
  # Awarding agency code
  # Example: "17"

sub_agency: String (nullable)
  # Sub-agency code
  # Example: "5700"

agency_name: String
  # Full agency name
  # Example: "Department of Defense"

action_date: Date
  # Contract action date
  # Example: 2023-03-01

start_date: Date (nullable)
  # Period of performance start
  # Example: 2023-03-01

end_date: Date (nullable)
  # Period of performance end
  # Example: 2025-03-01

obligated_amount: Long
  # Amount obligated (dollars)
  # Example: 500000

base_and_all_options_value: Long (nullable)
  # Total potential value including options
  # Example: 1000000

competition_type: String
  # SOLE_SOURCE, LIMITED, FULL_AND_OPEN, UNKNOWN
  # Example: "SOLE_SOURCE"

vendor_name: String
  # Contractor name
  # Example: "Acme AI Inc."

vendor_uei: String (nullable)
  # Contractor UEI
  # Example: "ABC123DEF456"  # pragma: allowlist secret

description: Text
  # Statement of work or description
  # Example: "AI-powered threat detection system"

naics_code: String (nullable)
  # Industry classification
  # Example: "541511"

psc_code: String (nullable)
  # Product/Service Code
  # Example: "D316"

place_of_performance: String (nullable)
  # Location where work performed
  # Example: "Arlington, VA"

created_at: DateTime
  # When node created in graph
  # Example: 2024-01-15T10:30:00Z

updated_at: DateTime
  # When node last updated
  # Example: 2024-01-15T10:30:00Z
```

### Constraints

- `contract_id` UNIQUE

### Indexes

- `contract_id` (PRIMARY)
- `agency` (for agency analysis)
- `action_date` (for time-based queries)
- `vendor_uei` (for vendor lookup)
- `competition_type` (for competition analysis)

### Example Cypher

```cypher
CREATE (c:Contract {
  contract_id: "FA1234-20-C-0001",
  piid: "FA1234-20-C-0001",
  agency: "17",
  action_date: date("2023-03-01"),
  obligated_amount: 500000,
  competition_type: "SOLE_SOURCE",
  vendor_name: "Acme AI Inc.",
  vendor_uei: "ABC123DEF456"  # pragma: allowlist secret
})
```

---

### 3. Transition Node

Represents a detected transition from award to contract.

**Label**: `:Transition`

### Properties

```yaml
transition_id: String (UNIQUE, PRIMARY KEY)
  # Unique identifier for transition
  # Format: "trans_" + hex(hash)
  # Example: "trans_a1b2c3d4e5f6"

award_id: String
  # Reference to award (foreign key)
  # Example: "SBIR-2020-PHASE-II-001"

contract_id: String
  # Reference to contract (foreign key)
  # Example: "FA1234-20-C-0001"

likelihood_score: Double
  # Composite score (0.0-1.0)
  # Example: 0.7625

confidence: String
  # Confidence level: HIGH, LIKELY, POSSIBLE
  # Example: "LIKELY"

detection_date: DateTime
  # When detection occurred
  # Example: 2024-01-15T10:30:00Z

detection_method: String
  # Method/version of detector
  # Example: "transition_detector_v1"

vendor_match_method: String
  # How vendor was resolved: UEI, CAGE, DUNS, FUZZY_NAME
  # Example: "UEI"

vendor_match_confidence: Double
  # Confidence in vendor match (0.0-1.0)
  # Example: 0.99

signals: Map (JSON stored)
  # All signal scores and details
  # Serialized TransitionSignals object
  # Example: {"agency_continuity": {...}, "timing_proximity": {...}}

evidence_bundle: Text (JSON)
  # Complete evidence justification
  # Serialized EvidenceBundle object

created_at: DateTime
  # When node created in graph
  # Example: 2024-01-15T10:30:00Z

updated_at: DateTime
  # When node last updated
  # Example: 2024-01-15T10:30:00Z
```

### Constraints

- `transition_id` UNIQUE

### Indexes

- `transition_id` (PRIMARY)
- `confidence` (for filtering by confidence)
- `likelihood_score` (for range queries)
- `detection_date` (for temporal analysis)
- `vendor_match_method` (for method distribution)

### Example Cypher

```cypher
CREATE (t:Transition {
  transition_id: "trans_a1b2c3d4e5f6",
  award_id: "SBIR-2020-PHASE-II-001",
  contract_id: "FA1234-20-C-0001",
  likelihood_score: 0.7625,
  confidence: "LIKELY",
  detection_date: datetime("2024-01-15T10:30:00Z"),
  vendor_match_method: "UEI",
  vendor_match_confidence: 0.99,
  signals: {agency: 0.0625, timing: 0.20},
  evidence_bundle: "{...}"
})
```

---

### 4. Company Node

Represents a company (SBIR recipient or federal contractor).

**Label**: `:Company`

### Properties

```yaml
company_id: String (UNIQUE, PRIMARY KEY)
  # Unique company identifier
  # Example: "company_abc123"

uei: String (nullable, UNIQUE)
  # Unique Entity Identifier
  # Example: "ABC123DEF456"  # pragma: allowlist secret

cage: String (nullable, UNIQUE)
  # CAGE code
  # Example: "1A2B3"

duns: String (nullable, UNIQUE)
  # DUNS number
  # Example: "123456789"

name: String
  # Company legal name
  # Example: "Acme AI Inc."

headquarters_state: String (nullable)
  # State where headquartered
  # Example: "VA"

business_size: String (nullable)
  # SMALL_BUSINESS or OTHER
  # Example: "SMALL_BUSINESS"

naics_primary: String (nullable)
  # Primary NAICS code
  # Example: "541511"

created_at: DateTime
  # When node created in graph
  # Example: 2024-01-15T10:30:00Z

updated_at: DateTime
  # When node last updated
  # Example: 2024-01-15T10:30:00Z
```

### Constraints

- `company_id` UNIQUE
- `uei` UNIQUE (where not null)
- `cage` UNIQUE (where not null)
- `duns` UNIQUE (where not null)

### Indexes

- `company_id` (PRIMARY)
- `uei` (for UEI lookup)
- `name` (for name search, full-text index)

### Example Cypher

```cypher
CREATE (co:Company {
  company_id: "company_abc123",
  uei: "ABC123DEF456",  # pragma: allowlist secret
  name: "Acme AI Inc.",
  headquarters_state: "VA",
  business_size: "SMALL_BUSINESS"
})
```

---

### 5. Patent Node

Represents a patent.

**Label**: `:Patent`

### Properties

```yaml
patent_id: String (UNIQUE, PRIMARY KEY)
  # USPTO patent number
  # Example: "US10123456B2"

patent_number: String
  # Patent number (numeric)
  # Example: "10123456"

publication_number: String (nullable)
  # Publication number
  # Example: "US20210123456"

filing_date: Date
  # Patent filing date
  # Example: 2022-01-15

publication_date: Date (nullable)
  # Patent publication date
  # Example: 2023-01-10

issue_date: Date (nullable)
  # Patent issue date
  # Example: 2024-01-10

title: String
  # Patent title
  # Example: "Neural network optimization for edge devices"

abstract: Text
  # Patent abstract
  # Example: "A method for optimizing neural networks..."

assignee: String (nullable)
  # Patent assignee name
  # Example: "Acme AI Inc."

inventor_names: List<String> (nullable)
  # Inventor names
  # Example: ["John Smith", "Jane Doe"]

cpc_codes: List<String> (nullable)
  # Cooperative Patent Classification codes
  # Example: ["G06F17/16", "G06N3/00"]

ipc_codes: List<String> (nullable)
  # International Patent Classification codes
  # Example: ["G06F17/16"]

created_at: DateTime
  # When node created in graph
  # Example: 2024-01-15T10:30:00Z

updated_at: DateTime
  # When node last updated
  # Example: 2024-01-15T10:30:00Z
```

### Constraints

- `patent_id` UNIQUE

### Indexes

- `patent_id` (PRIMARY)
- `filing_date` (for temporal analysis)
- `assignee` (for assignee lookup)

### Example Cypher

```cypher
CREATE (p:Patent {
  patent_id: "US10123456B2",
  patent_number: "10123456",
  filing_date: date("2022-01-15"),
  issue_date: date("2024-01-10"),
  title: "Neural network optimization for edge devices",
  assignee: "Acme AI Inc."
})
```

---

### 6. CETArea Node

Represents a Critical & Emerging Technology area.

**Label**: `:CETArea`

### Properties

```yaml
cet_id: String (UNIQUE, PRIMARY KEY)
  # CET area identifier
  # Example: "cet_ai_ml"

name: String (UNIQUE)
  # CET area name
  # Example: "AI & Machine Learning"

description: Text
  # Area description
  # Example: "Artificial intelligence and machine learning technologies..."

priority_level: String
  # Priority level: CRITICAL or EMERGING
  # Example: "CRITICAL"

established_year: Integer (nullable)
  # Year CET area was established
  # Example: 2021

keywords: List<String>
  # Keywords for detection
  # Example: ["AI", "machine learning", "neural network", "NLP"]

created_at: DateTime
  # When node created in graph
  # Example: 2024-01-15T10:30:00Z

updated_at: DateTime
  # When node last updated
  # Example: 2024-01-15T10:30:00Z
```

### Constraints

- `cet_id` UNIQUE
- `name` UNIQUE

### Indexes

- `cet_id` (PRIMARY)
- `name` (for CET lookup)

### Example Cypher

```cypher
CREATE (cet:CETArea {
  cet_id: "cet_ai_ml",
  name: "AI & Machine Learning",
  priority_level: "CRITICAL",
  keywords: ["AI", "machine learning", "neural network"]
})
```

---

### 7. TransitionProfile Node

Represents company-level transition profile (aggregated metrics).

**Label**: `:TransitionProfile`

### Properties

```yaml
profile_id: String (UNIQUE, PRIMARY KEY)
  # Profile identifier
  # Format: "profile_" + company_id
  # Example: "profile_company_abc123"

company_id: String
  # Reference to company
  # Example: "company_abc123"

total_awards: Long
  # Total SBIR awards for this company
  # Example: 5

total_transitions: Long
  # Total detected transitions
  # Example: 3

success_rate: Double
  # Transition rate (transitions / awards)
  # Example: 0.60

avg_likelihood_score: Double
  # Average likelihood score of transitions
  # Example: 0.72

avg_time_to_transition: Double (nullable)
  # Average days from award completion to contract
  # Example: 245.5

highest_confidence_transition: String (nullable)
  # confidence of best transition
  # Example: "HIGH"

total_contract_value: Long (nullable)
  # Sum of obligated amounts
  # Example: 2500000

created_at: DateTime
  # When profile created
  # Example: 2024-01-15T10:30:00Z

updated_at: DateTime
  # When profile last updated
  # Example: 2024-01-15T10:30:00Z
```

### Constraints

- `profile_id` UNIQUE

### Indexes

- `profile_id` (PRIMARY)
- `company_id` (for company lookup)
- `success_rate` (for performance ranking)
- `total_transitions` (for volume analysis)

### Example Cypher

```cypher
CREATE (tp:TransitionProfile {
  profile_id: "profile_company_abc123",
  company_id: "company_abc123",
  total_awards: 5,
  total_transitions: 3,
  success_rate: 0.60,
  avg_likelihood_score: 0.72
})
```

---

## Relationship Types

### 1. TRANSITIONED_TO (Award → Transition)

Represents award that led to transition detection.

**Source**: `:Award`
**Target**: `:Transition`
**Direction**: Directed (outgoing)

### Properties

```yaml
award_id: String
  # Redundant with start node, for clarity

contract_id: String
  # Redundant with relationship target, for clarity

created_at: DateTime
  # When relationship created
  # Example: 2024-01-15T10:30:00Z

notes: String (nullable)
  # Additional context
```

### Example Cypher

```cypher
MATCH (a:Award {award_id: "SBIR-2020-PHASE-II-001"})
MATCH (t:Transition {transition_id: "trans_a1b2c3d4e5f6"})
CREATE (a)-[:TRANSITIONED_TO]->(t)
```

### Query Examples

```cypher

## Find all transitions from an award

MATCH (a:Award {award_id: "SBIR-2020-PHASE-II-001"})-[:TRANSITIONED_TO]->(t:Transition)
RETURN t

## Count transitions per award

MATCH (a:Award)-[:TRANSITIONED_TO]->(t:Transition)
RETURN a.award_id, count(t) as transition_count
ORDER BY transition_count DESC
```

---

### 2. RESULTED_IN (Transition → Contract)

Represents contract resulting from transition.

**Source**: `:Transition`
**Target**: `:Contract`
**Direction**: Directed (outgoing)

### Properties

```yaml
contract_id: String
  # Redundant with target node

created_at: DateTime
  # When relationship created
```

### Example Cypher

```cypher
MATCH (t:Transition {transition_id: "trans_a1b2c3d4e5f6"})
MATCH (c:Contract {contract_id: "FA1234-20-C-0001"})
CREATE (t)-[:RESULTED_IN]->(c)
```

### Query Examples

```cypher

## Find contract from transition

MATCH (t:Transition {transition_id: "trans_a1b2c3d4e5f6"})-[:RESULTED_IN]->(c:Contract)
RETURN c

## Award → Transition → Contract pathway

MATCH (a:Award {award_id: "SBIR-2020-PHASE-II-001"})

      -[:TRANSITIONED_TO]->(t:Transition)
      -[:RESULTED_IN]->(c:Contract)

RETURN a, t, c
```

---

### 3. ENABLED_BY (Transition → Patent)

Represents patents that enabled transition.

**Source**: `:Transition`
**Target**: `:Patent`
**Direction**: Directed (outgoing)

### Properties

```yaml
patent_id: String
  # Patent identifier

patent_topic_similarity: Double
  # TF-IDF similarity to contract description
  # Example: 0.76

pre_contract: Boolean
  # Whether patent filed before contract start
  # Example: true

created_at: DateTime
  # When relationship created
```

### Example Cypher

```cypher
MATCH (t:Transition {transition_id: "trans_a1b2c3d4e5f6"})
MATCH (p:Patent {patent_id: "US10123456B2"})
CREATE (t)-[:ENABLED_BY {patent_topic_similarity: 0.76, pre_contract: true}]->(p)
```

### Query Examples

```cypher

## Find patents enabling a transition

MATCH (t:Transition {transition_id: "trans_a1b2c3d4e5f6"})-[:ENABLED_BY]->(p:Patent)
RETURN p

## Find patent-backed transitions

MATCH (t:Transition)-[:ENABLED_BY]->(p:Patent)
WHERE t.confidence IN ["HIGH", "LIKELY"]
RETURN t, p
COUNT(DISTINCT t) as patent_backed_transitions
```

---

### 4. INVOLVES_TECHNOLOGY (Transition → CETArea)

Represents CET area of transition.

**Source**: `:Transition`
**Target**: `:CETArea`
**Direction**: Directed (outgoing)

### Properties

```yaml
cet_area: String
  # CET area name

cet_alignment_type: String
  # EXACT, PARTIAL, or INFERRED
  # Example: "EXACT"

created_at: DateTime
  # When relationship created
```

### Example Cypher

```cypher
MATCH (t:Transition {transition_id: "trans_a1b2c3d4e5f6"})
MATCH (cet:CETArea {name: "AI & Machine Learning"})
CREATE (t)-[:INVOLVES_TECHNOLOGY {cet_alignment_type: "EXACT"}]->(cet)
```

### Query Examples

```cypher

## Find CET area of transition

MATCH (t:Transition {transition_id: "trans_a1b2c3d4e5f6"})-[:INVOLVES_TECHNOLOGY]->(cet:CETArea)
RETURN cet

## Transitions by CET area

MATCH (t:Transition)-[:INVOLVES_TECHNOLOGY]->(cet:CETArea)
RETURN cet.name, count(t) as transition_count
ORDER BY transition_count DESC
```

---

### 5. FUNDED_BY (Award → Company)

Represents company that received award.

**Source**: `:Award`
**Target**: `:Company`
**Direction**: Directed (outgoing)

### Properties

```yaml
recipient_role: String
  # PRIME, SUBCONTRACTOR, or OTHER
  # Example: "PRIME"

created_at: DateTime
  # When relationship created
```

### Example Cypher

```cypher
MATCH (a:Award {award_id: "SBIR-2020-PHASE-II-001"})
MATCH (co:Company {uei: "ABC123DEF456"})  # pragma: allowlist secret
CREATE (a)-[:FUNDED_BY {recipient_role: "PRIME"}]->(co)
```

### Query Examples

```cypher

## Find company that received award

MATCH (a:Award {award_id: "SBIR-2020-PHASE-II-001"})-[:FUNDED_BY]->(co:Company)
RETURN co

## Companies with multiple awards

MATCH (a:Award)-[:FUNDED_BY]->(co:Company)
RETURN co.name, count(a) as award_count
ORDER BY award_count DESC
```

---

### 6. AWARDED_CONTRACT (Company → Contract)

Represents company that won contract.

**Source**: `:Company`
**Target**: `:Contract`
**Direction**: Directed (outgoing)

### Properties

```yaml
vendor_role: String
  # PRIME, SUBCONTRACTOR, or OTHER
  # Example: "PRIME"

created_at: DateTime
  # When relationship created
```

### Example Cypher

```cypher
MATCH (co:Company {uei: "ABC123DEF456"})  # pragma: allowlist secret
MATCH (c:Contract {contract_id: "FA1234-20-C-0001"})
CREATE (co)-[:AWARDED_CONTRACT {vendor_role: "PRIME"}]->(c)
```

---

### 7. FILED (Company → Patent)

Represents company that filed patent.

**Source**: `:Company`
**Target**: `:Patent`
**Direction**: Directed (outgoing)

### Properties

```yaml
assignee_type: String
  # OWNER, LICENSOR, or OTHER
  # Example: "OWNER"

created_at: DateTime
  # When relationship created
```

### Example Cypher

```cypher
MATCH (co:Company {name: "Acme AI Inc."})
MATCH (p:Patent {patent_id: "US10123456B2"})
CREATE (co)-[:FILED {assignee_type: "OWNER"}]->(p)
```

---

### 8. ACHIEVED (Company → TransitionProfile)

Represents company's transition profile.

**Source**: `:Company`
**Target**: `:TransitionProfile`
**Direction**: Directed (outgoing)

### Properties

```yaml
created_at: DateTime
  # When relationship created
```

### Example Cypher

```cypher
MATCH (co:Company {company_id: "company_abc123"})
MATCH (tp:TransitionProfile {profile_id: "profile_company_abc123"})
CREATE (co)-[:ACHIEVED]->(tp)
```

---

## Indexes and Constraints

### Node Indexes

```cypher

## Award indexes

CREATE INDEX idx_award_id ON :Award(award_id)
CREATE INDEX idx_award_phase ON :Award(phase)
CREATE INDEX idx_award_agency ON :Award(agency)
CREATE INDEX idx_award_completion_date ON :Award(completion_date)
CREATE INDEX idx_award_cet_area ON :Award(cet_area)

## Contract indexes

CREATE INDEX idx_contract_id ON :Contract(contract_id)
CREATE INDEX idx_contract_agency ON :Contract(agency)
CREATE INDEX idx_contract_action_date ON :Contract(action_date)
CREATE INDEX idx_contract_vendor_uei ON :Contract(vendor_uei)
CREATE INDEX idx_contract_competition_type ON :Contract(competition_type)

## Transition indexes

CREATE INDEX idx_transition_id ON :Transition(transition_id)
CREATE INDEX idx_transition_confidence ON :Transition(confidence)
CREATE INDEX idx_transition_likelihood_score ON :Transition(likelihood_score)
CREATE INDEX idx_transition_detection_date ON :Transition(detection_date)
CREATE INDEX idx_transition_vendor_match_method ON :Transition(vendor_match_method)

## Company indexes

CREATE INDEX idx_company_id ON :Company(company_id)
CREATE INDEX idx_company_uei ON :Company(uei)
CREATE INDEX idx_company_name ON :Company(name)

## Patent indexes

CREATE INDEX idx_patent_id ON :Patent(patent_id)
CREATE INDEX idx_patent_filing_date ON :Patent(filing_date)
CREATE INDEX idx_patent_assignee ON :Patent(assignee)

## CETArea indexes

CREATE INDEX idx_cet_id ON :CETArea(cet_id)
CREATE INDEX idx_cet_name ON :CETArea(name)

## TransitionProfile indexes

CREATE INDEX idx_profile_id ON :TransitionProfile(profile_id)
CREATE INDEX idx_profile_company_id ON :TransitionProfile(company_id)
CREATE INDEX idx_profile_success_rate ON :TransitionProfile(success_rate)
CREATE INDEX idx_profile_total_transitions ON :TransitionProfile(total_transitions)
```

### Unique Constraints

```cypher

## Award

CREATE CONSTRAINT award_award_id_unique ON (a:Award) ASSERT a.award_id IS UNIQUE

## Contract

CREATE CONSTRAINT contract_contract_id_unique ON (c:Contract) ASSERT c.contract_id IS UNIQUE

## Transition

CREATE CONSTRAINT transition_transition_id_unique ON (t:Transition) ASSERT t.transition_id IS UNIQUE

## Company

CREATE CONSTRAINT company_company_id_unique ON (co:Company) ASSERT co.company_id IS UNIQUE
CREATE CONSTRAINT company_uei_unique ON (co:Company) ASSERT co.uei IS UNIQUE
CREATE CONSTRAINT company_cage_unique ON (co:Company) ASSERT co.cage IS UNIQUE
CREATE CONSTRAINT company_duns_unique ON (co:Company) ASSERT co.duns IS UNIQUE

## Patent

CREATE CONSTRAINT patent_patent_id_unique ON (p:Patent) ASSERT p.patent_id IS UNIQUE

## CETArea

CREATE CONSTRAINT cet_cet_id_unique ON (cet:CETArea) ASSERT cet.cet_id IS UNIQUE
CREATE CONSTRAINT cet_name_unique ON (cet:CETArea) ASSERT cet.name IS UNIQUE

## TransitionProfile

CREATE CONSTRAINT profile_profile_id_unique ON (tp:TransitionProfile) ASSERT tp.profile_id IS UNIQUE
```

---

## Query Examples

### Basic Traversals

```cypher

## Award → Transition → Contract pathway

MATCH (a:Award {award_id: "SBIR-2020-PHASE-II-001"})

      -[:TRANSITIONED_TO]->(t:Transition)
      -[:RESULTED_IN]->(c:Contract)

RETURN a, t, c

## Award → Patent → Transition → Contract

MATCH (a:Award {award_id: "SBIR-2020-PHASE-II-001"})

      -[:FUNDED_BY]->(co:Company)

      <-[:FILED]-(p:Patent)
      <-[:ENABLED_BY]-(t:Transition)

      -[:RESULTED_IN]->(c:Contract)

RETURN a, co, p, t, c

## Company-level view

MATCH (co:Company {uei: "ABC123DEF456"})  # pragma: allowlist secret
      <-[:FUNDED_BY]-(a:Award)

      -[:TRANSITIONED_TO]->(t:Transition)
      -[:RESULTED_IN]->(c:Contract)

RETURN co, a, t, c

## Find HIGH confidence transitions

MATCH (t:Transition {confidence: "HIGH"})
      <-[:TRANSITIONED_TO]-(a:Award)
      <-[:FUNDED_BY]-(co:Company)

      -[:RESULTED_IN]->(c:Contract)

RETURN co.name, a.topic, c.piid, t.likelihood_score
ORDER BY t.likelihood_score DESC
```

### Aggregation Queries

```cypher

## Transitions by CET area

MATCH (t:Transition)-[:INVOLVES_TECHNOLOGY]->(cet:CETArea)
RETURN cet.name,
       count(t) as transition_count,
       avg(t.likelihood_score) as avg_score,
       max(t.likelihood_score) as max_score
ORDER BY transition_count DESC

## Company transition profile summary

MATCH (co:Company)
      <-[:FUNDED_BY]-(a:Award)

      -[:TRANSITIONED_TO]->(t:Transition)

RETURN co.name,
       count(DISTINCT a) as total_awards,
       count(DISTINCT t) as total_transitions,
       round(100.0 * count(DISTINCT t) / count(DISTINCT a)) as success_rate_percent
HAVING count(DISTINCT a) > 0
ORDER BY success_rate_percent DESC

## Transitions by agency

MATCH (a:Award)-[:TRANSITIONED_TO]->(t:Transition)
RETURN a.agency_name,
       count(t) as transitions,
       count(DISTINCT a) as awards,
       round(100.0 * count(t) / count(DISTINCT a)) as transition_rate_percent
ORDER BY transitions DESC
```

### Pattern Detection

```cypher

## Fast-tracked transitions (< 90 days)

MATCH (t:Transition)-[:RESULTED_IN]->(c:Contract)
      <-[:TRANSITIONED_TO]-(a:Award)
WHERE (c.action_date - a.completion_date) < 90
AND t.confidence IN ["HIGH", "LIKELY"]
RETURN a.award_id, a.recipient_name, c.piid, c.obligated_amount
ORDER BY c.action_date DESC

## Patent-backed transitions

MATCH (t:Transition {confidence: "HIGH"})

      -[:ENABLED_BY]->(p:Patent)
      -[:RESULTED_IN]->(c:Contract)

RETURN t.transition_id, p.title, c.piid, p.filing_date

## Multi-contract companies

MATCH (co:Company)
      <-[:FUNDED_BY]-(a:Award)

      -[:TRANSITIONED_TO]->(t:Transition)
      -[:RESULTED_IN]->(c:Contract)

WHERE a.phase = "PHASE_II"
WITH co, collect(DISTINCT c.piid) as contracts, count(DISTINCT c) as contract_count
WHERE contract_count > 1
RETURN co.name, contract_count, contracts
ORDER BY contract_count DESC
```

### Analysis Queries

```cypher

## Transition effectiveness by CET area

MATCH (a:Award)-[:INVOLVES_TECHNOLOGY]->(cet:CETArea)
      <-[:INVOLVES_TECHNOLOGY]-(t:Transition)
RETURN cet.name,
       count(DISTINCT a) as total_awards,
       count(DISTINCT t) as transitions,
       round(100.0 * count(DISTINCT t) / count(DISTINCT a)) as effectiveness_percent,
       avg(t.likelihood_score) as avg_confidence
ORDER BY effectiveness_percent DESC

## Time-to-transition analysis

MATCH (a:Award)-[:TRANSITIONED_TO]->(t:Transition)-[:RESULTED_IN]->(c:Contract)
WHERE c.action_date > a.completion_date
RETURN a.agency_name,
       count(*) as transitions,
       round(avg(c.action_date - a.completion_date)) as avg_days_to_transition,
       round(percentile(c.action_date - a.completion_date, 0.5)) as median_days
ORDER BY avg_days_to_transition ASC

## High-value commercialization

MATCH (a:Award)-[:TRANSITIONED_TO]->(t:Transition)-[:RESULTED_IN]->(c:Contract)
RETURN a.recipient_name,
       a.award_amount,
       sum(c.obligated_amount) as total_contracted,
       round(100.0 * sum(c.obligated_amount) / (a.award_amount + 1)) as roi_percent
ORDER BY total_contracted DESC
LIMIT 20
```

---

## Data Loading

### Loading Awards

```cypher
UNWIND $award_records AS record
MERGE (a:Award {award_id: record.award_id})
SET a.phase = record.phase,
    a.program = record.program,
    a.agency = record.agency,
    a.award_date = record.award_date,
    a.completion_date = record.completion_date,
    a.award_amount = record.award_amount,
    a.recipient_name = record.recipient_name,
    a.recipient_uei = record.recipient_uei,
    a.cet_area = record.cet_area,
    a.updated_at = timestamp()
```

### Loading Contracts

```cypher
UNWIND $contract_records AS record
MERGE (c:Contract {contract_id: record.contract_id})
SET c.piid = record.piid,
    c.agency = record.agency,
    c.action_date = record.action_date,
    c.obligated_amount = record.obligated_amount,
    c.competition_type = record.competition_type,
    c.vendor_name = record.vendor_name,
    c.vendor_uei = record.vendor_uei,
    c.updated_at = timestamp()
```

### Loading Transitions

```cypher
UNWIND $transition_records AS record
MERGE (t:Transition {transition_id: record.transition_id})
SET t.award_id = record.award_id,
    t.contract_id = record.contract_id,
    t.likelihood_score = record.likelihood_score,
    t.confidence = record.confidence,
    t.detection_date = record.detection_date,
    t.vendor_match_method = record.vendor_match_method,
    t.signals = record.signals,
    t.evidence_bundle = record.evidence_bundle,
    t.updated_at = timestamp()
```

### Creating Relationships

```cypher

## Award → Transition

UNWIND $transitions AS t
MATCH (a:Award {award_id: t.award_id})
MATCH (tr:Transition {transition_id: t.transition_id})
MERGE (a)-[:TRANSITIONED_TO]->(tr)

## Transition → Contract

UNWIND $transitions AS t
MATCH (tr:Transition {transition_id: t.transition_id})
MATCH (c:Contract {contract_id: t.contract_id})
MERGE (tr)-[:RESULTED_IN]->(c)

## Transition → Patent (if applicable)

UNWIND $enabled_by AS eb
MATCH (t:Transition {transition_id: eb.transition_id})
MATCH (p:Patent {patent_id: eb.patent_id})
MERGE (t)-[:ENABLED_BY {patent_topic_similarity: eb.similarity}]->(p)

## Transition → CETArea

UNWIND $cet_links AS cl
MATCH (t:Transition {transition_id: cl.transition_id})
MATCH (cet:CETArea {name: cl.cet_name})
MERGE (t)-[:INVOLVES_TECHNOLOGY {cet_alignment_type: cl.alignment_type}]->(cet)
```

---

## Best Practices

### Query Performance

1. **Use Indexes**: Always query on indexed properties first
2. **Limit Result Sets**: Use WHERE clauses early to reduce matches
3. **Batch Operations**: Load data in batches of 1,000-10,000 for performance
4. **Cache Results**: Store frequently accessed data in application layer

### Data Integrity

1. **Use MERGE**: Avoid duplicate nodes/relationships
2. **Timestamps**: Always set created_at and updated_at
3. **Constraints**: Use UNIQUE constraints on identifiers
4. **Validation**: Validate data before loading to Neo4j

### Schema Maintenance

1. **Version Control**: Track schema changes with dates
2. **Backups**: Regular backups before schema changes
3. **Testing**: Test queries on development database first
4. **Documentation**: Document custom indexes and constraints

---

## References

- **Implementation**: `src/loaders/transition_loader.py`
- **Tests**: `tests/unit/test_transition_loader.py`
- **Queries**: `src/transition/queries/transition_pathway_queries.py`
- **Neo4j Documentation**: https://neo4j.com/docs/cypher-manual/current/
