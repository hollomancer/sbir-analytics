# ADR-001: Allow Negative Obligation Amounts in Federal Contracts

## Status

Accepted (2025-10-28)

## Context

During implementation of federal contracts ingestion (Task 5), we discovered that the USAspending transaction_normalized table contains contract records with negative obligation amounts. These represent **deobligations** - contract modifications that reduce the obligated amount.

### Analysis

From USAspending subset database (first 1M transaction records):

- **Frequency**: ~0.03% of all contract transactions (126 out of ~460,535)
- **Magnitude**: Range from -$1 to -$409,143
- **Action Types**: Appear in "New", "Continuation", and null action types
- **Modification Numbers**: Often associated with modification numbers (e.g., 0501, 0503, 1801)

### Business Meaning

Negative obligations in USAspending represent:

1. **Contract Deobligations**: Reducing previously obligated funds
2. **Contract Modifications**: Downward adjustments to contract value
3. **Funds Recapture**: Returning unused obligated amounts

**Key Insight**: A deobligation still indicates an **active contract relationship** between the vendor and agency. It's evidence of ongoing contract management, not absence of a contract.

## Decision

We will **allow negative values** in the `obligation_amount` field and add an `is_deobligation` flag to track them.

### Implementation

```python
class FederalContract(BaseModel):
    obligation_amount: Optional[float] = Field(
        None, 
        description="Contract obligation/award amount. Can be negative for deobligations."
    )
    is_deobligation: bool = Field(
        default=False,
        description="True if obligation_amount is negative (contract reduction/modification)."
    )
```

## Alternatives Considered

### Option 1: Store as Absolute Values

Convert negative to positive, losing sign information.

- **Rejected**: Loses financial accuracy needed for proper accounting

### Option 2: Store Negative Values (SELECTED)

Allow negative values, add deobligation flag.

- **Selected**: Preserves accurate financial data while flagging for special handling

### Option 3: Filter Out Negatives

Skip negative obligation records entirely.

- **Rejected**: Loses evidence of vendor-agency contract relationships

### Option 4: Store Zero for Negatives

Treat deobligations as zero-value contracts.

- **Rejected**: Distorts financial data without clear benefit

### Option 5: Separate Deobligation Records

Complex schema with base + adjustment amounts.

- **Rejected**: Too complex for current needs, can implement later if needed

## Consequences

### Positive

- **Accurate financial representation**: Can calculate true net contract values
- **Complete audit trail**: All transaction types preserved
- **Flexible analysis**: Can include/exclude deobligations as needed
- **Correct vendor relationships**: Deobligations still show active contracts

### Negative

- **Downstream handling**: Must check `is_deobligation` in analysis code
- **Aggregation complexity**: Need to decide if/when to include negatives
- **User confusion**: May need documentation about negative values

### Neutral

- **Transition detection**: Both approaches work; deobligations are ~0.03% of data
- **Storage impact**: Minimal - flag adds 1 byte per record

## Implementation Notes

### In ContractExtractor

```python
obligation_amount = float(obligation_str) if obligation_str else 0.0
is_deobligation = (obligation_amount < 0)
```

### In Analysis Code

```python

## Example: Calculate net contract value

net_value = sum(c.obligation_amount for c in contracts)

## Example: Count only positive obligations

positive_count = sum(1 for c in contracts if not c.is_deobligation)

## Example: Get contract activity regardless of direction

all_activity = [c for c in contracts]  # Includes deobligations
```

## References

- USAspending Data Dictionary: https://files.usaspending.gov/docs/Data_Dictionary_Crosswalk.xlsx
- Discussion: Task 5 - Federal Contracts Ingestion
- Files Modified:
  - `src/models/transition_models.py` (FederalContract model)
  - `src/extractors/contract_extractor.py` (extraction logic)

## Related ADRs

None (first ADR)

## Notes

This decision aligns with **Option 2** from the negative obligations analysis. If future requirements demand more sophisticated handling (e.g., linking modifications to base contracts), we can migrate to **Option 5** without losing data.

The key principle: **Preserve data accuracy and let analysis code decide how to handle special cases.**
