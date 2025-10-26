# Company Search Enrichment Analysis

Generated: 2025-10-26T10:48:31.681199 UTC

## Summary

- Company rows: **9515**
- Awards rows: **6**

## Identifier coverage

- UEI non-null: **4482**
- DUNS non-null: **5987**
- Company URLs present: **3207**

## Exact match counts (awards -> companies)

- Exact UEI matches: **0**
- Exact DUNS matches: **0**
- Exact (UEI or DUNS) matches: **0**

## Fuzzy match estimates (sample-based)

- Sample size used for fuzzy estimate: **6**
- High-confidence fuzzy matches in sample (>= threshold): **0**
- Medium-confidence fuzzy matches in sample (>= threshold): **4**
- Estimated high-confidence matches in full unmatched set: **0**
- Estimated medium-confidence matches in full unmatched set: **4**

Top fuzzy match examples (from sample):

- Award company: Acme Innovations → Best match: agility innovations llc (score 81.48148148148148)
- Award company: BioTech Labs → Best match: eci biotech (score 77.77777777777777)
- Award company: NanoWorks → Best match: aid networks (score 66.66666666666666)
- Award company: TechStart Inc → Best match: technest inc (score 80.0)
- Award company: GreenEnergy Corp → Best match: neoenergy corp (score 80.0)

---
Recommendations:

1. Use UEI and DUNS for exact enrichment where present (deterministic).
2. Use fuzzy matching (token-based) as a conservative fallback; accept only high-score matches automatically.
3. Persist match score & method on enriched awards for auditing and manual review of medium-confidence candidates.
4. Consider additional blocking (state/zip) to reduce candidate set size for large company corpora.
