---
Type: Overview
Maintainer: Conrad Hollomon
Last-Reviewed: 2026-08-18
Status: active
---

# Research Outputs

This page shows which questions each research note or report helps answer, how
much confidence to place in it, and which data it covers. See
[research-questions.md](../research-questions.md) for the full list of questions.

Do not cite an output as a validated finding unless its linked
`studies/<study-id>/study.yaml` file says `citable`. A working pipeline or a dated
report may still be early research. See [evidence levels](../steering/epistemic-tiers.md)
and [study requirements](../../studies/README.md) for the review rules.

Every document in this directory should open by declaring its reader — a
`**Prepared for:**` or `**Audience:**` header line. A doc addressed to policy
staff or program officers is signed up for plain language and findings-first
ordering (the policy briefs are the model); a doc declared for maintainers may
be as technical as it needs to be. Technical appendices linked from a plain
brief count as maintainer-facing.

## Capital formation, exits, and firm pathways

| Output | Questions | Evidence status | Data covered |
| --- | --- | --- | --- |
| [Form D fundraising analysis](sbir-form-d-fundraising-analysis.md) | F1, F3 | Reproducible study (`studies/form-d-fundraising`); not approved for citation | Form D and SBIR spending, 2009–2024; method revised 2026-04-23 |
| [DoD Form D leverage](dod-form-d-leverage.md) | A3, A4, F3 | Dated breakdown and follow-up analysis | Combined 2026-06-21 |
| [Form D data dictionary](form-d-data-dictionary.md) | F1, F3 | Reference for fields and confidence levels | Form D files currently produced by the pipeline |
| [NSF Phase I to Phase II baseline comparison](agency-private-capital-phase1-nsf.md) | B2, B3, F3 | Exploratory Phase 1 review; non-citable with incomplete outcomes | Pinned SBIR.gov snapshot (219,500 rows); NSF Phase I firms, 2015–2019 |
| [Agency private-capital Phase 2 method](agency-private-capital-phase2-form-d.md) | B2, B3, F3 | Compares matched groups; does not prove cause and effect | No fixed published run |
| [M&A exit analysis](sbir-ma-exit-analysis.md) | A4, F1, F2 | Dated analysis; likely understates exits because it uses public filings | Run documented 2026-04-23 |
| [Capital-pathway cohorts](sbir-pathway-cohorts.md) | F1, F2 | Dated group analysis | 3,639 firms with high-confidence matches; 2026-06-23 |
| [UCC-1 pilot](sbir-ucc1-pilot.md) | F1 | Early, partial pilot for one state | California subset; 2026-05-16 |
| [California UCC API notes](ucc1-bizfileonline-api.md) | E5, F1 | Reference for the data source; not a research result | Web addresses recorded 2026-05-16 |
| [SEC EDGAR learnings](sec-edgar-sbir-learnings.md) | E5, F1, F2 | Notes on implementation and source behavior | Observations from 2026-04-19 and 2026-04-22 |

## Procurement, transition, and industrial-base research

| Output | Questions | Evidence status | Data covered |
| --- | --- | --- | --- |
| [DoD industrial-base concentration](dod_supply_chain_initial_analysis.md) | A1–A3 | Early descriptive starting point | FY2012–FY2025; main results use FY2021–FY2025 |
| [GSA and OTSB Phase III analysis](sbir-phase3-gsa-otsb-analysis.md) | B2, B3 | Working keyword analysis; known to miss some award codes | FY2008–FY2026 sources assembled 2026-06-28 |
| [Phase II→III latency method](../phase-transition-latency.md) | B3 | Method works in the pipeline; not an approved finding | Uses the data selected for each pipeline run |
| [Follow-on multiplier method](../follow-on-multiplier-analysis.md) | A3 | Method works; testing against real outcomes is still open | Uses the selected SBIR and USAspending inputs |
| [Multiplier repeatability test](../follow-on-multiplier-reproducibility.md) | A3 | Automated test with made-up edge cases; not a program estimate | Test data only |
| [Commercialization benchmark method](../commercialization-benchmark-methodology.md) | B3 | Method is documented; this repository cannot recreate the local audit | FY2026 local audit described in the document |
| [Monthly procurement-transition report](../procurement-transition-report.md) | B4, E6 | Instructions for producing a report; not research evidence | Current public-source pipeline |

The Phase III census has its own formal study record: the
[study file](../../studies/phase-iii-census/study.yaml),
[February 2026 data-build review](../../studies/phase-iii-census/materialization-2026-02-06.md),
and [August 2026 control-group identity review](../../studies/phase-iii-census/identity-eligibility-audit-2026-08-03.md).
The work can be repeated, but it is not yet approved for citation. The comparison
group, matching, and placebo test are not finished.

## Economic and fiscal methods

| Output | Questions | Evidence status | Data covered |
| --- | --- | --- | --- |
| [Open-source tax-impact modeling](open-source-tax-impact-modeling.md) | D2, D3 | Early comparison written before a formal spec | Dated 2026-04-19 |

The maintained pipeline guide is [SBIR fiscal analysis](../fiscal/sbir-fiscal-pipeline-guide.md).

## Technology-area reports

Start with the policy brief for a plain summary. The findings and method documents
explain how firms were selected and what the results cannot show.

| Area | Questions | Evidence status | Data covered |
| --- | --- | --- | --- |
| Nanotechnology: [brief](nanotech_sbir_policy_brief.md), [findings](nanotech_sbir_transition_findings.md), [method](../nano-phase3-methodology.md) | A1, A2, B2, B3, C1 | Early estimates with stated bounds; not final program rates | SBIR.gov FY2025; USAspending FY2024; PatentsView March 2026 |
| Hypersonics: [brief](hypersonics_sbir_policy_brief.md), [findings](hypersonics_sbir_transition_findings.md) | A1, A2, B2, B3, C1 | Early firm group built from several signals; outcome rates are unavailable | SBIR.gov through FY2025 |
| Quantum information science: [brief](quantum_information_science_sbir_policy_brief.md), [findings](quantum_information_science_sbir_transition_findings.md) | A1, A2, B2, B3, C1 | Early firm group built from several signals; outcome rates are unavailable | SBIR.gov through FY2025 |

## Research planning and communication

- [Literature map and citation audit](literature-map/README.md) — research published
  from 2019–2026 and missing coverage across question areas A–F.
- [Solicitation document and requirement evidence plan](solicitation_document_evidence_plan.md) —
  bounded acquisition, linkage, attachment parsing, and classifier gates for A1 and E5; Phase 1 is
  implemented, but this remains a plan rather than research evidence.
- [Solicitation source coverage spike status](solicitation_source_coverage_status.md) — current
  Phase 0 adapter decisions and the pinned SBIR.gov bulk award linkage baseline.
- [Government-policy demo plan](../guides/government-policy-demo-plan.md) —
  what to show each audience and in what order; not an evidence source.
