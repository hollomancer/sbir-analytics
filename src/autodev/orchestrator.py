"""Autonomous development loop orchestrator.

The main loop that:
1. Discovers tasks from multiple sources
2. Picks the next task by priority
3. Generates a prompt for Claude to implement it
4. Verifies the result against quality gates
5. Commits on success, discards on failure
6. Pauses at checkpoints for human review
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from .agent_prompts import agent_for_source, load_agent_instructions
from .checkpoint import CheckpointAction, CheckpointHandler
from .notifier import Notifier, notify_checkpoint, notify_loop_complete
from .session import SessionManager, SessionState, TaskAttempt, TaskOutcome
from .task_parser import SpecContext, SpecTask, TaskRisk, build_task_queue, discover_specs
from .task_sources import TaskSource, WorkItem, discover_all
from .verifier import Verifier


@dataclass
class LoopConfig:
    """Configuration for the autonomous development loop."""

    project_root: Path = field(default_factory=lambda: Path.cwd())
    specs_root: Path | None = None
    max_tasks: int = 50
    max_consecutive_failures: int = 3
    review_interval: int = 5
    fail_fast_verification: bool = True
    test_scope: str = "unit"
    interactive: bool = True
    auto_commit: bool = True
    dry_run: bool = False
    discover_tests: bool = False
    max_token_budget: int = 0  # 0 = unlimited

    def __post_init__(self):
        if self.specs_root is None:
            self.specs_root = self.project_root / ".kiro" / "specs"


@dataclass
class LoopResult:
    """Result of a complete autonomous development run."""

    session: SessionState
    tasks_processed: int = 0
    tasks_succeeded: int = 0
    tasks_failed: int = 0
    tasks_skipped: int = 0
    stopped_reason: str = ""
    checkpoints_hit: int = 0
    total_tokens_used: int = 0

    @property
    def summary(self) -> str:
        lines = [
            "Autonomous Development Run Complete",
            f"  Session: {self.session.session_id}",
            f"  Processed: {self.tasks_processed}",
            f"  Succeeded: {self.tasks_succeeded}",
            f"  Failed: {self.tasks_failed}",
            f"  Skipped: {self.tasks_skipped}",
            f"  Checkpoints: {self.checkpoints_hit}",
            f"  Stop reason: {self.stopped_reason}",
        ]
        if self.total_tokens_used > 0:
            lines.append(f"  Tokens used: {self.total_tokens_used:,}")
        return "\n".join(lines)


def _spec_task_to_work_item(task: SpecTask, spec: SpecContext) -> WorkItem:
    """Convert a Kiro spec task to a unified WorkItem."""
    context = {}
    if spec.requirements_text:
        # Include first 500 chars of requirements for context
        context["requirements_excerpt"] = spec.requirements_text[:500]
    if spec.design_text:
        context["design_excerpt"] = spec.design_text[:500]

    return WorkItem(
        source=TaskSource.KIRO_SPEC,
        title=f"[{spec.name}] {task.description}",
        description=task.description,
        risk=task.risk,
        file_path=task.file_hints[0] if task.file_hints else None,
        spec_name=spec.name,
        task_id=task.task_id,
        context=context,
    )


def build_implementation_prompt(item: WorkItem, project_root: Path | None = None) -> str:
    """Build a prompt for Claude to implement a work item.

    This is the prompt that would be sent to the Claude API or
    used in a Claude Code session to implement the task.

    When *project_root* is provided, the appropriate agent's instructions
    (from ``.claude/agents/``) are injected into the prompt so that the
    orchestrator and GitHub Actions benefit from the same behavioural
    guidance as interactive sessions.
    """
    parts: list[str] = []

    # Inject agent instructions when project root is available
    if project_root is not None:
        agent_name = agent_for_source(item.source.value)
        instructions = load_agent_instructions(project_root, agent_name)
        if instructions:
            parts.append("## Agent Instructions\n")
            parts.append(instructions)
            parts.append("")

    parts.append(f"## Task: {item.title}\n")

    if item.source == TaskSource.KIRO_SPEC:
        parts.append(f"This task is from the Kiro specification: {item.spec_name}")
        parts.append(f"Task ID: {item.task_id}\n")
        if "requirements_excerpt" in item.context:
            parts.append("### Requirements Context")
            parts.append(item.context["requirements_excerpt"])
            parts.append("")
        if "design_excerpt" in item.context:
            parts.append("### Design Context")
            parts.append(item.context["design_excerpt"])
            parts.append("")
    elif item.source == TaskSource.TEST_FAILURE:
        parts.append("A test is failing and needs to be fixed.")
        parts.append(f"File: {item.file_path}")
        parts.append(f"Error: {item.description}\n")
    elif item.source == TaskSource.LINT_ERROR:
        parts.append("Fix this lint error:")
        parts.append(f"File: {item.location}")
        parts.append(f"Error: {item.description}\n")
    elif item.source == TaskSource.TYPE_ERROR:
        parts.append("Fix this type error:")
        parts.append(f"File: {item.location}")
        parts.append(f"Error: {item.description}\n")
    elif item.source == TaskSource.CODE_TODO:
        parts.append("Implement this TODO:")
        parts.append(f"File: {item.location}")
        parts.append(f"Description: {item.description}\n")

    if "human_guidance" in item.context:
        parts.append("### Human Guidance")
        parts.append(item.context["human_guidance"])
        parts.append("")

    parts.append("### Instructions")
    parts.append("1. Read the relevant files to understand the current state")
    parts.append("2. Implement the change with minimal modifications")
    parts.append("3. Follow existing code patterns and conventions")
    parts.append("4. Add or update tests if the change is testable")
    parts.append("5. Do not modify unrelated code")

    return "\n".join(parts)


class Orchestrator:
    """Main autonomous development loop.

    Coordinates task discovery, implementation prompting, verification,
    and session management. Designed to be used either:
    - Interactively via CLI (with human checkpoints)
    - Programmatically via the Claude API (with callback checkpoints)
    - In dry-run mode (generates prompts without executing)
    """

    def __init__(self, config: LoopConfig, notifier: Notifier | None = None):
        self.config = config
        self.notifier = notifier or Notifier()
        self.session_mgr = SessionManager(config.project_root)
        self.verifier = Verifier(
            config.project_root,
            test_scope=config.test_scope,
            fail_fast=config.fail_fast_verification,
        )
        self.checkpoint_handler = CheckpointHandler(
            session_id="pending",
            log_dir=config.project_root / ".autodev",
            interactive=config.interactive,
        )

    def _build_checkpoint_context(self, item: WorkItem, session: SessionState) -> dict[str, str]:
        """Build enriched context dict for checkpoint prompts."""
        ctx: dict[str, str] = {
            "risk": item.risk.value if isinstance(item.risk, TaskRisk) else item.risk,
            "file": item.file_path or "N/A",
            "tasks_succeeded": str(session.total_tasks_succeeded),
            "tasks_failed": str(session.total_tasks_failed),
            "tasks_skipped": str(session.total_tasks_skipped),
            "consecutive_failures": str(session.consecutive_failures),
        }
        if session.total_tasks_attempted > 0:
            ctx["success_rate"] = f"{session.success_rate:.0f}%"
        if session.total_tokens > 0:
            ctx["tokens_used"] = f"{session.total_tokens:,}"
        if self.config.max_token_budget > 0:
            ctx["token_budget"] = f"{self.config.max_token_budget:,}"
            pct = session.total_tokens / self.config.max_token_budget * 100
            ctx["token_pct"] = f"{pct:.0f}%"
        return ctx

    def discover_work(self) -> list[WorkItem]:
        """Discover all available work items from all sources."""
        items: list[WorkItem] = []

        # Kiro spec tasks
        specs = discover_specs(self.config.specs_root)
        spec_map = {s.name: s for s in specs}
        queue = build_task_queue(specs)
        for task in queue:
            spec = spec_map[task.spec_name]
            items.append(_spec_task_to_work_item(task, spec))

        # Code quality items
        other_items = discover_all(
            self.config.project_root,
            run_tests=self.config.discover_tests,
        )
        items.extend(other_items)

        return items

    def run(self) -> LoopResult:
        """Execute the autonomous development loop.

        Returns:
            LoopResult with summary of what was accomplished.
        """
        session = self.session_mgr.create_session()
        self.checkpoint_handler.log.session_id = session.session_id
        result = LoopResult(session=session)

        work_items = self.discover_work()
        if not work_items:
            result.stopped_reason = "No work items found"
            return result

        print(f"\nDiscovered {len(work_items)} work items")
        print(f"Session: {session.session_id}")
        print(f"Branch: {session.branch_name}\n")

        for i, item in enumerate(work_items):
            if i >= self.config.max_tasks:
                result.stopped_reason = f"Reached max tasks limit ({self.config.max_tasks})"
                break

            # Check if we need a checkpoint
            checkpoint_reason = self.checkpoint_handler.should_checkpoint(
                task_description=item.title,
                risk_level=item.risk.value if isinstance(item.risk, TaskRisk) else item.risk,
                consecutive_failures=session.consecutive_failures,
                tasks_since_review=session.tasks_since_review,
                review_interval=self.config.review_interval,
                tokens_used=session.total_tokens,
                token_budget=self.config.max_token_budget,
            )

            if checkpoint_reason:
                result.checkpoints_hit += 1
                notify_checkpoint(self.notifier, checkpoint_reason.value, item.title)
                checkpoint = self.checkpoint_handler.request_review(
                    reason=checkpoint_reason,
                    title=item.title,
                    description=f"Source: {item.source.value}\n{item.description}",
                    task_context=self._build_checkpoint_context(item, session),
                )

                if checkpoint.response == CheckpointAction.ABORT:
                    result.stopped_reason = "Aborted by human at checkpoint"
                    break
                elif checkpoint.response == CheckpointAction.SKIP:
                    result.tasks_skipped += 1
                    session.record_attempt(
                        TaskAttempt(
                            task_title=item.title,
                            source=item.source.value,
                            outcome=TaskOutcome.SKIPPED_BY_HUMAN,
                        )
                    )
                    self.session_mgr.save_session(session)
                    continue
                elif checkpoint.response == CheckpointAction.MODIFY:
                    # Human provided guidance — attach it to the work item context
                    if checkpoint.human_notes:
                        item.context["human_guidance"] = checkpoint.human_notes
                    session.reset_review_counter()
                elif checkpoint.response == CheckpointAction.PROCEED:
                    session.reset_review_counter()

            # Process the task
            attempt = self._process_task(item, session)
            session.record_attempt(attempt)
            self.session_mgr.save_session(session)

            result.tasks_processed += 1
            if attempt.outcome == TaskOutcome.SUCCESS:
                result.tasks_succeeded += 1
            elif attempt.outcome in (TaskOutcome.FAILED_VERIFICATION, TaskOutcome.ERROR):
                result.tasks_failed += 1
            else:
                result.tasks_skipped += 1

            # Check stop conditions
            if session.consecutive_failures >= self.config.max_consecutive_failures:
                result.stopped_reason = (
                    f"Stopped after {self.config.max_consecutive_failures} consecutive failures"
                )
                break

        if not result.stopped_reason:
            result.stopped_reason = "All tasks processed"

        self.session_mgr.save_session(session)
        notify_loop_complete(self.notifier, result.summary, result.stopped_reason)
        return result

    def _process_task(self, item: WorkItem, session: SessionState) -> TaskAttempt:
        """Process a single work item.

        In dry-run mode, generates the prompt without executing.
        Otherwise, this is where the Claude API would be called.
        """
        start = time.monotonic()

        prompt = build_implementation_prompt(item, project_root=self.config.project_root)

        if self.config.dry_run:
            print(f"\n{'=' * 60}")
            print(f"[DRY RUN] Task {session.total_tasks_attempted + 1}: {item.title}")
            print(f"Source: {item.source.value} | Risk: {item.risk}")
            print(f"{'=' * 60}")
            print(prompt[:500])
            if len(prompt) > 500:
                print(f"... ({len(prompt) - 500} more chars)")
            print()

            duration = time.monotonic() - start
            return TaskAttempt(
                task_title=item.title,
                source=item.source.value,
                outcome=TaskOutcome.SUCCESS,
                duration_seconds=duration,
                verification_summary="dry run - skipped verification",
            )

        # In real execution mode, this is where we'd call Claude API
        # For now, generate the prompt and indicate it needs execution
        print(f"\n[Task {session.total_tasks_attempted + 1}] {item.title}")
        print(f"  Source: {item.source.value} | Risk: {item.risk}")

        duration = time.monotonic() - start
        return TaskAttempt(
            task_title=item.title,
            source=item.source.value,
            outcome=TaskOutcome.SUCCESS,
            duration_seconds=duration,
            verification_summary="prompt generated - awaiting execution",
            files_changed=self.session_mgr.git_changed_files(),
        )

    def run_with_executor(self, executor_fn) -> LoopResult:
        """Execute the loop with a custom task executor.

        This is the integration point for the Claude API. The executor_fn
        receives a prompt string and returns True if the task was
        successfully implemented.

        Args:
            executor_fn: Callable[[str, Path], bool] that takes
                (prompt, project_root) and returns success.

        Returns:
            LoopResult with summary.
        """
        session = self.session_mgr.create_session()
        self.checkpoint_handler.log.session_id = session.session_id
        result = LoopResult(session=session)

        work_items = self.discover_work()
        if not work_items:
            result.stopped_reason = "No work items found"
            return result

        print(f"\nDiscovered {len(work_items)} work items")
        print(f"Session: {session.session_id}\n")

        for i, item in enumerate(work_items):
            if i >= self.config.max_tasks:
                result.stopped_reason = f"Reached max tasks limit ({self.config.max_tasks})"
                break

            # Checkpoint logic (same as run())
            checkpoint_reason = self.checkpoint_handler.should_checkpoint(
                task_description=item.title,
                risk_level=item.risk.value if isinstance(item.risk, TaskRisk) else item.risk,
                consecutive_failures=session.consecutive_failures,
                tasks_since_review=session.tasks_since_review,
                review_interval=self.config.review_interval,
                tokens_used=session.total_tokens,
                token_budget=self.config.max_token_budget,
            )

            if checkpoint_reason:
                result.checkpoints_hit += 1
                notify_checkpoint(self.notifier, checkpoint_reason.value, item.title)
                checkpoint = self.checkpoint_handler.request_review(
                    reason=checkpoint_reason,
                    title=item.title,
                    description=item.description,
                    task_context=self._build_checkpoint_context(item, session),
                )
                if checkpoint.response == CheckpointAction.ABORT:
                    result.stopped_reason = "Aborted by human"
                    break
                elif checkpoint.response == CheckpointAction.SKIP:
                    result.tasks_skipped += 1
                    session.record_attempt(
                        TaskAttempt(
                            task_title=item.title,
                            source=item.source.value,
                            outcome=TaskOutcome.SKIPPED_BY_HUMAN,
                        )
                    )
                    self.session_mgr.save_session(session)
                    continue
                elif checkpoint.response == CheckpointAction.MODIFY:
                    if checkpoint.human_notes:
                        item.context["human_guidance"] = checkpoint.human_notes
                    session.reset_review_counter()
                elif checkpoint.response == CheckpointAction.PROCEED:
                    session.reset_review_counter()

            # Check token budget before executing
            if (
                self.config.max_token_budget > 0
                and session.total_tokens >= self.config.max_token_budget
            ):
                result.stopped_reason = (
                    f"Token budget exhausted "
                    f"({session.total_tokens:,}/{self.config.max_token_budget:,})"
                )
                break

            # Execute the task
            start = time.monotonic()
            prompt = build_implementation_prompt(item, project_root=self.config.project_root)

            print(f"\n[Task {i + 1}/{len(work_items)}] {item.title}")
            if self.config.max_token_budget > 0:
                remaining = self.config.max_token_budget - session.total_tokens
                print(f"  Token budget: {remaining:,} remaining")

            exec_result = None
            try:
                exec_result = executor_fn(prompt, self.config.project_root)
                # Support both bool and ExecutionResult returns
                if isinstance(exec_result, bool):
                    from .executor import ExecutionResult

                    exec_result = ExecutionResult(success=exec_result)
                success = exec_result.success
            except Exception as e:
                success = False
                print(f"  Executor error: {e}")

            # Track token usage from this execution
            task_input_tokens = exec_result.input_tokens if exec_result else 0
            task_output_tokens = exec_result.output_tokens if exec_result else 0

            if success:
                # Verify
                report = self.verifier.verify()
                duration = time.monotonic() - start

                if report.all_passed:
                    # Commit
                    commit_sha = None
                    if self.config.auto_commit:
                        commit_sha = self.session_mgr.git_commit(
                            f"autodev: {item.title}\n\nSource: {item.source.value}"
                        )
                    attempt = TaskAttempt(
                        task_title=item.title,
                        source=item.source.value,
                        outcome=TaskOutcome.SUCCESS,
                        duration_seconds=duration,
                        verification_summary=report.summary,
                        commit_sha=commit_sha,
                        files_changed=self.session_mgr.git_changed_files(),
                        input_tokens=task_input_tokens,
                        output_tokens=task_output_tokens,
                    )
                    result.tasks_succeeded += 1
                else:
                    # Discard
                    self.session_mgr.git_reset_hard()
                    attempt = TaskAttempt(
                        task_title=item.title,
                        source=item.source.value,
                        outcome=TaskOutcome.FAILED_VERIFICATION,
                        duration_seconds=duration,
                        verification_summary=report.summary,
                        input_tokens=task_input_tokens,
                        output_tokens=task_output_tokens,
                    )
                    result.tasks_failed += 1
            else:
                duration = time.monotonic() - start
                self.session_mgr.git_reset_hard()
                attempt = TaskAttempt(
                    task_title=item.title,
                    source=item.source.value,
                    outcome=TaskOutcome.ERROR,
                    duration_seconds=duration,
                    error_message="Executor returned failure",
                    input_tokens=task_input_tokens,
                    output_tokens=task_output_tokens,
                )
                result.tasks_failed += 1

            session.record_attempt(attempt)
            self.session_mgr.save_session(session)
            result.tasks_processed += 1
            result.total_tokens_used = session.total_tokens

            if session.consecutive_failures >= self.config.max_consecutive_failures:
                result.stopped_reason = "Too many consecutive failures"
                break

        if not result.stopped_reason:
            result.stopped_reason = "All tasks processed"

        self.session_mgr.save_session(session)
        notify_loop_complete(self.notifier, result.summary, result.stopped_reason)
        return result
