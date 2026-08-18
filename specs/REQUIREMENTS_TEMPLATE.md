# [Feature Name] — Requirements

<!--
Before writing: read specs/status.md (lifecycle), docs/development/spec-workflow-guide.md
(shapes), docs/steering/epistemic-tiers.md (contracts), and CLAUDE.md (conventions).
Design and tasks shapes live in the workflow guide — there are no separate DESIGN/TASKS
template files.
-->

> **Lifecycle status:** [see `specs/status.md` — Active | Maintenance | Gated backlog |
> Deferred | Archive candidate]
> **Spec-file progress (optional):** [Not yet started | In progress | Partially implemented | Complete]
> Anchors inventory question(s) **[RQ IDs]** in [docs/research-questions.md](../docs/research-questions.md).

**Target epistemic tier:** [`primitives` | `pipelines` | `evidence` | `exploratory`]
(see [epistemic-tiers.md](../docs/steering/epistemic-tiers.md))

**Research question anchor:** [e.g., A3 — DoD leverage ratio]
**Answers for:** [audiences from the RQ inventory — e.g., policy analysts, SBIR program managers]
**RQ complexity tier:** [Descriptive | Relational | Inferential | Predictive]
(not epistemic tier; see [research-questions.md](../docs/research-questions.md))

<!--
Evidence-tier only — omit for other tiers. Required when Target epistemic tier is `evidence`:
**Declared estimand:** [what quantity is estimated, and what would make it wrong]
Plus an amendments.md freeze log with a SHA-256 digest and/or raw-byte freeze language.
See docs/steering/epistemic-tiers.md. Default to pipelines or exploratory when the
four-item evidence contract is not yet in place.
-->

---

## Done when

> [A concrete, first-person statement of the output — not what the system does, but what
> an analyst can say or show as a result. Example:
>
> "An analyst can state: 'NASEM reports 4:1. Our pipeline yields [X]:1 using [method].
> The difference is attributable to [Y]. Here is the stratification by vintage and CET area.'"
>
> If the output is a report, name the report. If it is a graph query, show the query shape.
> If it is a briefing, describe the claim the briefing can make.]

---

## Background

[2–4 sentences: what is the problem, why can't it be answered today, what data makes it
tractable. Cite the relevant RQ section. Do not repeat the glossary or the requirements.]

## Glossary

[Optional. Define only terms that are ambiguous in *this* spec or that have
project-specific meanings here. Omit standard terms like "award", "agency",
"API", or "CLI". Do **not** redefine confidence bands — link the owning config
or doc from [glossary.md](../docs/steering/glossary.md).]

---

## Requirements

### Requirement 1 — [Short name]

**User story:** As a [actor from taxonomy below], I want [outcome], so that [downstream
decision or use — not "so that I can see X" but "so that I can brief/publish/flag X"].

#### Acceptance Criteria

1. WHEN [triggering condition], THE System SHALL [observable behavior or output].
2. WHEN [condition], THE System SHALL [behavior].
3. ...

---

### Requirement 2 — [Short name]

**User story:** As a [actor], I want [outcome], so that [downstream use].

#### Acceptance Criteria

1. WHEN [condition], THE System SHALL [behavior].
2. ...

---

<!-- Add more requirements as needed. Each requirement should be independently testable. -->

---

## Dependencies

- [Upstream spec or existing component] — [EXISTS | IN PROGRESS | BLOCKED]
- ...

---

<!--
ACTOR TAXONOMY — use these labels (or close variants) in user stories:

  policy analyst              preparing a congressional or OMB briefing; needs citable,
                              benchmark-anchored figures (A3, D2, F3 leverage questions)

  SBIR program manager        SBA / NIH / DoD / NSF program office staff evaluating
                              portfolio performance and statutory compliance (B-area,
                              commercialization-benchmark, E-area questions)

  defense industrial base     DoD acquisition / OSTP / HASC/SASC staff assessing DIB
  analyst                     resilience, concentration, and choke-point risk (Section A
                              vulnerability questions)

  entrepreneurial finance     Kauffman / NBER researchers and VC/PE analysts
  researcher                  benchmarking SBIR-firm capital formation (F-area questions)

  pipeline engineer           Internal developer maintaining the ETL pipeline
                              (infrastructure specs: imputation, graph labels, NAICS
                              enricher consolidation, iterative refresh). Use this actor
                              only when the feature has no direct research-output facing.

Avoid: "data analyst", "user", "developer" as stand-alone actors in research-output specs.
-->
