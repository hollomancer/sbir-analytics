# Research Plan Alignment

Maps the [SBIR Analytics Research Plan](# "Obsidian: SBIR Analytics Research Plan — Summary") milestones to codebase components, Kiro specs, and remaining work.

## Milestone → Codebase Status

### M1: DOD Leverage Ratio Replication — PARTIAL

**Goal:** Reproduce NASEM's 4:1 non-SBIR-to-SBIR funding ratio for DOD firms.

| Component | Status | Location |
|-----------|--------|----------|
| FPDS contract extraction | Built | `src/tools/phase0/extract_fpds_contracts.py` |
| Entity resolution (UEI/DUNS) | Built | `src/tools/phase0/resolve_entities.py`, `src/transition/features/vendor_resolver.py` |
| Contract analytics (DuckDB) | Built | `src/transition/performance/contract_analytics.py` |
| Vendor crosswalk | Built | `src/transition/features/vendor_crosswalk.py` |
| Company categorization | 77% spec | `.kiro/specs/company-categorization/` |
| **Leverage ratio computation** | **Missing** | Needs: ratio calculator, cohort stratification, NASEM reconciliation |
| **Agency comparison (DOE)** | **Missing** | Needs: civilian agency extraction, cross-agency ratio |

**Gap:** Core data plumbing exists. Missing the actual leverage ratio computation and NASEM reconciliation logic.

### M2: Patent Linkage and Spillover — PARTIAL

**Goal:** Link SBIR awards to USPTO patents, compute marginal cost per patent, trace citation networks.

| Component | Status | Location |
|-----------|--------|----------|
| USPTO data extraction | Built | `src/extractors/` (USPTO bulk download pipeline) |
| Patent transformer | Built | `src/transformers/patent_transformer.py` |
| Patent-award fuzzy matching | Built | `PatentAssignmentTransformer` with rapidfuzz |
| Patent analyzer (transition) | Built | `src/transition/features/patent_analyzer.py` |
| USPTO Lambda downloads | 90% spec | `.kiro/specs/uspto-lambda-downloads/` |
| USPTO data validators | Built | `src/quality/uspto_validators.py` |
| **Marginal cost per patent** | **Missing** | Needs: cost calculator linking award amounts to patent counts |
| **Citation network/spillover** | **Missing** | Needs: citation graph builder, spillover multiplier computation |
| **NIH/DOE benchmark replication** | **Missing** | Needs: agency-specific cost benchmarks |

**Gap:** Patent extraction and linking exists. Missing the analytical layer: cost metrics, citation networks, spillover tracing.

### M3: Cross-Agency Technology Taxonomy — PARTIAL

**Goal:** Deploy CET classifier across full SBIR.gov corpus for unified cross-agency view.

| Component | Status | Location |
|-----------|--------|----------|
| CET keyword classifier | Built | `src/transition/features/cet_analyzer.py` |
| Topic extraction | Built | `src/tools/mission_a/extract_topics.py` |
| Topic clustering | Built | `src/tools/mission_a/cluster_topics.py` |
| Portfolio metrics | Built | `src/tools/mission_a/compute_portfolio_metrics.py` |
| Gap detection | Built | `src/tools/mission_a/detect_gaps.py` |
| PaECTER embeddings | 30% spec | `.kiro/specs/paecter_analysis_layer/` |
| **Full corpus classification** | **Missing** | Needs: batch classifier run on all SBIR.gov awards |
| **Cross-agency visualization** | **Missing** | Needs: agency-level technology allocation output |

**Gap:** Classifier and topic tools exist. Missing the full-corpus batch run and cross-agency output format.

### M4: Fiscal Return Estimation — EXISTS (archived spec, 100% complete)

**Goal:** Connect StateIO fiscal modeling to SBIR award/outcome data for Treasury return estimates.

| Component | Status | Location |
|-----------|--------|----------|
| Fiscal ROI calculator | Built | `src/transformers/fiscal/roi.py` |
| Tax estimation | Built | `src/tools/mission_c/tax_estimation.py` |
| StateIO adapter | Built | `src/transformers/r_stateio_adapter.py`, `r_stateio_functions.py` |
| StateIO multipliers | Built | `src/tools/mission_c/stateio_multipliers.py` |
| NAICS-BEA crosswalk | Built | `src/tools/mission_c/naics_to_bea_crosswalk.py` |
| Sensitivity analysis | Built | `src/transformers/fiscal/sensitivity.py` |
| District allocator | Built | `src/transformers/fiscal/district_allocator.py` |
| Fiscal audit trail | Built | `src/utils/fiscal_audit_trail.py` |
| Fiscal pipeline | Built | `src/transformers/sbir_fiscal_pipeline.py` |

**Gap:** Substantially complete. Archived spec at 100%. May need refresh to connect M1/M2 outputs as inputs.

### M5: Continuous Monitoring Architecture — PARTIAL

**Goal:** Operationalize M1–M4 as rolling analytics.

| Component | Status | Location |
|-----------|--------|----------|
| Weekly data refresh | 85% spec | `.kiro/specs/weekly-award-data-refresh/` |
| Dagster asset pipeline | Built | `src/assets/` |
| Autodev loop | Built | `src/autodev/` |
| MCP agent tools | Spec exists | `.kiro/specs/mcp_agent_tools/` |
| **Rolling analytics API** | **Missing** | Needs: snapshot generation, quarter-over-quarter comparison |
| **User-facing dashboard** | **Missing** | Needs: query interface for current-quarter snapshots |

**Gap:** Scheduling and pipeline infrastructure exists. Missing the user-facing query/snapshot layer.

## Priority Matrix for Autodev

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

These questions need answers before M1/M2 sprints begin:

- [ ] Graph DB state: which data sources loaded, entity types populated, linkages exist?
- [ ] Entity resolution: UEI-based, DUNS-based, name-matching, hybrid? Match rate?
- [ ] Classifier state: trained on what taxonomy, needs retraining or re-running?
- [ ] FPDS data: pulled? Linked to entities? How current?
- [ ] Infrastructure: which CDK stacks deployed vs. IaC-only?
