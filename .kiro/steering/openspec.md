# Kiro Specification Guidelines

## Migration Complete

**Status**: The project has successfully migrated from OpenSpec to Kiro for specification-driven development. All OpenSpec content has been archived and is available for historical reference only.

## Using Kiro Specifications

### When to Create Kiro Specs
Create Kiro specifications for:
- "create a proposal" / "plan a change" / "spec this out"
- "breaking change" / "architecture change" / "new capability"
- "performance optimization" / "security update"
- Any new feature or system modification

### File References
Use Kiro's file reference syntax in specification documents:
- Configuration: `#[[file:config/base.yaml]]`
- Schemas: `#[[file:docs/schemas/patent-neo4j-schema.md]]`
- APIs: `#[[file:openapi/sam-gov-api.yaml]]`

### Kiro Workflow
1. **Planning Phase**: Create spec in `.kiro/specs/[feature-name]/`
2. **Requirements Phase**: Write requirements.md with EARS patterns and user stories
3. **Design Phase**: Create design.md with technical architecture (if needed)
4. **Implementation Phase**: Create tasks.md with actionable implementation steps
5. **Execution Phase**: Use Kiro's task execution to implement incrementally

## Kiro Specification Structure

```
.kiro/specs/[feature-name]/
├── requirements.md         # EARS-formatted requirements with user stories
├── design.md              # Technical design and architecture (optional)
└── tasks.md               # Implementation task list
```

## Quality Gates

Before any implementation:
1. Create or review relevant Kiro spec in `.kiro/specs/`
2. Ensure requirements follow EARS patterns
3. Validate task structure and dependencies
4. Get approval before coding

## Historical Reference

### Archived OpenSpec Content
OpenSpec content is preserved in `archive/openspec/` for:
- Historical reference and context
- Understanding past decisions
- Migration traceability
- Audit and compliance purposes

### Migration Mapping
Use `archive/openspec/migration_mapping.json` to find:
- Which OpenSpec changes became which Kiro specs
- Consolidated specification mappings
- Complete traceability between old and new systems

## File Organization (Current)

```
.kiro/specs/                # Active Kiro specifications
├── [feature-name]/
│   ├── requirements.md     # EARS requirements with user stories
│   ├── design.md          # Technical design (optional)
│   └── tasks.md           # Implementation tasks
└── archive/               # Completed specifications
    └── completed-migrations/

archive/openspec/          # Historical OpenSpec content (read-only)
├── openspec/              # Complete archived OpenSpec structure
├── migration_mapping.json # Traceability mapping
└── README.md              # Archive documentation
```

## Development Workflow

All new development should use Kiro specifications:
1. Create spec in `.kiro/specs/[feature-name]/`
2. Follow EARS patterns for requirements
3. Use task-driven implementation
4. Archive completed specs when done

For historical context, reference `archive/openspec/` but do not create new OpenSpec content.