"""Notification support for the autonomous development loop.

Sends notifications when the loop completes, hits a checkpoint, or encounters
errors. Supports three notification channels:

- **bell**: Terminal bell character (always available)
- **desktop**: OS-native desktop notifications (Linux notify-send, macOS osascript)
- **webhook**: HTTP POST to ntfy.sh or any compatible endpoint (mobile push)
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class NotifyChannel(StrEnum):
    """Available notification channels."""

    BELL = "bell"
    DESKTOP = "desktop"
    WEBHOOK = "webhook"


class NotifyLevel(StrEnum):
    """Notification urgency level."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class Notifier:
    """Sends notifications through configured channels.

    Channels are best-effort — failures are logged but never raise.
    """

    channels: list[NotifyChannel] = field(default_factory=lambda: [NotifyChannel.BELL])
    webhook_url: str = ""
    app_name: str = "sbir-autodev"

    def notify(
        self,
        title: str,
        body: str,
        level: NotifyLevel = NotifyLevel.INFO,
    ) -> dict[str, bool]:
        """Send a notification through all configured channels.

        Returns a dict of channel -> success for observability.
        """
        results: dict[str, bool] = {}
        for channel in self.channels:
            try:
                if channel == NotifyChannel.BELL:
                    self._send_bell()
                elif channel == NotifyChannel.DESKTOP:
                    self._send_desktop(title, body, level)
                elif channel == NotifyChannel.WEBHOOK:
                    self._send_webhook(title, body, level)
                results[channel.value] = True
            except Exception:
                logger.debug("Notification failed on channel %s", channel, exc_info=True)
                results[channel.value] = False
        return results

    def _send_bell(self) -> None:
        """Emit terminal bell character."""
        sys.stderr.write("\a")
        sys.stderr.flush()

    def _send_desktop(self, title: str, body: str, level: NotifyLevel) -> None:
        """Send OS-native desktop notification."""
        if sys.platform == "linux" and shutil.which("notify-send"):
            urgency_map = {
                NotifyLevel.INFO: "normal",
                NotifyLevel.WARNING: "normal",
                NotifyLevel.ERROR: "critical",
            }
            subprocess.run(
                [
                    "notify-send",
                    "--urgency",
                    urgency_map.get(level, "normal"),
                    "--app-name",
                    self.app_name,
                    title,
                    body,
                ],
                check=False,
                capture_output=True,
                timeout=5,
            )
        elif sys.platform == "darwin" and shutil.which("osascript"):
            # AppleScript display notification
            script = f'display notification "{body}" with title "{title}" sound name "Glass"'
            subprocess.run(
                ["osascript", "-e", script],
                check=False,
                capture_output=True,
                timeout=5,
            )
        else:
            logger.debug("No desktop notification tool available on %s", sys.platform)

    def _send_webhook(self, title: str, body: str, level: NotifyLevel) -> None:
        """POST to a webhook endpoint (ntfy.sh compatible)."""
        if not self.webhook_url:
            logger.debug("Webhook URL not configured, skipping")
            return

        priority_map = {
            NotifyLevel.INFO: "default",
            NotifyLevel.WARNING: "high",
            NotifyLevel.ERROR: "urgent",
        }

        req = Request(
            self.webhook_url,
            data=body.encode("utf-8"),
            headers={
                "Title": title,
                "Priority": priority_map.get(level, "default"),
                "Tags": self.app_name,
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=10) as resp:  # noqa: S310
                resp.read()
        except (URLError, TimeoutError):
            raise


def _level_for_stop_reason(reason: str) -> NotifyLevel:
    """Map a stop reason string to notification urgency."""
    if "abort" in reason.lower() or "failure" in reason.lower():
        return NotifyLevel.ERROR
    if "budget" in reason.lower() or "limit" in reason.lower():
        return NotifyLevel.WARNING
    return NotifyLevel.INFO


def notify_loop_complete(notifier: Notifier, summary: str, stop_reason: str) -> None:
    """Convenience: send a loop-complete notification."""
    level = _level_for_stop_reason(stop_reason)
    notifier.notify(
        title="Autodev Run Complete",
        body=summary,
        level=level,
    )


def notify_checkpoint(notifier: Notifier, reason: str, title: str) -> None:
    """Convenience: notify that a checkpoint needs attention."""
    level = NotifyLevel.WARNING if "budget" in reason else NotifyLevel.INFO
    notifier.notify(
        title=f"Checkpoint: {reason}",
        body=title,
        level=level,
    )
