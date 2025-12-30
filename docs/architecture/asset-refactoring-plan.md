# Phase 3: Asset File Refactoring Plan

**Status**: Ready for Implementation
**Created**: 2025-11-05
**Estimated Duration**: 2-3 weeks
**Risk Level**: Medium (requires careful migration)

## Executive Summary

This plan details the refactoring of three large asset files (totaling 8,828 lines) into focused, maintainable modules. The refactoring will improve code organization, reduce merge conflicts, and make the codebase more approachable for new contributors.

## Problem Statement

### Current State

| File | Lines | Assets | Checks | Helpers | Issues |
|------|-------|--------|--------|---------|--------|
| `cet_assets.py` | 3,593 | 19 | 3 | 24 | Hard to navigate, multiple concerns *(legacy)* |
| `uspto_assets.py` | 2,992 | 33 | 8 | 56 | Too many assets in one file *(legacy)* |
| `transition_assets.py` | 2,243 | 18 | 8 | 28 | Mix of extraction, transformation, loading *(legacy)* |
| **Total** | **8,828** | **70** | **19** | **108** | **Maintainability issues** |

> Note: these legacy files have been replaced by packages (`src/assets/cet/`, `src/assets/uspto/`,
> `src/assets/transition/`). The historical metrics above are preserved for context.

### Pain Points

1. **Hard to Navigate** - Finding specific assets requires scrolling through thousands of lines
2. **Merge Conflicts** - Multiple developers editing same file causes conflicts
3. **Cognitive Load** - Understanding asset dependencies is difficult
4. **Testing Complexity** - Large files make unit testing harder
5. **Code Review** - Reviewers struggle with context in large PRs

## Goals

### Primary Goals

- ✅ Reduce file sizes to < 1,000 lines per module
- ✅ Group related assets together logically
- ✅ Maintain all existing functionality (zero breaking changes)
- ✅ Preserve Dagster asset dependencies
- ✅ Keep test coverage at current levels

### Secondary Goals

- ✅ Improve code discoverability
- ✅ Enable parallel development on different modules
- ✅ Simplify code reviews
- ✅ Document asset groupings and relationships

## Refactoring Strategy

### Approach: Incremental Module Extraction

We'll use a **safe, incremental approach**:

1. **Create new module structure** alongside existing files
2. **Move assets one group at a time** with tests
3. **Update imports gradually**
4. **Verify Dagster recognizes all assets**
5. **Delete old files** only after full validation

### Risk Mitigation

- ✅ Keep existing files until migration complete
- ✅ Test asset loading after each move
- ✅ Use feature flags if needed
- ✅ Maintain backward compatibility during transition

---

## Detailed Refactoring Plans

## 1. CET Assets Refactoring

### Historical Structure (cet_assets.py - 3,593 lines)

**Assets (19):**

- Taxonomy: `raw_cet_taxonomy` (1)
- Classifications: `enriched_cet_award_classifications`, `enriched_cet_patent_classifications` (2)
- Training: `train_cet_patent_classifier`, `cet_award_training_dataset` (2)
- Analytics: `transformed_cet_analytics`, `transformed_cet_analytics_aggregates` (2)
- Validation: `raw_cet_human_sampling`, `validated_cet_iaa_report`, `validated_cet_drift_detection` (3)
- Company: `transformed_cet_company_profiles` (1)
- Loading: `loaded_cet_areas`, `loaded_award_cet_enrichment`, `loaded_company_cet_enrichment`, + 5 more (8)

**Asset Checks (3):**

- `cet_taxonomy_completeness_check`
- `cet_award_classifications_quality_check`
- `cet_company_profiles_check`

### Proposed Structure

```text
src/assets/cet/
├── __init__.py                      # Re-exports all assets (50 lines)
├── taxonomy.py                      # Taxonomy loading + checks (~600 lines)
│   ├── raw_cet_taxonomy
│   ├── cet_taxonomy_completeness_check
│   └── taxonomy_to_dataframe() helper
│
├── classifications.py               # Award & patent classifications (~900 lines)
│   ├── enriched_cet_award_classifications
│   ├── enriched_cet_patent_classifications
│   ├── cet_award_classifications_quality_check
│   └── classification helpers
│
├── training.py                      # ML training assets (~700 lines)
│   ├── train_cet_patent_classifier
│   ├── cet_award_training_dataset
│   └── training helpers
│
├── analytics.py                     # Analytics & aggregation (~700 lines)
│   ├── transformed_cet_analytics
│   ├── transformed_cet_analytics_aggregates
│   └── analytics helpers
│
├── validation.py                    # Human validation & drift (~600 lines)
│   ├── raw_cet_human_sampling
│   ├── validated_cet_iaa_report
│   ├── validated_cet_drift_detection
│   └── validation helpers
│
├── company.py                       # Company profiles (~400 lines)
│   ├── transformed_cet_company_profiles
│   ├── cet_company_profiles_check
│   └── company helpers
│
├── loading.py                       # Neo4j loading (~500 lines)
│   ├── loaded_cet_areas
│   ├── loaded_award_cet_enrichment
│   ├── loaded_company_cet_enrichment
│   ├── 5 more loading assets
│   └── _get_neo4j_client() helper
│
└── utils.py                         # Shared utilities (~150 lines)
    ├── save_dataframe_parquet()
    ├── _read_parquet_or_ndjson()
    ├── _serialize_metrics()
    └── Other helpers
```

**Benefits:**

- Clear separation of concerns
- Each module < 1,000 lines
- Easy to find specific functionality
- Parallel development on different areas

---

## 2. USPTO Assets Refactoring

### Current Structure (uspto_assets.py - 2,992 lines)

**Assets (33):**

- Raw extraction: 5 raw assets (`raw_uspto_assignments`, etc.)
- Parsing: 5 parsed assets (`parsed_uspto_assignments`, etc.)
- Validation: 6 validated assets + 3 checks
- Transformation: 8 transformed assets
- Loading: 9 loading assets + 5 checks

**Asset Checks (8):**

- USPTO-specific checks (rf_id, completeness, referential integrity, etc.)

### Proposed Structure

```text
src/assets/uspto/
├── __init__.py                      # Re-exports all assets (80 lines)
├── extraction.py                    # Raw file extraction (~400 lines)
│   ├── raw_uspto_assignments
│   ├── raw_uspto_assignees
│   ├── raw_uspto_assignors
│   ├── raw_uspto_documentids
│   ├── raw_uspto_conveyances
│   ├── _get_input_dir() helper
│   └── _discover_table_files() helper
│
├── parsing.py                       # DTA file parsing (~500 lines)
│   ├── parsed_uspto_assignments
│   ├── validated_uspto_assignees
│   ├── validated_uspto_assignors
│   ├── parsed_uspto_documentids
│   ├── parsed_uspto_conveyances
│   ├── _attempt_parse_sample() helper
│   └── _make_parsing_check() helper
│
├── validation.py                    # Schema validation + checks (~700 lines)
│   ├── validated_uspto_assignments
│   ├── uspto_rf_id_asset_check
│   ├── uspto_completeness_asset_check
│   ├── uspto_referential_asset_check
│   ├── _build_validator_config() helper
│   └── _extract_table_results() helper
│
├── transformation.py                # Patent transformations (~600 lines)
│   ├── 8 transformation assets
│   ├── Related asset checks (2)
│   └── Transformation helpers
│
├── loading.py                       # Neo4j loading (~600 lines)
│   ├── 9 loading assets
│   ├── Loading checks (3)
│   └── Loading helpers
│
└── utils.py                         # Shared utilities (~200 lines)
    ├── _now_suffix()
    ├── _ensure_dir()
    ├── _load_sbir_index()
    ├── _serialize_assignment()
    ├── _iter_small_sample()
    ├── _coerce_str()
    └── Other helpers
```

**Benefits:**

- Clear pipeline stages (extract → parse → validate → transform → load)
- Each module represents one stage
- Easy to test individual stages
- Reduces complexity per file

---

## 3. Transition Assets Refactoring

### Current Structure (transition_assets.py - 2,243 lines)

**Assets (18):**

- Contracts: `raw_contracts`, `validated_contracts_sample` (2)
- Vendor: `enriched_vendor_resolution` (1)
- Scoring: `transformed_transition_scores` (1)
- Evidence: `transformed_transition_evidence` (1)
- Detections: `transformed_transition_detections` (1)
- Analytics: `transformed_transition_analytics` (1)
- Loading: `loaded_transitions` + more (2)
- Evaluation: Additional assets (9)

**Asset Checks (8):**

- Quality checks for each stage

### Proposed Structure

```text
src/assets/transition/
├── __init__.py                      # Re-exports all assets (50 lines)
├── contracts.py                     # Contract extraction (~600 lines)
│   ├── raw_contracts
│   ├── validated_contracts_sample
│   ├── contracts_sample_quality_check
│   └── Contract helpers
│
├── vendor_resolution.py             # Vendor matching (~400 lines)
│   ├── enriched_vendor_resolution
│   ├── vendor_resolution_quality_check
│   └── Vendor helpers
│
├── scoring.py                       # Transition scoring (~500 lines)
│   ├── transformed_transition_scores
│   ├── transition_scores_quality_check
│   └── Scoring helpers
│
├── evidence.py                      # Evidence generation (~400 lines)
│   ├── transformed_transition_evidence
│   ├── transition_evidence_quality_check
│   └── Evidence helpers
│
├── detections.py                    # Detection consolidation (~400 lines)
│   ├── transformed_transition_detections
│   ├── transition_detections_quality_check
│   └── Detection helpers
│
├── analytics.py                     # Analytics & evaluation (~500 lines)
│   ├── transformed_transition_analytics
│   ├── transition_analytics_quality_check
│   └── Analytics helpers
│
├── loading.py                       # Neo4j loading (~300 lines)
│   ├── loaded_transitions
│   ├── transition_node_count_check
│   ├── Additional loading assets
│   └── Loading helpers
│
└── utils.py                         # Shared utilities (~150 lines)
    ├── save_dataframe_parquet()
    ├── write_json()
    ├── _prepare_transition_dataframe()
    ├── _get_neo4j_driver()
    └── Other helpers
```

**Benefits:**

- Mirrors the transition detection pipeline stages
- Clear progression from contracts → scoring → evidence → loading
- Each module is a logical unit
- Easy to understand data flow

---

## Migration Strategy

### Phase-by-Phase Approach

#### Step 1: Create Module Structure (1 day)

```bash
# Create directory structures
mkdir -p src/assets/cet src/assets/uspto src/assets/transition

# Create __init__.py files
touch src/assets/cet/__init__.py
touch src/assets/uspto/__init__.py
touch src/assets/transition/__init__.py
```

#### Step 2: Extract One Module at a Time (Per File)

**For each asset file:**

1. **Start with utilities** (lowest dependencies)
   - Move helper functions to `utils.py`
   - Update imports in original file
   - Test asset loading

2. **Move one asset group** (e.g., taxonomy.py)
   - Copy assets + checks to new module
   - Add re-export in `__init__.py`
   - Update imports in original file
   - Test with `dagster dev` - verify assets appear
   - Run existing tests

3. **Repeat for each module** (incremental)
   - Move next logical group
   - Update imports
   - Test continuously

4. **Clean up** (final step)
   - Remove old file
   - Update imports in `src/definitions.py`
   - Run full test suite
   - Verify Dagster UI shows all assets

### Testing Strategy

**After each module extraction:**

```bash
# 1. Verify Python imports work
python -c "from src.assets.cet.taxonomy import raw_cet_taxonomy"

# 2. Verify Dagster recognizes assets
dagster asset list | grep cet_taxonomy

# 3. Run unit tests
pytest tests/unit/test_cet_* -v

# 4. Check Dagster UI
dagster dev  # Visit http://localhost:3000
# Verify: All assets appear, dependencies intact
```

**Integration testing:**

- Run small test materialization
- Verify outputs are identical to before
- Check asset lineage in Dagster UI

---

## Implementation Plan

### Week 1: CET Assets (3,593 lines → 7 modules)

**Day 1: Setup + Utils**

- Create `src/assets/cet/` structure
- Move shared utilities to `utils.py`
- Create `__init__.py` with re-exports

**Day 2: Taxonomy + Classifications**

- Extract `taxonomy.py` (~600 lines)
- Extract `classifications.py` (~900 lines)
- Test Dagster asset loading

**Day 3: Training + Analytics**

- Extract `training.py` (~700 lines)
- Extract `analytics.py` (~700 lines)
- Run integration tests

**Day 4: Validation + Company**

- Extract `validation.py` (~600 lines)
- Extract `company.py` (~400 lines)
- Test all asset checks

**Day 5: Loading + Cleanup**

- Extract `loading.py` (~500 lines)
- Delete `cet_assets.py`
- Update `src/definitions.py`
- Full test suite

### Week 2: USPTO Assets (2,992 lines → 6 modules)

**Day 1: Setup + Utils**

- Create `src/assets/uspto/` structure
- Move shared utilities

**Day 2-3: Extraction → Validation**

- Extract `extraction.py`, `parsing.py`, `validation.py`
- Test each module

**Day 4: Transformation + Loading**

- Extract `transformation.py`, `loading.py`
- Integration testing

**Day 5: Cleanup**

- Delete `uspto_assets.py`
- Update imports
- Full test suite

### Week 3: Transition Assets (2,243 lines → 8 modules)

**Day 1: Setup + Utils**

- Create `src/assets/transition/` structure
- Move shared utilities

**Day 2-3: Contracts → Evidence**

- Extract `contracts.py`, `vendor_resolution.py`, `scoring.py`, `evidence.py`

**Day 4: Detections → Loading**

- Extract `detections.py`, `analytics.py`, `loading.py`

**Day 5: Final Cleanup + Documentation**

- Delete `transition_assets.py`
- Update all imports
- Document new structure
- Create ADR

---

## Import Updates

### Before Refactoring

```python
# In src/definitions.py
from .assets.cet import (
    raw_cet_taxonomy,
    enriched_cet_award_classifications,
    # ... 19 more assets
)
```

### After Refactoring

```python
# In src/definitions.py
from .assets.cet import (
    raw_cet_taxonomy,
    enriched_cet_award_classifications,
    # ... all assets imported from cet/__init__.py
)
```

**Key Point**: The `__init__.py` files handle all re-exports, so import statements in `definitions.py` change minimally.

---

## Testing Requirements

### Unit Tests

**Update test imports:**

```python
# OLD
from src.assets.cet import raw_cet_taxonomy

# NEW
from src.assets.cet.taxonomy import raw_cet_taxonomy
# OR (if using __init__ re-exports)
from src.assets.cet import raw_cet_taxonomy
```

**Test files to update:**

- `tests/unit/test_cet_award_asset.py`
- `tests/unit/test_cet_patent_asset.py`
- `tests/unit/test_uspto_assets.py`
- `tests/unit/transition/test_transition_assets_unit.py`

### Integration Tests

**Verify:**

- All assets load in Dagster
- Asset dependencies preserved
- Asset materialization produces same results
- Neo4j loading works correctly

### Manual Testing Checklist

- [ ] Run `dagster dev` - all assets visible
- [ ] Check asset lineage graph - dependencies intact
- [ ] Materialize small subset - outputs identical
- [ ] Run full test suite - all passing
- [ ] Check CI/CD pipeline - no failures

---

## Rollback Plan

If issues arise, rollback is straightforward:

1. **Revert commits** - Each module extraction is one commit
2. **Restore old files** - Keep original files until confirmed working
3. **Update imports** - Revert import changes in `definitions.py`

**Timeline**: Rollback takes < 30 minutes

---

## Success Criteria

### Quantitative Metrics

- [ ] All asset files < 1,000 lines
- [ ] Zero functionality regressions
- [ ] 100% test pass rate maintained
- [ ] All 70 assets + 19 checks working
- [ ] Dagster UI shows complete asset graph

### Qualitative Metrics

- [ ] Code is easier to navigate
- [ ] Developers can work on modules independently
- [ ] Code reviews are faster
- [ ] New contributors can find code easily
- [ ] Documentation is clear

---

## Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Import errors break Dagster | High | Medium | Test after each change, keep old files |
| Asset dependencies lost | High | Low | Verify lineage graph, integration tests |
| Test failures | Medium | Medium | Update test imports incrementally |
| Merge conflicts during migration | Medium | High | Coordinate with team, use feature branch |
| Performance degradation | Low | Low | Benchmark asset loading times |

---

## Documentation Updates

### Create New Docs

1. **Architecture Documentation**
   - Document new asset module structure
   - Explain grouping rationale
   - Show asset dependency diagrams

2. **Developer Guide**
   - How to find specific assets
   - Where to add new assets
   - Module organization principles

3. **ADR (Architecture Decision Record)**
   - `docs/decisions/ADR-003-asset-file-refactoring.md`
   - Context, decision, consequences

### Update Existing Docs

- `README.md` - Update asset organization section
- `docs/index.md` - Add links to new structure
- Any diagrams showing asset files

---

## Timeline Summary

| Week | Focus | Files | Deliverables |
|------|-------|-------|--------------|
| Week 1 | CET Assets | 3,593 lines → 7 modules | 19 assets working, tests passing |
| Week 2 | USPTO Assets | 2,992 lines → 6 modules | 33 assets working, tests passing |
| Week 3 | Transition Assets | 2,243 lines → 8 modules | 18 assets working, docs complete |

**Total Duration**: ~15 working days (3 weeks)

**Estimated Effort**: 60-80 hours

---

## Next Steps

1. **Review this plan** with team
2. **Get approval** for timeline and approach
3. **Create feature branch** for refactoring
4. **Start Week 1** (CET assets)
5. **Daily check-ins** to track progress

---

## Questions for Team

1. **Timing**: Is 3 weeks acceptable, or do we need to accelerate?
2. **Coordination**: Who else is working on these files? Need freeze?
3. **Testing**: Any additional integration tests needed?
4. **Documentation**: What level of detail needed in ADR?
5. **Rollout**: Feature flag, or direct merge after testing?

---

## Conclusion

This refactoring will significantly improve code maintainability while preserving all functionality. The incremental approach minimizes risk, and comprehensive testing ensures no regressions.

**Recommendation**: Proceed with Week 1 (CET Assets) as a pilot. If successful, continue with USPTO and Transition assets.

**Ready to start**: Yes ✅
