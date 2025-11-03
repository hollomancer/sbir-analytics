# Transition Pathway Queries

## Overview

The Transition Pathway Queries module provides a comprehensive interface for traversing and analyzing transition detection pathways in the Neo4j graph. These queries enable sophisticated analysis of how SBIR awards transition to federal contracts, the role of patents in facilitating transitions, and company-level success patterns.

## Architecture

Transition pathways are built on the following Neo4j graph model:

```text
Award
  ├─ TRANSITIONED_TO → Transition (score, confidence, evidence)
  │   └─ RESULTED_IN → Contract
  ├─ FILED → Patent
  │   └─ (Patent) ← ENABLED_BY (Transition)
  └─ APPLICABLE_TO → CETArea
       └─ (CETArea) ← INVOLVES_TECHNOLOGY (Transition)

Company
  └─ ACHIEVED → TransitionProfile (aggregated metrics)
```

## Query Interface

All queries are implemented in `src/transition/queries/pathway_queries.py` through the `TransitionPathwayQueries` class.

```python
from neo4j import GraphDatabase
from src.transition.queries.pathway_queries import TransitionPathwayQueries

## Initialize driver

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))

## Create query executor

queries = TransitionPathwayQueries(driver)

## Execute queries

result = queries.award_to_transition_to_contract(min_score=0.80)
print(f"Found {result.records_count} pathways")
for record in result.records:
    print(record)
```

## Query Specifications

### 1. Award → Transition → Contract

**Purpose:** Find all federal contracts reachable from an SBIR award through detected transitions.

**Method:** `award_to_transition_to_contract()`

### Parameters:

- `award_id` (Optional[str]): Filter to specific award (None for all)
- `min_score` (float): Minimum transition score (0.0-1.0), default 0.0
- `confidence_levels` (Optional[List[str]]): Filter by confidence ('high', 'likely', 'possible')
- `limit` (int): Maximum results to return, default 1000

**Returns:** `PathwayResult` with:
- `award_id`: Unique award identifier
- `award_name`: Award title
- `transition_id`: Unique transition identifier
- `transition_score`: Composite likelihood score (0-1)
- `transition_confidence`: Confidence level
- `contract_id`: Federal contract identifier
- `contract_name`: Contract description
- `detection_date`: When transition was detected

### Example:

```python

## Find high-confidence transitions for a specific award

result = queries.award_to_transition_to_contract(
    award_id="SBIR-FY2020-123456",
    min_score=0.80,
    confidence_levels=["high", "likely"]
)

## Find all transitions across all awards

result = queries.award_to_transition_to_contract(min_score=0.60)
print(f"Found {result.records_count} award→contract pathways")
```

### Use Cases:

- Track individual award outcomes to federal contracts
- Validate transition detection precision for specific awards
- Identify contract vehicles by transition confidence levels

---

### 2. Award → Patent → Transition → Contract

**Purpose:** Identify contract transitions backed by patent filings, demonstrating technology transfer.

**Method:** `award_to_patent_to_transition_to_contract()`

### Parameters:

- `award_id` (Optional[str]): Filter to specific award (None for all)
- `min_patent_contribution` (float): Minimum patent contribution score, default 0.0
- `limit` (int): Maximum results to return, default 1000

**Returns:** `PathwayResult` with:
- `award_id`: Source SBIR award
- `award_name`: Award title
- `patent_id`: Patent number
- `patent_title`: Patent title
- `patent_contribution`: Score indicating patent's role in transition (0-1)
- `transition_id`: Transition identifier
- `transition_score`: Likelihood score
- `contract_id`: Resulting federal contract
- `contract_name`: Contract description

### Example:

```python

## Find patent-backed transitions with strong contribution

result = queries.award_to_patent_to_transition_to_contract(
    min_patent_contribution=0.50
)
print(f"Found {result.records_count} patent-backed transitions")

## Analyze patents for a specific award

result = queries.award_to_patent_to_transition_to_contract(
    award_id="SBIR-FY2019-654321"
)
```

### Use Cases:

- Quantify technology transfer rate through patent-backed contracts
- Identify most impactful patents in enabling transitions
- Analyze patent-to-commercialization pathways

---

### 3. Award → CET → Transition

**Purpose:** Analyze transitions within specific technology areas (CET = Critical and Emerging Technologies).

**Method:** `award_to_cet_to_transition()`

### Parameters:

- `cet_area` (Optional[str]): Specific technology area (None for all)
- `min_score` (float): Minimum transition score, default 0.0
- `limit` (int): Maximum results to return, default 1000

**Returns:** `PathwayResult` with:
- `award_id`: SBIR award
- `award_title`: Award title
- `transition_id`: Transition identifier
- `transition_score`: Likelihood score
- `cet_area`: Technology area ID
- `cet_name`: Human-readable technology area name
- `cet_alignment`: Score indicating CET area alignment (0-1)
- `confidence`: Transition confidence level

### Example:

```python

## Find all transitions in Artificial Intelligence

result = queries.award_to_cet_to_transition(
    cet_area="Artificial Intelligence",
    min_score=0.70
)
print(f"Found {result.records_count} AI transitions")

## Analyze high-confidence transitions across all tech areas

result = queries.award_to_cet_to_transition(min_score=0.85)
```

### Use Cases:

- Assess CET area effectiveness for driving commercialization
- Identify which technology areas show highest transition potential
- Support strategic investment decisions by tech area

---

### 4. Company → TransitionProfile

**Purpose:** Retrieve company-level transition success metrics and performance profiles.

**Method:** `company_to_transition_profile()`

### Parameters:

- `company_id` (Optional[str]): Specific company (None for top performers)
- `min_success_rate` (float): Minimum success rate (0-1), default 0.0
- `limit` (int): Maximum results to return, default 100

**Returns:** `PathwayResult` with:
- `company_id`: Unique company identifier
- `company_name`: Company name
- `profile_id`: Unique profile identifier
- `total_awards`: Count of SBIR awards received
- `total_transitions`: Count of detected transitions
- `success_rate`: Ratio of transitions to awards (0-1)
- `avg_score`: Average transition likelihood score
- `high_confidence`: Count of high-confidence transitions
- `likely_confidence`: Count of likely-confidence transitions
- `last_transition`: Most recent transition date
- `avg_time_to_transition_days`: Average days from award to transition

### Example:

```python

## Find all companies with 50%+ transition success rate

result = queries.company_to_transition_profile(min_success_rate=0.50)
print(f"Found {result.records_count} high-performing companies")

## Get details for specific company

result = queries.company_to_transition_profile(
    company_id="COMPANY-123",
    limit=1
)
profile = result.records[0]
print(f"{profile['company_name']}: {profile['success_rate']*100}% success rate")
```

### Use Cases:

- Identify high-performing SBIR companies
- Benchmark company transition success
- Analyze company investment portfolio quality

---

### 5. Transition Rates by CET Area

**Purpose:** Aggregate transition statistics across technology areas for strategic analysis.

**Method:** `transition_rates_by_cet_area()`

### Parameters:

- `limit` (int): Maximum CET areas to return, default 50

**Returns:** `PathwayResult` with:
- `cet_area`: Technology area ID
- `cet_name`: Technology area name
- `total_awards`: Awards in this technology area
- `transitions_detected`: Count of detected transitions
- `transition_rate`: Ratio of transitions to awards (0-1)
- `avg_transition_score`: Average transition score
- `high_confidence_count`: High-confidence transitions

### Example:

```python

## Get transition rates for all CET areas

result = queries.transition_rates_by_cet_area(limit=50)

## Display ranked by transition effectiveness

for record in sorted(result.records, key=lambda x: x['transition_rate'], reverse=True):
    print(f"{record['cet_name']}: {record['transition_rate']*100:.1f}% "
          f"({record['transitions_detected']}/{record['total_awards']})")
```

### Use Cases:

- Identify most productive technology areas
- Support agency decision-making on program focus
- Benchmark transition effectiveness by technology

---

### 6. Patent-Backed Transition Rates by CET Area

**Purpose:** Analyze the role of patents in enabling transitions for each technology area.

**Method:** `patent_backed_transition_rates_by_cet_area()`

### Parameters:

- `limit` (int): Maximum CET areas to return, default 50

**Returns:** `PathwayResult` with:
- `cet_area`: Technology area ID
- `cet_name`: Technology area name
- `total_awards`: Awards in this technology area
- `patent_backed_transitions`: Count of patent-backed transitions
- `patent_backed_rate`: Ratio of patent-backed transitions to awards (0-1)
- `avg_transition_score`: Average score of patent-backed transitions

### Example:

```python

## Identify CET areas where patents enable transitions

result = queries.patent_backed_transition_rates_by_cet_area()

## Compare patent-backed rate to overall transition rate

for cet_area in result.records:
    print(f"{cet_area['cet_name']}: "
          f"{cet_area['patent_backed_rate']*100:.1f}% of awards have patent-backed transitions")
```

### Use Cases:

- Assess patent importance by technology area
- Identify areas needing stronger IP strategies
- Measure commercialization support effectiveness

---

## Performance Considerations

### Query Optimization

1. **Indexes:** All pathway queries rely on indexes created during Neo4j graph loading:
   - `Transition.transition_id` (primary lookup)
   - `Transition.confidence` (filtering)
   - `Transition.likelihood_score` (ranking)
   - `TransitionProfile.company_id` (company lookups)
   - `TransitionProfile.success_rate` (ranking)

2. **Batch Processing:** Large result sets (>10K records) should be paginated:

   ```python
   # Process in pages
   for offset in range(0, total_records, 1000):
       result = queries.award_to_transition_to_contract(limit=1000)
       process_batch(result.records)
   ```

3. **Filtering Strategy:** Apply filters in this order for best performance:
   1. `min_score` (reduces candidate set early)
   2. `confidence_levels` (index-based filtering)
   3. `cet_area` (narrows graph traversal)

### Expected Performance

- Single award lookup: ~10-50ms
- All transitions (252K awards, ~70K transitions): ~500ms
- CET area aggregation (10 areas): ~1-2 seconds
- Company profile lookups: ~50-100ms each

---

## Integration Examples

### Dashboard Integration

```python

## Generate dashboard metrics

def get_dashboard_metrics():
    queries = TransitionPathwayQueries(driver)
    
    return {
        "cet_performance": queries.transition_rates_by_cet_area(limit=10).records,
        "top_companies": queries.top_companies_by_success_rate(limit=20).records,
        "confidence_distribution": queries.confidence_distribution_analysis().records,
        "patent_impact": queries.patent_backed_transition_rates_by_cet_area().records,
    }
```

### Award Lifecycle Tracking

```python

## Track individual award journey

def track_award_journey(award_id):
    queries = TransitionPathwayQueries(driver)
    
    # Basic transition
    basic = queries.award_to_transition_to_contract(award_id=award_id)
    
    # Patent-backed component
    patent_backed = queries.award_to_patent_to_transition_to_contract(award_id=award_id)
    
    # CET context
    cet_context = queries.award_to_cet_to_transition(cet_area=award.cet_area)
    
    return {
        "direct_transitions": basic.records,
        "patent_transitions": patent_backed.records,
        "tech_area_context": cet_context.records,
    }
```

### Company Performance Analysis

```python

## Analyze company success patterns

def analyze_company_performance(company_id):
    queries = TransitionPathwayQueries(driver)
    
    profile = queries.company_to_transition_profile(company_id=company_id).records[0]
    
    return {
        "profile": profile,
        "success_rate": profile["success_rate"],
        "avg_time_to_transition": profile["avg_time_to_transition_days"],
        "high_confidence_ratio": profile["high_confidence"] / profile["total_transitions"],
    }
```

---

## Related Documentation

- **Graph Model:** [`docs/schemas/transition-graph-schema.md`](../schemas/transition-graph-schema.md)
- **Detection Algorithm:** [`docs/transition/detection_algorithm.md`](../transition/detection_algorithm.md)
- **Scoring Guide:** [`docs/transition/scoring_guide.md`](../transition/scoring_guide.md)
- **Evidence Bundles:** [`docs/transition/evidence_bundles.md`](../transition/evidence_bundles.md)

---

## Troubleshooting

### Empty Results

**Symptom:** Query returns 0 records when data should exist.

### Solutions:

1. Verify Neo4j graph was loaded successfully via `neo4j-transition_loader` asset
2. Check that indexes were created: Run `SHOW INDEXES` in Neo4j Browser
3. Verify filter thresholds are not too strict (try `min_score=0.0`)
4. Confirm relationship names match exactly (case-sensitive)

### Slow Queries

**Symptom:** Queries take >5 seconds to complete.

### Solutions:

1. Add `min_score` filter to reduce candidate set
2. Reduce `limit` parameter for exploratory queries
3. Check Neo4j memory: `CALL dbms.memory.stats()`
4. Verify indexes exist and are used: Prepend `EXPLAIN` to Cypher query

### Connection Issues

**Symptom:** "Connection refused" or timeout errors.

### Solutions:

1. Verify Neo4j service is running: `docker ps | grep neo4j`
2. Check credentials in connection string
3. Ensure firewall allows 7687 (bolt) or 7474 (http)

---

## API Reference

### PathwayResult Dataclass

```python
@dataclass
class PathwayResult:
    pathway_name: str              # Query name (e.g., "Award → Transition → Contract")
    records_count: int             # Number of records returned
    records: List[Dict[str, Any]]  # Actual data records
    metadata: Dict[str, Any]       # Query parameters and context
```

### TransitionPathwayQueries Class

### Initialization:

```python
queries = TransitionPathwayQueries(driver: Driver)
```

### Available Methods:

- `award_to_transition_to_contract()` → PathwayResult
- `award_to_patent_to_transition_to_contract()` → PathwayResult
- `award_to_cet_to_transition()` → PathwayResult
- `company_to_transition_profile()` → PathwayResult
- `transition_rates_by_cet_area()` → PathwayResult
- `patent_backed_transition_rates_by_cet_area()` → PathwayResult
- `confidence_distribution_analysis()` → PathwayResult
- `top_companies_by_success_rate()` → PathwayResult

```text
</content>