# Vendor Matching & Resolution Guide

## Overview

Vendor matching is the process of identifying which federal contracts were awarded to the same companies that received SBIR awards. This is a critical first step in transition detection, as it determines the candidate contracts to analyze.

**Goal**: Map each SBIR award recipient to their corresponding federal contract vendor(s) with high confidence.

**Challenge**: Companies have multiple identifiers across systems (UEI, CAGE code, DUNS number, legal name variations), and not all identifiers are present in all records.

**Solution**: Multi-method resolution strategy that prioritizes high-confidence identifier matches and falls back to fuzzy name matching when needed.

## Matching Methods

### Method 1: UEI (Unique Entity Identifier) - Primary

**Confidence**: 0.99 (highest)

**What is it**: 12-character alphanumeric code that uniquely identifies entities in federal systems.

**Adoption**: Required for federal awards and contracts since 2021 via SAM.gov transition.

**Matching**: Exact string comparison (case-insensitive).

**Data Fields**:
- SBIR: Award recipient UEI (typically in `recipient_uei` or similar field)
- Contract: Contractor UEI (typically in `vendor_uei` or `contractor_uei` field)

**Example**:
```
SBIR Award Recipient UEI: ABC123DEF456
Federal Contract Vendor UEI: ABC123DEF456
→ MATCH (confidence: 0.99)
```

**Advantages**:
- Standard federal identifier
- Guaranteed unique (no duplicates within same entity)
- Available in modern data (2021+)
- Deterministic matching (no ambiguity)

**Disadvantages**:
- Legacy data (pre-2021) may lack UEI
- Some fields may have incomplete/corrupted UEI values
- Company transitions/acquisitions may change UEI

**Coverage**:
- **SBIR Data**: ~99% of Phase II awards have valid UEI
- **Federal Contracts**: ~90% of recent contracts have valid UEI

**When to Use**: Primary method; always check UEI first.

**Implementation**:
```python
def resolve_by_uei(sbir_recipient_uei: str, contract_uei: str) -> bool:
    """Check if UEIs match exactly."""
    if not sbir_recipient_uei or not contract_uei:
        return False
    return sbir_recipient_uei.upper().strip() == contract_uei.upper().strip()
```

---

### Method 2: CAGE Code (Commercial and Government Entity) - Defense-Specific

**Confidence**: 0.95 (very high)

**What is it**: 5-character code assigned by the Defense Logistics Information Service (DLIS) for entities doing business with DoD.

**Adoption**: Primarily DoD and defense-related procurement; not used by civilian agencies.

**Matching**: Exact string comparison.

**Data Fields**:
- SBIR: Recipient CAGE code (may be in `cage_code` or `defense_identifier` field)
- Contract: Contractor CAGE code (typically in `contractor_cage` field)

**Example**:
```
SBIR Award Recipient CAGE: 1A2B3
Federal Contract Vendor CAGE: 1A2B3
→ MATCH (confidence: 0.95)
```

**Advantages**:
- High confidence for defense contracts
- Relatively stable over time
- Available for most defense-focused companies

**Disadvantages**:
- Only applicable to DoD contracts (~30% of federal contracts)
- Not used by civilian agencies (NSF, NIH, NOAA, etc.)
- May not be present for commercial companies
- Less standardized than UEI

**Coverage**:
- **SBIR DoD Data**: ~60% have valid CAGE code
- **Federal DoD Contracts**: ~80% have valid CAGE code
- **Civilian Data**: ~5% have CAGE codes

**When to Use**: Secondary method for DoD contracts when UEI not available.

**Implementation**:
```python
def resolve_by_cage(sbir_cage: str, contract_cage: str) -> bool:
    """Check if CAGE codes match exactly."""
    if not sbir_cage or not contract_cage:
        return False
    return sbir_cage.upper().strip() == contract_cage.upper().strip()
```

---

### Method 3: DUNS Number (Data Universal Numbering System) - Legacy

**Confidence**: 0.90 (good, but declining)

**What is it**: 9-digit code issued by Dun & Bradstreet to identify businesses.

**Adoption**: Legacy federal system; being phased out in favor of UEI. Still in older contracts and SBIR data.

**Matching**: Exact string comparison (9 digits).

**Data Fields**:
- SBIR: Recipient DUNS number (may be in `duns_number` or `recipient_duns` field)
- Contract: Contractor DUNS (typically in `vendor_duns` field)

**Example**:
```
SBIR Award Recipient DUNS: 123456789
Federal Contract Vendor DUNS: 123456789
→ MATCH (confidence: 0.90)
```

**Advantages**:
- Widely available in legacy data (pre-2021)
- Publicly searchable via Dun & Bradstreet
- Covers all sectors

**Disadvantages**:
- Declining usage (being replaced by UEI)
- Can match parent companies, not just subsidiaries
- May become stale if not renewed
- Availability inconsistent across data sources

**Coverage**:
- **SBIR Legacy Data**: ~70% have valid DUNS
- **Federal Legacy Contracts**: ~60% have valid DUNS
- **Recent Data**: ~20% still use DUNS

**When to Use**: Tertiary method for legacy data when UEI/CAGE not available.

**Implementation**:
```python
def resolve_by_duns(sbir_duns: str, contract_duns: str) -> bool:
    """Check if DUNS numbers match exactly."""
    if not sbir_duns or not contract_duns:
        return False
    # Normalize to 9 digits
    sbir_norm = str(sbir_duns).strip().zfill(9)
    contract_norm = str(contract_duns).strip().zfill(9)
    return sbir_norm == contract_norm
```

---

### Method 4: Fuzzy Name Matching - Fallback

**Confidence**: 0.65–0.85 (variable, requires validation)

**What it does**: Approximate string matching on company names using normalized text comparison.

**Algorithm**: RapidFuzz `token_set_ratio` with configurable thresholds.

**Matching Process**:

1. **Normalization**:
   - Convert to uppercase
   - Remove special characters: `!@#$%^&*()_+-={}[]|:;<>?,./`
   - Collapse whitespace (multiple spaces → single space)
   - Strip leading/trailing whitespace
   - Example: "Acme AI, Inc." → "ACME AI INC"

2. **Similarity Calculation**:
   - Tokenize names into words
   - Calculate token_set_ratio (order-independent token comparison)
   - Return score 0.0 (completely different) to 1.0 (identical)

3. **Thresholds**:
   - **Primary threshold**: 0.85 (high confidence, ~80% reliable)
   - **Secondary threshold**: 0.70 (exploratory, ~60% reliable)

**Data Fields**:
- SBIR: Recipient company name
- Contract: Contractor company name

**Example 1: High Confidence**:
```
SBIR Award Recipient: "Acme Artificial Intelligence Inc."
Federal Contract Vendor: "Acme AI Inc."

Normalized:
- SBIR: "ACME ARTIFICIAL INTELLIGENCE INC"
- Contract: "ACME AI INC"

Token Sets:
- SBIR: {ACME, ARTIFICIAL, INTELLIGENCE, INC}
- Contract: {ACME, AI, INC}

Similarity (token_set_ratio): 0.88 (≥0.85 threshold)
→ MATCH (confidence: 0.80)
```

**Example 2: Secondary Match**:
```
SBIR Award Recipient: "Acme AI LLC"
Federal Contract Vendor: "Acme Artificial Intelligence Limited Liability"

Normalized:
- SBIR: "ACME AI LLC"
- Contract: "ACME ARTIFICIAL INTELLIGENCE LIMITED LIABILITY"

Token Sets:
- SBIR: {ACME, AI, LLC}
- Contract: {ACME, ARTIFICIAL, INTELLIGENCE, LIMITED, LIABILITY}

Similarity (token_set_ratio): 0.72 (≥0.70 threshold)
→ POSSIBLE MATCH (confidence: 0.65)
```

**Example 3: No Match**:
```
SBIR Award Recipient: "Acme AI"
Federal Contract Vendor: "Beta Computing"

Normalized:
- SBIR: "ACME AI"
- Contract: "BETA COMPUTING"

Similarity (token_set_ratio): 0.22 (<0.70 threshold)
→ NO MATCH
```

**Advantages**:
- Handles name variations (acronyms, legal suffixes, spelling variations)
- Fallback when identifiers not available
- Flexible threshold configuration

**Disadvantages**:
- High false positive rate at low thresholds (~15% at 0.70)
- False negatives for companies with different trading names
- Computationally expensive for large datasets (O(n²) worst case)
- Requires manual validation for exploratory use

**Coverage**:
- **Fuzzy Primary (0.85)**: ~10–15% of awards without identifiers
- **Fuzzy Secondary (0.70)**: ~30–40% of awards without identifiers

**When to Use**: Last resort when UEI/CAGE/DUNS not available; requires manual verification.

**Tuning**:
```python
# More conservative (higher precision, lower recall)
primary_threshold: 0.88
secondary_threshold: 0.75

# More permissive (lower precision, higher recall)
primary_threshold: 0.80
secondary_threshold: 0.65
```

**Implementation**:
```python
from rapidfuzz import fuzz

def resolve_by_name(
    sbir_name: str,
    contract_name: str,
    primary_threshold: float = 0.85,
    secondary_threshold: float = 0.70
) -> tuple[bool, float, str]:
    """
    Fuzzy match company names.
    
    Returns:
        (matched, confidence, threshold_used)
    """
    if not sbir_name or not contract_name:
        return False, 0.0, "N/A"
    
    # Normalize
    sbir_norm = normalize_name(sbir_name)
    contract_norm = normalize_name(contract_name)
    
    if sbir_norm == contract_norm:
        return True, 1.0, "exact"
    
    # Calculate similarity
    similarity = fuzz.token_set_ratio(sbir_norm, contract_norm) / 100.0
    
    # Apply thresholds
    if similarity >= primary_threshold:
        return True, similarity, "primary"
    elif similarity >= secondary_threshold:
        return True, similarity, "secondary"
    else:
        return False, similarity, "none"

def normalize_name(name: str) -> str:
    """Normalize company name for comparison."""
    import re
    # Uppercase
    name = name.upper().strip()
    # Remove special characters
    name = re.sub(r'[!@#$%^&*()_+\-=\{\}\[\]|:;<>?,./]', '', name)
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name)
    return name.strip()
```

---

## Resolution Strategy

### Priority-Based Resolution

The vendor resolver uses a **priority cascade**: try highest-confidence methods first, fall back to lower-confidence methods if no match found.

```
┌─────────────────────────────────────────────┐
│ Award Recipient & Contract Vendor           │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
        ┌─────────────────┐
        │ UEI Match?      │
        │ (conf: 0.99)    │
        └────┬────────┬───┘
          Yes│        │No
             │        ▼
             │   ┌──────────────┐
             │   │ CAGE Match?  │
             │   │ (conf: 0.95) │
             │   └────┬────┬────┘
             │      Yes│   │No
             │        │   ▼
             │        │  ┌───────────┐
             │        │  │ DUNS Match│
             │        │  │ (conf: 0.90)
             │        │  └────┬──┬───┘
             │        │     Yes│ │No
             │        │       │ ▼
             │        │       │ ┌────────────────┐
             │        │       │ │ Fuzzy Name?    │
             │        │       │ │ (conf: 0.65-85)│
             │        │       │ └────┬────────┬──┘
             │        │       │    Yes│       │No
             │        │       │      │       │
             └────────┴───────┴──────┴───────┘
                      │
                      ▼
          ┌─────────────────────────┐
          │ Matched Vendor          │
          │ Match Type & Confidence │
          └─────────────────────────┘
```

### Resolution Flow

**Input**: SBIR award recipient with identifiers (UEI, CAGE, DUNS, name) and list of federal contracts.

**Process**:
1. For each award recipient
2. For each federal contract
3. Try UEI match → If match, record (UEI, 0.99) and move to next contract
4. Else try CAGE match → If match, record (CAGE, 0.95) and move to next contract
5. Else try DUNS match → If match, record (DUNS, 0.90) and move to next contract
6. Else try fuzzy name match (primary 0.85) → If match, record (FUZZY_PRIMARY, 0.80-0.85) and move to next contract
7. Else try fuzzy name match (secondary 0.70) → If match, record (FUZZY_SECONDARY, 0.65-0.75) and move to next contract
8. Else no match for this contract

**Output**: For each award-contract pair, one of:
- No match
- (match_type, confidence) where match_type ∈ {UEI, CAGE, DUNS, FUZZY_PRIMARY, FUZZY_SECONDARY}

### Multi-Match Handling

An award recipient may match multiple contracts (common scenario):

```
Award: Acme AI Inc. (UEI: ABC123DEF456)

Contracts Found:
1. Contract 1: UEI ABC123DEF456 (match, confidence 0.99)
2. Contract 2: UEI ABC123DEF456 (match, confidence 0.99)
3. Contract 3: Different UEI, but CAGE match (match, confidence 0.95)
4. Contract 4: No match

→ Result: Award linked to 3 contracts with different match types
```

All matching contracts are candidates for transition scoring.

---

## Configuration

### Vendor Resolver Configuration

```yaml
vendor_resolution:
  # Enable/disable resolution methods
  methods:
    uei: true
    cage: true
    duns: true
    fuzzy_name: true
  
  # Fuzzy matching parameters
  fuzzy_matching:
    algorithm: "token_set_ratio"  # or "token_sort_ratio", "ratio"
    primary_threshold: 0.85
    secondary_threshold: 0.70
    
    # Name normalization
    normalize:
      uppercase: true
      remove_special_chars: true
      collapse_whitespace: true
      strip_whitespace: true
  
  # Common legal suffixes to strip
  legal_suffixes:
    - "Inc"
    - "LLC"
    - "Ltd"
    - "Corporation"
    - "Company"
    - "Co"
    - "Inc."
    - "Ltd."
    - "Inc., Ltd"
  
  # Common abbreviations
  abbreviations:
    - ["Artificial Intelligence", "AI"]
    - ["Software Development", "Software"]
    - ["Research and Development", "R&D"]
    - ["Science and Technology", "Sci & Tech"]
  
  # Exclusion patterns (for filtering false matches)
  exclusions:
    - "Generic Inc"
    - "Technology Solutions"  # Too generic
```

### Environment Variable Overrides

```bash
# Thresholds
export SBIR_ETL__VENDOR_RESOLUTION__FUZZY_PRIMARY_THRESHOLD=0.85
export SBIR_ETL__VENDOR_RESOLUTION__FUZZY_SECONDARY_THRESHOLD=0.70

# Methods (disable/enable)
export SBIR_ETL__VENDOR_RESOLUTION__USE_FUZZY_NAME=true
export SBIR_ETL__VENDOR_RESOLUTION__REQUIRE_UEI=false

# Performance
export SBIR_ETL__VENDOR_RESOLUTION__BATCH_SIZE=1000
export SBIR_ETL__VENDOR_RESOLUTION__CACHE_ENABLED=true
```

---

## Implementation Details

### VendorResolver Class

```python
from src.transition.features.vendor_resolver import VendorResolver

# Initialize
resolver = VendorResolver(config=resolution_config)

# Add award recipients
resolver.add_award_recipient(
    recipient_id="SBIR-AWARD-123",
    uei="ABC123DEF456",
    cage="1A2B3",
    duns="123456789",
    name="Acme AI Inc."
)

# Resolve against contracts
matches = resolver.resolve_batch(contracts_df, match_type="all")

# Query results
for award_id, contract_id, match_info in matches:
    print(f"Award {award_id} → Contract {contract_id}")
    print(f"  Match type: {match_info['match_type']}")
    print(f"  Confidence: {match_info['confidence']}")
```

### Vendor Cross-Walk

Resolutions are persisted in a cross-walk table:

```
vendor_resolution.parquet
├── award_recipient_id: str
├── contractor_id: str
├── match_type: str (UEI, CAGE, DUNS, FUZZY_PRIMARY, FUZZY_SECONDARY)
├── confidence: float (0.0-1.0)
├── award_uei: str (nullable)
├── contractor_uei: str (nullable)
├── award_cage: str (nullable)
├── contractor_cage: str (nullable)
├── award_duns: str (nullable)
├── contractor_duns: str (nullable)
├── award_name: str (nullable)
├── contractor_name: str (nullable)
└── resolution_date: datetime
```

**Example**:
```
award_recipient_id  contractor_id  match_type  confidence  award_uei        contractor_uei
─────────────────────────────────────────────────────────────────────────────────────────
SBIR-2020-1         CONTRACT-001   UEI         0.99        ABC123DEF456     ABC123DEF456
SBIR-2020-1         CONTRACT-002   UEI         0.99        ABC123DEF456     ABC123DEF456
SBIR-2020-2         CONTRACT-003   CAGE        0.95        ABC456DEF123     XYZ789ABC012
SBIR-2020-3         CONTRACT-004   FUZZY_PRIM  0.84        [null]           [null]
```

### Caching & Performance

For large datasets (6.7M+ contracts), vendor resolution can be slow. Use caching:

```python
from src.transition.performance.contract_analytics import VendorResolutionCache

# Initialize cache
cache = VendorResolutionCache(ttl_hours=24)

# Resolve with caching
matches = resolver.resolve_batch(
    contracts_df,
    use_cache=True,
    cache_backend=cache
)

# Monitor cache performance
print(cache.get_stats())
# Output: {'hits': 1250, 'misses': 350, 'hit_rate': 0.78}
```

---

## Quality Metrics

### Coverage Metrics

**Resolution Rate**: Percentage of SBIR awards that match at least one contract.

```
Resolution Rate = (Awards with ≥1 match) / (Total awards) × 100%
Target: ≥80%
```

**Identifier Coverage** (percentage of awards with each identifier):

```
UEI Coverage: ~99% (Phase II awards)
CAGE Coverage: ~60% (DoD-focused awards)
DUNS Coverage: ~70% (legacy data)
Name Available: 100%
```

**Match Type Distribution**:

```
UEI matches: ~70% (highest confidence)
CAGE matches: ~5%
DUNS matches: ~10%
Fuzzy Primary (0.85): ~10%
Fuzzy Secondary (0.70): ~5%
No match: ~20%
```

### Precision Metrics

**Manual Validation**: Review 50 random matches per confidence level.

```
Confidence Level  Typical Precision  Sample Size  Validation Method
──────────────────────────────────────────────────────────────────
UEI               >99%               10 samples   Check SAM.gov
CAGE              >95%               10 samples   Verify DoD CAGE registry
DUNS              >90%               10 samples   Cross-reference with D&B
Fuzzy Primary     ~85%               15 samples   Manual company research
Fuzzy Secondary   ~60%               15 samples   Manual verification
```

**Validation Process**:
1. Sample 50 random matches
2. Per each match, verify:
   - Is this the same company?
   - Could there be legal entity changes (acquisition, rebranding)?
   - Are the identifiers current?
3. Calculate precision = (correct matches) / (total samples)

---

## Common Issues & Troubleshooting

### Issue 1: Low Coverage (<80% resolution rate)

**Symptoms**:
- Many awards with no contract matches
- Lots of "no match" results

**Causes**:
- Awards and contracts from different time periods
- Vendor name variations not captured by fuzzy matching
- Missing identifier data in contracts

**Solutions**:
1. **Check data sources**: Ensure SBIR and contract data overlap in time
2. **Increase fuzzy thresholds**: Lower primary/secondary thresholds
3. **Enable secondary fuzzy**: Ensure `fuzzy_secondary` enabled
4. **Investigate data quality**: Sample awards/contracts to verify identifier availability
5. **Consider acquisition/rebranding**: Some companies may have changed names

**Example Fix**:
```yaml
fuzzy_matching:
  primary_threshold: 0.80  # was 0.85
  secondary_threshold: 0.65  # was 0.70
```

### Issue 2: High False Positive Rate (>20% incorrect matches)

**Symptoms**:
- Manual validation shows many incorrect matches
- Fuzzy matches especially problematic
- Fuzzy Secondary matches almost all wrong

**Causes**:
- Thresholds too low (catching false positives)
- Common company names (e.g., "Tech Solutions Inc")
- Abbreviations causing spurious matches

**Solutions**:
1. **Increase fuzzy thresholds**: More strict matching
2. **Disable fuzzy secondary**: If too many false positives
3. **Add exclusion patterns**: Exclude generic names
4. **Manual review list**: Build manual exception list
5. **Stricter identifier matching**: Require UEI/CAGE when possible

**Example Fix**:
```yaml
fuzzy_matching:
  primary_threshold: 0.90  # was 0.85
  secondary_threshold: 0.75  # was 0.70

exclusions:
  - "Tech Inc"
  - "Solutions LLC"
  - "Consulting Group"
```

### Issue 3: Missing Identifiers in Contracts

**Symptoms**:
- Contract data lacks UEI/CAGE/DUNS
- Forced to rely on fuzzy name matching
- Low precision results

**Causes**:
- Data source doesn't capture identifiers
- Legacy contracts predate identifier systems
- Data extraction/transformation issues

**Solutions**:
1. **Enrich contract data**: Add UEI via SAM.gov lookup
2. **Use alternative data sources**: Try different contract databases
3. **Accept lower precision**: Fuzzy matching is best available
4. **Manual resolution**: For critical contracts, resolve manually
5. **Use parent company UEI**: If subsidiary info not available

**Example Enrichment**:
```python
# Lookup UEI via SAM.gov API
from src.extractors.sam_api import SAMClient

sam = SAMClient()
for idx, contract in contracts_df.iterrows():
    if pd.isna(contract['contractor_uei']):
        uei = sam.lookup_entity(contract['contractor_name'])
        contracts_df.loc[idx, 'contractor_uei'] = uei
```

### Issue 4: Acquisition/Rebranding Breaks Matches

**Symptoms**:
- Award matched to vendor A
- Vendor A acquired by vendor B
- Contracts now under vendor B name
- Matches break post-acquisition

**Causes**:
- Company legal name changes
- Acquisition changes UEI
- Merger creates new entity

**Solutions**:
1. **Track aliases**: Maintain company name history
2. **Use parent/subsidiary mapping**: Link entities across transactions
3. **Manual verification**: Review acquisition history
4. **Cross-walk updates**: Update identifiers in resolution table
5. **Consider temporal matching**: Use acquisition dates to guide matching

**Example**:
```
Pre-Acquisition:
  Award: Acme AI Inc. (UEI: ABC123)
  Contracts: Acme AI Inc. (UEI: ABC123)
  → Match ✓

Post-Acquisition (Acquired by BigTech Corp):
  Award: Acme AI Inc. (UEI: ABC123)  # Historical record
  Contracts: BigTech Corp (UEI: XYZ789)  # New UEI
  → No match ✗ (unless acquisition history tracked)

Solution: Add acquisition record
  Acme AI Inc. (ABC123) → acquired by BigTech Corp (XYZ789) on 2023-06-01
```

---

## Best Practices

### 1. Always Prioritize UEI

- Check UEI first (most reliable)
- Only fall back to CAGE/DUNS when UEI unavailable
- Never rely solely on fuzzy name matching for production

### 2. Validate Fuzzy Matches

- Manual spot-check ~10% of fuzzy matches
- Maintain false positive/negative rates
- Adjust thresholds if validation fails

### 3. Track Resolution Metadata

- Store match method and confidence with results
- Document resolution date for auditing
- Keep resolution logic version controlled

### 4. Cache Results

- Cache vendor resolutions for performance
- Reuse cross-walk table for repeated analyses
- Document cache invalidation strategy

### 5. Monitor Coverage

- Track resolution rate over time
- Alert if coverage drops below 80%
- Investigate systematic drops (data source changes)

### 6. Document Exceptions

- Maintain list of manually resolved cases
- Document why certain matches required manual review
- Use for validation and improvement

---

## Performance Considerations

### Throughput

**Typical Performance**:
- UEI/CAGE/DUNS exact matching: ~100,000 matches/second
- Fuzzy name matching: ~1,000 matches/second
- Full resolution (mixed methods): ~5,000–10,000 matches/second

**Bottleneck**: Fuzzy name matching (token_set_ratio is O(n²) in name length)

### Memory Usage

- **Per 1,000 awards**: ~5 MB
- **Per 1,000 contracts**: ~10 MB
- **Fuzzy matcher index**: ~100 MB per 100,000 names

### Optimization Tips

1. **Pre-filter by time**: Only match contracts within reasonable time window
2. **Index by UEI/CAGE/DUNS**: Pre-compute indices for fast lookups
3. **Batch fuzzy matching**: Group by first letters for parallel processing
4. **Cache results**: Reuse cross-walk table
5. **Lazy loading**: Load patent/CET data only after vendor match

---

## References

- **Implementation**: `src/transition/features/vendor_resolver.py`
- **Cross-Walk**: `src/transition/features/vendor_crosswalk.py`
- **Tests**: `tests/unit/test_vendor_resolver.py`
- **SAM.gov**: https://sam.gov/
- **RapidFuzz**: https://maxbachmann.github.io/RapidFuzz/
- **DUNS**: https://www.dnb.com/business-tools/duns-number.html