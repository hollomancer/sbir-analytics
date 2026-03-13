# Leverage Ratio Analysis — Requirements

Research Plan Milestone: **M1 — DOD Leverage Ratio Replication**

## Background

NASEM reports a 4:1 non-SBIR-to-SBIR funding ratio for DOD SBIR/STTR firms.
This spec implements the analytics to reproduce, reconcile, and extend that finding.

## Requirements

1. **SHALL** compute aggregate leverage ratio (non-SBIR DOD obligations / SBIR/STTR obligations) for DOD SBIR firms
2. **SHALL** stratify ratios by: award vintage (cohort year), firm size, technology area, experienced vs. new firm
3. **SHALL** produce a reconciliation narrative comparing pipeline result to NASEM's 4:1 benchmark
4. **SHALL** compute the same ratio for at least one civilian agency (DOE preferred)
5. **SHOULD** decompose the ratio as a time series (is it growing or shrinking?)
6. **SHOULD** compute technology-area breakdown showing which clusters generate highest follow-on leverage
7. **SHALL** report match rates and entity resolution coverage as sensitivity metadata

## Gate Condition

Can state: "NASEM reports 4:1. Our pipeline yields [X]:1 using [method]. The difference is attributable to [Y]."
The reconciliation matters more than the match.

## Dependencies

- FPDS contract data (`src/tools/phase0/extract_fpds_contracts.py`) — EXISTS
- Entity resolution (`src/tools/phase0/resolve_entities.py`) — EXISTS
- Company categorization (`.kiro/specs/company-categorization/`) — 77% complete
- CET classifier (`src/transition/features/cet_analyzer.py`) — EXISTS (for tech-area stratification)
