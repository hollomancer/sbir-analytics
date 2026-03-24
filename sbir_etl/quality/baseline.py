"""Quality baseline management for enrichment regression detection.

This module provides utilities to store, load, and compare enrichment quality
baselines across runs. Baselines are used to detect quality regressions and
can be configured to fail assets when match rates drop significantly.

Features:
- Baseline storage with versioning and metadata
- Per-run baseline creation and comparison
- Regression detection with configurable thresholds
- Historical baseline tracking
- Markdown/JSON reporting for baseline changes
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass
class QualityBaseline:
    """Represents a quality baseline for enrichment."""

    timestamp: datetime
    match_rate: float
    matched_records: int
    total_records: int
    exact_matches: int
    fuzzy_matches: int
    run_id: str | None = None
    processing_mode: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert baseline to dict for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "match_rate": self.match_rate,
            "matched_records": self.matched_records,
            "total_records": self.total_records,
            "exact_matches": self.exact_matches,
            "fuzzy_matches": self.fuzzy_matches,
            "run_id": self.run_id,
            "processing_mode": self.processing_mode,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QualityBaseline":
        """Create QualityBaseline from dict."""
        data = data.copy()
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class BaselineComparison:
    """Result of comparing current quality to baseline."""

    baseline: QualityBaseline
    current: QualityBaseline
    match_rate_delta_percent: float
    matched_records_delta: int
    regression_severity: str = "PASS"  # PASS, WARNING, FAILURE
    regression_messages: list[str] = field(default_factory=list)
    exceeded_threshold: bool = False
    threshold_percent: float = 5.0

    @property
    def has_regression(self) -> bool:
        """Check if regression detected (match rate declined)."""
        return self.match_rate_delta_percent < 0

    @property
    def regression_percent_change(self) -> float:
        """Calculate percentage change in match rate."""
        if self.baseline.match_rate == 0:
            return 0.0
        return (self.current.match_rate - self.baseline.match_rate) / self.baseline.match_rate * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert comparison to dict."""
        return {
            "baseline": self.baseline.to_dict(),
            "current": self.current.to_dict(),
            "match_rate_delta_percent": self.match_rate_delta_percent,
            "matched_records_delta": self.matched_records_delta,
            "regression_severity": self.regression_severity,
            "regression_messages": self.regression_messages,
            "exceeded_threshold": self.exceeded_threshold,
            "threshold_percent": self.threshold_percent,
            "has_regression": self.has_regression,
            "regression_percent_change": self.regression_percent_change,
        }

    def to_markdown(self) -> str:
        """Format comparison as Markdown report."""
        lines = [
            "## Quality Baseline Comparison",
            "",
            f"**Regression Severity:** {self.regression_severity}",
            f"**Threshold:** {self.threshold_percent:.1f}% decline",
            "",
            "### Metrics",
            "",
            "| Metric | Baseline | Current | Delta |",
            "|--------|----------|---------|-------|",
            f"| Match Rate | {self.baseline.match_rate:.1%} | {self.current.match_rate:.1%} | {self.match_rate_delta_percent:+.2f}pp |",
            f"| Matched Records | {self.baseline.matched_records} | {self.current.matched_records} | {self.matched_records_delta:+d} |",
            f"| Exact Matches | {self.baseline.exact_matches} | {self.current.exact_matches} | {self.current.exact_matches - self.baseline.exact_matches:+d} |",
            f"| Fuzzy Matches | {self.baseline.fuzzy_matches} | {self.current.fuzzy_matches} | {self.current.fuzzy_matches - self.baseline.fuzzy_matches:+d} |",
            "",
        ]

        if self.regression_messages:
            lines.extend(["### Regression Details", ""])
            for msg in self.regression_messages:
                lines.append(f"- {msg}")
            lines.append("")

        if self.exceeded_threshold:
            lines.append(
                f"⚠️ **WARNING:** Match rate declined {abs(self.match_rate_delta_percent):.2f}pp "
                f"(exceeds {self.threshold_percent:.1f}% threshold)"
            )
        else:
            lines.append("✓ Match rate regression within acceptable threshold")

        return "\n".join(lines)


class QualityBaselineManager:
    """Manages storage and comparison of quality baselines."""

    def __init__(self, baseline_dir: Path | None = None):
        """Initialize baseline manager.

        Args:
            baseline_dir: Directory to store baselines. Defaults to reports/baselines/
        """
        self.baseline_dir = baseline_dir or Path("reports/baselines")
        self.baseline_dir.mkdir(parents=True, exist_ok=True)
        self.baseline_file = self.baseline_dir / "baseline.json"
        self.history_file = self.baseline_dir / "history.jsonl"

    def save_baseline(self, baseline: QualityBaseline) -> Path:
        """Save baseline as current baseline.

        Args:
            baseline: Baseline to save

        Returns:
            Path to baseline file
        """
        with open(self.baseline_file, "w") as f:
            json.dump(baseline.to_dict(), f, indent=2, default=str)

        logger.info(f"Baseline saved to {self.baseline_file}")

        # Also append to history
        with open(self.history_file, "a") as f:
            f.write(json.dumps(baseline.to_dict(), default=str) + "\n")

        return self.baseline_file

    def load_baseline(self) -> QualityBaseline | None:
        """Load current baseline.

        Returns:
            QualityBaseline or None if no baseline exists
        """
        if not self.baseline_file.exists():
            logger.warning(f"No baseline file found at {self.baseline_file}")
            return None

        with open(self.baseline_file) as f:
            data = json.load(f)

        baseline = QualityBaseline.from_dict(data)
        logger.info(f"Loaded baseline: {baseline.match_rate:.1%} match rate")
        return baseline

    def create_baseline_from_metrics(
        self,
        match_rate: float,
        matched_records: int,
        total_records: int,
        exact_matches: int,
        fuzzy_matches: int,
        run_id: str | None = None,
        processing_mode: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> QualityBaseline:
        """Create baseline from enrichment metrics.

        Args:
            match_rate: Match rate as decimal (0-1)
            matched_records: Number of matched records
            total_records: Total records processed
            exact_matches: Number of exact matches
            fuzzy_matches: Number of fuzzy matches
            run_id: Dagster run ID
            processing_mode: Processing mode used (standard/chunked)
            metadata: Optional additional metadata

        Returns:
            Created QualityBaseline
        """
        baseline = QualityBaseline(
            timestamp=datetime.now(),
            match_rate=match_rate,
            matched_records=matched_records,
            total_records=total_records,
            exact_matches=exact_matches,
            fuzzy_matches=fuzzy_matches,
            run_id=run_id,
            processing_mode=processing_mode,
            metadata=metadata or {},
        )

        return baseline

    def compare_to_baseline(
        self,
        current: QualityBaseline,
        baseline: QualityBaseline | None = None,
        regression_threshold_percent: float = 5.0,
    ) -> BaselineComparison:
        """Compare current baseline to historical baseline.

        Args:
            current: Current quality metrics
            baseline: Baseline to compare to (loads default if not provided)
            regression_threshold_percent: Fail if match rate declines by more than this percent

        Returns:
            BaselineComparison result
        """
        if baseline is None:
            baseline = self.load_baseline()

        # If no baseline exists, create comparison with pass status
        if baseline is None:
            logger.info("No historical baseline found, creating initial baseline")
            return BaselineComparison(
                baseline=current,
                current=current,
                match_rate_delta_percent=0.0,
                matched_records_delta=0,
                regression_severity="PASS",
                regression_messages=["Initial baseline (no historical comparison)"],
                threshold_percent=regression_threshold_percent,
            )

        # Calculate deltas
        match_rate_delta_pp = (current.match_rate - baseline.match_rate) * 100  # percentage points
        matched_records_delta = current.matched_records - baseline.matched_records

        # Determine severity
        regression_messages = []
        exceeded_threshold = False
        regression_severity = "PASS"

        if current.match_rate < baseline.match_rate:
            delta_percent = abs(match_rate_delta_pp)
            regression_messages.append(
                f"Match rate declined from {baseline.match_rate:.1%} to {current.match_rate:.1%} "
                f"({delta_percent:.2f}pp)"
            )

            if delta_percent > regression_threshold_percent:
                exceeded_threshold = True
                regression_severity = "FAILURE"
                regression_messages.append(
                    f"Regression exceeds threshold of {regression_threshold_percent:.1f}pp"
                )
            else:
                regression_severity = "WARNING"
                regression_messages.append(
                    f"Regression within acceptable threshold ({regression_threshold_percent:.1f}pp)"
                )
        elif current.match_rate > baseline.match_rate:
            delta_percent = match_rate_delta_pp
            regression_messages.append(
                f"Match rate improved from {baseline.match_rate:.1%} to {current.match_rate:.1%} "
                f"({delta_percent:+.2f}pp)"
            )
            regression_severity = "PASS"

        comparison = BaselineComparison(
            baseline=baseline,
            current=current,
            match_rate_delta_percent=match_rate_delta_pp,
            matched_records_delta=matched_records_delta,
            regression_severity=regression_severity,
            regression_messages=regression_messages,
            exceeded_threshold=exceeded_threshold,
            threshold_percent=regression_threshold_percent,
        )

        return comparison

    def get_history(self, limit: int | None = None) -> list[QualityBaseline]:
        """Load historical baselines.

        Args:
            limit: Maximum number of baselines to load (most recent first)

        Returns:
            List of historical baselines
        """
        if not self.history_file.exists():
            return []

        baselines = []
        with open(self.history_file) as f:
            for line in f:
                try:
                    data = json.loads(line)
                    baselines.append(QualityBaseline.from_dict(data))
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse baseline line: {line}")
                    continue

        # Return most recent first
        baselines.reverse()

        if limit:
            baselines = baselines[:limit]

        return baselines

    def calculate_trend(self, num_recent: int = 10) -> dict[str, Any]:
        """Calculate trend across recent baselines.

        Args:
            num_recent: Number of recent baselines to analyze

        Returns:
            Trend analysis dict
        """
        history = self.get_history(limit=num_recent)

        if not history:
            return {
                "trend": "no_data",
                "direction": "unknown",
                "baselines_analyzed": 0,
            }

        match_rates = [b.match_rate for b in history]
        first_rate = history[-1].match_rate
        last_rate = history[0].match_rate

        trend = "stable"
        if last_rate > first_rate * 1.02:
            trend = "improving"
        elif last_rate < first_rate * 0.98:
            trend = "declining"

        return {
            "trend": trend,
            "direction": "up"
            if last_rate > first_rate
            else "down"
            if last_rate < first_rate
            else "stable",
            "baselines_analyzed": len(history),
            "oldest_match_rate": first_rate,
            "newest_match_rate": last_rate,
            "rate_change_percent": (last_rate - first_rate) / first_rate * 100
            if first_rate > 0
            else 0,
            "min_match_rate": min(match_rates),
            "max_match_rate": max(match_rates),
            "avg_match_rate": sum(match_rates) / len(match_rates),
        }
