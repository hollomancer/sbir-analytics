# Research Plan Alignment

Maps the [SBIR Analytics Research Plan](# "Obsidian: SBIR Analytics Research Plan — Summary") milestones to codebase components, Kiro specs, and remaining work.

## What We Are Building

The awards database already exists (SAM.gov, USAspending, FPDS, SBIR.gov). We are **not** duplicating it. We are building the **outcomes layer** — the connective tissue between award records and downstream effects that no existing system provides.

Four linkages define the outcomes layer:

| Linkage | What it connects | Why it doesn't exist today |
|---------|-----------------|---------------------------|
| **Award → Follow-on Contract** (M1) | SBIR Phase II → non-SBIR DOD contract | USAspending shows both but doesn't flag the relationship |
| **Award → Patent** (M2) | SBIR award → USPTO patent | Government interest statements exist but aren't joined to award DBs |
| **Award → Outcome Through Primes** (M2 ext) | SBIR tech → prime contractor system | FPDS doesn't track sub-tier; patent citations trace IP flow where procurement can't |
| **Award → Firm-Level Outcomes** (M4 inputs) | Award → revenue, employment, VC, acquisitions | Not in USAspending; NASEM used surveys. We connect programmatically. |

Each milestone produces an analytical output that (a) replicates or exceeds a specific NASEM claim, and (b) acts as continuous monitoring that informs future Academies work. If the pipeline cannot reproduce a NASEM finding faster and with more granularity, it is not yet ready.

**Causal inference disclaimer:** This pipeline does portfolio characterization, outcomes linkage, and fiscal estimation. It does NOT do impact evaluation in the counterfactual sense.

## Milestone → Codebase Status

### M1: DOD Leverage Ratio Replication — PARTIAL

**Linkage:** Award → Follow-on Contract

**Goal:** Reproduce NASEM's 4:1 non-SBIR-to-SBIR funding ratio for DOD firms. USAspending can show Firm X got SBIR Phase II then later got a non-SBIR DOD contract — but it doesn't flag the relationship. Our entity resolution + FPDS pipeline automates this linkage at scale.

| Component | Status | Location |
|-----------|--------|----------|
| FPDS contract extraction | Built | `packages/sbir-analytics/sbir_analytics/tools/phase0/extract_fpds_contracts.py` |
| Entity resolution (UEI/DUNS) | Built | `packages/sbir-analytics/sbir_analytics/tools/phase0/resolve_entities.py`, `packages/sbir-ml/sbir_ml/transition/features/vendor_resolver.py` |
| Contract analytics (DuckDB) | Built | `packages/sbir-ml/sbir_ml/transition/performance/contract_analytics.py` |
| Vendor crosswalk | Built | `packages/sbir-ml/sbir_ml/transition/features/vendor_crosswalk.py` |
| Company categorization | 77% spec | `.kiro/specs/company-categorization/` |
| **Leverage ratio computation** | **Missing** | Needs: ratio calculator, cohort stratification, NASEM reconciliation |
| **Agency comparison (DOE)** | **Missing** | Needs: civilian agency extraction, cross-agency ratio |

**Gap:** Core data plumbing exists. Missing the actual leverage ratio computation and NASEM reconciliation logic.

### M2: Patent Linkage and Spillover — PARTIAL

**Linkage:** Award → Patent + Award → Outcome Through Primes

**Goal:** Link SBIR awards to USPTO patents, compute marginal cost per patent, trace citation networks. USAspending has no patent field. USPTO government interest statements contain grant/contract numbers but aren't joined back to award databases. Our pipeline performs this join. When SBIR tech enters a prime's system via subcontract, FPDS can't see it — patent citation networks trace IP flow where procurement data cannot.

| Component | Status | Location |
|-----------|--------|----------|
| USPTO data extraction | Built | `sbir_etl/extractors/` (USPTO bulk download pipeline) |
| Patent transformer | Built | `sbir_etl/transformers/patent_transformer.py` |
| Patent-award fuzzy matching | Built | `PatentAssignmentTransformer` with rapidfuzz |
| Patent analyzer (transition) | Built | `packages/sbir-ml/sbir_ml/transition/features/patent_analyzer.py` |
| USPTO Lambda downloads | 90% spec | `.kiro/specs/uspto-lambda-downloads/` |
| USPTO data validators | Built | `sbir_etl/quality/uspto_validators.py` |
| **Marginal cost per patent** | **Missing** | Needs: cost calculator linking award amounts to patent counts |
| **Citation network/spillover** | **Missing** | Needs: citation graph builder, spillover multiplier computation |
| **NIH/DOE benchmark replication** | **Missing** | Needs: agency-specific cost benchmarks |

**Gap:** Patent extraction and linking exists. Missing the analytical layer: cost metrics, citation networks, spillover tracing.

### M3: Cross-Agency Technology Taxonomy — PARTIAL

**What NASEM cannot do:** Every study is siloed by committee mandate. No unified view of what the federal SBIR portfolio is buying.

**Goal:** Deploy CET classifier across full SBIR.gov corpus for unified cross-agency view.

| Component | Status | Location |
|-----------|--------|----------|
| CET keyword classifier | Built | `packages/sbir-ml/sbir_ml/transition/features/cet_analyzer.py` |
| Topic extraction | Built | `packages/sbir-analytics/sbir_analytics/tools/mission_a/extract_topics.py` |
| Topic clustering | Built | `packages/sbir-analytics/sbir_analytics/tools/mission_a/cluster_topics.py` |
| Portfolio metrics | Built | `packages/sbir-analytics/sbir_analytics/tools/mission_a/compute_portfolio_metrics.py` |
| Gap detection | Built | `packages/sbir-analytics/sbir_analytics/tools/mission_a/detect_gaps.py` |
| PaECTER embeddings | 30% spec | `.kiro/specs/paecter_analysis_layer/` |
| **Full corpus classification** | **Missing** | Needs: batch classifier run on all SBIR.gov awards |
| **Cross-agency visualization** | **Missing** | Needs: agency-level technology allocation output |

**Gap:** Classifier and topic tools exist. Missing the full-corpus batch run and cross-agency output format.

### M4: Fiscal Return Estimation — EXISTS (archived spec, 100% complete)

**Linkage:** Award → Firm-Level Outcomes

**What NASEM cannot do:** Measures proxies (revenue, patents, jobs). No study estimates returns to Treasury.

**Goal:** Connect StateIO fiscal modeling to SBIR award/outcome data for Treasury return estimates. Revenue, employment, VC, acquisitions — none in USAspending. NASEM used surveys. Our pipeline connects programmatically.

| Component | Status | Location |
|-----------|--------|----------|
| Fiscal ROI calculator | Built | `sbir_etl/transformers/fiscal/roi.py` |
| Tax estimation | Built | `packages/sbir-analytics/sbir_analytics/tools/mission_c/tax_estimation.py` |
| StateIO adapter | Built | `sbir_etl/transformers/r_stateio_adapter.py`, `r_stateio_functions.py` |
| StateIO multipliers | Built | `packages/sbir-analytics/sbir_analytics/tools/mission_c/stateio_multipliers.py` |
| NAICS-BEA crosswalk | Built | `packages/sbir-analytics/sbir_analytics/tools/mission_c/naics_to_bea_crosswalk.py` |
| Sensitivity analysis | Built | `sbir_etl/transformers/fiscal/sensitivity.py` |
| District allocator | Built | `sbir_etl/transformers/fiscal/district_allocator.py` |
| Fiscal audit trail | Built | `sbir_etl/utils/fiscal_audit_trail.py` |
| Fiscal pipeline | Built | `sbir_etl/transformers/sbir_fiscal_pipeline.py` |

**Gap:** Substantially complete. Archived spec at 100%. May need refresh to connect M1/M2 outputs as inputs.

### M5: Continuous Monitoring Architecture — PARTIAL

**What NASEM cannot do:** Quadrennial cycle. Four years between snapshots. No rolling analytics.

**Goal:** Operationalize M1–M4 as rolling analytics.

| Component | Status | Location |
|-----------|--------|----------|
| Weekly data refresh | 85% spec | `.kiro/specs/weekly-award-data-refresh/` |
| Dagster asset pipeline | Built | `packages/sbir-analytics/sbir_analytics/assets/` |
| MCP agent tools | Spec exists | `.kiro/specs/mcp_agent_tools/` |
| **Rolling analytics API** | **Missing** | Needs: snapshot generation, quarter-over-quarter comparison |
| **User-facing dashboard** | **Missing** | Needs: query interface for current-quarter snapshots |

**Gap:** Scheduling and pipeline infrastructure exists. Missing the user-facing query/snapshot layer.

## Priority Matrix

### Immediate (finish what's started — highest ROI)
1. **`company-categorization`** (77%) — Entity categorization unlocks M1 leverage ratios
2. **`uspto-lambda-downloads`** (90%) — URL verification unlocks M2 patent pipeline refresh
3. **`weekly-award-data-refresh`** (85%) — PR automation unlocks M5 continuous monitoring

### Next Sprint (M1 + M3 parallel)
4. **New: `leverage-ratio-analysis`** — M1 core: ratio computation, cohort stratification, NASEM reconciliation
5. **`paecter_analysis_layer`** (30%) — Embeddings infrastructure for M3 full-corpus classification
6. **New: `cross-agency-taxonomy`** — M3 core: batch classifier, agency-level output, visualization

### Following Sprint (M2 analytical layer)
7. **New: `patent-cost-spillover`** — M2 core: marginal cost calculator, citation network builder, spillover tracing

### Integration Sprint (M4 refresh + M5 operationalization)
8. **M4 refresh** — Connect M1/M2 outputs to existing fiscal pipeline
9. **New: `monitoring-snapshot-api`** — M5 core: rolling analytics, quarterly snapshots

## Phase 0 Checklist (from Research Plan)

Audit completed 2026-03-13. Status: **ready for Phase 1**.

- [x] **Graph DB state:** Neo4j 5.x with Company, Patent, Award, CET nodes. SBIR.gov, SAM.gov, USAspending, USPTO all loaded. Entity linkages via canonical IDs. 3,500+ lines of Neo4j loader code.
- [x] **Entity resolution:** Hybrid 6-step pipeline: UEI exact → DUNS exact → CAGE code → Name+State+NAICS deterministic → rapidfuzz (75-90 thresholds) → LLM tiebreaker. 85%+ deterministic match rate. Gold set calibration. Confidence scoring (1.0 deterministic, 0.5-0.95 fuzzy). (`packages/sbir-analytics/sbir_analytics/tools/phase0/resolve_entities.py`, 376 lines)
- [x] **Classifier state:** CET classifier trained on 21 NSTC Critical & Emerging Technology categories. TF-IDF + keyword boosting + logistic regression with probability calibration. Production-ready with ≥60% high-confidence target. Full training pipeline in `packages/sbir-analytics/sbir_analytics/assets/cet/training.py`.
- [x] **FPDS data:** Pulled via USAspending PostgreSQL dump streaming. Linked to entities via vendor crosswalk. Refresh: daily (FPDS), monthly (USAspending bulk). DuckDB analytics for 6.7M+ contracts. (`packages/sbir-analytics/sbir_analytics/tools/phase0/extract_fpds_contracts.py`, `packages/sbir-ml/sbir_ml/transition/performance/contract_analytics.py`)
- [x] **Infrastructure:** CDK stacks defined (Storage → Security → Batch). 6+ GitHub Actions workflows active (CI, data-refresh, ML jobs, nightly security). Docker + Dagster orchestration. Deployment status to AWS uncertain — verify before M5 operationalization.
