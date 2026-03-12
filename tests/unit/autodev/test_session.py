"""Tests for session management."""

from src.autodev.session import SessionManager, SessionState, TaskAttempt, TaskOutcome


class TestSessionState:
    def test_initial_state(self):
        state = SessionState()
        assert state.total_tasks_attempted == 0
        assert state.success_rate == 0.0

    def test_record_success(self):
        state = SessionState()
        state.record_attempt(
            TaskAttempt(
                task_title="test",
                source="test",
                outcome=TaskOutcome.SUCCESS,
            )
        )
        assert state.total_tasks_succeeded == 1
        assert state.consecutive_failures == 0
        assert state.success_rate == 100.0

    def test_record_failure(self):
        state = SessionState()
        state.record_attempt(
            TaskAttempt(
                task_title="test",
                source="test",
                outcome=TaskOutcome.FAILED_VERIFICATION,
            )
        )
        assert state.total_tasks_failed == 1
        assert state.consecutive_failures == 1

    def test_consecutive_failures_reset_on_success(self):
        state = SessionState()
        state.record_attempt(TaskAttempt("t1", "s", TaskOutcome.FAILED_VERIFICATION))
        state.record_attempt(TaskAttempt("t2", "s", TaskOutcome.FAILED_VERIFICATION))
        assert state.consecutive_failures == 2
        state.record_attempt(TaskAttempt("t3", "s", TaskOutcome.SUCCESS))
        assert state.consecutive_failures == 0

    def test_summary(self):
        state = SessionState()
        state.record_attempt(TaskAttempt("t1", "s", TaskOutcome.SUCCESS))
        assert "1/1 succeeded" in state.summary

    def test_token_tracking(self):
        state = SessionState()
        state.record_attempt(
            TaskAttempt(
                "t1",
                "s",
                TaskOutcome.SUCCESS,
                input_tokens=1000,
                output_tokens=500,
            )
        )
        state.record_attempt(
            TaskAttempt(
                "t2",
                "s",
                TaskOutcome.SUCCESS,
                input_tokens=2000,
                output_tokens=800,
            )
        )
        assert state.total_input_tokens == 3000
        assert state.total_output_tokens == 1300
        assert state.total_tokens == 4300

    def test_token_tracking_initial_zero(self):
        state = SessionState()
        assert state.total_tokens == 0
        assert state.total_input_tokens == 0
        assert state.total_output_tokens == 0

    def test_summary_includes_tokens_when_nonzero(self):
        state = SessionState()
        state.record_attempt(
            TaskAttempt(
                "t1",
                "s",
                TaskOutcome.SUCCESS,
                input_tokens=1000,
                output_tokens=500,
            )
        )
        assert "Tokens:" in state.summary
        assert "1,500" in state.summary

    def test_summary_omits_tokens_when_zero(self):
        state = SessionState()
        state.record_attempt(TaskAttempt("t1", "s", TaskOutcome.SUCCESS))
        assert "Tokens:" not in state.summary


class TestSessionManager:
    def test_create_and_load_session(self, tmp_path):
        mgr = SessionManager(tmp_path, log_dir=tmp_path / ".autodev")
        session = mgr.create_session(branch_name="test-branch")

        loaded = mgr.load_session(session.session_id)
        assert loaded is not None
        assert loaded.session_id == session.session_id
        assert loaded.branch_name == "test-branch"

    def test_save_with_attempts(self, tmp_path):
        mgr = SessionManager(tmp_path, log_dir=tmp_path / ".autodev")
        session = mgr.create_session()
        session.record_attempt(TaskAttempt("task1", "spec", TaskOutcome.SUCCESS))
        mgr.save_session(session)

        loaded = mgr.load_session(session.session_id)
        assert loaded.total_tasks_succeeded == 1

    def test_list_sessions(self, tmp_path):
        mgr = SessionManager(tmp_path, log_dir=tmp_path / ".autodev")
        mgr.create_session(branch_name="branch-1")
        mgr.create_session(branch_name="branch-2")

        sessions = mgr.list_sessions()
        assert len(sessions) == 2

    def test_load_nonexistent_session(self, tmp_path):
        mgr = SessionManager(tmp_path, log_dir=tmp_path / ".autodev")
        loaded = mgr.load_session("nonexistent")
        assert loaded is None

    def test_loaded_attempts_have_enum_outcome(self, tmp_path):
        """Verify TaskOutcome is properly deserialized as enum, not string."""
        mgr = SessionManager(tmp_path, log_dir=tmp_path / ".autodev")
        session = mgr.create_session()
        session.record_attempt(TaskAttempt("task1", "spec", TaskOutcome.SUCCESS))
        session.record_attempt(TaskAttempt("task2", "spec", TaskOutcome.FAILED_VERIFICATION))
        mgr.save_session(session)

        loaded = mgr.load_session(session.session_id)
        assert loaded.attempts[0].outcome == TaskOutcome.SUCCESS
        assert loaded.attempts[1].outcome == TaskOutcome.FAILED_VERIFICATION
        assert isinstance(loaded.attempts[0].outcome, TaskOutcome)

    def test_token_usage_persisted(self, tmp_path):
        """Verify token counts survive save/load roundtrip."""
        mgr = SessionManager(tmp_path, log_dir=tmp_path / ".autodev")
        session = mgr.create_session()
        session.record_attempt(
            TaskAttempt(
                "task1",
                "spec",
                TaskOutcome.SUCCESS,
                input_tokens=5000,
                output_tokens=2000,
            )
        )
        mgr.save_session(session)

        loaded = mgr.load_session(session.session_id)
        assert loaded.total_input_tokens == 5000
        assert loaded.total_output_tokens == 2000
        assert loaded.total_tokens == 7000
        assert loaded.attempts[0].input_tokens == 5000
        assert loaded.attempts[0].output_tokens == 2000

    def test_list_sessions_includes_tokens(self, tmp_path):
        mgr = SessionManager(tmp_path, log_dir=tmp_path / ".autodev")
        session = mgr.create_session()
        session.record_attempt(
            TaskAttempt(
                "task1",
                "spec",
                TaskOutcome.SUCCESS,
                input_tokens=1000,
                output_tokens=500,
            )
        )
        mgr.save_session(session)

        sessions = mgr.list_sessions()
        assert sessions[0]["total_tokens"] == "1500"
