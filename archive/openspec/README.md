# OpenSpec Archive

This directory contains the complete archived OpenSpec content from the migration to Kiro specifications.

## Archive Date
2025-10-30 15:26:50

## Contents

- `openspec/` - Complete copy of the original OpenSpec directory structure
- `migration_mapping.json` - Detailed mapping between OpenSpec and Kiro specs
- `README.md` - This file

## Directory Structure

```
openspec/
├── changes/           # OpenSpec change proposals
│   ├── archive/       # Previously completed changes
│   └── [active]/      # Changes that were migrated to Kiro specs
├── specs/             # OpenSpec specifications (consolidated into Kiro specs)
├── project.md         # Project context and conventions
└── AGENTS.md          # AI assistant instructions
```

## Migration Notes

- All active OpenSpec changes have been converted to Kiro specifications
- OpenSpec specifications have been consolidated into cohesive Kiro specs
- This archived content is preserved for historical reference and audit purposes
- New development should use the Kiro specification system in `.kiro/specs/`

## Accessing Archived Content

This archived content is read-only and should be used only for:
- Historical reference
- Understanding past decisions
- Audit and compliance purposes
- Migration troubleshooting

For active development, use the Kiro specifications in `.kiro/specs/`.

## Migration Mapping

See `migration_mapping.json` for detailed traceability between:
- OpenSpec changes → Kiro specs
- OpenSpec specifications → Consolidated Kiro specs
- File-level mapping and transformation details

## Support

If you need to reference specific OpenSpec content or understand migration decisions,
consult the migration mapping and archived files in this directory.
