# Design Document

## Overview

The Company Categorization System classifies SBIR companies as Product, Service, or Mixed firms based on their complete federal contract portfolio from USAspending. The system implements a rule-based classification approach that operates at two levels: (1) individual contract classification using PSC codes, contract types, and description analysis, and (2) company-level aggregation based on dollar-weighted portfolio composition. The design leverages existing USAspending data infrastructure (DuckDB extractor, enrichment client) and integrates with the current Dagster asset pipeline.

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Company Categorization System                    │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                │                   │                   │
                ▼                   ▼                   ▼
        ┌───────────────┐   ┌──────────────┐   ┌──────────────┐
        │   Contract    │   │   Company    │   │   Output     │
        │  Classifier   │   │  Aggregator  │   │  Generator   │
        └───────────────┘   └──────────────┘   └──────────────┘
                │                   │                   │
                ▼                   ▼                   ▼
        ┌───────────────┐   ┌──────────────┐   ┌──────────────┐
        │ Award-level   │   │ Portfolio    │   │ Classification│
        │ Classification│   │ Aggregation  │   │ Metadata     │
        └───────────────┘   └──────────────┘   └──────────────┘
```

### Data Flow

```
SBIR Awards (validated_sbir_awards)
        │
        ▼
USAspending Contract Retrieval
        │
        ├─→ Query by UEI
        ├─→ Query by DUNS
        └─→ Query by CAGE
        │
        ▼
Contract Portfolio (per company)
        │
        ▼
Contract Classifier
        │
        ├─→ PSC-based rules
        ├─→ Contract type rules
        ├─→ Description inference
        └─→ SBIR phase adjustment
        │
        ▼
Classified Contracts
        │
        ▼
Company Aggregator
        │
        ├─→ Dollar-weighted percentages
        ├─→ Classification thresholds
        ├─→ Override rules
        └─→ Confidence scoring
        │
        ▼
Company Classifications
        │
        ▼
Output: enriched_sbir_companies_with_categorization
```

## Components and Interfaces

### 1. Contract Classifier

**Purpose**: Classify individual federal contracts as Product, Service, or R&D

**Input**:
- Contract record with fields: PSC, contract_type, pricing, description, sbir_phase

**Output**:
- Classification: "Product", "Service", or "R&D"
- Classification method: "psc_numeric", "psc_alphabetic", "contract_type", "description_inference", "sbir_adjustment"
- Confidence: 0.0-1.0

**Classification Logic**:

```python
def classify_contract(contract: dict) -> dict:
    """Classify a single contract.
    
    Returns:
        {
            "classification": "Product" | "Service" | "R&D",
            "method": str,
            "confidence": float
        }
    """
    psc = contract.get("psc", "")
    contract_type = contract.get("contract_type", "")
    pricing = contract.get("pricing", "")
    description = contract.get("description", "")
    sbir_phase = contract.get("sbir_phase", "")
    
    # Rule 1: Contract type overrides (highest priority)
    if contract_type in ["CPFF", "Cost-Type"] or pricing == "T&M":
        return {
            "classification": "Service",
            "method": "contract_type",
            "confidence": 0.95
        }
    
    # Rule 2: PSC-based classification
    if psc:
        if psc[0].isdigit():  # Numeric PSC
            classification = "Product"
            method = "psc_numeric"
        elif psc[0] in ["A", "B"]:  # R&D PSC
            classification = "R&D"
            method = "psc_rd"
        else:  # Alphabetic PSC
            classification = "Service"
            method = "psc_alphabetic"
        
        # Rule 3: Description inference (can override PSC for FFP contracts)
        if pricing == "FFP" and description:
            product_keywords = ["prototype", "hardware", "device"]
            if any(kw in description.lower() for kw in product_keywords):
                return {
                    "classification": "Product",
                    "method": "description_inference",
                    "confidence": 0.85
                }
        
        # Rule 4: SBIR phase adjustment
        if sbir_phase in ["I", "II"]:
            if classification == "Product":
                # Keep Product classification for numeric PSC
                return {
                    "classification": "Product",
                    "method": "sbir_numeric_psc",
                    "confidence": 0.90
                }
            else:
                # Override to R&D for Phase I/II
                return {
                    "classification": "R&D",
                    "method": "sbir_adjustment",
                    "confidence": 0.90
                }
        
        return {
            "classification": classification,
            "method": method,
            "confidence": 0.90
        }
    
    # Default: Service (low confidence)
    return {
        "classification": "Service",
        "method": "default",
        "confidence": 0.50
    }
```

### 2. Company Aggregator

**Purpose**: Aggregate contract classifications to company level

**Input**:
- List of classified contracts for a company
- Company identifier (UEI)

**Output**:
- Company classification: "Product-leaning", "Service-leaning", "Mixed", "Uncertain"
- Product percentage: 0.0-100.0
- Service percentage: 0.0-100.0
- Confidence level: "Low", "Medium", "High"
- Metadata: award_count, psc_family_count, override_reasons

**Aggregation Logic**:

```python
def aggregate_company_classification(contracts: list[dict], company_uei: str) -> dict:
    """Aggregate contract classifications to company level.
    
    Returns:
        {
            "company_uei": str,
            "classification": str,
            "product_pct": float,
            "service_pct": float,
            "confidence": str,
            "metadata": dict
        }
    """
    # Handle edge case: insufficient data
    if len(contracts) < 2:
        return {
            "company_uei": company_uei,
            "classification": "Uncertain",
            "product_pct": 0.0,
            "service_pct": 0.0,
            "confidence": "Low",
            "metadata": {
                "award_count": len(contracts),
                "override_reason": "insufficient_awards"
            }
        }
    
    # Calculate dollar-weighted percentages
    total_dollars = sum(c.get("award_amount", 0) for c in contracts)
    product_dollars = sum(
        c.get("award_amount", 0) 
        for c in contracts 
        if c.get("classification") == "Product"
    )
    service_rd_dollars = sum(
        c.get("award_amount", 0) 
        for c in contracts 
        if c.get("classification") in ["Service", "R&D"]
    )
    
    product_pct = (product_dollars / total_dollars * 100) if total_dollars > 0 else 0
    service_pct = (service_rd_dollars / total_dollars * 100) if total_dollars > 0 else 0
    
    # Count PSC families
    psc_families = set()
    for c in contracts:
        psc = c.get("psc", "")
        if psc:
            psc_families.add(psc[0])
    
    # Apply override rules
    override_reason = None
    
    # Override 1: Too many PSC families (integrator)
    if len(psc_families) > 6:
        classification = "Mixed"
        override_reason = "high_psc_diversity"
    # Standard classification
    elif product_pct >= 60:
        classification = "Product-leaning"
    elif service_pct >= 60:
        classification = "Service-leaning"
    else:
        classification = "Mixed"
    
    # Determine confidence level
    if len(contracts) <= 2:
        confidence = "Low"
    elif len(contracts) <= 5:
        confidence = "Medium"
    else:
        confidence = "High"
    
    return {
        "company_uei": company_uei,
        "classification": classification,
        "product_pct": round(product_pct, 2),
        "service_pct": round(service_pct, 2),
        "confidence": confidence,
        "metadata": {
            "award_count": len(contracts),
            "psc_family_count": len(psc_families),
            "total_dollars": total_dollars,
            "product_dollars": product_dollars,
            "service_rd_dollars": service_rd_dollars,
            "override_reason": override_reason
        }
    }
```

### 3. USAspending Contract Retriever

**Purpose**: Retrieve complete federal contract portfolio for SBIR companies

**Input**:
- Company identifiers: UEI, DUNS, CAGE
- Date range (optional)

**Output**:
- List of contracts with required fields

**Integration Points**:
- Uses existing `DuckDBUSAspendingExtractor` from `src/extractors/usaspending.py`
- Queries `transaction_normalized` table from USAspending dump
- Filters by recipient identifiers

**Query Pattern**:

```python
def retrieve_company_contracts(
    extractor: DuckDBUSAspendingExtractor,
    uei: str | None = None,
    duns: str | None = None,
    cage: str | None = None
) -> pd.DataFrame:
    """Retrieve all contracts for a company from USAspending.
    
    Returns DataFrame with columns:
    - award_id
    - psc (product_or_service_code)
    - contract_type (type_of_contract_pricing)
    - pricing (type_of_contract_pricing)
    - description (award_description)
    - award_amount (federal_action_obligation)
    - sbir_phase (extracted from description or award metadata)
    """
    conn = extractor.connect()
    
    # Build WHERE clause based on available identifiers
    where_clauses = []
    if uei:
        where_clauses.append(f"recipient_uei = '{uei}'")
    if duns:
        where_clauses.append(f"recipient_duns = '{duns}'")
    if cage:
        where_clauses.append(f"cage_code = '{cage}'")
    
    if not where_clauses:
        return pd.DataFrame()
    
    where_clause = " OR ".join(where_clauses)
    
    query = f"""
    SELECT 
        award_id,
        product_or_service_code as psc,
        type_of_contract_pricing as contract_type,
        type_of_contract_pricing as pricing,
        award_description as description,
        federal_action_obligation as award_amount,
        recipient_uei,
        recipient_duns,
        cage_code
    FROM usaspending_awards
    WHERE {where_clause}
    """
    
    return conn.execute(query).fetchdf()
```

## Data Models

### ContractClassification

```python
from pydantic import BaseModel, Field

class ContractClassification(BaseModel):
    """Classification result for a single contract."""
    
    award_id: str = Field(..., description="Contract/award identifier")
    classification: str = Field(..., description="Product, Service, or R&D")
    method: str = Field(..., description="Classification method used")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Classification confidence")
    
    # Original contract data
    psc: str | None = Field(None, description="Product Service Code")
    contract_type: str | None = Field(None, description="Contract type")
    pricing: str | None = Field(None, description="Pricing type")
    description: str | None = Field(None, description="Award description")
    award_amount: float | None = Field(None, description="Award amount in USD")
    sbir_phase: str | None = Field(None, description="SBIR phase if applicable")
```

### CompanyClassification

```python
class CompanyClassification(BaseModel):
    """Classification result for a company."""
    
    company_uei: str = Field(..., description="Company UEI")
    company_name: str = Field(..., description="Company name")
    classification: str = Field(..., description="Product-leaning, Service-leaning, Mixed, or Uncertain")
    product_pct: float = Field(..., ge=0.0, le=100.0, description="Percentage of dollars from product contracts")
    service_pct: float = Field(..., ge=0.0, le=100.0, description="Percentage of dollars from service/R&D contracts")
    confidence: str = Field(..., description="Low, Medium, or High")
    
    # Metadata
    award_count: int = Field(..., description="Total number of contracts")
    psc_family_count: int = Field(..., description="Number of distinct PSC families")
    total_dollars: float = Field(..., description="Total contract dollars")
    product_dollars: float = Field(..., description="Product contract dollars")
    service_rd_dollars: float = Field(..., description="Service/R&D contract dollars")
    override_reason: str | None = Field(None, description="Reason for override if applied")
    
    # Contract details (for audit trail)
    contracts: list[ContractClassification] = Field(default_factory=list, description="Individual contract classifications")
```

## Error Handling

### Error Scenarios

1. **No USAspending contracts found**
   - Classification: "Uncertain"
   - Confidence: "Low"
   - Metadata: `{"error": "no_contracts_found"}`

2. **Insufficient contracts (<2)**
   - Classification: "Uncertain"
   - Confidence: "Low"
   - Metadata: `{"override_reason": "insufficient_awards"}`

3. **Missing required fields**
   - Skip contract in classification
   - Log warning with contract ID
   - Continue with remaining contracts

4. **USAspending query failure**
   - Retry with exponential backoff (3 attempts)
   - If all retries fail, mark company as "Uncertain"
   - Log error with company identifier

### Logging Strategy

```python
# Contract-level logging
logger.debug(f"Classified contract {award_id}: {classification} via {method}")

# Company-level logging
logger.info(f"Classified company {uei}: {classification} ({confidence} confidence)")

# Error logging
logger.warning(f"No contracts found for company {uei}")
logger.error(f"USAspending query failed for company {uei}: {error}")
```

## Testing Strategy

### Unit Tests

1. **Contract Classifier Tests**
   - Test PSC numeric → Product
   - Test PSC alphabetic → Service
   - Test PSC A/B → R&D
   - Test contract type overrides (CPFF, T&M → Service)
   - Test description inference (prototype, hardware, device → Product)
   - Test SBIR phase adjustment (Phase I/II → R&D unless numeric PSC)
   - Test FFP with PSC retention

2. **Company Aggregator Tests**
   - Test 60% threshold for Product-leaning
   - Test 60% threshold for Service-leaning
   - Test Mixed classification
   - Test Uncertain for <2 contracts
   - Test PSC family override (>6 families → Mixed)
   - Test confidence levels (Low/Medium/High)

3. **USAspending Retriever Tests**
   - Test UEI query
   - Test DUNS query
   - Test CAGE query
   - Test combined identifier query
   - Test empty result handling

### Integration Tests

1. **End-to-End Classification**
   - Load sample SBIR companies
   - Retrieve USAspending contracts
   - Classify contracts
   - Aggregate to company level
   - Verify output format and completeness

2. **DuckDB Integration**
   - Test with real USAspending dump
   - Verify query performance
   - Test with large result sets

### Test Data

```python
# Sample contracts for testing
TEST_CONTRACTS = [
    {
        "award_id": "TEST001",
        "psc": "1234",  # Numeric → Product
        "contract_type": "FFP",
        "pricing": "FFP",
        "description": "Hardware development",
        "award_amount": 100000,
        "sbir_phase": None
    },
    {
        "award_id": "TEST002",
        "psc": "R425",  # Alphabetic → Service
        "contract_type": "CPFF",
        "pricing": "CPFF",
        "description": "Research services",
        "award_amount": 150000,
        "sbir_phase": None
    },
    {
        "award_id": "TEST003",
        "psc": "A123",  # A/B → R&D
        "contract_type": "FFP",
        "pricing": "FFP",
        "description": "Basic research",
        "award_amount": 200000,
        "sbir_phase": "I"
    }
]

# Expected company classification
EXPECTED_CLASSIFICATION = {
    "classification": "Service-leaning",  # (150k + 200k) / 450k = 77.8%
    "product_pct": 22.22,
    "service_pct": 77.78,
    "confidence": "Medium",  # 3 contracts
    "award_count": 3
}
```

## Performance Considerations

### Query Optimization

1. **Batch Processing**
   - Process companies in batches of 100
   - Use parallel queries where possible
   - Cache USAspending connection

2. **Index Usage**
   - Ensure DuckDB indexes on recipient_uei, recipient_duns, cage_code
   - Use EXPLAIN to verify query plans

3. **Memory Management**
   - Stream large result sets
   - Process contracts in chunks
   - Clear intermediate DataFrames

### Scalability

- **Expected volume**: ~50,000 SBIR companies
- **Average contracts per company**: 10-50
- **Total contracts to classify**: ~500,000-2,500,000
- **Processing time estimate**: 2-4 hours for full dataset

### Monitoring

```python
# Track processing metrics
metrics = {
    "companies_processed": 0,
    "contracts_classified": 0,
    "classification_distribution": {
        "Product-leaning": 0,
        "Service-leaning": 0,
        "Mixed": 0,
        "Uncertain": 0
    },
    "avg_contracts_per_company": 0.0,
    "processing_time_seconds": 0.0
}
```

## Configuration

### Configuration Schema

```yaml
company_categorization:
  # Classification thresholds
  thresholds:
    product_leaning_pct: 60.0
    service_leaning_pct: 60.0
    psc_family_diversity_threshold: 6
    
  # Confidence levels
  confidence:
    low_max_awards: 2
    medium_max_awards: 5
    
  # Processing
  batch_size: 100
  parallel_workers: 4
  
  # USAspending query
  usaspending:
    table_name: "usaspending_awards"
    timeout_seconds: 30
    retry_attempts: 3
    
  # Output
  output:
    include_contract_details: true
    include_metadata: true
```

## Dagster Asset Integration

### Asset Definition

```python
@asset(
    name="enriched_sbir_companies_with_categorization",
    group_name="company_categorization",
    deps=[validated_sbir_awards],
    description="SBIR companies enriched with Product/Service/Mixed categorization"
)
def enriched_sbir_companies_with_categorization(
    context: AssetExecutionContext,
    validated_sbir_awards: pd.DataFrame
) -> pd.DataFrame:
    """Categorize SBIR companies based on USAspending contract portfolio."""
    
    config = get_config()
    extractor = DuckDBUSAspendingExtractor(config.duckdb.database_path)
    
    # Get unique companies
    companies = validated_sbir_awards[["company_uei", "company_name"]].drop_duplicates()
    
    results = []
    for _, company in companies.iterrows():
        # Retrieve contracts
        contracts = retrieve_company_contracts(
            extractor,
            uei=company["company_uei"]
        )
        
        # Classify contracts
        classified_contracts = [
            classify_contract(contract.to_dict())
            for _, contract in contracts.iterrows()
        ]
        
        # Aggregate to company level
        company_classification = aggregate_company_classification(
            classified_contracts,
            company["company_uei"]
        )
        
        results.append(company_classification)
    
    return pd.DataFrame(results)
```

### Asset Check

```python
@asset_check(asset=enriched_sbir_companies_with_categorization)
def company_categorization_completeness_check(
    enriched_sbir_companies_with_categorization: pd.DataFrame
) -> AssetCheckResult:
    """Verify categorization completeness and quality."""
    
    total = len(enriched_sbir_companies_with_categorization)
    uncertain = (
        enriched_sbir_companies_with_categorization["classification"] == "Uncertain"
    ).sum()
    
    uncertain_pct = (uncertain / total * 100) if total > 0 else 0
    
    # Target: <20% uncertain classifications
    passed = uncertain_pct < 20.0
    
    return AssetCheckResult(
        passed=passed,
        metadata={
            "total_companies": total,
            "uncertain_count": uncertain,
            "uncertain_pct": round(uncertain_pct, 2),
            "classification_distribution": enriched_sbir_companies_with_categorization[
                "classification"
            ].value_counts().to_dict()
        }
    )
```

## Related Documents

- Requirements: `.kiro/specs/company-categorization/requirements.md`
- USAspending Extractor: `src/extractors/usaspending.py`
- Award Model: `src/models/award.py`
- Company Model: `src/models/company.py`
- Enrichment Patterns: `.kiro/steering/enrichment-patterns.md`
- Pipeline Orchestration: `.kiro/steering/pipeline-orchestration.md`
