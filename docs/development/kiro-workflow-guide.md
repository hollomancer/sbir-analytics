# Kiro Specification Workflow Guide

This guide explains how to use Kiro specifications for feature development in the SBIR ETL pipeline project.

## Overview

Kiro is a specification-driven development system that uses structured requirements, design documents, and task lists to guide implementation. All specifications are stored in `.kiro/specs/` with a consistent structure.

## Kiro Spec Structure

Each Kiro specification consists of:

```text
.kiro/specs/[feature-name]/
├── requirements.md    # EARS-formatted requirements with user stories
├── design.md         # Technical design and architecture (optional)
└── tasks.md          # Implementation task list
```

## Creating a New Kiro Spec

### 1. Requirements Document (`requirements.md`)

The requirements document follows this structure:

```markdown

## Requirements Document

## Introduction

[Brief description of the feature/system]

## Glossary

- **Term**: Definition
- **System_Name**: System component definition

## Requirements

### Requirement 1

**User Story:** As a [role], I want [feature], so that [benefit]

#### Acceptance Criteria

1. THE [System_Name] SHALL [requirement using EARS pattern]
2. WHEN [condition], THE [System_Name] SHALL [response]
3. WHILE [state], THE [System_Name] SHALL [behavior]
```

#### EARS Patterns

Use these EARS (Easy Approach to Requirements Syntax) patterns:

- **Ubiquitous**: `THE <system> SHALL <response>`
- **Event-driven**: `WHEN <trigger>, THE <system> SHALL <response>`
- **State-driven**: `WHILE <condition>, THE <system> SHALL <response>`
- **Unwanted event**: `IF <condition>, THEN THE <system> SHALL <response>`
- **Optional feature**: `WHERE <option>, THE <system> SHALL <response>`

### 2. Design Document (`design.md`)

Include these sections as needed:

```markdown

## Design Document

## Overview

[High-level description]

## Architecture

[System architecture and components]

## Components and Interfaces

[Detailed component descriptions]

## Data Models

[Data structures and schemas]

## Error Handling

[Error scenarios and responses]

## Testing Strategy

[Testing approach and coverage]
```

### 3. Task List (`tasks.md`)

Structure tasks hierarchically:

```markdown

## Implementation Plan

- [ ] 1. Major task category
- [ ] 1.1 Specific implementation task
  - Detailed description of what to implement
  - Technical requirements and constraints
  - _Requirements: 1.1, 2.3_ (reference to requirements)

- [ ] 1.2 Another specific task
  - Implementation details
  - _Requirements: 1.2_

- [ ]* 1.3 Optional task (marked with *)
  - Optional tasks can be skipped
  - Usually testing or documentation tasks
  - _Requirements: 1.1_
```

## Executing Tasks

### Using Kiro in the IDE

1. Open the task file (`.kiro/specs/[feature]/tasks.md`)
2. Click "Start task" next to a task item
3. The AI assistant will implement the task based on:
   - Requirements from `requirements.md`
   - Design guidance from `design.md`
   - Task-specific instructions

### Task Execution Guidelines

- **Sequential execution**: Complete tasks in order when dependencies exist
- **Incremental progress**: Each task builds on previous work
- **Requirement traceability**: Tasks reference specific requirements
- **Optional tasks**: Tasks marked with `*` can be skipped for MVP

## Best Practices

### Requirements Writing

1. **Use active voice**: "The system SHALL process data" not "Data will be processed"
2. **Be specific**: Avoid vague terms like "quickly" or "efficiently"
3. **One requirement per statement**: Don't combine multiple requirements
4. **Measurable criteria**: Include specific thresholds and limits
5. **Consistent terminology**: Use glossary terms consistently

### Task Planning

1. **Atomic tasks**: Each task should be completable in one session
2. **Clear objectives**: Task descriptions should be unambiguous
3. **Proper sequencing**: Order tasks to build incrementally
4. **Requirement links**: Always reference which requirements the task addresses

### Design Documentation

1. **Architecture first**: Start with high-level architecture
2. **Component interfaces**: Define clear boundaries and contracts
3. **Data flow**: Show how data moves through the system
4. **Error scenarios**: Plan for failure cases
5. **Testing strategy**: Include testability in design

## Common Patterns

### Feature Implementation

1. **Analysis**: Understand the problem and requirements
2. **Design**: Create technical design and architecture
3. **Planning**: Break down into implementable tasks
4. **Implementation**: Execute tasks incrementally
5. **Validation**: Verify requirements are met

### Requirement Categories

- **Functional**: What the system must do
- **Performance**: Speed, throughput, resource usage
- **Security**: Authentication, authorization, data protection
- **Reliability**: Error handling, recovery, availability
- **Usability**: User interface and experience requirements

## Integration with Existing Code

### Codebase Alignment

- Follow existing patterns in `src/` directory structure
- Use established configuration patterns in `config/`
- Integrate with Dagster assets and jobs
- Maintain compatibility with Docker deployment

### Testing Integration

- Unit tests in `tests/unit/`
- Integration tests in `tests/integration/`
- Follow existing test patterns and fixtures
- Maintain ≥85% test coverage

## Troubleshooting

### Common Issues

1. **Requirements too vague**: Add specific acceptance criteria
2. **Tasks too large**: Break down into smaller, atomic tasks
3. **Missing dependencies**: Ensure task ordering reflects dependencies
4. **Unclear design**: Add more detail to architecture and components

### Getting Help

- Review existing specs in `.kiro/specs/` for examples
- Check archived OpenSpec content in `archive/openspec/` for historical context
- Consult `AGENTS.md` for AI assistant guidance
- Reference migration mapping in `archive/openspec/migration_mapping.json`

## Examples

See these existing specs for reference:

- **Simple feature**: `.kiro/specs/iterative_api_enrichment/`
- **Complex system**: `.kiro/specs/data_pipeline_consolidated/`
- **Migration example**: `.kiro/specs/openspec-to-kiro-migration/`

## Migration from OpenSpec

If you encounter references to OpenSpec:

1. **Active development**: Use Kiro specs in `.kiro/specs/`
2. **Historical reference**: Check `archive/openspec/` for context
3. **Migration mapping**: Use `archive/openspec/migration_mapping.json` for traceability
4. **Legacy workflows**: All OpenSpec workflows have been replaced with Kiro

The migration is complete - all new development should use Kiro specifications.