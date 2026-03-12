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
