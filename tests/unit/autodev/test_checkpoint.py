"""Tests for the checkpoint system."""

from src.autodev.checkpoint import (
    Checkpoint,
    CheckpointAction,
    CheckpointHandler,
    CheckpointLog,
    CheckpointReason,
)


class TestCheckpointHandler:
    def test_should_checkpoint_high_risk(self):
        handler = CheckpointHandler("test", interactive=False)
        reason = handler.should_checkpoint("deploy to prod", "high")
        assert reason == CheckpointReason.HIGH_RISK_TASK

    def test_should_checkpoint_consecutive_failures(self):
        handler = CheckpointHandler("test", interactive=False)
        reason = handler.should_checkpoint("write tests", "low", consecutive_failures=3)
        assert reason == CheckpointReason.MAX_RETRIES_EXCEEDED

    def test_should_checkpoint_periodic_review(self):
        handler = CheckpointHandler("test", interactive=False)
        reason = handler.should_checkpoint(
            "write tests", "low", tasks_since_review=10, review_interval=10
        )
        assert reason == CheckpointReason.PERIODIC_REVIEW

    def test_should_checkpoint_medium_risk_by_default(self):
        handler = CheckpointHandler("test", interactive=False)
        reason = handler.should_checkpoint("create new dagster asset", "medium")
        assert reason == CheckpointReason.DESIGN_DECISION

    def test_auto_skip_medium_risk(self):
        handler = CheckpointHandler("test", interactive=False, auto_skip_medium_risk=True)
        reason = handler.should_checkpoint("create new dagster asset", "medium")
        assert reason is None

    def test_no_checkpoint_needed(self):
        handler = CheckpointHandler("test", interactive=False)
        reason = handler.should_checkpoint("write tests", "low")
        assert reason is None

    def test_non_interactive_auto_skips(self):
        handler = CheckpointHandler("test", interactive=False)
        checkpoint = handler.request_review(
            CheckpointReason.HIGH_RISK_TASK,
            "Risky task",
            "Details",
        )
        assert checkpoint.response == CheckpointAction.SKIP

    def test_token_budget_warning_at_threshold(self):
        handler = CheckpointHandler("test", interactive=False, token_budget_warning_pct=0.75)
        reason = handler.should_checkpoint(
            "write tests",
            "low",
            tokens_used=7500,
            token_budget=10000,
        )
        assert reason == CheckpointReason.TOKEN_BUDGET_WARNING

    def test_token_budget_warning_fires_once(self):
        handler = CheckpointHandler("test", interactive=False, token_budget_warning_pct=0.75)
        reason1 = handler.should_checkpoint(
            "task1",
            "low",
            tokens_used=8000,
            token_budget=10000,
        )
        assert reason1 == CheckpointReason.TOKEN_BUDGET_WARNING
        # Second call should not fire again
        reason2 = handler.should_checkpoint(
            "task2",
            "low",
            tokens_used=9000,
            token_budget=10000,
        )
        assert reason2 is None

    def test_token_budget_warning_not_fired_below_threshold(self):
        handler = CheckpointHandler("test", interactive=False, token_budget_warning_pct=0.75)
        reason = handler.should_checkpoint(
            "write tests",
            "low",
            tokens_used=5000,
            token_budget=10000,
        )
        assert reason is None

    def test_token_budget_warning_no_budget_set(self):
        handler = CheckpointHandler("test", interactive=False)
        reason = handler.should_checkpoint(
            "write tests",
            "low",
            tokens_used=100000,
            token_budget=0,
        )
        assert reason is None

    def test_checkpoint_log_persistence(self, tmp_path):
        log = CheckpointLog(
            session_id="test-123",
            log_path=tmp_path / "checkpoints.json",
        )
        checkpoint = Checkpoint(
            reason=CheckpointReason.HIGH_RISK_TASK,
            title="Test",
            description="Test checkpoint",
        )
        checkpoint.response = CheckpointAction.SKIP
        log.add(checkpoint)

        assert log.log_path.exists()
        import json

        data = json.loads(log.log_path.read_text())
        assert data["session_id"] == "test-123"
        assert len(data["checkpoints"]) == 1
