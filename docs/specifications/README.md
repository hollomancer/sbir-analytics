# Specification System Documentation

This document centralizes information about the specification systems used in the SBIR ETL project, including the active Kiro specifications and the archived OpenSpec content.

## Table of Contents

1.  [Kiro Specifications (Active)](#1-kiro-specifications-active)
    *   [Purpose](#purpose)
    *   [Location](#location)
    *   [Usage](#usage)
2.  [OpenSpec Archive](#2-openspec-archive)
    *   [Purpose](#purpose-1)
    *   [Location](#location-1)
    *   [Contents](#contents)
    *   [Migration Notes](#migration-notes)
    *   [Accessing Archived Content](#accessing-archived-content)
3.  [Guidelines for Contributors](#3-guidelines-for-contributors)

---

## 1. Kiro Specifications (Active)

### Purpose

Kiro specifications are the **active and authoritative source of truth** for all development work in the SBIR ETL project. They are used for:

-   **Planning**: Defining new features, capabilities, and project phases.
-   **Architecture**: Documenting design decisions, architectural patterns, and system components.
-   **Requirements**: Capturing functional and non-functional requirements using structured patterns (e.g., EARS).
-   **Implementation**: Guiding task-driven development and providing detailed implementation plans.
-   **Design**: Documenting system designs, data models, and API contracts.

### Location

All Kiro specifications are located in the `.kiro/specs/` directory.

### Usage

When contributing to the project, always refer to and update the relevant Kiro specifications for:

-   Defining new features or capabilities.
-   Proposing architecture changes.
-   Documenting requirements.
-   Planning implementation tasks.
-   Updating design documentation.

## 2. OpenSpec Archive

### Purpose

The OpenSpec content has been **archived** following the migration to Kiro specifications. It is preserved for historical reference and audit purposes. It is **not** to be used for active development.

### Location

The complete archived OpenSpec content is located in the `archive/openspec/` directory.

### Contents

The archive includes:

-   `openspec/` - Complete copy of the original OpenSpec directory structure.
-   `migration_mapping.json` - Detailed mapping between OpenSpec and Kiro specs.
-   `README.md` - An overview of the archive.

### Migration Notes

-   All active OpenSpec changes have been converted to Kiro specifications.
-   OpenSpec specifications have been consolidated into cohesive Kiro specs.
-   This archived content is preserved for historical reference and audit purposes.
-   New development should use the Kiro specification system in `.kiro/specs/`.

### Accessing Archived Content

This archived content is read-only and should be used only for:

-   Historical reference.
-   Understanding past decisions.
-   Audit and compliance purposes.
-   Migration troubleshooting.

For active development, use the Kiro specifications in `.kiro/specs/`.

## 3. Guidelines for Contributors

-   **Always use Kiro specs** (`.kiro/specs/`) for any new or updated specifications.
-   **Do not modify content** within the `archive/openspec/` directory.
-   If you need to reference past decisions, consult the `archive/openspec/` content and its `migration_mapping.json` for traceability.
-   Ensure that any changes to architecture, data contracts, or requirements are reflected in the appropriate Kiro specifications.
