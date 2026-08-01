"""Auditable rule-based CET screening for local research builds."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TAXONOMY_PATH = PROJECT_ROOT / "config" / "cet" / "taxonomy.yaml"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "cet" / "local_rule_classifier.yaml"


@dataclass(frozen=True)
class KeywordEvidence:
    """One keyword match contributing to a CET screening score."""

    keyword: str
    source: str
    weight: float


@dataclass(frozen=True)
class LocalCETRuleClassifier:
    """Deterministic CET classifier backed by the versioned taxonomy keywords."""

    version: str
    taxonomy_version: str
    areas: tuple[dict[str, Any], ...]
    config: dict[str, Any]

    def classify_frame(self, awards: pd.DataFrame) -> pd.DataFrame:
        """Return one primary classification row per award with qualifying evidence."""

        if "award_id" not in awards.columns:
            raise ValueError("awards must contain award_id")

        records: list[dict[str, Any]] = []
        for raw_row in awards.to_dict(orient="records"):
            row = {str(key): value for key, value in raw_row.items()}
            candidates = self._classify_row(row)
            if not candidates:
                continue
            primary = candidates[0]
            supporting = candidates[1 : 1 + int(self.config["max_supporting_cets"])]
            records.append(
                {
                    "award_id": str(row["award_id"]),
                    "primary_cet": primary["cet_id"],
                    "primary_score": primary["score"],
                    "supporting_cets": [
                        {"cet_id": item["cet_id"], "score": item["score"]} for item in supporting
                    ],
                    "evidence": primary["evidence"],
                    "taxonomy_version": self.taxonomy_version,
                    "classifier_version": self.version,
                }
            )
        return pd.DataFrame.from_records(records)

    def _classify_row(self, row: dict[str, Any]) -> list[dict[str, Any]]:
        fields = {name: _normalize_text(row.get(name)) for name in self.config["field_weights"]}
        candidates: list[dict[str, Any]] = []
        for area in self.areas:
            evidence = self._keyword_evidence(area.get("keywords", []), fields)
            raw_score = sum(item.weight for item in evidence)
            negative_matches = _matched_keywords(
                area.get("negative_keywords", []), " ".join(fields.values())
            )
            if negative_matches:
                raw_score *= float(self.config["negative_keyword_multiplier"]) ** len(
                    negative_matches
                )
            if raw_score < float(self.config["minimum_raw_score"]):
                continue
            score = min(
                float(self.config["maximum_output_score"]),
                float(self.config["base_output_score"])
                + float(self.config["raw_score_multiplier"]) * raw_score,
            )
            if score < float(self.config["minimum_output_score"]):
                continue
            candidates.append(
                {
                    "cet_id": area["cet_id"],
                    "score": round(score, 2),
                    "evidence": [
                        {
                            "keyword": item.keyword,
                            "source": item.source,
                            "weight": round(item.weight, 3),
                        }
                        for item in sorted(evidence, key=lambda item: (-item.weight, item.keyword))[
                            :5
                        ]
                    ],
                }
            )
        return sorted(candidates, key=lambda item: (-item["score"], item["cet_id"]))

    def _keyword_evidence(
        self, keywords: list[str], fields: dict[str, str]
    ) -> list[KeywordEvidence]:
        evidence: list[KeywordEvidence] = []
        for keyword in keywords:
            pattern = _keyword_pattern(keyword)
            best: KeywordEvidence | None = None
            for source, text in fields.items():
                if text and pattern.search(text):
                    weight = float(self.config["field_weights"][source]) * _specificity_weight(
                        keyword, self.config["keyword_specificity"]
                    )
                    item = KeywordEvidence(keyword=keyword, source=source, weight=weight)
                    if best is None or item.weight > best.weight:
                        best = item
            if best is not None:
                evidence.append(best)
        return evidence


def load_local_cet_rule_classifier(
    *, taxonomy_path: Path = DEFAULT_TAXONOMY_PATH, config_path: Path = DEFAULT_CONFIG_PATH
) -> LocalCETRuleClassifier:
    """Load and validate the local classifier and canonical taxonomy."""

    taxonomy = yaml.safe_load(taxonomy_path.read_text(encoding="utf-8"))
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if taxonomy.get("version") != config.get("taxonomy_version"):
        raise ValueError(
            f"classifier expects taxonomy {config.get('taxonomy_version')!r}, "
            f"found {taxonomy.get('version')!r}"
        )
    areas = tuple(taxonomy.get("cet_areas", []))
    if len(areas) != 21:
        raise ValueError(f"expected 21 CET areas, found {len(areas)}")
    return LocalCETRuleClassifier(
        version=str(config["version"]),
        taxonomy_version=str(config["taxonomy_version"]),
        areas=areas,
        config=config,
    )


def _normalize_text(value: object) -> str:
    if value is None or value is pd.NA:
        return ""
    return re.sub(r"\s+", " ", str(value).lower()).strip()


def _keyword_pattern(keyword: str) -> re.Pattern[str]:
    parts = [re.escape(part) for part in keyword.lower().split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(parts) + r"(?!\w)")


def _matched_keywords(keywords: list[str], text: str) -> list[str]:
    return [keyword for keyword in keywords if _keyword_pattern(keyword).search(text)]


def _specificity_weight(keyword: str, config: dict[str, Any]) -> float:
    words = keyword.split()
    if len(words) > 1:
        return float(config["multiword"])
    length = len(words[0])
    if length >= 5:
        return float(config["long_single_word"])
    if length >= 3:
        return float(config["short_single_word"])
    return float(config["abbreviation"])


__all__ = ["LocalCETRuleClassifier", "load_local_cet_rule_classifier"]
