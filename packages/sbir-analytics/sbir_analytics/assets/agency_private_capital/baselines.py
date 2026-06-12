"""Published-baseline registry.

Loads the cited VC / small-business-survival baselines from
``config/agency_private_capital/published_baselines.yaml`` and exposes them as typed
records. Three baseline kinds are supported:

- ``rate``: a published proportion comparable to a cohort rate.
- ``effect_size``: a directional effect (e.g. +27% growth) reported as
  narrative context rather than a rate-vs-rate delta.
- ``framing``: qualitative claim with no numeric baseline (e.g. ITIF).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import yaml


DEFAULT_REGISTRY_PATH = Path("config/agency_private_capital/published_baselines.yaml")


class BaselineKind(StrEnum):
    RATE = "rate"
    EFFECT_SIZE = "effect_size"
    FRAMING = "framing"


@dataclass(frozen=True)
class PublishedBaseline:
    """One cited VC / small-business baseline."""

    id: str
    cohort_metric: str
    label: str
    kind: BaselineKind
    point_estimate: float | None
    as_of: str
    population: str
    citation: str
    citation_url: str
    notes: str
    effect_description: str | None = None


@dataclass(frozen=True)
class PublishedBaselineRegistry:
    """In-memory collection of ``PublishedBaseline`` records."""

    baselines: tuple[PublishedBaseline, ...]

    @classmethod
    def load(cls, path: str | Path = DEFAULT_REGISTRY_PATH) -> PublishedBaselineRegistry:
        text = Path(path).read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
        raw = data.get("baselines") or []
        records = tuple(_to_baseline(entry) for entry in raw)
        return cls(baselines=records)

    def for_metric(self, metric: str) -> list[PublishedBaseline]:
        return [b for b in self.baselines if b.cohort_metric == metric]

    def __iter__(self):
        return iter(self.baselines)

    def __len__(self) -> int:
        return len(self.baselines)


def _to_baseline(entry: dict) -> PublishedBaseline:
    required = ("id", "cohort_metric", "label", "kind", "as_of", "citation")
    missing = [k for k in required if k not in entry]
    if missing:
        raise ValueError(f"baseline entry missing keys {missing}: {entry!r}")
    pe = entry.get("point_estimate")
    return PublishedBaseline(
        id=str(entry["id"]),
        cohort_metric=str(entry["cohort_metric"]),
        label=str(entry["label"]),
        kind=BaselineKind(entry["kind"]),
        point_estimate=float(pe) if pe is not None else None,
        as_of=str(entry["as_of"]),
        population=str(entry.get("population", "")),
        citation=str(entry["citation"]),
        citation_url=str(entry.get("citation_url", "")),
        notes=str(entry.get("notes", "")).strip(),
        effect_description=(
            str(entry["effect_description"]) if entry.get("effect_description") else None
        ),
    )
