"""Tests for the notification system."""

from unittest.mock import patch

from src.autodev.notifier import (
    NotifyChannel,
    NotifyLevel,
    Notifier,
    _level_for_stop_reason,
    notify_checkpoint,
    notify_loop_complete,
)


class TestNotifier:
    def test_bell_writes_to_stderr(self):
        notifier = Notifier(channels=[NotifyChannel.BELL])
        with patch("sys.stderr") as mock_stderr:
            results = notifier.notify("title", "body")
        assert results["bell"] is True
        mock_stderr.write.assert_called_once_with("\a")

    def test_multiple_channels(self):
        notifier = Notifier(channels=[NotifyChannel.BELL, NotifyChannel.DESKTOP])
        with (
            patch("sys.stderr"),
            patch.object(notifier, "_send_desktop") as mock_desktop,
        ):
            results = notifier.notify("title", "body")
        assert results["bell"] is True
        assert results["desktop"] is True
        mock_desktop.assert_called_once()

    def test_failed_channel_does_not_stop_others(self):
        notifier = Notifier(channels=[NotifyChannel.DESKTOP, NotifyChannel.BELL])
        with (
            patch.object(notifier, "_send_desktop", side_effect=RuntimeError("no tool")),
            patch("sys.stderr"),
        ):
            results = notifier.notify("title", "body")
        assert results["desktop"] is False
        assert results["bell"] is True

    def test_webhook_skipped_when_no_url(self):
        notifier = Notifier(channels=[NotifyChannel.WEBHOOK], webhook_url="")
        # Should not raise; just logs debug
        results = notifier.notify("title", "body")
        assert results["webhook"] is True  # _send_webhook returns without error

    def test_empty_channels(self):
        notifier = Notifier(channels=[])
        results = notifier.notify("title", "body")
        assert results == {}

    def test_desktop_linux_notify_send(self):
        notifier = Notifier(channels=[NotifyChannel.DESKTOP])
        with (
            patch("sys.platform", "linux"),
            patch("shutil.which", return_value="/usr/bin/notify-send"),
            patch("subprocess.run") as mock_run,
        ):
            results = notifier.notify("Test Title", "Test Body", NotifyLevel.ERROR)
        assert results["desktop"] is True
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "notify-send"
        assert "--urgency" in args
        assert "critical" in args

    def test_desktop_macos_osascript(self):
        notifier = Notifier(channels=[NotifyChannel.DESKTOP])
        with (
            patch("sys.platform", "darwin"),
            patch("shutil.which", return_value="/usr/bin/osascript"),
            patch("subprocess.run") as mock_run,
        ):
            results = notifier.notify("Test Title", "Test Body")
        assert results["desktop"] is True
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "osascript"


class TestLevelForStopReason:
    def test_abort_is_error(self):
        assert _level_for_stop_reason("Aborted by human") == NotifyLevel.ERROR

    def test_failure_is_error(self):
        assert _level_for_stop_reason("Too many consecutive failures") == NotifyLevel.ERROR

    def test_budget_is_warning(self):
        assert _level_for_stop_reason("Token budget exhausted") == NotifyLevel.WARNING

    def test_limit_is_warning(self):
        assert _level_for_stop_reason("Reached max tasks limit (50)") == NotifyLevel.WARNING

    def test_all_processed_is_info(self):
        assert _level_for_stop_reason("All tasks processed") == NotifyLevel.INFO


class TestConvenienceFunctions:
    def test_notify_loop_complete(self):
        notifier = Notifier(channels=[NotifyChannel.BELL])
        with patch("sys.stderr"):
            notify_loop_complete(notifier, "summary text", "All tasks processed")

    def test_notify_checkpoint(self):
        notifier = Notifier(channels=[NotifyChannel.BELL])
        with patch("sys.stderr"):
            notify_checkpoint(notifier, "periodic_review", "Write tests")

    def test_notify_checkpoint_budget_uses_warning(self):
        notifier = Notifier(channels=[])
        with patch.object(notifier, "notify") as mock:
            notify_checkpoint(notifier, "token_budget_warning", "Next task")
        mock.assert_called_once()
        assert mock.call_args[1]["level"] == NotifyLevel.WARNING
