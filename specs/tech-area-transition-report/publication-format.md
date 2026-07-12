# Tech-Area Transition Report — Publication Format (policy leaders)

**Status:** normative for new and revised findings documents  
**Applies to:** `docs/*_sbir_transition_findings.md` (technical) and optional `docs/*_sbir_policy_brief.md` (executive)

## Two-layer model

| Layer | Audience | File pattern | Content |
|-------|----------|--------------|---------|
| **Policy brief** | S&T policy leaders, NSET reviewers | `docs/<area>_sbir_policy_brief.md` | Decisions, headline table, interpretations, language guardrails |
| **Technical findings** | Analysts, reproducibility | `docs/<area>_sbir_transition_findings.md` | Full evidence, instrument detail, methodological notes |
| **Appendix** | Implementers | `docs/<area>_phase3_methodology.md` or `data/reports/<area>/methodology_stub.md` | Cohort defs, matching rules, confidence tiers, CLI |

Policy briefs may be produced by restructuring technical findings (nanotech) or as a **provisional cohort brief** when channel signals are absent (quantum, hypersonics v1).

## Required policy-brief elements

### 1. Title and audience line

- Title pattern: **`<Technology> SBIR/STTR Phase II Outcomes: What Policy Leaders Can Safely Conclude`**
- **Prepared for:** named audience (not generic "analysis team")
- **Status:** Provisional; bounded estimates, not final program rates
- **Data through:** explicit vintages

### 2. Bottom line (first screen)

One paragraph + **headline table** with three columns:

| Measure | Result | How to use it |

Every row must state what the number **is** (evidence-channel observation) and what it **is not** (e.g. not a transition rate unless defensible).

### 3. Clarity pass (when revising)

**What changed in this clarity and rigor pass** — four bullets:

1. Separate facts, interpretations, and policy implications.
2. Use **observable evidence** unless the measure supports a rate claim.
3. Make uncertainty operational (decompose indeterminate / censored / identity / coding gaps).
4. Define the decision standard (what can be used for cross-agency comparison).

### 4. Findings structure

Each finding:

- **Fact block** — tables and counts first
- **Policy interpretation** — one short subsection (optional **Rigor caveat** for floors/ceilings)
- Avoid burying the policy takeaway in methodology prose

### 5. What policy leaders should take away

Numbered list (5–8 items), imperative voice, actionable for reporting standards.

### 6. Language to avoid

Explicit **Avoid / Use** pairs for phrases that overclaim:

- "transition rate" → "observable evidence from channel X"
- "did not commercialize" → "remain indeterminate after recovery checks applied"
- "patents prove commercialization" → "commercialization-adjacent evidence"
- "FPDS shows agency performance" → "FPDS-coded Phase III is a procurement-system signal with agency-specific coverage"

### 7. Recommended publication structure

1. One-page executive summary + headline table
2. Evidence-channel findings (procurement, private capital, acquisition, patents, subawards — as available)
3. Measurement limits and why they matter for policy
4. Recommended agency reporting standard
5. Technical appendix (link, do not inline)

## Provisional reports (signals absent)

When digest / Form D / M&A artifacts are missing, the policy brief **must**:

- Publish cohort headline table only (Method A size, agency mix, recency, triangulation)
- Include a **Channel status** row per missing artifact (Not computed — not zero)
- State **what leaders can conclude now** vs **what requires the next pipeline step**
- Reuse language guardrails (do not imply 0% transition)

## Area-specific adaptations

| Area | Policy emphasis |
|------|-----------------|
| Nanotechnology | Dual pathway (procurement vs private capital); dark-majority triage |
| Quantum (small N) | Instrument-dependent counts; small-N warning on any future rate |
| Hypersonics | Procurement-first; subaward channel priority over Form D |

## Generator hooks (future)

`build_tech_area_cohort.py` could emit a `policy_brief_stub.md` alongside `methodology_stub.md` using `overlap_summary.json` + agency aggregates. Not implemented in v1 — hand-authored briefs follow this spec.
