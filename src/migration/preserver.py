"""
Historical Preserver

This module handles archiving OpenSpec content for historical reference
and creating migration mapping documentation.
"""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from .models import FileSystemError, GeneratedSpec


class HistoricalPreserver:
    """Preserves OpenSpec content for historical reference."""

    def __init__(self):
        """Initialize preserver."""
        self.logger = logging.getLogger(__name__)

    def archive_openspec(self, openspec_path: Path, archive_path: Path,
                        generated_specs: list[GeneratedSpec]):
        """Archive complete OpenSpec directory structure."""
        self.logger.info(f"Archiving OpenSpec content to {archive_path}")

        try:
            # Create archive directory
            archive_path.mkdir(parents=True, exist_ok=True)

            # Copy entire openspec directory
            openspec_archive = archive_path / "openspec"
            if openspec_archive.exists():
                shutil.rmtree(openspec_archive)

            shutil.copytree(openspec_path, openspec_archive)
            self.logger.info(f"Copied OpenSpec directory to {openspec_archive}")

            # Create migration mapping
            self._create_migration_mapping(archive_path, generated_specs)

            # Create README for archived content
            self._create_archive_readme(archive_path)

            self.logger.info("OpenSpec archival complete")

        except Exception as e:
            raise FileSystemError(f"Failed to archive OpenSpec content: {e}")

    def _create_migration_mapping(self, archive_path: Path, generated_specs: list[GeneratedSpec]):
        """Create mapping from OpenSpec to Kiro specs."""
        self.logger.info("Creating migration mapping")

        mapping = {
            "migration_metadata": {
                "migration_date": datetime.now().isoformat(),
                "migration_tool": "openspec_to_kiro_migrator",
                "total_specs_generated": len(generated_specs)
            },
            "openspec_to_kiro_mapping": self._build_spec_mapping(generated_specs),
            "archived_content": {
                "openspec_directory": "openspec/",
                "changes_directory": "openspec/changes/",
                "specs_directory": "openspec/specs/",
                "project_documentation": "openspec/project.md",
                "agent_instructions": "openspec/AGENTS.md"
            },
            "migration_notes": [
                "All OpenSpec content has been preserved in the openspec/ directory",
                "Generated Kiro specs are located in .kiro/specs/",
                "This mapping provides traceability between old and new systems",
                "Archived content should be treated as read-only historical reference"
            ]
        }

        mapping_file = archive_path / "migration_mapping.json"
        with open(mapping_file, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Migration mapping created: {mapping_file}")

    def _build_spec_mapping(self, generated_specs: list[GeneratedSpec]) -> dict:
        """Build mapping between OpenSpec changes and Kiro specs."""
        mapping = {}

        for spec in generated_specs:
            mapping[spec.name] = {
                "kiro_spec_path": str(spec.path),
                "files_created": spec.files_created,
                "source_openspec_changes": spec.source_changes,
                "source_openspec_specs": spec.source_specs,
                "migration_status": "completed"
            }

        return mapping

    def _create_archive_readme(self, archive_path: Path):
        """Create README for archived content."""
        readme_content = f"""# OpenSpec Archive

This directory contains the complete archived OpenSpec content from the migration to Kiro specifications.

## Archive Date
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

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
"""

        readme_file = archive_path / "README.md"
        readme_file.write_text(readme_content, encoding='utf-8')

        self.logger.info(f"Archive README created: {readme_file}")
