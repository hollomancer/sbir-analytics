"""Session state management for autonomous development runs.

Tracks progress across tasks, manages git operations, and maintains
a persistent session log that can be resumed.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import StrEnum
from pathlib import Path


class TaskOutcome(StrEnum):
    """Outcome of attempting a task."""

    SUCCESS = "success"
    FAILED_VERIFICATION = "failed_verification"
    SKIPPED_BY_HUMAN = "skipped_by_human"
    SKIPPED_HIGH_RISK = "skipped_high_risk"
    ABORTED = "aborted"
    ERROR = "error"


@dataclass
class TaskAttempt:
    """Record of a single task attempt."""

    task_title: str
    source: str
    outcome: TaskOutcome
    duration_seconds: float = 0.0
    verification_summary: str = ""
    commit_sha: str | None = None
    files_changed: list[str] = field(default_factory=list)
    error_message: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class SessionState:
    """Persistent state for an autonomous development session."""

    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    project_root: str = ""
    branch_name: str = ""
    attempts: list[TaskAttempt] = field(default_factory=list)
    total_tasks_attempted: int = 0
    total_tasks_succeeded: int = 0
    total_tasks_failed: int = 0
    total_tasks_skipped: int = 0
    consecutive_failures: int = 0
    tasks_since_review: int = 0

    @property
    def success_rate(self) -> float:
        if self.total_tasks_attempted == 0:
            return 0.0
        return self.total_tasks_succeeded / self.total_tasks_attempted * 100

    def record_attempt(self, attempt: TaskAttempt) -> None:
        """Record a task attempt and update counters."""
        self.attempts.append(attempt)
        self.total_tasks_attempted += 1

        if attempt.outcome == TaskOutcome.SUCCESS:
            self.total_tasks_succeeded += 1
            self.consecutive_failures = 0
            self.tasks_since_review += 1
        elif attempt.outcome in (TaskOutcome.FAILED_VERIFICATION, TaskOutcome.ERROR):
            self.total_tasks_failed += 1
            self.consecutive_failures += 1
            self.tasks_since_review += 1
        else:
            self.total_tasks_skipped += 1

    def reset_review_counter(self) -> None:
        """Reset after a human review checkpoint."""
        self.tasks_since_review = 0
        self.consecutive_failures = 0

    @property
    def summary(self) -> str:
        return (
            f"Session {self.session_id}: "
            f"{self.total_tasks_succeeded}/{self.total_tasks_attempted} succeeded "
            f"({self.success_rate:.0f}%), "
            f"{self.total_tasks_failed} failed, "
            f"{self.total_tasks_skipped} skipped"
        )


class SessionManager:
    """Manages session persistence and git operations."""

    def __init__(self, project_root: Path, log_dir: Path | None = None):
        self.project_root = project_root
        self.log_dir = log_dir or project_root / ".autodev"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def create_session(self, branch_name: str = "") -> SessionState:
        """Create a new session."""
        state = SessionState(
            project_root=str(self.project_root),
            branch_name=branch_name or self._current_branch(),
        )
        self._save(state)
        return state

    def load_session(self, session_id: str) -> SessionState | None:
        """Load a session from disk."""
        path = self.log_dir / f"session-{session_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        state = SessionState(**{
            k: v for k, v in data.items()
            if k != "attempts"
        })
        state.attempts = [TaskAttempt(**a) for a in data.get("attempts", [])]
        return state

    def save_session(self, state: SessionState) -> None:
        """Persist session state."""
        self._save(state)

    def list_sessions(self) -> list[dict[str, str]]:
        """List all saved sessions."""
        sessions = []
        for path in sorted(self.log_dir.glob("session-*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                sessions.append({
                    "session_id": data["session_id"],
                    "started_at": data["started_at"],
                    "branch": data.get("branch_name", ""),
                    "tasks_attempted": str(data.get("total_tasks_attempted", 0)),
                    "tasks_succeeded": str(data.get("total_tasks_succeeded", 0)),
                })
            except (json.JSONDecodeError, KeyError):
                continue
        return sessions

    def _save(self, state: SessionState) -> None:
        path = self.log_dir / f"session-{state.session_id}.json"
        data = {
            "session_id": state.session_id,
            "started_at": state.started_at,
            "project_root": state.project_root,
            "branch_name": state.branch_name,
            "total_tasks_attempted": state.total_tasks_attempted,
            "total_tasks_succeeded": state.total_tasks_succeeded,
            "total_tasks_failed": state.total_tasks_failed,
            "total_tasks_skipped": state.total_tasks_skipped,
            "consecutive_failures": state.consecutive_failures,
            "tasks_since_review": state.tasks_since_review,
            "attempts": [
                {
                    "task_title": a.task_title,
                    "source": a.source,
                    "outcome": a.outcome.value,
                    "duration_seconds": a.duration_seconds,
                    "verification_summary": a.verification_summary,
                    "commit_sha": a.commit_sha,
                    "files_changed": a.files_changed,
                    "error_message": a.error_message,
                    "timestamp": a.timestamp,
                }
                for a in state.attempts
            ],
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _current_branch(self) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return "unknown"

    def git_stash_changes(self) -> bool:
        """Stash current changes (for discarding failed attempts)."""
        try:
            result = subprocess.run(
                ["git", "stash", "push", "-m", "autodev: discarding failed attempt"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def git_stash_pop(self) -> bool:
        """Restore stashed changes."""
        try:
            result = subprocess.run(
                ["git", "stash", "pop"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def git_changed_files(self) -> list[str]:
        """Get list of changed files in working directory."""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return [f for f in result.stdout.strip().splitlines() if f]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

    def git_commit(self, message: str) -> str | None:
        """Stage all changes and commit, returning the SHA."""
        try:
            subprocess.run(
                ["git", "add", "-A"],
                cwd=self.project_root,
                capture_output=True,
                timeout=30,
            )
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                sha_result = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=self.project_root,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                return sha_result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    def git_reset_hard(self) -> bool:
        """Reset working directory to HEAD (discard all changes)."""
        try:
            result = subprocess.run(
                ["git", "checkout", "--", "."],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            # Also clean untracked files created by the attempt
            subprocess.run(
                ["git", "clean", "-fd", "--exclude=.autodev/"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
