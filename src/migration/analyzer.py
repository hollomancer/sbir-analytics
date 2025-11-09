"""
OpenSpec Content Analyzer

This module provides functionality to analyze and parse existing OpenSpec
content structure, extracting all changes, specifications, and metadata.
"""

import re
from pathlib import Path

from loguru import logger

from .models import (
    ContentParsingError,
    OpenSpecChange,
    OpenSpecContent,
    OpenSpecDesign,
    OpenSpecImpact,
    OpenSpecProposal,
    OpenSpecSpec,
    OpenSpecTask,
    OpenSpecTasks,
)


class OpenSpecAnalyzer:
    """Analyzes existing OpenSpec content structure."""

    def __init__(self, openspec_path: Path):
        """Initialize analyzer with OpenSpec directory path."""
        self.openspec_path = openspec_path

    def analyze_openspec_structure(self) -> OpenSpecContent:
        """Scan and catalog all OpenSpec content."""
        logger.info("Starting OpenSpec content analysis")

        try:
            content = OpenSpecContent(
                active_changes=self._scan_changes(),
                specifications=self._scan_specs(),
                project_context=self._parse_project_md(),
                agent_instructions=self._parse_agents_md(),
                archived_changes=self._list_archived_changes(),
            )

            logger.info(
                f"Analysis complete: {len(content.active_changes)} active changes, "
                f"{len(content.specifications)} specs, "
                f"{len(content.archived_changes)} archived changes"
            )

            return content

        except Exception as e:
            raise ContentParsingError(f"Failed to analyze OpenSpec structure: {e}")

    def _scan_changes(self) -> list[OpenSpecChange]:
        """Extract all active changes from openspec/changes/."""
        changes: list[Any] = []
        changes_path = self.openspec_path / "changes"

        if not changes_path.exists():
            logger.warning(f"Changes directory not found: {changes_path}")
            return changes

        for change_dir in changes_path.iterdir():
            if change_dir.is_dir() and change_dir.name != "archive":
                try:
                    change = self._parse_change(change_dir)
                    changes.append(change)
                    logger.debug(f"Parsed change: {change.id}")
                except Exception as e:
                    logger.error(f"Failed to parse change {change_dir.name}: {e}")

        return changes

    def _parse_change(self, change_dir: Path) -> OpenSpecChange:
        """Parse individual OpenSpec change directory."""
        change_id = change_dir.name

        change = OpenSpecChange(id=change_id, path=change_dir)

        # Parse proposal.md
        proposal_file = change_dir / "proposal.md"
        if proposal_file.exists():
            change.proposal = self._parse_proposal(proposal_file)

        # Parse tasks.md
        tasks_file = change_dir / "tasks.md"
        if tasks_file.exists():
            change.tasks = self._parse_tasks(tasks_file)

        # Parse design.md
        design_file = change_dir / "design.md"
        if design_file.exists():
            change.design = self._parse_design(design_file)

        # Extract metadata
        change.metadata = self._extract_change_metadata(change_dir)

        return change

    def _parse_proposal(self, proposal_file: Path) -> OpenSpecProposal:
        """Parse OpenSpec proposal.md file."""
        content = proposal_file.read_text(encoding="utf-8")

        # Extract title (first heading)
        title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
        title = title_match.group(1) if title_match else proposal_file.parent.name

        # Extract "Why" section
        why_match = re.search(r"##\s+Why\s*\n(.*?)(?=##|\Z)", content, re.DOTALL | re.IGNORECASE)
        why = why_match.group(1).strip() if why_match else ""

        # Extract "What Changes" section
        what_match = re.search(
            r"##\s+What\s+Changes?\s*\n(.*?)(?=##|\Z)", content, re.DOTALL | re.IGNORECASE
        )
        what_changes = []
        if what_match:
            what_content = what_match.group(1).strip()
            # Extract bullet points
            what_changes = re.findall(r"^\s*[-*]\s+(.+)", what_content, re.MULTILINE)

        # Extract impact information
        impact = self._parse_impact_section(content)

        return OpenSpecProposal(
            title=title, why=why, what_changes=what_changes, impact=impact, raw_content=content
        )

    def _parse_impact_section(self, content: str) -> OpenSpecImpact:
        """Parse impact section from proposal content."""
        impact = OpenSpecImpact()

        # Extract affected specs
        specs_match = re.search(
            r"###\s+Affected\s+Specs\s*\n(.*?)(?=###|\Z)", content, re.DOTALL | re.IGNORECASE
        )
        if specs_match:
            specs_content = specs_match.group(1).strip()
            impact.affected_specs = re.findall(
                r"^\s*[-*]\s+\*\*([^*]+)\*\*", specs_content, re.MULTILINE
            )

        # Extract affected code
        code_match = re.search(
            r"###\s+Affected\s+Code\s*\n(.*?)(?=###|\Z)", content, re.DOTALL | re.IGNORECASE
        )
        if code_match:
            code_content = code_match.group(1).strip()
            impact.affected_code = re.findall(r"^\s*[-*]\s+`([^`]+)`", code_content, re.MULTILINE)

        # Extract dependencies
        deps_match = re.search(
            r"###\s+Dependencies\s*\n(.*?)(?=###|\Z)", content, re.DOTALL | re.IGNORECASE
        )
        if deps_match:
            deps_content = deps_match.group(1).strip()
            impact.dependencies = re.findall(r"^\s*[-*]\s+(.+)", deps_content, re.MULTILINE)

        return impact

    def _parse_tasks(self, tasks_file: Path) -> OpenSpecTasks:
        """Parse OpenSpec tasks.md file."""
        content = tasks_file.read_text(encoding="utf-8")
        tasks = []

        # Parse task items (looking for checkbox format)
        task_pattern = r"^\s*-\s*\[\s*([x\s])\s*\]\s*(\d+(?:\.\d+)*)\s+(.+)"

        current_task = None
        for line in content.split("\n"):
            task_match = re.match(task_pattern, line)
            if task_match:
                # Save previous task if exists
                if current_task:
                    tasks.append(current_task)

                # Create new task
                completed = task_match.group(1).lower() == "x"
                task_id = task_match.group(2)
                description = task_match.group(3).strip()

                current_task = OpenSpecTask(
                    id=task_id, description=description, completed=completed
                )
            elif line.strip().startswith("-") and current_task:
                # This is a subtask
                subtask = line.strip()[1:].strip()
                if subtask:
                    current_task.subtasks.append(subtask)
            elif line.strip().startswith("Notes:") and current_task:
                # This is a note
                current_task.notes = line.strip()[6:].strip()

        # Add final task
        if current_task:
            tasks.append(current_task)

        return OpenSpecTasks(tasks=tasks, raw_content=content)

    def _parse_design(self, design_file: Path) -> OpenSpecDesign:
        """Parse OpenSpec design.md file."""
        content = design_file.read_text(encoding="utf-8")

        # Extract sections
        sections = {}
        current_section = None
        current_content: list[Any] = []

        for line in content.split("\n"):
            if line.startswith("##"):
                # Save previous section
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()

                # Start new section
                current_section = line[2:].strip()
                current_content = []
            else:
                current_content.append(line)

        # Save final section
        if current_section:
            sections[current_section] = "\n".join(current_content).strip()

        return OpenSpecDesign(content=content, sections=sections)

    def _extract_change_metadata(self, change_dir: Path) -> dict:
        """Extract metadata from change directory."""
        metadata = {"directory_name": change_dir.name, "files_present": []}

        # List all files in change directory
        for file_path in change_dir.rglob("*"):
            if file_path.is_file():
                metadata["files_present"].append(str(file_path.relative_to(change_dir)))

        return metadata

    def _scan_specs(self) -> list[OpenSpecSpec]:
        """Extract all specifications from openspec/specs/."""
        specs: list[Any] = []
        specs_path = self.openspec_path / "specs"

        if not specs_path.exists():
            logger.warning(f"Specs directory not found: {specs_path}")
            return specs

        for spec_dir in specs_path.iterdir():
            if spec_dir.is_dir():
                try:
                    spec = self._parse_spec(spec_dir)
                    specs.append(spec)
                    logger.debug(f"Parsed spec: {spec.name}")
                except Exception as e:
                    logger.error(f"Failed to parse spec {spec_dir.name}: {e}")

        return specs

    def _parse_spec(self, spec_dir: Path) -> OpenSpecSpec:
        """Parse individual OpenSpec specification directory."""
        spec_file = spec_dir / "spec.md"

        if not spec_file.exists():
            raise ContentParsingError(f"spec.md not found in {spec_dir}")

        content = spec_file.read_text(encoding="utf-8")

        # Extract sections similar to design parsing
        sections = {}
        current_section = None
        current_content: list[Any] = []

        for line in content.split("\n"):
            if line.startswith("##"):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = line[2:].strip()
                current_content = []
            else:
                current_content.append(line)

        if current_section:
            sections[current_section] = "\n".join(current_content).strip()

        return OpenSpecSpec(name=spec_dir.name, path=spec_dir, content=content, sections=sections)

    def _parse_project_md(self) -> str | None:
        """Parse openspec/project.md file."""
        project_file = self.openspec_path / "project.md"

        if project_file.exists():
            return project_file.read_text(encoding="utf-8")

        return None

    def _parse_agents_md(self) -> str | None:
        """Parse openspec/AGENTS.md file."""
        agents_file = self.openspec_path / "AGENTS.md"

        if agents_file.exists():
            return agents_file.read_text(encoding="utf-8")

        return None

    def _list_archived_changes(self) -> list[str]:
        """List archived changes."""
        archived = []
        archive_path = self.openspec_path / "changes" / "archive"

        if archive_path.exists():
            for item in archive_path.iterdir():
                if item.is_dir():
                    archived.append(item.name)

        return archived
