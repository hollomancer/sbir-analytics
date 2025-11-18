# PSC Code Retrieval Fix - Summary

## Problem
PSC (Product or Service Code) codes were not being retrieved from the USAspending API, preventing proper classification of contracts as Product/Service/R&D.

## Root Cause
**Incorrect API response parsing**: The code was looking for PSC codes in the wrong location within the awards endpoint response structure.

According to USAspending API documentation, for **contract awards** (types A, B, C, D), the PSC code is located in:
```
latest_transaction_contract_data → product_or_service_code
```

The code was checking top-level fields and other nested locations, but missing the correct path.

## Solution

### Two-Step Retrieval Approach
1. **Step 1**: Use `/search/spending_by_award/` to get list of company awards
   - Efficient pagination for bulk retrieval
   - Uses `recipient_search_text` filter (searches UEI/DUNS)
   - Returns `internal_id` field needed for Step 2

2. **Step 2**: For each award, query `/awards/{internal_id}/` to get PSC code
   - Now correctly extracts from `latest_transaction_contract_data.product_or_service_code`
   - Rate limited (0.5s delays, 120 req/min)
   - Configurable limit (default: 100 awards)

### Code Changes

**File**: `src/enrichers/company_categorization.py`

**Key fixes**:
1. Prioritize `internal_id` over `Award ID` when extracting award identifiers (line 284-288)
2. Extract PSC from correct location: `latest_transaction_contract_data.product_or_service_code` (line 427-429)
3. Added comprehensive debug logging to track response structure
4. Enhanced fallback logic to check multiple possible PSC locations

```python
# Primary location for contract awards
latest_contract = award_data.get("latest_transaction_contract_data", {})
if isinstance(latest_contract, dict):
    psc = latest_contract.get("product_or_service_code")
```

## Testing

### Quick Test
```bash
# Run the test script with a known UEI
python test_psc_retrieval.py
# Enter UEI: RMG1AZ1ZH8Q7 (or any SBIR company UEI)
```

### Full Validation
```bash
# Test with validation dataset (10 companies)
python test_categorization_validation.py --use-api --limit 10 --detailed
```

### Expected Results
- PSC codes should now be successfully retrieved for contract awards
- Coverage should be >80% for companies with federal contracts
- Classification (Product/Service/R&D) should work correctly

## API Endpoints Used

### `/search/spending_by_award/` (Step 1)
- **Purpose**: Get list of awards for a company
- **Method**: POST
- **Filters**: `recipient_search_text` (array), `award_type_codes` (A, B, C, D)
- **Returns**: Award metadata including `internal_id`

### `/awards/{internal_id}/` (Step 2)
- **Purpose**: Get detailed award information including PSC
- **Method**: GET
- **URL Format**: `https://api.usaspending.gov/api/v2/awards/CONT_IDV_{PIID}_{AGENCY}/`
- **Returns**: Full award details with `latest_transaction_contract_data.product_or_service_code`

## Configuration

The `retrieve_company_contracts_api()` function accepts these parameters:

```python
def retrieve_company_contracts_api(
    uei: str | None = None,
    duns: str | None = None,
    page_size: int = 100,
) -> pd.DataFrame:
```

- PSC codes are now fetched directly from the transaction endpoint whenever possible.
  A small built-in fallback limit fetches detailed award data when PSC values are
  missing, so no explicit tuning is required.

> Note: The fallback currently caps additional award-detail lookups at ~50 per call,
> keeping PSC coverage high without hammering the API.

## Performance

- **Step 1** (Award Search): ~1-2 seconds for typical company (depends on pagination)
- **Step 2** (PSC Retrieval): ~0.5s per award × N awards
  - 10 awards: ~5 seconds
  - 100 awards: ~50 seconds
  - 1000 awards: ~500 seconds (8+ minutes)

**Recommendation**: Monitor PSC coverage logs; the fallback will automatically
inspect detailed award records for a small subset of missing PSCs, keeping both accuracy
and performance balanced without manual tuning.

## Related Files

- **`src/enrichers/company_categorization.py`** - Main retrieval logic
- **`test_psc_retrieval.py`** - Quick test script
- **`test_categorization_validation.py`** - Full validation with classification
- **`debug_api_response.py`** - Debug script to inspect API responses

## References

- USAspending API Docs: https://api.usaspending.gov/docs/endpoints
- GitHub API Contracts: https://github.com/fedspendingtransparency/usaspending-api
- Awards Endpoint Contract: https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/api_contracts/contracts/v2/awards/award_id.md

## Troubleshooting

### If PSC codes are still missing:

1. **Check award types**: Only contract awards (A, B, C, D) have PSC codes
   - Grants and other award types don't have PSC codes
   - Filter in Step 1 ensures only contracts are retrieved

2. **Verify award ID format**: Should be `internal_id` like `CONT_IDV_...`
   - Check debug logs for "First award ID fields"
   - Ensure we're using `internal_id` not just `Award ID`

3. **Inspect API response**: Run debug script to see actual structure
   ```bash
   python debug_api_response.py
   ```

4. **Check API rate limits**: 120 requests/minute
   - Code has built-in 0.5s delays
   - If hitting limits, response will be 429 status

5. **Enable verbose logging**:
   ```bash
   python test_psc_retrieval.py  # Already has DEBUG enabled
   ```

## Next Steps

1. Test the fix with your validation dataset
2. Verify PSC code coverage is acceptable
3. Monitor PSC fallback logs (built-in lookup limit) to ensure coverage meets expectations
4. Run full categorization pipeline with API mode
5. Compare results with DuckDB mode for consistency
