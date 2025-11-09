# OpenSpec to Kiro Migration Guide

**Status**: Migration in Progress
**Target Completion**: Q1 2025
**Migration Spec**: [OpenSpec to Kiro Migration](.kiro/specs/openspec-to-kiro-migration/requirements.md)

## Overview

This project is migrating from OpenSpec to Kiro for specification-driven development. This guide helps developers understand the transition and new workflows.

## Current State

- **OpenSpec System**: Legacy specification system in `openspec/` directory
- **Kiro System**: New specification system in `.kiro/specs/` directory
- **Migration Period**: Both systems temporarily coexist during transition

## Key Differences

### OpenSpec vs Kiro Structure

| Aspect | OpenSpec | Kiro |
|--------|----------|------|
| **Location** | `openspec/changes/` and `openspec/specs/` | `.kiro/specs/` |
| **Change Model** | Proposal → Implementation → Archive | Requirements → Design → Tasks → Execution |
| **File Structure** | `proposal.md`, `tasks.md`, `design.md`, spec deltas | `requirements.md`, `design.md`, `tasks.md` |
| **Requirements Format** | Free-form proposals | EARS patterns with user stories |
| **Workflow** | OpenSpec CLI commands | Kiro spec execution |

### Content Mapping

| OpenSpec Element | Kiro Element | Notes |
|------------------|--------------|-------|
| `proposal.md` → Why/What/Impact | `requirements.md` → Introduction/Requirements | Converted to user stories with EARS patterns |
| `tasks.md` | `tasks.md` | Preserved with requirement references |
| `design.md` | `design.md` | Direct migration with format updates |
| Spec deltas (ADDED/MODIFIED/REMOVED) | Requirements | Consolidated into cohesive requirements |

## Migration Timeline

### Phase 1: Foundation (Weeks 1-2) ✅

- [x] Create migration specification
- [x] Update documentation references
- [x] Establish Kiro spec structure

### Phase 2: Content Migration (Weeks 3-4) 🔄

- [ ] Migrate active OpenSpec changes to Kiro specs
- [ ] Consolidate OpenSpec specifications
- [ ] Validate migrated content

### Phase 3: Workflow Transition (Weeks 5-6) ⏳

- [ ] Update development workflows
- [ ] Archive OpenSpec content
- [ ] Complete documentation updates

### Phase 4: Cutover (Weeks 7-8) ⏳

- [ ] Disable OpenSpec tooling
- [ ] Final validation and testing
- [ ] Developer training and support

## Developer Guidelines

### During Migration Period

### For New Work:

- ✅ **Use Kiro specs** for new features and capabilities
- ✅ Create specs in `.kiro/specs/[feature-name]/`
- ✅ Follow EARS patterns for requirements
- ✅ Reference existing architecture documents

### For Existing OpenSpec Work:

- ⚠️ **Continue with OpenSpec** for active changes until migrated
- ⚠️ Check migration status before starting new OpenSpec changes
- ⚠️ Coordinate with migration team for change priorities

### Kiro Spec Creation

1. **Create spec directory**: `.kiro/specs/[feature-name]/`
2. **Write requirements.md**:

   ```markdown
   # Requirements Document

   ## Introduction
   [Context and problem statement]

   ## Glossary

   - **Term**: Definition

   ## Requirements

   ### Requirement 1

   **User Story:** As a [user], I want [goal], so that [benefit].

   #### Acceptance Criteria

   1. THE system SHALL [specific behavior]
   2. THE system SHALL [specific behavior]
   ```

3. **Write tasks.md**:

   ```markdown
   # Implementation Plan

   ## 1. [Phase Name]

   - [ ] 1.1 [Task description]
     - [Subtask details]
     - _Requirements: 1.1_
   ```

4. **Write design.md** (if needed):

   ```markdown
   # Design Document

   ## Overview
   [Technical approach]

   ## Architecture
   [System design]
   ```

### EARS Pattern Examples

### Good EARS Patterns:

- "THE system SHALL validate user input before processing"
- "THE API SHALL return results within 200ms for 95% of requests"
- "THE database SHALL maintain referential integrity across all tables"

### Convert from OpenSpec:

- OpenSpec: "Add user authentication"
- Kiro: "THE system SHALL authenticate users using JWT tokens"

## Migration Support

### Resources

- **Migration Spec**: [OpenSpec to Kiro Migration](.kiro/specs/openspec-to-kiro-migration/requirements.md)
- **Consolidation Plan**: [Codebase Consolidation Refactor Plan](consolidation-refactor-plan.md)
- **Architecture Docs**: [Shared Tech Stack](shared-tech-stack.md)

### Getting Help

- **Migration Questions**: Check migration spec or ask development team
- **Kiro Spec Format**: Reference existing specs in `.kiro/specs/`
- **EARS Patterns**: See requirements examples in migrated specs

### Common Migration Patterns

### Converting Proposals to Requirements:

```markdown

## OpenSpec proposal.md


## Why

Need to improve API performance

## What Changes

- Add caching layer
- Optimize database queries

## Kiro requirements.md


### Requirement 1

**User Story:** As an API consumer, I want fast response times, so that my application performs well.

#### Acceptance Criteria

1. THE API SHALL implement caching for frequently accessed data
2. THE API SHALL optimize database queries to reduce response time
3. THE API SHALL return results within 200ms for 95% of requests
```

### Converting Tasks:

```markdown

## OpenSpec tasks.md

- [ ] 1.1 Add Redis caching
- [ ] 1.2 Optimize SQL queries

## Kiro tasks.md

- [ ] 1.1 Implement Redis caching layer
  - Set up Redis connection
  - Add cache middleware
  - _Requirements: 1.1_

- [ ] 1.2 Optimize database queries
  - Analyze slow queries
  - Add database indexes
  - _Requirements: 1.2_
```

## Quality Assurance

### Validation Checklist

- [ ] All requirements follow EARS patterns
- [ ] User stories include clear acceptance criteria
- [ ] Tasks reference specific requirements
- [ ] Design documents provide sufficient technical guidance
- [ ] All migrated content passes Kiro validation

### Testing Migration

- [ ] Verify no OpenSpec content is lost
- [ ] Validate Kiro specs are executable
- [ ] Test new development workflow
- [ ] Confirm historical preservation

## Post-Migration

### After Cutover

- **OpenSpec Content**: Archived in `archive/openspec/` for historical reference
- **New Development**: All new work uses Kiro specs exclusively
- **Documentation**: Updated to reference Kiro system only
- **Tooling**: OpenSpec commands disabled to prevent confusion

### Ongoing Maintenance

- Regular review of Kiro specs for accuracy
- Updates to requirements as features evolve
- Continuous improvement of EARS patterns
- Developer training on Kiro best practices

---

**Document Version**: 1.0
**Last Updated**: October 30, 2025
**Next Review**: After Phase 2 completion
