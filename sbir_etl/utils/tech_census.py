"""Config-driven, all-phase technology-relevance census over SBIR/STTR awards.

Generalizes the ad hoc drone-manufacturing analysis into a reusable engine:
given an award universe (all phases -- this is a different question from the
Phase-II-scoped cohort work in ``build_tech_area_cohort.py`` /
``transition_signals.py``, which exists to support Phase II -> III transition
analysis, not a technology-relevance census) and a YAML config, classify each
award into a technology subset and aggregate counts/dollars by fiscal year.

Design, validated against real data while building the first config
(drone manufacturing):

  - A GATE of broad relevance terms decides whether an award is in scope at
    all. A term counts as a hit only if it appears in the award TITLE, or the
    TOTAL occurrence count across all gate terms in title+abstract meets
    ``min_abstract_only_occurrences``. Counting total occurrences (not
    distinct pattern names) matters: several gate patterns are near-synonyms
    that overlap on a single phrase (e.g. "unmanned aerial system" and
    "unmanned aerial" both match "unmanned aerial systems"), so a naive
    "N distinct terms" rule can be satisfied by one incidental sentence.
    Spot-checked false positives (a hypersonic-interceptor award, a
    lunar-battery award, a weather-forecasting-software award) each produced
    exactly 2 total occurrences from one incidental mention; genuinely
    relevant awards ran well past that.
  - EXCLUSIONS are gate-passing awards that represent an adjacent-but-distinct
    concept (e.g. counter-UAS defeat technology is not drone manufacturing).
    They are tracked and reported separately, never silently dropped.
  - SUBSETS sub-classify the remaining awards by more specific terminology,
    in priority order (most specific first); anything matching no subset
    falls into the configured fallback bucket. Each award gets exactly one
    subset, so subset totals sum to the grand total without double-counting.

Config schema: see config/tech_census/drone_manufacturing.yaml for a worked
example. Callers normalize their own data source's column names into the
canonical award dict shape this module expects (title, abstract, company,
agency, phase, award_year, award_amount) -- this keeps the engine independent
of both raw award_data.csv's column names and any DataFrame-based caller's
naming conventions.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any, TypedDict

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config" / "tech_census"


class CensusAward(TypedDict, total=False):
    """Canonical award shape the engine operates on."""

    title: str
    abstract: str
    company: str
    agency: str
    phase: str
    award_year: int
    award_amount: float


def load_census_config(area_id: str, config_dir: Path | None = None) -> dict[str, Any]:
    """Load and lightly validate a tech-census area config."""
    path = (config_dir or CONFIG_DIR) / f"{area_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"No tech-census config at {path}. Add config/tech_census/{area_id}.yaml"
        )
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if cfg.get("area_id") and cfg["area_id"] != area_id:
        raise ValueError(f"area_id in {path} is {cfg['area_id']!r}, expected {area_id!r}")
    cfg["area_id"] = area_id
    for required in ("display_name", "gate", "subsets", "fallback_subset"):
        if required not in cfg:
            raise ValueError(f"{path} missing required key {required!r}")
    if not cfg["gate"].get("terms"):
        raise ValueError(f"{path}: gate.terms must be non-empty")
    return cfg


def _compile(patterns: list[str]) -> list[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


class CompiledCensus:
    """Compiled regex form of a census config, built once and reused per award."""

    def __init__(self, cfg: dict[str, Any]):
        self.area_id: str = cfg["area_id"]
        self.display_name: str = cfg["display_name"]
        self.gate_terms: list[re.Pattern] = _compile(cfg["gate"]["terms"])
        self.min_abstract_only_occurrences: int = cfg["gate"].get(
            "min_abstract_only_occurrences", 2
        )

        self.exclusions: list[tuple[str, str, list[re.Pattern]]] = [
            (e["name"], e.get("display_name", e["name"]), _compile(e["terms"]))
            for e in cfg.get("exclusions", [])
        ]
        self.adjacent: list[tuple[str, str, list[re.Pattern]]] = [
            (a["name"], a.get("display_name", a["name"]), _compile(a["terms"]))
            for a in cfg.get("adjacent_nonaerial", cfg.get("adjacent", []))
        ]
        # Priority-ordered: first matching subset wins.
        self.subsets: list[tuple[str, list[re.Pattern]]] = [
            (s["name"], _compile(s["terms"])) for s in cfg["subsets"]
        ]
        self.fallback_subset: str = cfg["fallback_subset"]

    @classmethod
    def from_area(cls, area_id: str, config_dir: Path | None = None) -> CompiledCensus:
        return cls(load_census_config(area_id, config_dir))


def _text_of(award: CensusAward) -> str:
    return f"{award.get('title', '') or ''} {award.get('abstract', '') or ''}"


def passes_gate(award: CensusAward, compiled: CompiledCensus) -> bool:
    """True if the award clears the relevance gate (title hit, or strong occurrence count)."""
    text = _text_of(award)
    title = award.get("title", "") or ""
    matched = [rx for rx in compiled.gate_terms if rx.search(text)]
    if not matched:
        return False
    if any(rx.search(title) for rx in matched):
        return True
    total_occurrences = sum(len(rx.findall(text)) for rx in compiled.gate_terms)
    return total_occurrences >= compiled.min_abstract_only_occurrences


def matched_exclusion(award: CensusAward, compiled: CompiledCensus) -> str | None:
    """Return the exclusion category name if the award matches one, else None."""
    text = _text_of(award)
    for name, _display, patterns in compiled.exclusions:
        if any(rx.search(text) for rx in patterns):
            return name
    return None


def matched_adjacent(award: CensusAward, compiled: CompiledCensus) -> str | None:
    """Return the adjacent (non-gate) category name if the award matches one, else None."""
    text = _text_of(award)
    for name, _display, patterns in compiled.adjacent:
        if any(rx.search(text) for rx in patterns):
            return name
    return None


def classify_subset(award: CensusAward, compiled: CompiledCensus) -> str:
    """Assign exactly one subset via priority order; fallback if nothing matches."""
    text = _text_of(award)
    for name, patterns in compiled.subsets:
        if any(rx.search(text) for rx in patterns):
            return name
    return compiled.fallback_subset


def run_census(awards: list[CensusAward], compiled: CompiledCensus) -> dict[str, Any]:
    """Classify every award and aggregate by fiscal year x subset.

    Returns a dict with: in-scope classified awards (list), per-(year,subset)
    counts/dollars, subset totals, year totals, grand total, and separately-
    tracked exclusion/adjacent category counts (never merged into the main
    total).
    """
    classified: list[dict[str, Any]] = []
    exclusion_counts: dict[str, int] = defaultdict(int)
    adjacent_counts: dict[str, int] = defaultdict(int)

    for award in awards:
        if not passes_gate(award, compiled):
            excl = matched_exclusion(award, compiled)
            adj = matched_adjacent(award, compiled)
            # Only count non-gate-passing awards here; gate-passing exclusions
            # are handled below so an award is never counted twice.
            if excl:
                exclusion_counts[excl] += 1
            elif adj:
                adjacent_counts[adj] += 1
            continue

        excl = matched_exclusion(award, compiled)
        if excl:
            exclusion_counts[excl] += 1
            continue

        subset = classify_subset(award, compiled)
        classified.append(
            {
                "title": award.get("title", ""),
                "company": award.get("company", ""),
                "agency": award.get("agency", ""),
                "phase": award.get("phase", ""),
                "year": award.get("award_year"),
                "amount": float(award.get("award_amount") or 0.0),
                "subset": subset,
            }
        )

    by_fy_subset: dict[tuple[int, str], dict[str, float]] = defaultdict(
        lambda: {"n": 0, "usd": 0.0}
    )
    subset_totals: dict[str, dict[str, float]] = defaultdict(lambda: {"n": 0, "usd": 0.0})
    fy_totals: dict[int, dict[str, float]] = defaultdict(lambda: {"n": 0, "usd": 0.0})
    grand_n = 0
    grand_usd = 0.0

    for row in classified:
        year, subset, amount = row["year"], row["subset"], row["amount"]
        by_fy_subset[(year, subset)]["n"] += 1
        by_fy_subset[(year, subset)]["usd"] += amount
        subset_totals[subset]["n"] += 1
        subset_totals[subset]["usd"] += amount
        fy_totals[year]["n"] += 1
        fy_totals[year]["usd"] += amount
        grand_n += 1
        grand_usd += amount

    return {
        "area_id": compiled.area_id,
        "display_name": compiled.display_name,
        "classified_awards": classified,
        "by_fy_subset": dict(by_fy_subset),
        "subset_totals": dict(subset_totals),
        "fy_totals": dict(fy_totals),
        "grand_total": {"n": grand_n, "usd": grand_usd},
        "exclusion_counts": dict(exclusion_counts),
        "adjacent_counts": dict(adjacent_counts),
    }


def _safe_amount(v: str) -> float:
    if not v:
        return 0.0
    v = v.replace("$", "").replace(",", "").strip()
    try:
        return float(v)
    except ValueError:
        return 0.0


def _safe_year(v: str) -> int | None:
    try:
        return int(float(v)) if v else None
    except ValueError:
        return None


def load_award_data_csv(path: Path) -> list[CensusAward]:
    """Load and normalize SBIR.gov's ``award_data.csv`` into the canonical shape.

    This exact column-mapping (Award Title/Abstract/Company/Agency/Phase/
    Award Year/Award Amount, ``utf-8-sig`` encoding for the BOM, oversized
    field-size limit for embedded newlines in abstracts) has been rewritten
    ad hoc several times across this repo's analysis scripts; centralized
    here as the one shared, tested loader for this source. All phases are
    included -- unlike ``build_tech_area_cohort.py``'s ``load_phase2_awards``,
    a technology-relevance census is not scoped to Phase II.
    """
    import csv

    csv.field_size_limit(2**31 - 1)
    awards: list[CensusAward] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            awards.append(
                {
                    "title": row.get("Award Title", "") or "",
                    "abstract": row.get("Abstract", "") or "",
                    "company": row.get("Company", "") or "",
                    "agency": row.get("Agency", "") or "",
                    "phase": row.get("Phase", "") or "",
                    "award_year": _safe_year(row.get("Award Year", "")),
                    "award_amount": _safe_amount(row.get("Award Amount", "")),
                }
            )
    return awards
