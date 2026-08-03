---
Type: Overview
Owner: research@project
Last-Reviewed: 2026-08-03
Status: active
---

# Research Outputs

This index maps research notes and reports to the questions they support, the
data cut they describe, and the weight their findings may carry. The canonical
question inventory remains [research-questions.md](../research-questions.md).

Unless a row links to a `studies/<study-id>/study.yaml` manifest with an explicit
`citable` status, treat it as exploratory or reproducible-but-non-citable. A
working pipeline, a dated report, or a provisional policy brief is not by itself
validated evidence. See [epistemic tiers](../steering/epistemic-tiers.md) and
[study contracts](../../studies/README.md).

## Capital formation, exits, and firm pathways

| Artifact | Questions | Evidence posture | Data cut or scope |
| --- | --- | --- | --- |
| [Form D fundraising analysis](sbir-form-d-fundraising-analysis.md) | F1, F3 | Dated research analysis; no citable study manifest | Form D and SBIR spending, 2009–2024; methodology revised 2026-04-23 |
| [DoD Form D leverage](dod-form-d-leverage.md) | A3, A4, F3 | Dated decomposition and follow-up analysis | Consolidated 2026-06-21 |
| [Form D data dictionary](form-d-data-dictionary.md) | F1, F3 | Field and confidence-tier reference | Current on-disk Form D artifact contract |
| [Agency private-capital Phase 2 method](agency-private-capital-phase2-form-d.md) | B2, B3, F3 | Descriptive matched-cohort method, not a causal estimate | No fixed published run |
| [M&A exit analysis](sbir-ma-exit-analysis.md) | A4, F1, F2 | Dated research analysis; public-filer lower bound | Run documented 2026-04-23 |
| [Capital-pathway cohorts](sbir-pathway-cohorts.md) | F1, F2 | Dated cohort analysis | High-confidence 3,639-firm cohort; 2026-06-23 |
| [UCC-1 pilot](sbir-ucc1-pilot.md) | F1 | Partial, state-specific exploratory pilot | California subset; 2026-05-16 |
| [California UCC API notes](ucc1-bizfileonline-api.md) | E5, F1 | Source-interface reference, not a result | Endpoints captured 2026-05-16 |
| [SEC EDGAR learnings](sec-edgar-sbir-learnings.md) | E5, F1, F2 | Implementation and source-behavior note | Observations from 2026-04-19/22 |

## Procurement, transition, and industrial-base research

| Artifact | Questions | Evidence posture | Data cut or scope |
| --- | --- | --- | --- |
| [DoD industrial-base concentration](dod_supply_chain_initial_analysis.md) | A1–A3 | Exploratory descriptive baseline | FY2012–FY2025; headline window FY2021–FY2025 |
| [GSA and OTSB Phase III analysis](sbir-phase3-gsa-otsb-analysis.md) | B2, B3 | Working keyword-discoverable analysis; known coding undercount | FY2008–FY2026 source universe built 2026-06-28 |
| [Phase II→III latency method](../phase-transition-latency.md) | B3 | Implemented pipeline method; not a citable result | Uses the configured materialization data cut |
| [Follow-on multiplier method](../follow-on-multiplier-analysis.md) | A3 | Implemented analytical method; empirical validation remains open | Uses configured SBIR and USAspending inputs |
| [Multiplier reproducibility fixture](../follow-on-multiplier-reproducibility.md) | A3 | Deterministic fixture verification, not a population estimate | Synthetic edge-case fixture |
| [Commercialization benchmark method](../commercialization-benchmark-methodology.md) | B3 | Methodology record; local audit harness is not reproducible from this repository | FY2026 local audit described in the document |
| [Monthly procurement-transition report](../procurement-transition-report.md) | B4, E6 | Operator/report contract, not research evidence | Current public-source pipeline |

The label-free Phase III census is tracked separately because it has a formal
study contract: [manifest](../../studies/phase-iii-census/study.yaml),
[February 2026 materialization audit](../../studies/phase-iii-census/materialization-2026-02-06.md),
and [August 2026 control-identity eligibility audit](../../studies/phase-iii-census/identity-eligibility-audit-2026-08-03.md).
Its status is reproducible, not citable; control construction, matching, and the
placebo remain unresolved.

## Economic and fiscal methods

| Artifact | Questions | Evidence posture | Data cut or scope |
| --- | --- | --- | --- |
| [Open-source tax-impact modeling](open-source-tax-impact-modeling.md) | D2, D3 | Research/pre-spec comparison | Dated 2026-04-19 |

The maintained pipeline guide is [SBIR fiscal analysis](../fiscal/sbir-fiscal-pipeline-guide.md).

## Technology-area reports

Each policy brief is the audience-facing entry point; its technical findings and
methodology preserve cohort definitions and limitations.

| Area | Questions | Evidence posture | Data cut |
| --- | --- | --- | --- |
| Nanotechnology: [brief](../nanotech_sbir_policy_brief.md), [findings](../nanotech_sbir_transition_findings.md), [method](../nano_phase3_methodology.md) | A1, A2, B2, B3, C1 | Provisional bounded estimates, not final program rates | SBIR.gov FY2025; USAspending FY2024; PatentsView March 2026 |
| Hypersonics: [brief](../hypersonics_sbir_policy_brief.md), [findings](../hypersonics_sbir_transition_findings.md) | A1, A2, B2, B3, C1 | Provisional cohort and triangulation; outcome-channel rates unavailable | SBIR.gov through FY2025 |
| Quantum information science: [brief](../quantum_information_science_sbir_policy_brief.md), [findings](../quantum_information_science_sbir_transition_findings.md) | A1, A2, B2, B3, C1 | Provisional cohort and triangulation; outcome-channel rates unavailable | SBIR.gov through FY2025 |

## Research planning and communication

- [Literature map and citation audit](literature-map/README.md) — 2019–2026
  literature coverage and gaps across question areas A–F.
- [Government-policy demo plan](../guides/government-policy-demo-plan.md) —
  audience framing and demonstration sequence; not an evidence source.
