# Cross-Agency Technology Taxonomy — Requirements

Research Plan Milestone: **M3 — Cross-Agency Technology Taxonomy**

## Background

No unified view exists of what the federal SBIR portfolio is buying across all 11 agencies.
NASEM studies are siloed by committee mandate. This spec deploys the CET classifier
across the full SBIR.gov corpus to produce that cross-agency view.

## Requirements

1. **SHALL** classify all SBIR.gov awards using the CET technology taxonomy
2. **SHALL** produce agency-level technology allocation breakdowns (% of awards per CET area per agency)
3. **SHALL** identify cross-agency overlap (same technology areas funded by multiple agencies)
4. **SHALL** identify concentration risk (technology areas dominated by a single agency)
5. **SHOULD** produce a single visualization showing SBIR technology allocation across all 11 agencies
6. **SHOULD** support temporal analysis (how technology mix shifts over time per agency)

## Gate Condition

A single visualization showing SBIR technology allocation across all 11 agencies.

## Dependencies

- CET classifier (`src/transition/features/cet_analyzer.py`) — EXISTS
- Topic extraction (`src/tools/mission_a/extract_topics.py`) — EXISTS
- PaECTER embeddings (`.kiro/specs/paecter_analysis_layer/`) — 30% complete (enhances but not required)
- Full SBIR.gov award corpus — needs verification of data freshness
