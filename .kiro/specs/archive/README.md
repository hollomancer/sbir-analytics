# Kiro Specifications Archive

This directory contains completed Kiro specifications that are no longer actively developed but preserved for historical reference and audit purposes.

## Archive Structure

```
archive/
├── completed-migrations/     # Migration and transition projects
├── deprecated-features/      # Features that were removed or replaced
├── completed-features/       # Successfully implemented features
└── README.md                # This file
```

## Archived Specifications

### Completed Migrations

#### openspec-to-kiro-migration (Completed: 2025-10-30)
- **Purpose**: Migrated project from OpenSpec to Kiro specification system
- **Status**: ✅ Completed successfully
- **Results**: 8 OpenSpec changes + 9 specs → 13 Kiro specifications
- **Impact**: Established Kiro as the project's specification system
- **Migration ID**: migration_20251030_152650
- **Location**: `completed-migrations/openspec-to-kiro-migration/`
- **Completion Record**: See `COMPLETION_RECORD.md` for detailed results and artifacts

### Completed Features

#### transition_detection (Completed: 2025-10-30)
- **Purpose**: SBIR Transition Detection Module for technology commercialization analysis
- **Status**: ✅ Fully completed (169/169 tasks)
- **Results**: Multi-signal detection engine, vendor resolution, Neo4j integration, dual-perspective analytics
- **Impact**: Enables comprehensive SBIR program effectiveness measurement and technology transfer tracking
- **Performance**: ≥10K detections/minute, ≥85% precision, ≥70% recall, 90%+ vendor match rate
- **Location**: `completed-features/transition_detection/`
- **Completion Record**: See `COMPLETION_RECORD.md` for detailed implementation results and validation metrics

## Archive Guidelines

### When to Archive

Archive specs when they are:
- ✅ **Completed**: All requirements implemented and validated
- 🚫 **Deprecated**: Feature removed or replaced
- 📦 **Consolidated**: Merged into other specifications
- 🔄 **Migrated**: Transitioned to new system or approach

### Archive Process

1. **Complete Implementation**: Ensure all tasks are finished
2. **Create Completion Record**: Document results and impact
3. **Move to Archive**: Place in appropriate archive subdirectory
4. **Update Index**: Add entry to this README
5. **Commit Changes**: Check in archive with completion notes

### Accessing Archived Specs

Archived specifications are:
- **Read-only**: For reference and audit purposes
- **Preserved**: Complete with all original documentation
- **Traceable**: Linked to implementation and outcomes
- **Searchable**: Indexed for easy discovery

Use archived specs for:
- Understanding past decisions and rationale
- Learning from previous implementation approaches
- Auditing completed work and outcomes
- Reference for similar future projects

## Active Development

For active development, use specifications in `.kiro/specs/` (parent directory).
See `docs/development/kiro-workflow-guide.md` for current workflow guidance.