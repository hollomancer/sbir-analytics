# Patent Cost and Spillover Analysis — Requirements

Research Plan Milestone: **M2 — Patent Linkage and Spillover Pipeline**

## Background

NASEM treats IP output as a count variable. This spec builds the analytical layer
on top of the existing patent-award linkage pipeline to compute marginal cost per patent,
trace citation networks for knowledge transfer, and replicate DOE spillover methodology.

## Requirements

1. **SHALL** compute marginal cost per patent by agency (award $ / linked patent count)
2. **SHALL** build citation network from USPTO citation data for SBIR-linked patents
3. **SHALL** compute spillover multiplier (citations from non-SBIR patents to SBIR patents)
4. **SHALL** replicate NIH ~$1.5M marginal cost benchmark and DOE 3x spillover multiplier
5. **SHOULD** extend both metrics across all agencies
6. **SHOULD** stratify by technology area, firm size, and award vintage

## Gate Condition

Reproduce NIH's ~$1.5M marginal cost per patent AND DOE's 3x spillover multiplier.
Then extend both across all agencies.

## Dependencies

- Patent-award linkage (`src/transformers/patent_transformer.py`) — EXISTS
- USPTO extraction pipeline — EXISTS
- USPTO Lambda downloads (`.kiro/specs/uspto-lambda-downloads/`) — 90% complete
- Entity resolution — EXISTS
- Leverage ratio analysis (M1) — for shared entity universe
