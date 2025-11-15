# Transaction Endpoint Fix - Summary

## What We Fixed

We switched from the two-step approach (spending_by_award + individual award lookups) to using the **`/search/spending_by_transaction/`** endpoint directly, which should return PSC codes in a single query.

## Key Changes

### 1. Added Missing `sort` Parameter (CRITICAL)
**Before:**
```python
payload = {
    "filters": filters,
    "fields": fields,
    "page": page,
    "limit": page_size,
    # Missing: "sort" field!
}
```

**After:**
```python
payload = {
    "filters": filters,
    "fields": fields,
    "sort": "Transaction Amount",  # REQUIRED by API contract
    "order": "desc",
    "page": page,
    "limit": page_size,
}
```

**Why this matters:** Per the USAspending API documentation, the `sort` field is **required** for the transaction endpoint. Without it, the API returns 400 Bad Request.

### 2. Changed PSC Field Name
**Before:** `"Product or Service Code"` (used in spending_by_award)
**After:** `"PSC"` (correct field name for spending_by_transaction)

### 3. Requested PSC in Fields List
```python
fields = [
    "Award ID",
    "Recipient Name",
    "Transaction Amount",
    "Transaction Description",
    "Action Date",
    "PSC",  # ← The key field we need!
    "Recipient UEI",
    "Award Type",
    "internal_id",
]
```

### 4. Changed Response Processing
**Before:** Two-step process:
1. Get awards from spending_by_award (no PSC)
2. Loop through each award calling /awards/{id}/ (N+1 queries)

**After:** Single-step process:
1. Get transactions from spending_by_transaction (includes PSC)
2. Done!

## Performance Comparison

| Approach | API Calls | Time for 100 awards | PSC Coverage |
|----------|-----------|---------------------|--------------|
| **Two-step (old)** | 1 + N (101 total) | ~50+ seconds | Depends on /awards/ endpoint |
| **Transaction (new)** | ~1-3 (pagination) | ~2-5 seconds | Direct from endpoint |

## Expected Results

When you run the test with a company that has contracts:

```bash
python test_psc_retrieval.py
# Enter UEI: RMG1AZ1ZH8Q7
```

**You should see:**
- ✅ Transactions retrieved successfully
- ✅ PSC codes populated in the response
- ✅ PSC coverage: >80%
- ✅ Much faster than the two-step approach

## Transaction vs Award Data

**Important distinction:**
- **Transaction endpoint** returns individual transaction records (multiple per award)
  - More granular data
  - Includes PSC codes directly
  - May have duplicates (same award, different transactions)

- **Award endpoint** returns aggregated award-level data
  - One record per award
  - Doesn't include PSC codes in search results
  - Requires individual lookups for PSC

Our code **deduplicates** transactions by award_id, so you get unique awards with PSC codes.

## API Contract Reference

According to the [USAspending API documentation](https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/api_contracts/contracts/v2/search/spending_by_transaction.md):

### Required Fields
- `filters` (AdvancedFilterObject) with `award_type_codes`
- `fields` (array of field names)
- `sort` (string) ← **We were missing this!**

### Available Response Fields
Including but not limited to:
- `Award ID`, `PSC`, `Transaction Amount`, `Transaction Description`
- `Action Date`, `Recipient Name`, `Recipient UEI`, `Award Type`
- `NAICS`, `Awarding Agency`, `Funding Agency`

## Testing Instructions

### Option 1: Full Test with Dependencies
If you have the environment set up with dependencies:

```bash
# In your environment with pandas/httpx installed
python test_psc_retrieval.py
```

### Option 2: Standalone Test (No Dependencies)
```bash
# Uses only Python standard library
python test_transaction_endpoint.py RMG1AZ1ZH8Q7
```

### Option 3: Docker/Make
```bash
make docker-exec SERVICE=dagster-webserver CMD="python test_psc_retrieval.py"
```

## What to Look For

When testing, check the logs for:

1. **First transaction structure:**
   ```
   DEBUG | First transaction result keys: ['Award ID', 'PSC', 'Transaction Amount', ...]
   DEBUG | First transaction PSC value: R425
   ```

2. **PSC coverage:**
   ```
   INFO | PSC code coverage: 850/1000 (85.0%)
   ```

3. **Sample transactions with PSC:**
   ```
   Award: N0017306C2049
     PSC: R425
     Amount: $14,509,033
   ```

## Troubleshooting

### If you still see 0% PSC coverage:

1. **Check the response structure**
   - Look at the DEBUG logs for "First transaction result keys"
   - Verify "PSC" is in the keys list

2. **Check if PSC values are empty strings vs. None**
   - The code checks for both null and empty strings
   - Log line: "PSC field empty for transaction"

3. **Verify award types**
   - Only contract awards (A, B, C, D) have PSC codes
   - Grants don't have PSC codes

4. **Check API response directly**
   - Run the standalone test script
   - Inspect `/tmp/transaction_response.json`

### If you get 400 Bad Request:

This was the original error. With the `sort` field added, this should be fixed.

If it still occurs:
- Check that all required fields are present
- Verify the filters structure matches AdvancedFilterObject format
- Check API documentation for any changes

### If you get 403 Forbidden:

The USAspending API is public and doesn't require authentication. A 403 could indicate:
- IP-based rate limiting (unlikely with our 0.5s delays)
- Network/firewall restrictions
- API service issues

Try:
- Testing from a different network
- Checking https://api.usaspending.gov/ status
- Waiting a few minutes and retrying

## Files Modified

1. **`src/enrichers/company_categorization.py`**
   - `retrieve_company_contracts_api()` - Switched to transaction endpoint
   - Added proper `sort` parameter
   - Changed PSC field name to "PSC"
   - Removed two-step approach code

2. **`test_transaction_endpoint.py`** (new)
   - Standalone test without dependencies
   - Uses Python standard library only
   - Tests endpoint directly

3. **`test_psc_retrieval.py`** (existing)
   - Full test with pandas integration
   - Shows PSC coverage and samples

## Expected Outcome

With this fix:
- ✅ PSC codes should be retrieved successfully
- ✅ Much faster performance (~10-20x faster)
- ✅ No rate limiting concerns (fewer API calls)
- ✅ Simpler code (no two-step process)

The transaction endpoint approach is the **correct** way to retrieve contract data with PSC codes from the USAspending API.
