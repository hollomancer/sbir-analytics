"""Human-in-the-loop checkpoint system.

Provides mechanisms for the autonomous loop to pause and request human input
when encountering high-risk tasks, ambiguous requirements, or decision points.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import StrEnum
from pathlib import Path


class CheckpointReason(StrEnum):
    """Why the loop is pausing for human input."""

    HIGH_RISK_TASK = "high_risk_task"
    AMBIGUOUS_REQUIREMENT = "ambiguous_requirement"
    VERIFICATION_FAILURE = "verification_failure"
    DESIGN_DECISION = "design_decision"
    EXTERNAL_SERVICE = "external_service"
    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"
    SPEC_CLARIFICATION = "spec_clarification"
    PERIODIC_REVIEW = "periodic_review"
    TOKEN_BUDGET_WARNING = "token_budget_warning"


class CheckpointAction(StrEnum):
    """What the human decided at a checkpoint."""

    PROCEED = "proceed"
    SKIP = "skip"
    MODIFY = "modify"
    ABORT = "abort"


@dataclass
class Checkpoint:
    """A point where the loop paused for human input."""

    reason: CheckpointReason
    title: str
    description: str
    task_context: dict[str, str] = field(default_factory=dict)
    options: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    response: CheckpointAction | None = None
    human_notes: str = ""


@dataclass
class CheckpointLog:
    """Persistent log of all checkpoints in a session."""

    session_id: str
    checkpoints: list[Checkpoint] = field(default_factory=list)
    log_path: Path | None = None

    def add(self, checkpoint: Checkpoint) -> None:
        self.checkpoints.append(checkpoint)
        if self.log_path:
            self._persist()

    def _persist(self) -> None:
        """Write checkpoint log to disk for review."""
        if not self.log_path:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "session_id": self.session_id,
            "checkpoints": [
                {
                    "reason": cp.reason.value,
                    "title": cp.title,
                    "description": cp.description,
                    "task_context": cp.task_context,
                    "timestamp": cp.timestamp,
                    "response": cp.response.value if cp.response else None,
                    "human_notes": cp.human_notes,
                }
                for cp in self.checkpoints
            ],
        }
        self.log_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


class CheckpointHandler:
    """Manages checkpoint creation and resolution.

    In interactive mode, prompts the user via stdin.
    In non-interactive mode (CI/batch), writes checkpoints to a file
    and waits for them to be resolved externally.
    """

    def __init__(
        self,
        session_id: str,
        log_dir: Path | None = None,
        interactive: bool = True,
        auto_skip_medium_risk: bool = False,
        token_budget_warning_pct: float = 0.75,
    ):
        self.interactive = interactive
        self.auto_skip_medium_risk = auto_skip_medium_risk
        self.token_budget_warning_pct = token_budget_warning_pct
        self._token_warning_fired = False
        log_path = None
        if log_dir:
            log_path = log_dir / f"checkpoints-{session_id}.json"
        self.log = CheckpointLog(session_id=session_id, log_path=log_path)

    def request_review(
        self,
        reason: CheckpointReason,
        title: str,
        description: str,
        task_context: dict[str, str] | None = None,
    ) -> Checkpoint:
        """Create a checkpoint and get human response.

        In interactive mode, blocks until the user responds.
        In non-interactive mode, writes to log and returns SKIP.
        """
        checkpoint = Checkpoint(
            reason=reason,
            title=title,
            description=description,
            task_context=task_context or {},
        )

        if self.interactive:
            checkpoint = self._interactive_prompt(checkpoint)
        else:
            # Non-interactive: log and skip
            checkpoint.response = CheckpointAction.SKIP
            checkpoint.human_notes = "auto-skipped (non-interactive mode)"

        self.log.add(checkpoint)
        return checkpoint

    def _interactive_prompt(self, checkpoint: Checkpoint) -> Checkpoint:
        """Prompt the user interactively for a decision."""
        print("\n" + "=" * 70)
        print(f"  CHECKPOINT: {checkpoint.reason.value}")
        print("=" * 70)
        print(f"\n  {checkpoint.title}\n")
        print(f"  {checkpoint.description}\n")

        if checkpoint.task_context:
            # Show session progress summary first
            session_keys = {
                "tasks_succeeded",
                "tasks_failed",
                "tasks_skipped",
                "success_rate",
                "tokens_used",
                "token_budget",
                "token_pct",
            }
            session_ctx = {k: v for k, v in checkpoint.task_context.items() if k in session_keys}
            task_ctx = {k: v for k, v in checkpoint.task_context.items() if k not in session_keys}

            if session_ctx:
                print("  Session Progress:")
                if "tasks_succeeded" in session_ctx:
                    print(
                        f"    Tasks: {session_ctx.get('tasks_succeeded', '0')} succeeded, "
                        f"{session_ctx.get('tasks_failed', '0')} failed, "
                        f"{session_ctx.get('tasks_skipped', '0')} skipped"
                    )
                if "success_rate" in session_ctx:
                    print(f"    Success rate: {session_ctx['success_rate']}")
                if "tokens_used" in session_ctx:
                    token_line = f"    Tokens: {session_ctx['tokens_used']}"
                    if "token_budget" in session_ctx:
                        token_line += f" / {session_ctx['token_budget']} budget"
                    if "token_pct" in session_ctx:
                        token_line += f" ({session_ctx['token_pct']})"
                    print(token_line)
                print()

            if task_ctx:
                print("  Task Context:")
                for key, value in task_ctx.items():
                    print(f"    {key}: {value}")
                print()
        else:
            print()

        print("  Actions:")
        print("    [p] Proceed - continue with this task")
        print("    [s] Skip   - skip this task, move to next")
        print("    [m] Modify - provide guidance before proceeding")
        print("    [a] Abort  - stop the autonomous loop")
        print()

        action_map = {
            "p": CheckpointAction.PROCEED,
            "s": CheckpointAction.SKIP,
            "m": CheckpointAction.MODIFY,
            "a": CheckpointAction.ABORT,
        }

        while True:
            try:
                choice = input("  Your choice [p/s/m/a]: ").strip().lower()
                if choice in action_map:
                    checkpoint.response = action_map[choice]
                    if choice == "m":
                        notes = input("  Guidance: ").strip()
                        checkpoint.human_notes = notes
                    break
                print("  Invalid choice. Please enter p, s, m, or a.")
            except (EOFError, KeyboardInterrupt):
                checkpoint.response = CheckpointAction.ABORT
                break

        return checkpoint

    def should_checkpoint(
        self,
        task_description: str,
        risk_level: str,
        consecutive_failures: int = 0,
        tasks_since_review: int = 0,
        review_interval: int = 10,
        tokens_used: int = 0,
        token_budget: int = 0,
    ) -> CheckpointReason | None:
        """Determine if a checkpoint is needed before proceeding.

        Returns the reason for checkpointing, or None if safe to proceed.
        """
        if risk_level == "high":
            return CheckpointReason.HIGH_RISK_TASK

        if risk_level == "medium" and not self.auto_skip_medium_risk:
            return CheckpointReason.DESIGN_DECISION

        if consecutive_failures >= 3:
            return CheckpointReason.MAX_RETRIES_EXCEEDED

        # Token budget warning (fires once at threshold)
        if (
            token_budget > 0
            and not self._token_warning_fired
            and tokens_used >= token_budget * self.token_budget_warning_pct
        ):
            self._token_warning_fired = True
            return CheckpointReason.TOKEN_BUDGET_WARNING

        if tasks_since_review >= review_interval:
            return CheckpointReason.PERIODIC_REVIEW

        return None
