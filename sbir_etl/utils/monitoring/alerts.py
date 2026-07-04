"""Pipeline-level alert system for performance and quality thresholds.

This module provides alert generation and notification utilities for
performance and quality metrics. Alerts are triggered when thresholds
are exceeded and can be surfaced via Dagster events, logs, or external
notification systems.

Features:
- Configurable alert thresholds from config
- Multiple alert severity levels (INFO, WARNING, FAILURE)
- Performance alerts (duration, memory, throughput)
- Quality alerts (match rate regressions)
- Dagster event integration for visibility
- JSON/Markdown alert formatting
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from loguru import logger

_VALID_DIMENSIONS = ("accuracy", "completeness", "consistency", "validity")


class AlertSeverity(str, Enum):
    """Alert severity levels."""

    INFO = "INFO"
    WARNING = "WARNING"
    FAILURE = "FAILURE"


@dataclass
class Alert:
    """Individual performance or quality alert."""

    timestamp: datetime
    severity: AlertSeverity
    alert_type: str  # "performance_duration", "performance_memory", "quality_match_rate", etc.
    message: str
    threshold_value: float
    actual_value: float
    metric_name: str
    delta_percent: float | None = None
    run_id: str | None = None
    asset_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert alert to dict for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity.value,
            "alert_type": self.alert_type,
            "message": self.message,
            "metric_name": self.metric_name,
            "threshold_value": self.threshold_value,
            "actual_value": self.actual_value,
            "delta_percent": self.delta_percent,
            "run_id": self.run_id,
            "asset_name": self.asset_name,
            "metadata": self.metadata,
        }

    def to_markdown(self) -> str:
        """Format alert as Markdown."""
        return f"""
### {self.severity.value}: {self.alert_type.replace("_", " ").title()}

**Message:** {self.message}

**Metric:** {self.metric_name}
- **Threshold:** {self.threshold_value}
- **Actual:** {self.actual_value}
{"- **Delta:** " + f"{self.delta_percent:+.1f}%" if self.delta_percent else ""}

*Timestamp: {self.timestamp.isoformat()}*
"""

    def to_log_dict(self) -> dict[str, Any]:
        """Format alert for structured logging."""
        return {
            "alert_severity": self.severity.value,
            "alert_type": self.alert_type,
            "alert_message": self.message,
            "metric_name": self.metric_name,
            "threshold_value": self.threshold_value,
            "actual_value": self.actual_value,
            "delta_percent": self.delta_percent,
            "asset_name": self.asset_name,
        }


@dataclass(frozen=True)
class Caveat:
    """Subthreshold reliability observation. Disclosure, not failure.

    Emitted where a signal is worse than a caveat threshold but does not
    fail an existing gate. Caveats surface known limitations on the manifest
    without changing run outcome.
    """

    timestamp: datetime
    dimension: Literal["accuracy", "completeness", "consistency", "validity"]
    metric_name: str
    observed_value: Any
    expected_value: Any
    description: str
    impact: str
    asset_name: str | None = None
    run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert caveat to dict for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "dimension": self.dimension,
            "metric_name": self.metric_name,
            "observed_value": self.observed_value,
            "expected_value": self.expected_value,
            "description": self.description,
            "impact": self.impact,
            "asset_name": self.asset_name,
            "run_id": self.run_id,
        }


@dataclass(frozen=True)
class ProvenanceEntry:
    """Per-input-source record. One entry per source the asset consumed."""

    source_id: str
    location: str
    retrieved_at: datetime
    sha256: str | None
    row_count: int
    extractor_module: str
    hash_omitted_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert provenance entry to dict for JSON serialization."""
        return {
            "source_id": self.source_id,
            "location": self.location,
            "retrieved_at": self.retrieved_at.isoformat(),
            "sha256": self.sha256,
            "row_count": self.row_count,
            "extractor_module": self.extractor_module,
            "hash_omitted_reason": self.hash_omitted_reason,
        }


class AlertThresholds:
    """Configurable alert thresholds."""

    # Performance thresholds
    DURATION_PER_RECORD_WARNING_SECONDS = 5.0  # > 5s per record = WARNING
    MEMORY_DELTA_WARNING_MB = 500.0  # > 500MB memory delta = WARNING
    MATCH_RATE_FAILURE_THRESHOLD = 0.70  # < 70% match rate = FAILURE

    # Memory pressure thresholds (for graceful degradation)
    MEMORY_PRESSURE_WARN_PERCENT = 80.0  # 80% of available memory
    MEMORY_PRESSURE_CRITICAL_PERCENT = 95.0  # 95% of available memory

    @classmethod
    def from_config(cls, config: Any) -> AlertThresholds:
        """Create AlertThresholds from configuration.

        Args:
            config: Configuration object with enrichment.performance settings

        Returns:
            AlertThresholds instance with config-driven values
        """
        thresholds = cls()

        # Performance thresholds
        if hasattr(config, "enrichment") and hasattr(config.enrichment, "performance"):
            perf_config = config.enrichment.performance

            if hasattr(perf_config, "duration_warning_seconds"):
                thresholds.DURATION_PER_RECORD_WARNING_SECONDS = (
                    perf_config.duration_warning_seconds
                )
            if hasattr(perf_config, "memory_delta_warning_mb"):
                thresholds.MEMORY_DELTA_WARNING_MB = perf_config.memory_delta_warning_mb
            if hasattr(perf_config, "match_rate_threshold"):
                thresholds.MATCH_RATE_FAILURE_THRESHOLD = perf_config.match_rate_threshold

        return thresholds


class AlertCollector:
    """Collects and manages performance and quality alerts."""

    def __init__(
        self,
        asset_name: str | None = None,
        run_id: str | None = None,
        config: Any | None = None,
    ):
        """Initialize alert collector.

        Args:
            asset_name: Name of the asset being monitored
            run_id: Dagster run ID
            config: Configuration object for threshold customization
        """
        self.asset_name = asset_name
        self.run_id = run_id
        self.alerts: list[Alert] = []
        self.caveats: list[Caveat] = []
        self.provenance: list[ProvenanceEntry] = []
        self.thresholds = AlertThresholds.from_config(config) if config else AlertThresholds()

    def check_duration_per_record(
        self,
        total_duration_seconds: float,
        total_records: int,
        metric_name: str = "enrichment_duration",
    ) -> Alert | None:
        """Check if duration per record exceeds warning threshold.

        Args:
            total_duration_seconds: Total processing duration
            total_records: Total records processed
            metric_name: Name of the metric

        Returns:
            Alert if threshold exceeded, None otherwise
        """
        if total_records == 0:
            return None

        duration_per_record = total_duration_seconds / total_records
        threshold = self.thresholds.DURATION_PER_RECORD_WARNING_SECONDS

        if duration_per_record > threshold:
            alert = Alert(
                timestamp=datetime.now(),
                severity=AlertSeverity.WARNING,
                alert_type="performance_duration",
                message=f"Processing duration per record ({duration_per_record:.3f}s) "
                f"exceeds warning threshold ({threshold:.3f}s)",
                metric_name=metric_name,
                threshold_value=threshold,
                actual_value=duration_per_record,
                delta_percent=(duration_per_record - threshold) / threshold * 100,
                run_id=self.run_id,
                asset_name=self.asset_name,
                metadata={
                    "total_duration_seconds": total_duration_seconds,
                    "total_records": total_records,
                },
            )
            self.alerts.append(alert)
            return alert

        return None

    def check_memory_delta(
        self,
        avg_memory_delta_mb: float,
        metric_name: str = "enrichment_memory",
    ) -> Alert | None:
        """Check if memory delta exceeds warning threshold.

        Args:
            avg_memory_delta_mb: Average memory delta in MB
            metric_name: Name of the metric

        Returns:
            Alert if threshold exceeded, None otherwise
        """
        threshold = self.thresholds.MEMORY_DELTA_WARNING_MB

        if avg_memory_delta_mb > threshold:
            alert = Alert(
                timestamp=datetime.now(),
                severity=AlertSeverity.WARNING,
                alert_type="performance_memory",
                message=f"Memory delta ({avg_memory_delta_mb:.1f}MB) "
                f"exceeds warning threshold ({threshold:.1f}MB)",
                metric_name=metric_name,
                threshold_value=threshold,
                actual_value=avg_memory_delta_mb,
                delta_percent=(avg_memory_delta_mb - threshold) / threshold * 100,
                run_id=self.run_id,
                asset_name=self.asset_name,
            )
            self.alerts.append(alert)
            return alert

        return None

    def check_match_rate(
        self,
        match_rate: float,
        metric_name: str = "enrichment_match_rate",
    ) -> Alert | None:
        """Check if match rate falls below failure threshold.

        Args:
            match_rate: Match rate as decimal (0-1)
            metric_name: Name of the metric

        Returns:
            Alert if threshold exceeded, None otherwise
        """
        threshold = self.thresholds.MATCH_RATE_FAILURE_THRESHOLD

        if match_rate < threshold:
            alert = Alert(
                timestamp=datetime.now(),
                severity=AlertSeverity.FAILURE,
                alert_type="quality_match_rate",
                message=f"Match rate ({match_rate:.1%}) falls below failure "
                f"threshold ({threshold:.1%})",
                metric_name=metric_name,
                threshold_value=threshold,
                actual_value=match_rate,
                delta_percent=(match_rate - threshold) / threshold * 100,
                run_id=self.run_id,
                asset_name=self.asset_name,
            )
            self.alerts.append(alert)
            return alert

        return None

    def check_memory_pressure(
        self,
        memory_percent_available: float,
        action_type: str = "check",  # "check", "warn", or "critical"
    ) -> Alert | None:
        """Check memory pressure level.

        Args:
            memory_percent_available: Percentage of available memory (0-100)
            action_type: "check" = info check, "warn" = pressure warning, "critical" = critical

        Returns:
            Alert if memory pressure high, None otherwise
        """
        if (
            action_type == "critical"
            and memory_percent_available < self.thresholds.MEMORY_PRESSURE_CRITICAL_PERCENT
        ):
            alert = Alert(
                timestamp=datetime.now(),
                severity=AlertSeverity.FAILURE,
                alert_type="memory_pressure_critical",
                message=f"Memory pressure critical: {memory_percent_available:.1f}% available "
                f"(threshold: {self.thresholds.MEMORY_PRESSURE_CRITICAL_PERCENT:.1f}%)",
                metric_name="memory_pressure",
                threshold_value=self.thresholds.MEMORY_PRESSURE_CRITICAL_PERCENT,
                actual_value=memory_percent_available,
                delta_percent=(
                    memory_percent_available - self.thresholds.MEMORY_PRESSURE_CRITICAL_PERCENT
                ),
                run_id=self.run_id,
                asset_name=self.asset_name,
            )
            self.alerts.append(alert)
            return alert

        if (
            action_type in ("warn", "check")
            and memory_percent_available < self.thresholds.MEMORY_PRESSURE_WARN_PERCENT
        ):
            alert = Alert(
                timestamp=datetime.now(),
                severity=AlertSeverity.WARNING,
                alert_type="memory_pressure_warning",
                message=f"Memory pressure warning: {memory_percent_available:.1f}% available "
                f"(threshold: {self.thresholds.MEMORY_PRESSURE_WARN_PERCENT:.1f}%)",
                metric_name="memory_pressure",
                threshold_value=self.thresholds.MEMORY_PRESSURE_WARN_PERCENT,
                actual_value=memory_percent_available,
                delta_percent=(
                    memory_percent_available - self.thresholds.MEMORY_PRESSURE_WARN_PERCENT
                ),
                run_id=self.run_id,
                asset_name=self.asset_name,
            )
            self.alerts.append(alert)
            return alert

        return None

    def get_alerts(self, severity: AlertSeverity | None = None) -> list[Alert]:
        """Get all alerts or filter by severity.

        Args:
            severity: Filter by AlertSeverity, or None for all

        Returns:
            List of alerts
        """
        if severity is None:
            return self.alerts

        return [a for a in self.alerts if a.severity == severity]

    def has_failures(self) -> bool:
        """Check if any FAILURE severity alerts exist."""
        return any(a.severity == AlertSeverity.FAILURE for a in self.alerts)

    def has_warnings(self) -> bool:
        """Check if any WARNING severity alerts exist."""
        return any(a.severity == AlertSeverity.WARNING for a in self.alerts)

    def to_dict(self) -> dict[str, Any]:
        """Convert all alerts to dict."""
        return {
            "alert_count": len(self.alerts),
            "failure_count": len(self.get_alerts(AlertSeverity.FAILURE)),
            "warning_count": len(self.get_alerts(AlertSeverity.WARNING)),
            "info_count": len(self.get_alerts(AlertSeverity.INFO)),
            "alerts": [a.to_dict() for a in self.alerts],
        }

    def to_markdown(self) -> str:
        """Format all alerts as Markdown report."""
        if not self.alerts:
            return "## Alerts\n\nNo alerts triggered.\n"

        failures = self.get_alerts(AlertSeverity.FAILURE)
        warnings = self.get_alerts(AlertSeverity.WARNING)
        infos = self.get_alerts(AlertSeverity.INFO)

        md = f"""## Alerts

**Summary:** {len(failures)} failures, {len(warnings)} warnings, {len(infos)} info

"""

        if failures:
            md += "### Failures\n"
            for alert in failures:
                md += alert.to_markdown()

        if warnings:
            md += "### Warnings\n"
            for alert in warnings:
                md += alert.to_markdown()

        if infos:
            md += "### Info\n"
            for alert in infos:
                md += alert.to_markdown()

        return md

    def log_alerts(self) -> None:
        """Log all alerts with structured context."""
        for alert in self.alerts:
            log_dict = alert.to_log_dict()
            if alert.severity == AlertSeverity.FAILURE:
                logger.error(alert.message, extra=log_dict)
            elif alert.severity == AlertSeverity.WARNING:
                logger.warning(alert.message, extra=log_dict)
            else:
                logger.info(alert.message, extra=log_dict)

    def save_to_file(self, output_path: Path) -> Path:
        """Save alerts to JSON file.

        Args:
            output_path: Path to save alerts to

        Returns:
            Path to saved file
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)

        logger.info(f"Alerts saved to {output_path}")
        return output_path

    def emit_caveat(
        self,
        dimension: Literal["accuracy", "completeness", "consistency", "validity"],
        metric_name: str,
        observed_value: Any,
        expected_value: Any,
        description: str,
        impact: str,
    ) -> Caveat:
        """Emit a subthreshold reliability disclosure.

        Does NOT append to self.alerts and does NOT change run outcome.
        Caveats are persisted only via save_manifest().

        Args:
            dimension: One of "accuracy", "completeness", "consistency", "validity".
            metric_name: Stable key used for cross-run diffing.
            observed_value: The measured value (float, int, or string).
            expected_value: Threshold, target, or expected shape.
            description: One-sentence human-readable statement.
            impact: One-sentence downstream-effect statement (required).

        Returns:
            The appended Caveat.

        Raises:
            ValueError: If dimension is not one of the four permitted values.
        """
        if dimension not in _VALID_DIMENSIONS:
            raise ValueError(
                f"Invalid dimension: {dimension!r}. Must be one of {_VALID_DIMENSIONS}"
            )

        caveat = Caveat(
            timestamp=datetime.now(UTC),
            dimension=dimension,
            metric_name=metric_name,
            observed_value=observed_value,
            expected_value=expected_value,
            description=description,
            impact=impact,
            asset_name=self.asset_name,
            run_id=self.run_id,
        )
        self.caveats.append(caveat)
        return caveat

    def record_provenance(
        self,
        source_id: str,
        location: str,
        row_count: int,
        extractor_module: str,
        sha256: str | None = None,
        hash_omitted_reason: str | None = None,
        retrieved_at: datetime | None = None,
    ) -> ProvenanceEntry:
        """Record one input source consumed by the asset.

        Args:
            source_id: Stable string identifier, e.g., "sbir_gov_bulk_download".
            location: URL or absolute path of the source.
            row_count: Number of rows the source contributed.
            extractor_module: Dotted Python path of the extractor.
            sha256: SHA-256 of source bytes; None permitted only with hash_omitted_reason.
            hash_omitted_reason: Required when sha256 is None.
            retrieved_at: When the source was retrieved (UTC). Defaults to now.

        Returns:
            The appended ProvenanceEntry.

        Raises:
            ValueError: If sha256 is None but no hash_omitted_reason is provided.
        """
        if sha256 is None and not hash_omitted_reason:
            raise ValueError("sha256=None requires hash_omitted_reason")

        entry = ProvenanceEntry(
            source_id=source_id,
            location=location,
            retrieved_at=retrieved_at or datetime.now(UTC),
            sha256=sha256,
            row_count=row_count,
            extractor_module=extractor_module,
            hash_omitted_reason=hash_omitted_reason,
        )
        self.provenance.append(entry)
        return entry

    def save_manifest(self, manifest_path: Path) -> dict[str, Any]:
        """Persist reliability manifest JSON.

        Computes resolved_caveats by diffing metric_names against the most-recent
        prior manifest in the same directory (mtime scan, excluding manifest_path
        itself so re-writes are idempotent).

        Args:
            manifest_path: Full path to write the manifest JSON to.

        Returns:
            The manifest dict that was written (so callers can pull counts without
            re-reading from disk).
        """
        manifest_path.parent.mkdir(parents=True, exist_ok=True)

        prior_caveats = self._read_prior_caveats(manifest_path.parent, manifest_path)
        current_metric_names = {c.metric_name for c in self.caveats}
        resolved = [
            c for c in prior_caveats if c.get("metric_name") not in current_metric_names
        ]

        manifest = {
            "asset_name": self.asset_name,
            "run_id": self.run_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "framework_reference": "GAO-20-283G",
            "caveats": [c.to_dict() for c in self.caveats],
            "resolved_caveats": resolved,
            "provenance": [p.to_dict() for p in self.provenance],
        }

        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2, default=str)

        logger.info(f"Reliability manifest saved to {manifest_path}")
        return manifest

    def _read_prior_caveats(
        self, directory: Path, exclude: Path
    ) -> list[dict[str, Any]]:
        """Return caveats from the most-recent manifest in `directory`.

        Excludes the file at `exclude` (typically the manifest currently being
        written). Returns an empty list if no prior manifest exists.
        """
        if not directory.exists():
            return []
        candidates = sorted(
            (p for p in directory.glob("*.json") if p != exclude),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            return []
        try:
            with open(candidates[0]) as f:
                prior = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Could not read prior manifest {candidates[0]}: {e}")
            return []
        return prior.get("caveats", [])
