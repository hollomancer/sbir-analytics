---
Type: Overview
Owner: docs@project
Last-Reviewed: 2025-01-XX
Status: active

---

# Archived Documentation

This directory contains historical documentation that has been archived but kept for reference.

## Structure

- `architecture/` - Historical architecture planning documents
  - `openspec-to-kiro-migration-guide.md` - Completed OpenSpec→Kiro migration (Oct 2025)
  - `consolidation-summary.md` - Completed codebase consolidation (Jan 2025)
  - `CODE_REDUNDANCY_ANALYSIS.md` - Code redundancy analysis and recommendations (Nov 2025)
  - `DESIGN_PATTERNS_GAP_ANALYSIS.md` - Design patterns gap analysis (Oct 2025, 91.3% complete)
- `deployment/` - Historical deployment planning documents
  - `cloud-migration-opportunities.md` - Cloud migration planning (completed Nov 2025 with AWS+Aura deployment)
- `ml/` - Historical ML/CET analysis documents
  - `cet-classifier-comparison.md` - CET classifier comparison analysis (completed Nov 2025)
- `fixes/` - Historical bug fix documentation
- `transition/` - Historical transition detection reports
- `DOCUMENTATION_CONSOLIDATION_PLAN.md` - Meta-documentation about documentation consolidation (Nov 2025)
- `DOCUMENTATION_OPTIMIZATION_ANALYSIS.md` - Comprehensive documentation optimization analysis (Jan 2025)
- `DOCUMENTATION_OPTIMIZATION_SUMMARY.md` - Executive summary of documentation optimization (Jan 2025)
- `EXPLORATION_SUMMARY.md` - Historical codebase exploration results (Nov 2025)
- `MARKDOWN_DOCUMENTATION_ANALYSIS.md` - Comprehensive markdown documentation analysis (Nov 2025)
- `MIGRATION_COMPLETE.md` - Migration completion marker

## Recent Archival (November 2025)

### Completed Initiatives Archived
- **Cloud Migration Planning** (`deployment/cloud-migration-opportunities.md`) - Migration to AWS S3, Lambda, and Neo4j Aura completed
- **CET Classifier Comparison** (`ml/cet-classifier-comparison.md`) - Analysis comparing archived sbir-cet-classifier with current implementation

### Documentation Reorganized
- **Enhanced Matching** - Moved from `docs/enhanced_matching.md` → `docs/enrichment/enhanced-matching.md`
- **PaECTER Testing** - Moved from `docs/PAECTER_TESTING_GUIDE.md` → `docs/ml/paecter-testing-guide.md`

### Removed Documentation
- **Neo4j Schema Migration Proposals** (`docs/migration/`) - Deleted unexecuted migration planning docs
  - Note: Actual migration system lives in `migrations/versions/` (active)

## When to Archive

Documentation should be archived when:
- The work described is complete and no longer actively referenced
- The information is historical but may be useful for context
- The document has been superseded by newer documentation
- Planning documents whose initiatives have been completed

## Active Documentation

For current documentation, see:
- `docs/` - Active documentation
- `.kiro/specs/` - Active specifications and requirements
- `README.md` - Project overview and quick start





