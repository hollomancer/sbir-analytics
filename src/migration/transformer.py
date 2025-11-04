"""
Content Transformer

This module transforms OpenSpec content to Kiro format, including
EARS pattern conversion and user story generation.
"""

import re

from loguru import logger

from .models import (
    KiroContent,
    KiroDesign,
    KiroRequirement,
    KiroRequirements,
    KiroSpec,
    KiroTask,
    KiroTasks,
    OpenSpecContent,
    TransformationError,
)


class ContentTransformer:
    """Transforms OpenSpec content to Kiro format."""

    def __init__(self):
        """Initialize transformer."""
        self.ears_converter = EARSConverter()

    def transform_content(self, openspec_content: OpenSpecContent) -> KiroContent:
        """Transform all OpenSpec content to Kiro format."""
        logger.info("Starting content transformation")

        try:
            kiro_content = KiroContent(
                specs=self._convert_changes_to_specs(openspec_content.active_changes),
                consolidation_mapping=self._plan_spec_consolidation(
                    openspec_content.specifications
                ),
            )

            # Add consolidated specs from OpenSpec specifications
            consolidated_specs = self._consolidate_specs(openspec_content.specifications)
            kiro_content.specs.extend(consolidated_specs)

            logger.info(
                f"Transformation complete: {len(kiro_content.specs)} Kiro specs generated"
            )

            return kiro_content

        except Exception as e:
            raise TransformationError(f"Failed to transform content: {e}")

    def _convert_changes_to_specs(self, changes) -> list[KiroSpec]:
        """Convert OpenSpec changes to Kiro specs."""
        kiro_specs = []

        for change in changes:
            try:
                spec = self._convert_single_change(change)
                kiro_specs.append(spec)
                logger.debug(f"Converted change {change.id} to spec {spec.name}")
            except Exception as e:
                logger.error(f"Failed to convert change {change.id}: {e}")

        return kiro_specs

    def _convert_single_change(self, change) -> KiroSpec:
        """Convert single OpenSpec change to Kiro spec."""
        spec_name = self._generate_spec_name(change)

        # Convert proposal to requirements
        requirements = None
        if change.proposal:
            requirements = self._convert_proposal_to_requirements(change.proposal)

        # Convert design if present
        design = None
        if change.design:
            design = self._convert_design(change.design)

        # Convert tasks
        tasks = None
        if change.tasks:
            tasks = self._convert_tasks(change.tasks)

        return KiroSpec(
            name=spec_name,
            requirements=requirements,
            design=design,
            tasks=tasks,
            source_mapping={
                "openspec_change_id": change.id,
                "source_files": change.metadata.get("files_present", []),
            },
        )

    def _generate_spec_name(self, change) -> str:
        """Generate Kiro spec name from OpenSpec change."""
        # Convert change ID to spec name
        name = change.id.replace("add-", "").replace("evaluate-", "")
        name = name.replace("-", "_")
        return name

    def _convert_proposal_to_requirements(self, proposal) -> KiroRequirements:
        """Convert OpenSpec proposal to Kiro requirements with EARS patterns."""
        # Extract user stories from proposal content
        user_stories = self._extract_user_stories(proposal)

        # Convert to EARS requirements
        requirements = []
        for i, story in enumerate(user_stories, 1):
            requirement = self.ears_converter.convert_to_ears_requirement(story, i)
            requirements.append(requirement)

        return KiroRequirements(
            introduction=self._generate_introduction(proposal),
            glossary=self._extract_glossary_terms(proposal),
            requirements=requirements,
        )

    def _extract_user_stories(self, proposal) -> list[dict]:
        """Extract user stories from proposal content."""
        stories = []

        # Primary story from the proposal title and why section
        primary_story = {
            "persona": "developer",
            "goal": proposal.title.lower(),
            "benefit": self._extract_benefit_from_why(proposal.why),
        }
        stories.append(primary_story)

        # Additional stories from what_changes items
        for _i, change in enumerate(proposal.what_changes[:3], 2):  # Limit to 3 additional stories
            story = {
                "persona": "developer",
                "goal": change.strip().rstrip("."),
                "benefit": "support the enhanced functionality described in the proposal",
            }
            stories.append(story)

        return stories

    def _extract_benefit_from_why(self, why_text: str) -> str:
        """Extract benefit statement from why section."""
        # Clean up the why text and extract key benefit
        sentences = why_text.split(".")
        if sentences:
            # Take the first sentence as the primary benefit
            benefit = sentences[0].strip()
            if benefit:
                return benefit.lower()

        return "address the requirements described in the proposal"

    def _generate_introduction(self, proposal) -> str:
        """Generate introduction from proposal."""
        return f"This specification implements {proposal.title}.\n\n{proposal.why}"

    def _extract_glossary_terms(self, proposal) -> dict[str, str]:
        """Extract glossary terms from proposal."""
        glossary = {}

        # Extract technical terms from the proposal content
        content = f"{proposal.title} {proposal.why} {' '.join(proposal.what_changes)}"

        # Common technical patterns to extract
        patterns = [
            (r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b", "technical_term"),  # CamelCase terms
            (r"\b([A-Z]{2,})\b", "acronym"),  # Acronyms
            (r"`([^`]+)`", "code_term"),  # Code terms in backticks
            (r"\*\*([^*]+)\*\*", "emphasized_term"),  # Bold terms
        ]

        for pattern, term_type in patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                if len(match) > 2 and match not in glossary:
                    # Generate a definition based on context
                    definition = self._generate_definition(match, term_type, content)
                    if definition:
                        glossary[match] = definition

        return glossary

    def _generate_definition(self, term: str, term_type: str, content: str) -> str:
        """Generate a definition for a glossary term."""
        if term_type == "acronym":
            return "System component or technology referenced in the implementation"
        elif term_type == "code_term":
            return f"Code component or file: {term}"
        elif term_type == "emphasized_term":
            return f"Key concept: {term}"
        elif term_type == "technical_term":
            return f"Technical component or system: {term}"

        return f"System component: {term}"

    def _convert_design(self, design) -> KiroDesign:
        """Convert OpenSpec design to Kiro design."""
        return KiroDesign(
            overview=design.sections.get("Overview", ""),
            architecture=design.sections.get("Architecture", ""),
            components=design.sections.get("Components", ""),
            data_models=design.sections.get("Data Models", ""),
            error_handling=design.sections.get("Error Handling", ""),
            testing_strategy=design.sections.get("Testing Strategy", ""),
            source_content=design.content,
        )

    def _convert_tasks(self, tasks) -> KiroTasks:
        """Convert OpenSpec tasks to Kiro tasks."""
        kiro_tasks = []

        for task in tasks.tasks:
            kiro_task = KiroTask(
                number=task.id,
                description=task.description,
                subtasks=task.subtasks,
                completed=task.completed,
                optional=task.description.endswith("*"),
            )
            kiro_tasks.append(kiro_task)

        return KiroTasks(tasks=kiro_tasks)

    def _plan_spec_consolidation(self, specifications) -> dict[str, list[str]]:
        """Plan consolidation of OpenSpec specifications."""
        consolidation_mapping = {}

        # Group related specifications by functional area
        functional_groups = {
            "data_pipeline": [
                "data-extraction",
                "data-validation",
                "data-transformation",
                "data-loading",
            ],
            "data_enrichment": ["data-enrichment"],
            "infrastructure": ["neo4j-server", "runtime-environment"],
            "orchestration": ["pipeline-orchestration"],
            "configuration": ["configuration"],
        }

        # Create mapping from spec names to their groups
        spec_names = [spec.name for spec in specifications]

        for group_name, group_specs in functional_groups.items():
            matching_specs = [spec for spec in group_specs if spec in spec_names]
            if matching_specs:
                consolidation_mapping[group_name] = matching_specs

        # Handle any ungrouped specs
        grouped_specs = set()
        for specs in consolidation_mapping.values():
            grouped_specs.update(specs)

        ungrouped = [spec for spec in spec_names if spec not in grouped_specs]
        if ungrouped:
            consolidation_mapping["miscellaneous"] = ungrouped

        return consolidation_mapping

    def _consolidate_specs(self, specifications) -> list[KiroSpec]:
        """Consolidate OpenSpec specifications into Kiro specs."""
        consolidated_specs = []
        consolidation_mapping = self._plan_spec_consolidation(specifications)

        for group_name, spec_names in consolidation_mapping.items():
            # Find the actual spec objects
            group_specs = [spec for spec in specifications if spec.name in spec_names]

            if group_specs:
                consolidated_spec = self._create_consolidated_spec(group_name, group_specs)
                consolidated_specs.append(consolidated_spec)

        return consolidated_specs

    def _create_consolidated_spec(self, group_name: str, specs) -> KiroSpec:
        """Create a consolidated Kiro spec from multiple OpenSpec specs."""
        # Combine content from all specs in the group
        combined_content = []
        combined_sections = {}

        for spec in specs:
            combined_content.append(f"## {spec.name.title().replace('-', ' ')}\n\n{spec.content}")
            combined_sections.update(spec.sections)

        # Generate requirements from consolidated content
        requirements = self._generate_consolidated_requirements(group_name, specs)

        # Create consolidated design
        design = KiroDesign(
            overview=f"This specification consolidates {len(specs)} related OpenSpec specifications: {', '.join([spec.name for spec in specs])}",
            architecture=combined_sections.get("Architecture", ""),
            components=combined_sections.get("Components", ""),
            data_models=combined_sections.get("Data Models", ""),
            error_handling=combined_sections.get("Error Handling", ""),
            testing_strategy=combined_sections.get("Testing Strategy", ""),
            source_content="\n\n".join(combined_content),
        )

        return KiroSpec(
            name=f"{group_name}_consolidated",
            requirements=requirements,
            design=design,
            tasks=None,  # Consolidated specs don't have tasks
            source_mapping={
                "consolidated_from": [spec.name for spec in specs],
                "consolidation_type": "functional_grouping",
            },
        )

    def _generate_consolidated_requirements(self, group_name: str, specs) -> KiroRequirements:
        """Generate requirements for consolidated spec."""
        # Create a user story for the consolidated functionality
        user_story = {
            "persona": "developer",
            "goal": f"consolidated {group_name.replace('_', ' ')} functionality",
            "benefit": f"have a unified approach to {group_name.replace('_', ' ')} across the system",
        }

        # Generate EARS requirement
        requirement = self.ears_converter.convert_to_ears_requirement(user_story, 1)

        return KiroRequirements(
            introduction=f"This consolidated specification covers {group_name.replace('_', ' ')} functionality from multiple OpenSpec specifications.",
            glossary=self._extract_consolidated_glossary(specs),
            requirements=[requirement],
        )

    def _extract_consolidated_glossary(self, specs) -> dict[str, str]:
        """Extract glossary terms from multiple specs."""
        glossary = {}

        # Common words to exclude from glossary
        excluded_words = {
            "THE",
            "AND",
            "OR",
            "NOT",
            "FOR",
            "FROM",
            "TO",
            "OF",
            "IN",
            "ON",
            "AT",
            "BY",
            "WITH",
            "SHALL",
            "WHEN",
            "THEN",
            "WHERE",
            "CASE",
            "ELSE",
            "END",
            "IF",
            "GIVEN",
            "PROVIDED",
            "SEE",
            "DOCUMENT",
            "DETAILS",
            "UNKNOWN",
            "ERROR",
            "WARNING",
            "INFO",
            "SET",
            "GET",
            "ORDER",
            "GROUP",
            "HAVING",
            "COUNT",
            "SELECT",
            "RETURN",
            "MATCH",
            "LIMIT",
            "DESC",
            "LEFT",
            "JOIN",
            "BETWEEN",
            "UNWIND",
            "OWNS",
            "FUNDED",
            "ALIGNED",
            "MISALIGNED",
        }

        for spec in specs:
            # Extract technical terms from spec content
            content = spec.content

            # Look for meaningful technical terms
            patterns = [
                (
                    r"\b([A-Z][a-z]+(?:[A-Z][a-z]+){2,})\b",
                    "technical_term",
                ),  # Longer CamelCase terms
                (
                    r"\b(API|ETL|CSV|SQL|JSON|YAML|ISO|UEI|DUNS|ZIP|SBIR|STTR|CET|NSTC|USPTO|IBM)\b",
                    "acronym",
                ),  # Specific acronyms
            ]

            for pattern, term_type in patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if len(match) > 3 and match not in excluded_words and match not in glossary:
                        if term_type == "acronym":
                            glossary[match] = f"System acronym referenced in {spec.name}"
                        else:
                            glossary[match] = f"Technical component from {spec.name}: {match}"

        return glossary


class EARSConverter:
    """Converts content to EARS (Easy Approach to Requirements Syntax) patterns."""

    def convert_to_ears_requirement(self, user_story: dict, number: int) -> KiroRequirement:
        """Convert user story to EARS requirement."""
        # Generate user story text
        story_text = f"As a {user_story['persona']}, I want {user_story['goal']}, so that {user_story['benefit']}."

        # Generate EARS acceptance criteria
        acceptance_criteria = self._generate_ears_criteria(user_story)

        return KiroRequirement(
            number=number, user_story=story_text, acceptance_criteria=acceptance_criteria
        )

    def _generate_ears_criteria(self, user_story: dict) -> list[str]:
        """Generate EARS-compliant acceptance criteria."""
        criteria = []
        goal = user_story["goal"]

        # Extract key verbs and nouns from the goal
        if "add" in goal.lower() or "implement" in goal.lower():
            criteria.append(f"THE System SHALL implement {self._clean_goal(goal)}")
            criteria.append(
                f"THE System SHALL validate the implementation of {self._clean_goal(goal)}"
            )
        elif "provide" in goal.lower() or "support" in goal.lower():
            criteria.append(f"THE System SHALL provide {self._clean_goal(goal)}")
        elif "enable" in goal.lower() or "allow" in goal.lower():
            criteria.append(f"THE System SHALL enable {self._clean_goal(goal)}")
        else:
            # Default EARS pattern
            criteria.append(f"THE System SHALL support {self._clean_goal(goal)}")

        # Add a validation criterion
        if len(criteria) == 1:
            criteria.append(f"THE System SHALL ensure proper operation of {self._clean_goal(goal)}")

        return criteria

    def _clean_goal(self, goal: str) -> str:
        """Clean and normalize goal text for EARS patterns."""
        # Remove common prefixes and clean up
        goal = goal.lower()
        goal = re.sub(r"^(add|implement|provide|support|enable|allow)\s+", "", goal)
        goal = goal.strip()
        return goal
