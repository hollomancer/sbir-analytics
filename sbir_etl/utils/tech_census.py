"""Config-driven technology censuses over SBIR/STTR awards.

Profiles answer two separate questions: broad technology relevance and a
stricter physical-product/manufacturing census.  The engine keeps the
classification rules in versioned YAML and emits enough evidence and source
identifiers to audit every included award.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any, TypedDict

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config" / "tech_census"


class CensusAward(TypedDict, total=False):
    """Canonical award shape used by the census engine."""

    title: str
    abstract: str
    company: str
    agency: str
    program: str
    phase: str
    award_year: int | None
    award_amount: float
    agency_tracking_number: str
    contract: str
    source_row: int


def load_census_config(area_id: str, config_dir: Path | None = None) -> dict[str, Any]:
    """Load and validate a census profile and its optional override ledger."""

    directory = (config_dir or CONFIG_DIR).resolve()
    path = directory / f"{area_id}.yaml"
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
    physical_gate = cfg.get("physical_gate")
    if physical_gate and (
        not physical_gate.get("terms") or not physical_gate.get("relationship_terms")
    ):
        raise ValueError(f"{path}: physical_gate requires terms and relationship_terms")

    cfg["_overrides"] = []
    cfg["_override_version"] = None
    override_name = cfg.get("overrides_file")
    if override_name:
        override_path = (directory / str(override_name)).resolve()
        try:
            override_path.relative_to(directory)
        except ValueError as exc:
            raise ValueError(f"{path}: overrides_file must remain under {directory}") from exc
        if not override_path.exists():
            raise FileNotFoundError(f"Override ledger not found: {override_path}")
        ledger = yaml.safe_load(override_path.read_text(encoding="utf-8")) or {}
        cfg["_overrides"] = ledger.get("overrides", []) or []
        cfg["_override_version"] = str(ledger.get("version", "unversioned"))
    return cfg


def _compile(patterns: Iterable[str]) -> list[re.Pattern[str]]:
    return [re.compile(pattern, re.IGNORECASE) for pattern in patterns]


def _compiled_rule(rule: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": rule["name"],
        "display_name": rule.get("display_name", rule["name"]),
        "reason": rule.get("reason", ""),
        "title_only": bool(rule.get("title_only", False)),
        "unless_title_only": bool(rule.get("unless_title_only", False)),
        "terms": _compile(rule.get("terms", [])),
        "unless_terms": _compile(rule.get("unless_terms", [])),
    }


class CompiledCensus:
    """Compiled regular-expression form of a census profile."""

    def __init__(self, cfg: dict[str, Any]):
        self.area_id = str(cfg["area_id"])
        self.display_name = str(cfg["display_name"])
        self.version = str(cfg.get("version", "unversioned"))
        self.programs = tuple(str(value).strip().upper() for value in cfg.get("programs", []))
        self.gate_terms = _compile(cfg["gate"]["terms"])
        self.gate_any = re.compile(
            "|".join(f"(?:{pattern.pattern})" for pattern in self.gate_terms),
            re.IGNORECASE,
        )
        self.min_abstract_only_occurrences = int(
            cfg["gate"].get("min_abstract_only_occurrences", 2)
        )

        physical = cfg.get("physical_gate") or {}
        self.physical_terms = _compile(physical.get("terms", []))
        self.physical_title_terms = self.physical_terms + _compile(physical.get("title_terms", []))
        self.physical_abstract_terms = self.physical_terms + _compile(
            physical.get("abstract_terms", [])
        )
        self.relationship_terms = _compile(physical.get("relationship_terms", []))
        self.physical_title_always_passes = bool(physical.get("title_term_always_passes", True))
        self.max_relationship_distance = int(physical.get("max_relationship_distance", 180))
        self.max_relevance_distance = int(physical.get("max_relevance_distance", 240))

        self.exclusions = [_compiled_rule(rule) for rule in cfg.get("exclusions", [])]
        self.adjacent = [
            _compiled_rule(rule) for rule in cfg.get("adjacent_nonaerial", cfg.get("adjacent", []))
        ]
        self.subsets = [
            (str(rule["name"]), _compile(rule.get("terms", []))) for rule in cfg["subsets"]
        ]
        self.fallback_subset = str(cfg["fallback_subset"])
        self.scope_classes = [
            (str(rule["name"]), _compile(rule.get("terms", [])))
            for rule in cfg.get("scope_classes", [])
        ]
        self.fallback_scope_class = str(cfg.get("fallback_scope_class", "Unclassified"))
        self.overrides = list(cfg.get("_overrides", []))
        self.override_version = cfg.get("_override_version")
        self._validate_overrides()

    def _validate_overrides(self) -> None:
        for index, override in enumerate(self.overrides, start=1):
            action = str(override.get("action", "")).lower()
            if action not in {"include", "exclude"}:
                raise ValueError(f"override {index}: action must be include or exclude")
            if not override.get("identifiers"):
                raise ValueError(f"override {index}: identifiers must be non-empty")
            if not str(override.get("reason", "")).strip():
                raise ValueError(f"override {index}: reason is required")

    @classmethod
    def from_area(cls, area_id: str, config_dir: Path | None = None) -> CompiledCensus:
        return cls(load_census_config(area_id, config_dir))


def _title_of(award: CensusAward) -> str:
    return str(award.get("title", "") or "")


def _text_of(award: CensusAward) -> str:
    return f"{_title_of(award)} {award.get('abstract', '') or ''}".strip()


def _merged_matches(text: str, patterns: Iterable[re.Pattern[str]]) -> list[tuple[int, int, str]]:
    """Return non-overlapping evidence spans, merging regex aliases on one phrase."""

    spans = sorted(
        (match.start(), match.end())
        for pattern in patterns
        for match in pattern.finditer(text)
        if match.end() > match.start()
    )
    merged: list[list[int]] = []
    for start, end in spans:
        if merged and start < merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end, text[start:end]) for start, end in merged]


def _evidence(text: str, patterns: Iterable[re.Pattern[str]]) -> list[str]:
    return [literal for _start, _end, literal in _merged_matches(text, patterns)]


def gate_evidence(award: CensusAward, compiled: CompiledCensus) -> list[str]:
    """Return distinct textual mentions supporting the relevance gate."""

    text = _text_of(award)
    if not compiled.gate_any.search(text):
        return []
    return _evidence(text, compiled.gate_terms)


def passes_gate(award: CensusAward, compiled: CompiledCensus) -> bool:
    """Return whether title evidence or repeated abstract evidence clears the gate."""

    title = _title_of(award)
    if any(pattern.search(title) for pattern in compiled.gate_terms):
        return True
    return len(gate_evidence(award, compiled)) >= compiled.min_abstract_only_occurrences


def _span_distance(left: tuple[int, int, str], right: tuple[int, int, str]) -> int:
    if left[1] < right[0]:
        return right[0] - left[1]
    if right[1] < left[0]:
        return left[0] - right[1]
    return 0


def physical_gate_evidence(award: CensusAward, compiled: CompiledCensus) -> list[str]:
    """Return physical and funded-development evidence supporting strict scope."""

    if not compiled.physical_terms:
        return []
    title = _title_of(award)
    title_matches = _merged_matches(title, compiled.physical_title_terms)
    title_has_relevance = any(pattern.search(title) for pattern in compiled.gate_terms)
    if compiled.physical_title_always_passes and title_matches and title_has_relevance:
        evidence = [f"physical: {match[2]}" for match in title_matches]
        abstract = str(award.get("abstract", "") or "")
        relationship_matches = _merged_matches(abstract, compiled.relationship_terms)
        if relationship_matches:
            evidence.append(f"relationship: {relationship_matches[0][2]}")
        return evidence

    abstract = str(award.get("abstract", "") or "")
    physical_matches = _merged_matches(abstract, compiled.physical_abstract_terms)
    relationship_matches = _merged_matches(abstract, compiled.relationship_terms)
    relevance_matches = _merged_matches(abstract, compiled.gate_terms)
    best: (
        tuple[
            int,
            tuple[int, int, str],
            tuple[int, int, str],
            tuple[int, int, str],
        ]
        | None
    ) = None
    for physical in physical_matches:
        for relationship in relationship_matches:
            # A single regex span cannot prove both that a deliverable is
            # physical and that funded development work is being performed.
            # For example, ``coating`` appears in both vocabularies.
            if physical[0] < relationship[1] and relationship[0] < physical[1]:
                continue
            relationship_distance = _span_distance(physical, relationship)
            if relationship_distance > compiled.max_relationship_distance:
                continue
            for relevance in relevance_matches:
                relevance_distance = _span_distance(physical, relevance)
                combined_distance = relationship_distance + relevance_distance
                if relevance_distance <= compiled.max_relevance_distance and (
                    best is None or combined_distance < best[0]
                ):
                    best = (combined_distance, physical, relationship, relevance)
    if best is None:
        return []
    return [
        f"physical: {best[1][2]}",
        f"relationship: {best[2][2]}",
        f"relevance: {best[3][2]}",
    ]


def _matched_rule(award: CensusAward, rules: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    full_text = _text_of(award)
    title = _title_of(award)
    for rule in rules:
        text = title if rule["title_only"] else full_text
        unless_text = title if rule["unless_title_only"] else full_text
        if any(pattern.search(text) for pattern in rule["terms"]) and not any(
            pattern.search(unless_text) for pattern in rule["unless_terms"]
        ):
            return rule
    return None


def matched_exclusion(award: CensusAward, compiled: CompiledCensus) -> str | None:
    """Return a matching exclusion category name, if any."""

    rule = _matched_rule(award, compiled.exclusions)
    return str(rule["name"]) if rule else None


def matched_adjacent(award: CensusAward, compiled: CompiledCensus) -> str | None:
    """Return a matching adjacent non-aerial category name, if any."""

    rule = _matched_rule(award, compiled.adjacent)
    return str(rule["name"]) if rule else None


def _classification(
    award: CensusAward,
    rules: Iterable[tuple[str, list[re.Pattern[str]]]],
    fallback: str,
) -> tuple[str, list[str]]:
    title = _title_of(award)
    for name, patterns in rules:
        evidence = _evidence(title, patterns)
        if evidence:
            return name, evidence
    text = _text_of(award)
    for name, patterns in rules:
        evidence = _evidence(text, patterns)
        if evidence:
            return name, evidence
    return fallback, []


def classify_subset(award: CensusAward, compiled: CompiledCensus) -> str:
    """Assign one priority-ordered technology subset."""

    return _classification(award, compiled.subsets, compiled.fallback_subset)[0]


def classify_scope(award: CensusAward, compiled: CompiledCensus) -> str:
    """Assign the orthogonal scope class (hardware, software, services, etc.)."""

    return _classification(award, compiled.scope_classes, compiled.fallback_scope_class)[0]


def _matching_override(award: CensusAward, compiled: CompiledCensus) -> dict[str, Any] | None:
    for override in compiled.overrides:
        identifiers = override.get("identifiers", {})
        if all(
            str(award.get(key, "") or "").strip().casefold() == str(expected).strip().casefold()
            for key, expected in identifiers.items()
        ):
            return override
    return None


def _audit_identity(award: CensusAward) -> dict[str, Any]:
    return {
        "title": award.get("title", ""),
        "company": award.get("company", ""),
        "program": award.get("program", ""),
        "agency_tracking_number": award.get("agency_tracking_number", ""),
        "contract": award.get("contract", ""),
        "source_row": award.get("source_row"),
    }


def run_census(
    awards: list[CensusAward],
    compiled: CompiledCensus,
    programs: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Classify awards and aggregate counts/dollars by year, subset, and scope."""

    effective_programs = (
        tuple(str(value).strip().upper() for value in programs)
        if programs is not None
        else compiled.programs
    )
    allowed_programs = set(effective_programs)
    classified: list[dict[str, Any]] = []
    excluded_awards: list[dict[str, Any]] = []
    exclusion_counts: dict[str, int] = defaultdict(int)
    adjacent_counts: dict[str, int] = defaultdict(int)
    program_exclusion_counts: dict[str, int] = defaultdict(int)
    rejection_counts: dict[str, int] = defaultdict(int)

    for award in awards:
        program = str(award.get("program", "") or "").strip().upper()
        if allowed_programs and program not in allowed_programs:
            program_exclusion_counts[program or "UNKNOWN"] += 1
            continue

        override = _matching_override(award, compiled)
        if override and str(override["action"]).lower() == "exclude":
            exclusion_counts["manual_override"] += 1
            excluded_awards.append(
                {
                    **_audit_identity(award),
                    "reason": override["reason"],
                    "classification_source": "override",
                }
            )
            continue

        relevance_evidence = gate_evidence(award, compiled)
        title_has_relevance = any(
            pattern.search(_title_of(award)) for pattern in compiled.gate_terms
        )
        standard_relevance = title_has_relevance or (
            len(relevance_evidence) >= compiled.min_abstract_only_occurrences
        )
        if not relevance_evidence and not override:
            rejection_counts["relevance_gate"] += 1
            adjacent = matched_adjacent(award, compiled)
            if adjacent:
                adjacent_counts[adjacent] += 1
            continue

        physical_evidence = physical_gate_evidence(award, compiled)
        # A strict profile has an independent physical-development gate.  In
        # that profile, one abstract UAS mention plus nearby physical/action
        # evidence is stronger than three repeated UAS mentions alone.
        clears_relevance = standard_relevance or bool(compiled.physical_terms and physical_evidence)
        if not (override and str(override["action"]).lower() == "include") and not (
            clears_relevance
        ):
            rejection_counts["relevance_gate"] += 1
            adjacent = matched_adjacent(award, compiled)
            exclusion_rule = _matched_rule(award, compiled.exclusions)
            if exclusion_rule:
                name = str(exclusion_rule["name"])
                exclusion_counts[name] += 1
                excluded_awards.append(
                    {
                        **_audit_identity(award),
                        "reason": exclusion_rule["reason"] or exclusion_rule["display_name"],
                        "classification_source": "rules",
                    }
                )
            elif adjacent:
                adjacent_counts[adjacent] += 1
            continue

        exclusion_rule = _matched_rule(award, compiled.exclusions)
        if not override and exclusion_rule:
            name = str(exclusion_rule["name"])
            exclusion_counts[name] += 1
            excluded_awards.append(
                {
                    **_audit_identity(award),
                    "reason": exclusion_rule["reason"] or exclusion_rule["display_name"],
                    "classification_source": "rules",
                }
            )
            continue

        if compiled.physical_terms and not override and not physical_evidence:
            rejection_counts["physical_gate"] += 1
            continue

        subset, subset_evidence = _classification(award, compiled.subsets, compiled.fallback_subset)
        scope, scope_evidence = _classification(
            award, compiled.scope_classes, compiled.fallback_scope_class
        )
        classification_source = "rules"
        override_reason = ""
        if override:
            subset = str(override.get("subset", subset))
            scope = str(override.get("scope_class", scope))
            classification_source = "override"
            override_reason = str(override["reason"])

        classified.append(
            {
                **_audit_identity(award),
                "agency": award.get("agency", ""),
                "phase": award.get("phase", ""),
                "year": award.get("award_year"),
                "amount": float(award.get("award_amount") or 0.0),
                "subset": subset,
                "scope_class": scope,
                "gate_evidence": relevance_evidence,
                "physical_evidence": physical_evidence,
                "subset_evidence": subset_evidence,
                "scope_evidence": scope_evidence,
                "classification_source": classification_source,
                "override_reason": override_reason,
            }
        )

    by_fy_subset: dict[tuple[int, str], dict[str, float]] = defaultdict(
        lambda: {"n": 0, "usd": 0.0}
    )
    subset_totals: dict[str, dict[str, float]] = defaultdict(lambda: {"n": 0, "usd": 0.0})
    scope_totals: dict[str, dict[str, float]] = defaultdict(lambda: {"n": 0, "usd": 0.0})
    fy_totals: dict[int, dict[str, float]] = defaultdict(lambda: {"n": 0, "usd": 0.0})
    grand_n = 0
    grand_usd = 0.0
    for row in classified:
        year = row["year"]
        subset = str(row["subset"])
        scope = str(row["scope_class"])
        amount = float(row["amount"])
        if isinstance(year, int):
            by_fy_subset[(year, subset)]["n"] += 1
            by_fy_subset[(year, subset)]["usd"] += amount
            fy_totals[year]["n"] += 1
            fy_totals[year]["usd"] += amount
        subset_totals[subset]["n"] += 1
        subset_totals[subset]["usd"] += amount
        scope_totals[scope]["n"] += 1
        scope_totals[scope]["usd"] += amount
        grand_n += 1
        grand_usd += amount

    for totals_by_key in (by_fy_subset, subset_totals, scope_totals, fy_totals):
        for totals in totals_by_key.values():
            totals["usd"] = round(totals["usd"], 2)

    return {
        "area_id": compiled.area_id,
        "display_name": compiled.display_name,
        "config_version": compiled.version,
        "override_version": compiled.override_version,
        "programs": sorted(allowed_programs),
        "classified_awards": classified,
        "excluded_awards": excluded_awards,
        "by_fy_subset": dict(by_fy_subset),
        "subset_totals": dict(subset_totals),
        "scope_totals": dict(scope_totals),
        "fy_totals": dict(fy_totals),
        "grand_total": {"n": grand_n, "usd": round(grand_usd, 2)},
        "exclusion_counts": dict(exclusion_counts),
        "adjacent_counts": dict(adjacent_counts),
        "program_exclusion_counts": dict(program_exclusion_counts),
        "rejection_counts": dict(rejection_counts),
    }


def _safe_amount(value: str) -> float:
    cleaned = (value or "").replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def _safe_year(value: str) -> int | None:
    try:
        return int(float(value)) if value else None
    except ValueError:
        return None


def load_award_data_csv(path: Path) -> list[CensusAward]:
    """Load and normalize SBIR.gov's ``award_data.csv`` export."""

    import csv

    csv.field_size_limit(2**31 - 1)
    awards: list[CensusAward] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for source_row, row in enumerate(csv.DictReader(handle), start=2):
            awards.append(
                {
                    "title": row.get("Award Title", "") or "",
                    "abstract": row.get("Abstract", "") or "",
                    "company": row.get("Company", "") or "",
                    "agency": row.get("Agency", "") or "",
                    "program": row.get("Program", "") or "",
                    "phase": row.get("Phase", "") or "",
                    "award_year": _safe_year(row.get("Award Year", "")),
                    "award_amount": _safe_amount(row.get("Award Amount", "")),
                    "agency_tracking_number": row.get("Agency Tracking Number", "") or "",
                    "contract": row.get("Contract", "") or "",
                    "source_row": source_row,
                }
            )
    return awards
