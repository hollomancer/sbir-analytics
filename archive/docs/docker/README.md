# Archived Docker Documentation

**Date Archived**: 2025-11-29
**Reason**: Consolidated into unified guides

## What Happened

These Docker documentation files were consolidated into two comprehensive guides:

- **[Docker Development Guide](../../../docs/deployment/docker-guide.md)** - Getting started, common tasks, workflows
- **[Docker Configuration Reference](../../../docs/deployment/docker-reference.md)** - Advanced configuration, optimization, security

## Archived Files

| Original File | Content Migrated To |
|---------------|---------------------|
| `containerization.md` | `docker-guide.md` (Quick Start, Profiles, Common Tasks) |
| `docker-quickstart.md` | `docker-guide.md` (Quick Start section) |
| `docker-new-developer-experience.md` | `docker-guide.md` (Development Workflow) |
| `docker-env-setup.md` | `docker-guide.md` (Environment Setup) + `docker-reference.md` (Environment Variables) |

## Why Consolidate?

**Before**: 8 Docker docs scattered across deployment/ and development/
**After**: 2 comprehensive guides organized by audience

**Benefits**:
- Single source of truth for Docker setup
- Easier to maintain and update
- Better navigation for users
- Reduced duplication

## Migration Guide

If you have bookmarks or links to old docs:

| Old Link | New Link |
|----------|----------|
| `docs/deployment/containerization.md` | `docs/deployment/docker-guide.md` |
| `docs/development/docker-quickstart.md` | `docs/deployment/docker-guide.md#quick-start` |
| `docs/development/docker-env-setup.md` | `docs/deployment/docker-reference.md#environment-variables` |
| `docs/deployment/docker-config-reference.md` | `docs/deployment/docker-reference.md` |

## Related

- [Documentation Improvements](../../../docs/DOCUMENTATION_IMPROVEMENTS.md) - Full consolidation plan
- [Docker Troubleshooting](../../../docs/development/docker-troubleshooting.md) - Still active (developer-focused)
