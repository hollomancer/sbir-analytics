# Enhanced Name Matching Features

This document describes the enhanced data cleaning features for handling misspelled, near-miss, and variant company and researcher names in the SBIR ETL pipeline.

## Overview

Four new matching strategies have been implemented to improve data quality:

1. **Phonetic Matching** - Catches sound-alike misspellings
2. **Jaro-Winkler Distance** - Better for names with distinctive prefixes
3. **Enhanced Abbreviations** - Normalizes common terms automatically
4. **ORCID-First Researcher Matching** - Identifier-based researcher resolution

All features are **configurable via YAML** and can be enabled/disabled independently.

---

## 1. Phonetic Matching

### What It Does

Phonetic matching identifies names that sound similar even if spelled differently, using algorithms like Metaphone, Double Metaphone, or Soundex.

### Use Cases

- **Typos**: "Smyth Technologies" → "Smith Technologies"
- **Alternative spellings**: "Mikrosystems" → "Microsystems"
- **OCR errors**: "Bpeing" → "Boeing"

### Configuration

```yaml
enrichment:
  enhanced_matching:
    enable_phonetic_matching: false  # Set to true to enable
    phonetic_algorithm: "metaphone"  # Options: "metaphone", "double_metaphone", "soundex"
    phonetic_boost: 5  # Score boost (0-10) when phonetic codes match
```

### How It Works

1. During indexing, phonetic codes are generated for all company names
2. When matching an award, the phonetic code of the award company is computed
3. If a match is found in the phonetic index, it's accepted with high confidence (95-100%)
4. Phonetic matching runs **after** exact UEI/DUNS matches but **before** fuzzy matching

### Code Example

```python
from src.enrichers.company_enricher import enrich_awards_with_companies

enhanced_config = {
    "enable_phonetic_matching": True,
    "phonetic_algorithm": "metaphone",
    "phonetic_boost": 5,
}

enriched = enrich_awards_with_companies(
    awards_df,
    companies_df,
    enhanced_config=enhanced_config
)
```

### Match Method

Records matched via phonetic matching will have `_match_method = "phonetic-match"`.

---

## 2. Jaro-Winkler Matching

### What It Does

Jaro-Winkler similarity gives extra weight to matching prefixes, making it particularly effective for company names where the first word is often the most distinctive (e.g., "Boeing", "Lockheed", "Raytheon").

### Use Cases

- **Prefix-heavy names**: "Boeing Advanced Systems" vs "Boeing Defense Technologies"
- **Corporate naming patterns**: "Lockheed Martin Space" vs "Lockheed Martin Aeronautics"
- **Brand-first names**: "Apple Technologies" vs "Apple Systems"

### Configuration

```yaml
enrichment:
  enhanced_matching:
    enable_jaro_winkler: false  # Set to true to enable
    jaro_winkler_prefix_weight: 0.1  # Weight for matching prefix (0.0-0.25)
    jaro_winkler_threshold: 90  # Min score to consider a match (0-100)
    jaro_winkler_use_as_primary: false  # Use as primary scorer instead of token_set_ratio
```

### How It Works

**Option 1: As Primary Scorer**
- Set `jaro_winkler_use_as_primary: true`
- Jaro-Winkler replaces `token_set_ratio` as the fuzzy matching scorer
- Better for datasets where prefix matching is critical

**Option 2: As Secondary Signal** (future enhancement)
- Set `jaro_winkler_use_as_primary: false`
- Use Jaro-Winkler to boost scores of candidates with matching prefixes
- Combines benefits of token-based and prefix-based matching

### Code Example

```python
enhanced_config = {
    "enable_jaro_winkler": True,
    "jaro_winkler_use_as_primary": True,
    "jaro_winkler_prefix_weight": 0.1,
}

enriched = enrich_awards_with_companies(
    awards_df,
    companies_df,
    enhanced_config=enhanced_config,
    high_threshold=90,
)
```

---

## 3. Enhanced Abbreviations

### What It Does

Automatically normalizes common terms to standard abbreviations, improving matching between long-form and abbreviated company names.

### Abbreviation Dictionary

The default dictionary includes 40+ common abbreviations:

| Term | Abbreviation | Category |
|------|--------------|----------|
| technologies | tech | Technology |
| systems | sys | Technology |
| solutions | sol | Technology |
| international | intl | Geography |
| aerospace | aero | Industry |
| defense | def | Industry |
| biotechnology | biotech | Industry |
| pharmaceuticals | pharma | Industry |
| research | res | Academic |
| laboratory | lab | Academic |
| advanced | adv | Descriptor |
| engineering | eng | Function |
| development | dev | Function |

See `src/utils/enhanced_matching.py:ENHANCED_ABBREVIATIONS` for the complete list.

### Use Cases

- **Long vs short forms**: "Advanced Aerospace Defense Systems" → "Adv Aero Def Sys"
- **Mixed notation**: "Tech International" → "tech intl"
- **Database standardization**: Normalize all names to abbreviated forms

### Configuration

```yaml
enrichment:
  enhanced_matching:
    enable_enhanced_abbreviations: false  # Set to true to enable
    custom_abbreviations:  # Add domain-specific abbreviations
      innovations: innov
      quantum: qnt
      artificial_intelligence: ai
```

### How It Works

1. During name normalization, each token is checked against the abbreviation dictionary
2. Matching tokens are replaced with their abbreviated form
3. Both award and company names are normalized consistently
4. Fuzzy matching then operates on normalized forms

### Code Example

```python
enhanced_config = {
    "enable_enhanced_abbreviations": True,
    "custom_abbreviations": {
        "innovations": "innov",
        "quantum": "qnt",
    },
}

enriched = enrich_awards_with_companies(
    awards_df,
    companies_df,
    enhanced_config=enhanced_config
)
```

---

## 4. ORCID-First Researcher Matching

### What It Does

Matches researcher records using a hierarchical identifier-first strategy, prioritizing authoritative identifiers over fuzzy name matching.

### Matching Hierarchy

1. **ORCID** (100% confidence) - Authoritative researcher identifier
2. **Email** (95% confidence) - High confidence, handles name variations
3. **Affiliation + Last Name** (80% confidence) - Medium confidence fallback

### Use Cases

- **Name variations**: "John Smith" vs "J. Smith, PhD" vs "Smith, John"
- **Name changes**: Researchers who change names (marriage, etc.)
- **Disambiguation**: Multiple researchers with similar names

### Configuration

```yaml
enrichment:
  researcher_matching:
    enable_orcid_matching: true
    orcid_confidence: 100
    enable_email_matching: true
    email_confidence: 95
    enable_affiliation_matching: true
    affiliation_confidence: 80
```

### How It Works

1. **ORCID Matching**: If both records have ORCIDs and they match (digits-only comparison), return 100% confidence
2. **Email Matching**: If ORCIDs don't match or are missing, try email (case-insensitive)
3. **Affiliation + Last Name**: If email doesn't match, try affiliation + last name
   - Extract last name from full name (handles "Last, First" and "First Last" formats)
   - Normalize affiliations (remove common words like "University of", "Institute")
   - Match if both last name and normalized affiliation match

### Code Example

```python
from src.utils.enhanced_matching import ResearcherMatcher

matcher_config = {
    "enable_orcid_matching": True,
    "enable_email_matching": True,
    "enable_affiliation_matching": True,
}

matcher = ResearcherMatcher(matcher_config)

query_researcher = {
    "name": "John Smith",
    "orcid": "0000-0001-2345-6789",
    "email": "j.smith@mit.edu",
    "affiliation": "MIT"
}

candidate_researcher = {
    "name": "J. Smith, PhD",
    "orcid": "0000-0001-2345-6789",
    "email": "john.smith@mit.edu",
    "affiliation": "Massachusetts Institute of Technology"
}

matched, confidence, method = matcher.match_researcher(
    query_researcher,
    candidate_researcher
)
# Result: (True, 100, "orcid-exact")
```

---

## Performance Considerations

### Memory Usage

- **Phonetic Matching**: Minimal overhead (one phonetic code per company)
- **Enhanced Abbreviations**: No additional memory (normalization is on-the-fly)
- **Jaro-Winkler**: Same as token_set_ratio (no additional memory)

### Speed

- **Phonetic Matching**: Very fast (O(1) lookup after indexing)
- **Enhanced Abbreviations**: Negligible impact (simple token replacement)
- **Jaro-Winkler**: Slightly slower than token_set_ratio for very large candidate sets

### Recommendations

- Enable **phonetic matching** for datasets with known OCR/typo issues
- Enable **Jaro-Winkler** for datasets with brand-heavy or prefix-heavy names
- Enable **enhanced abbreviations** when mixing data sources with different naming conventions
- Use **ORCID matching** whenever ORCID data is available

---

## Testing

### Unit Tests

Run enhanced matching tests:

```bash
pytest tests/unit/utils/test_enhanced_matching.py -v
pytest tests/unit/enrichers/test_company_enricher_enhanced.py -v
```

### Demo Script

Run the interactive demo:

```bash
python examples/enhanced_matching_demo.py
```

This demonstrates all four features with sample data showing common data quality issues.

---

## Configuration Examples

### Development (All Features Enabled)

```yaml
# config/dev.yaml
enrichment:
  enhanced_matching:
    enable_phonetic_matching: true
    enable_jaro_winkler: true
    enable_enhanced_abbreviations: true
```

### Production (Conservative)

```yaml
# config/prod.yaml
enrichment:
  enhanced_matching:
    enable_phonetic_matching: false  # Disable until validated
    enable_jaro_winkler: false
    enable_enhanced_abbreviations: true  # Low-risk enhancement
```

### High-Accuracy Use Case

```yaml
enrichment:
  enhanced_matching:
    enable_phonetic_matching: true
    phonetic_algorithm: "double_metaphone"  # More accurate than metaphone
    phonetic_boost: 3  # Conservative boost
    enable_jaro_winkler: true
    jaro_winkler_use_as_primary: true
    jaro_winkler_threshold: 92  # Higher threshold
    enable_enhanced_abbreviations: true
```

---

## Future Enhancements

Potential additions for future releases:

1. **N-gram matching** for character-level typos
2. **Machine learning-based scoring** combining multiple signals
3. **Active learning** for threshold tuning
4. **Custom phonetic rules** for domain-specific terminology
5. **Temporal validation** (e.g., researcher affiliation changes over time)

---

## References

- **Phonetic Algorithms**: [Jellyfish Library Documentation](https://github.com/jamesturk/jellyfish)
- **Jaro-Winkler**: [RapidFuzz Documentation](https://github.com/rapidfuzz/RapidFuzz)
- **ORCID**: [ORCID Registry](https://orcid.org/)

---

## Support

For questions or issues:
- Open an issue on GitHub
- See `examples/enhanced_matching_demo.py` for usage examples
- Review unit tests in `tests/unit/utils/test_enhanced_matching.py`
