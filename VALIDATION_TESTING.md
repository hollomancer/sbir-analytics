# Validation Testing Guide - 200 Sample Companies

Quick guide for testing the company categorization system against the high-volume SBIR companies validation dataset.

## Dataset

**Location:** `data/raw/sbir/over-100-awards-company_search_1763075384.csv`

**Description:** 200+ companies with >100 SBIR awards each (high-volume contractors)

**Columns:**
- `UEI`: Company UEI
- `Company Name`: Company name
- `SBIR Awards`: Number of SBIR awards received
- Additional metadata

---

## Quick Start Testing

### 1. Test First 10 Companies (Fastest - ~2 minutes)

```bash
poetry run python test_categorization_validation.py --limit 10
```

**Expected Output:**
```
Loading validation dataset from: data/raw/sbir/over-100-awards-company_search_1763075384.csv
Loaded 200+ companies from validation dataset
Processing first 10 companies

[1/10] Processing: Acme Technologies (UEI: ABC123, SBIR Awards: 150)
  Retrieved 45 USAspending contracts
  Contract breakdown: 30 Product, 10 Service, 5 R&D
  Result: Product-leaning (66.7% Product, 33.3% Service) - High confidence

...

================================================================================
CATEGORIZATION SUMMARY
================================================================================

Total companies processed: 10
Companies with contracts: 8
Companies without contracts: 2

Classification Distribution:
  Product-leaning: 5 (50.0%)
  Service-leaning: 2 (20.0%)
  Mixed: 1 (10.0%)
  Uncertain: 2 (20.0%)
...
```

### 2. Test Specific Company by UEI

```bash
poetry run python test_categorization_validation.py --uei ABC123DEF456
```

Shows detailed analysis for a single company.

### 3. Test All Companies + Export Results

```bash
poetry run python test_categorization_validation.py --output validation_results.csv
```

Processes all 200+ companies and exports to CSV (~20-30 minutes).

### 4. Test and Load to Neo4j

```bash
poetry run python test_categorization_validation.py --limit 20 --load-neo4j
```

Tests 20 companies and loads results to Neo4j.

---

## Step-by-Step Testing Process

### Step 1: Verify Prerequisites

```bash
# 1. Check validation dataset exists
ls -lh data/raw/sbir/over-100-awards-company_search_1763075384.csv

# 2. Check DuckDB database exists (with USAspending data)
ls -lh data/processed/sbir.duckdb

# 3. Verify dependencies installed
poetry install
```

**If validation dataset is missing:**
The dataset should be at `data/raw/sbir/over-100-awards-company_search_1763075384.csv` per the spec.

**If USAspending data is missing:**
You'll need to load USAspending database dump first. See main README for instructions.

### Step 2: Run Initial Test (10 companies)

```bash
poetry run python test_categorization_validation.py --limit 10 --verbose
```

This will:
- ✓ Load validation dataset
- ✓ Process first 10 companies
- ✓ Retrieve USAspending contracts for each
- ✓ Classify contracts (Product/Service/R&D)
- ✓ Aggregate to company level
- ✓ Print detailed summary

**Review the output** to verify:
- Contract retrieval is working
- Classifications look reasonable
- Confidence levels are appropriate

### Step 3: Spot-Check Results

Look for companies you know and verify classifications make sense:

```bash
# Example: Check a specific aerospace company
poetry run python test_categorization_validation.py --uei <KNOWN_UEI>
```

**Manual validation checklist:**
- [ ] Product companies have high % numeric PSCs (1000-9999)
- [ ] Service companies have high % alphabetic PSCs (R, S, etc.)
- [ ] Mixed companies have diverse PSC families (>6)
- [ ] Confidence levels match award counts (Low <=2, Medium 2-5, High >5)

### Step 4: Run Full Validation

```bash
poetry run python test_categorization_validation.py --output full_validation.csv
```

**This will take 20-30 minutes** depending on database size and network.

### Step 5: Analyze Results

```bash
# Open CSV in Excel/LibreOffice or analyze with pandas
poetry run python
```

```python
>>> import pandas as pd
>>> results = pd.read_csv("full_validation.csv")

>>> # Classification distribution
>>> results['classification'].value_counts()
Product-leaning    85
Service-leaning    65
Mixed             35
Uncertain         15

>>> # Average metrics by classification
>>> results.groupby('classification')[['product_pct', 'service_pct', 'award_count']].mean()

>>> # High-confidence classifications
>>> high_conf = results[results['confidence'] == 'High']
>>> len(high_conf)
120

>>> # Companies with insufficient data
>>> uncertain = results[results['classification'] == 'Uncertain']
>>> uncertain[['company_name', 'award_count', 'override_reason']]
```

### Step 6: Load to Neo4j (Optional)

```bash
# Test with small batch first
poetry run python test_categorization_validation.py --limit 20 --load-neo4j

# If successful, load all
poetry run python test_categorization_validation.py --load-neo4j --output full_results.csv
```

Then query Neo4j:

```cypher
// Verify companies were updated
MATCH (c:Company)
WHERE c.classification IS NOT NULL
RETURN count(c) as categorized_companies;

// Check classification distribution
MATCH (c:Company)
WHERE c.classification IS NOT NULL
RETURN c.classification, count(c) as count
ORDER BY count DESC;

// Find high-value product companies
MATCH (c:Company)
WHERE c.classification = "Product-leaning"
  AND c.categorization_total_dollars > 1000000
RETURN c.name, c.product_pct, c.categorization_total_dollars
ORDER BY c.categorization_total_dollars DESC
LIMIT 10;
```

---

## Interpreting Results

### Expected Distribution

For the high-volume SBIR company dataset (>100 awards each), expect:

**Classification:**
- ~40-50% Product-leaning (companies selling physical products/systems)
- ~30-40% Service-leaning (consulting, R&D services, studies)
- ~10-20% Mixed (integrators, diverse portfolios)
- ~5-10% Uncertain (insufficient USAspending data)

**Confidence:**
- ~60-70% High confidence (>5 USAspending contracts)
- ~20-30% Medium confidence (2-5 contracts)
- ~10% Low confidence (<=2 contracts)

### Red Flags to Investigate

❌ **High Uncertain rate (>20%)**:
- Check USAspending database is loaded correctly
- Verify UEI matching is working

❌ **Low confidence rate too high (>25%)**:
- These are high-volume SBIR companies, most should have many USAspending contracts
- Check database query logic

❌ **All companies same classification**:
- Logic error in classifier
- Check PSC code handling

✓ **Good signs:**
- Mix of all classifications
- Confidence correlates with award count
- Results match manual spot-checks

---

## Sample Companies to Spot-Check

Here are some well-known SBIR companies you can use for manual validation:

**Aerospace/Defense (expect Product-leaning):**
- Physical Systems Inc.
- Orbital ATK
- Ball Aerospace

**R&D Services (expect Service-leaning):**
- Booz Allen Hamilton
- MITRE Corporation
- Leidos

**Mixed:**
- General Dynamics
- Raytheon
- Lockheed Martin (might be Product or Mixed)

Find their UEIs in the dataset and test:

```bash
poetry run python test_categorization_validation.py --uei <THEIR_UEI>
```

---

## Troubleshooting

### "Validation dataset not found"

```bash
# Check file exists
ls data/raw/sbir/over-100-awards-company_search_1763075384.csv

# If missing, check alternative locations
find data -name "*over-100-awards*"
```

### "No USAspending contracts found" for all companies

**Cause:** USAspending database not loaded or table name mismatch

**Fix:**
```bash
# Check config
poetry run python -c "from src.config.loader import get_config; print(get_config().extraction.usaspending)"

# Verify table exists in DuckDB
poetry run python -c "
import duckdb
conn = duckdb.connect('data/processed/sbir.duckdb')
print(conn.execute('SHOW TABLES').fetchall())
conn.close()
"
```

### Script crashes with memory error

**Fix:** Use smaller batches or increase system memory

```bash
# Process in chunks of 50
for i in 0 50 100 150; do
    poetry run python test_categorization_validation.py \
        --limit 50 \
        --output results_chunk_$i.csv
done

# Combine results
poetry run python -c "
import pandas as pd
import glob
chunks = [pd.read_csv(f) for f in sorted(glob.glob('results_chunk_*.csv'))]
pd.concat(chunks).to_csv('full_results.csv', index=False)
"
```

---

## Next Steps After Validation

1. **Review Classification Distribution**
   - Does it match expectations for SBIR contractors?
   - Are confidence levels appropriate?

2. **Manual Spot-Checks**
   - Pick 10-20 companies you know
   - Verify classifications match their actual business

3. **Adjust Thresholds (if needed)**
   - Edit `config/base.yaml`:
     ```yaml
     company_categorization:
       product_leaning_pct: 60.0  # Adjust threshold
       psc_family_diversity_threshold: 6  # Adjust diversity limit
     ```

4. **Run Full Pipeline in Dagster**
   ```bash
   poetry run dagster dev
   # Materialize: enriched_sbir_companies_with_categorization
   # Review asset checks
   ```

5. **Load to Neo4j for Analysis**
   ```bash
   # After validation looks good
   poetry run python test_categorization_validation.py --load-neo4j
   ```

---

## Success Criteria

✅ **Validation passes if:**
- Classification distribution is reasonable (not all one type)
- Confidence levels correlate with award counts
- Spot-checks match known company types
- <20% Uncertain rate
- >50% High confidence rate
- Neo4j load success rate >95%

Once validation passes, the system is ready for production use!
