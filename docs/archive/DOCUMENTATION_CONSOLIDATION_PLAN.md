# Documentation Consolidation Plan

## Overview

This document identifies opportunities to consolidate, simplify, and remove outdated documentation.

## Consolidation Opportunities

### 1. CLI Testing Documentation (HIGH PRIORITY)

**Current State**: 3 overlapping files with significant duplication
- `docs/cli/TESTING.md` (288 lines) - Comprehensive guide
- `docs/cli/TESTING_SUMMARY.md` (192 lines) - Summary/quick start
- `docs/cli/TESTING_QUICKSTART.md` (140 lines) - Quick start guide

**Recommendation**: Consolidate into single `docs/cli/TESTING.md` with sections:
- Quick Start (from TESTING_QUICKSTART.md)
- Running Tests (from TESTING.md)
- Test Structure (from TESTING.md)
- Coverage Summary (from TESTING_SUMMARY.md)
- Troubleshooting (from all three)

**Action**: Merge TESTING_QUICKSTART.md and TESTING_SUMMARY.md into TESTING.md, then delete duplicates.

### 2. Neo4j Aura Documentation (MEDIUM PRIORITY)

**Current State**: 2 files with overlapping content
- `docs/neo4j-aura-testing.md` (393 lines) - Testing-focused
- `docs/data/neo4j-aura-setup.md` (196 lines) - Setup-focused

**Recommendation**: Keep both but clarify scope:
- `docs/neo4j-aura-testing.md` → Focus on testing strategies
- `docs/data/neo4j-aura-setup.md` → Focus on weekly workflow setup
- Add cross-references between them

**Action**: Add clear scope statements and cross-references.

### 3. Historical Consolidation Docs (ARCHIVE)

**Current State**: 3 completed planning documents
- `docs/architecture/consolidation-summary.md` - Summary of completed work
- `docs/architecture/consolidation-refactor-plan.md` - Original plan (completed)
- `docs/architecture/consolidation-migration-guide.md` - Migration guide (completed)

**Recommendation**: Archive to `docs/archive/architecture/` since consolidation is complete.

**Action**: Move to archive, keep summary for reference.

### 4. Root-Level Fix Documentation (ARCHIVE)

**Current State**: 2 historical fix documents
- `TRANSACTION_ENDPOINT_FIX.md` - Fix documentation
- `PSC_RETRIEVAL_FIX.md` - Fix documentation

**Recommendation**: Archive to `docs/archive/fixes/` - these are historical fixes.

**Action**: Move to archive.

### 5. Root-Level Testing Docs (REORGANIZE)

**Current State**: 2 testing guides in root
- `VALIDATION_TESTING.md` - Validation testing guide
- `TESTING_CATEGORIZATION.md` - Categorization testing guide

**Recommendation**: Move to `docs/testing/` directory for better organization.

**Action**: Move files and update README links.

### 6. Planning/Analysis Docs (ARCHIVE IF COMPLETE)

**Current State**: 2 planning documents
- `TEST_COVERAGE_IMPROVEMENT_PLAN.md` - Coverage improvement plan
- `COVERAGE_GAP_ANALYSIS.md` - Coverage gap analysis

**Recommendation**: Archive if work is complete, or move to `.kiro/specs/` if still active.

**Action**: Review status and archive or relocate.

### 7. Quick Start Files (CLARIFY SCOPE)

**Current State**: 2 quick start files
- `QUICK_START.md` - Dagster quick start
- `docs/TESTING_QUICK_START.md` - Testing quick start

**Recommendation**: Keep both but ensure clear naming and cross-references.

**Action**: Add cross-references, ensure clear scope.

## Files to Remove/Archive

### Archive (Move to `docs/archive/`)
1. `docs/architecture/consolidation-refactor-plan.md` → `docs/archive/architecture/`
2. `docs/architecture/consolidation-migration-guide.md` → `docs/archive/architecture/`
3. `TRANSACTION_ENDPOINT_FIX.md` → `docs/archive/fixes/`
4. `PSC_RETRIEVAL_FIX.md` → `docs/archive/fixes/`
5. `TEST_COVERAGE_IMPROVEMENT_PLAN.md` → `docs/archive/` (if complete)
6. `COVERAGE_GAP_ANALYSIS.md` → `docs/archive/` (if complete)

### Consolidate (Merge then delete)
1. `docs/cli/TESTING_QUICKSTART.md` → Merge into `docs/cli/TESTING.md`
2. `docs/cli/TESTING_SUMMARY.md` → Merge into `docs/cli/TESTING.md`

### Reorganize (Move to proper location)
1. `VALIDATION_TESTING.md` → `docs/testing/validation-testing.md`
2. `TESTING_CATEGORIZATION.md` → `docs/testing/categorization-testing.md`

## Summary

**Total files to archive**: 6
**Total files to consolidate**: 2 (merge into existing)
**Total files to reorganize**: 2 (move to proper directory)

**Net reduction**: ~8 files removed from active docs, better organization

