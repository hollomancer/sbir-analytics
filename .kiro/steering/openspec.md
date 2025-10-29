# OpenSpec Integration Guidelines

## When to Use OpenSpec with Kiro

### Automatic Triggers
When Kiro detects these patterns in user requests, automatically reference OpenSpec:
- "create a proposal" / "plan a change" / "spec this out"
- "breaking change" / "architecture change" / "new capability"
- "performance optimization" / "security update"

### File References
Use Kiro's file reference syntax in OpenSpec documents:
- Configuration: `#[[file:config/base.yaml]]`
- Schemas: `#[[file:docs/schemas/patent-neo4j-schema.md]]`
- APIs: `#[[file:openapi/sam-gov-api.yaml]]`

### Integration with Project Planning
1. **Discovery Phase**: Use `openspec list` and `openspec show` to understand current state
2. **Planning Phase**: Create proposals with file references to relevant specs
3. **Implementation Phase**: Use Kiro's code generation with OpenSpec context
4. **Validation Phase**: Use `openspec validate --strict` before implementation

## OpenSpec Commands for Kiro

```bash
# Essential discovery commands
openspec list                    # Active changes
openspec list --specs            # Current capabilities
openspec show <item>             # View details
openspec validate <item> --strict # Validate proposals

# Project management
openspec archive <change-id> --yes  # Archive completed changes
```

## Quality Gates

Before any implementation:
1. Read relevant specs: `openspec show <spec-id>`
2. Check for conflicts: `openspec list`
3. Validate proposal: `openspec validate <change-id> --strict`
4. Get approval before coding

## File Organization

```
openspec/
├── project.md              # Project conventions (reference with #[[file:openspec/project.md]])
├── specs/                  # Current capabilities
│   └── [capability]/
│       ├── spec.md         # Requirements
│       └── design.md       # Technical patterns
├── changes/                # Active proposals
│   └── [change-id]/
│       ├── proposal.md     # Why/what/impact
│       ├── tasks.md        # Implementation checklist
│       └── specs/          # Delta specifications
└── AGENTS.md              # AI assistant instructions
```