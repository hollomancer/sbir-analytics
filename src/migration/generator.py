"""
Kiro Spec Generator

This module generates Kiro specification files from transformed content.
"""

import logging
from pathlib import Path

from .models import FileSystemError, GeneratedSpec, KiroContent, KiroSpec


class KiroSpecGenerator:
    """Generates Kiro specification files."""

    def __init__(self, kiro_path: Path):
        """Initialize generator with Kiro specs path."""
        self.kiro_path = kiro_path
        self.logger = logging.getLogger(__name__)

    def generate_kiro_specs(self, kiro_content: KiroContent) -> list[GeneratedSpec]:
        """Generate all Kiro spec files."""
        self.logger.info(f"Generating {len(kiro_content.specs)} Kiro specs")

        generated_specs = []

        for spec in kiro_content.specs:
            try:
                generated_spec = self._generate_single_spec(spec)
                generated_specs.append(generated_spec)
                self.logger.debug(f"Generated spec: {spec.name}")
            except Exception as e:
                self.logger.error(f"Failed to generate spec {spec.name}: {e}")
                raise FileSystemError(f"Failed to generate spec {spec.name}: {e}")

        return generated_specs

    def _generate_single_spec(self, spec: KiroSpec) -> GeneratedSpec:
        """Generate single Kiro specification."""
        spec_dir = self.kiro_path / spec.name
        spec_dir.mkdir(parents=True, exist_ok=True)

        files_created = []

        # Generate requirements.md
        if spec.requirements:
            requirements_file = spec_dir / "requirements.md"
            self._write_requirements_file(requirements_file, spec.requirements)
            files_created.append("requirements.md")

        # Generate design.md if present
        if spec.design:
            design_file = spec_dir / "design.md"
            self._write_design_file(design_file, spec.design)
            files_created.append("design.md")

        # Generate tasks.md
        if spec.tasks:
            tasks_file = spec_dir / "tasks.md"
            self._write_tasks_file(tasks_file, spec.tasks)
            files_created.append("tasks.md")

        return GeneratedSpec(
            name=spec.name,
            path=spec_dir,
            files_created=files_created,
            source_changes=spec.source_mapping.get("openspec_change_id", []),
            source_specs=spec.source_mapping.get("openspec_specs", []),
        )

    def _write_requirements_file(self, file_path: Path, requirements):
        """Write requirements.md in proper Kiro format."""
        content = f"""# Requirements Document

## Introduction

{requirements.introduction}

## Glossary

{self._format_glossary(requirements.glossary)}

## Requirements

{self._format_requirements(requirements.requirements)}
"""
        file_path.write_text(content, encoding="utf-8")

    def _format_glossary(self, glossary: dict) -> str:
        """Format glossary section."""
        if not glossary:
            return "No specific terms defined for this specification."

        lines = []
        for term, definition in glossary.items():
            lines.append(f"- **{term}**: {definition}")

        return "\n".join(lines)

    def _format_requirements(self, requirements: list) -> str:
        """Format requirements section."""
        if not requirements:
            return "No requirements defined."

        sections = []

        for req in requirements:
            section = f"""### Requirement {req.number}

**User Story:** {req.user_story}

#### Acceptance Criteria

{self._format_acceptance_criteria(req.acceptance_criteria)}
"""
            sections.append(section)

        return "\n".join(sections)

    def _format_acceptance_criteria(self, criteria: list) -> str:
        """Format acceptance criteria."""
        if not criteria:
            return "No acceptance criteria defined."

        lines = []
        for i, criterion in enumerate(criteria, 1):
            lines.append(f"{i}. {criterion}")

        return "\n".join(lines)

    def _write_design_file(self, file_path: Path, design):
        """Write design.md in proper Kiro format."""
        content = f"""# Design Document

## Overview

{design.overview}

## Architecture

{design.architecture}

## Components and Interfaces

{design.components}

## Data Models

{design.data_models}

## Error Handling

{design.error_handling}

## Testing Strategy

{design.testing_strategy}
"""
        file_path.write_text(content, encoding="utf-8")

    def _write_tasks_file(self, file_path: Path, tasks):
        """Write tasks.md in proper Kiro format."""
        content = f"""# Implementation Plan

{self._format_tasks(tasks.tasks)}
"""
        file_path.write_text(content, encoding="utf-8")

    def _format_tasks(self, tasks: list) -> str:
        """Format tasks section."""
        if not tasks:
            return "No tasks defined."

        lines = []

        for task in tasks:
            # Format task with checkbox
            checkbox = "[x]" if task.completed else "[ ]"
            optional_marker = "*" if task.optional else ""

            lines.append(f"- {checkbox}{optional_marker} {task.number} {task.description}")

            # Add subtasks
            for subtask in task.subtasks:
                lines.append(f"  - {subtask}")

            # Add requirement references
            if task.requirements_refs:
                refs = ", ".join(task.requirements_refs)
                lines.append(f"  - _Requirements: {refs}_")

            lines.append("")  # Empty line between tasks

        return "\n".join(lines)
