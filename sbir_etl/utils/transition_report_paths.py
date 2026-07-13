"""Path conventions for technology-area transition reports and dark-majority WS.

Canonical layout
----------------
``data/reports/<area_id>/`` holds all area-scoped artifacts::

    cohort_keyword.csv
    form_d_post_phase2.csv
    ws1_contract_evidence.csv
    dark_firm_liveness.csv
    ...
    analysis/*.png

Global bulk inputs (``award_data.csv``, Form D / EDGAR / USPTO zips, API caches)
stay under ``data/`` and are shared across areas.

Legacy nanotech layout
----------------------
PR #428 wrote ``data/nano_*.csv``. ``ReportPaths.legacy_nano()`` maps the same
logical stems onto those filenames so existing ``nano_*`` scripts can migrate
incrementally via ``--area nanotechnology --legacy``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = REPO_ROOT / "data"
REPORTS = DATA / "reports"
CONFIG_DIR = REPO_ROOT / "config" / "transition_reports"

# Logical stem → filename under data/reports/<area>/
ARTIFACT_STEMS = {
    "cohort_keyword": "cohort_keyword.csv",
    "cohort_cet": "cohort_cet.csv",
    "cohort_cpc": "cohort_cpc.csv",
    "form_d_post_phase2": "form_d_post_phase2.csv",
    "ws1_contract_evidence": "ws1_contract_evidence.csv",
    "ws2_contract_evidence": "ws2_contract_evidence.csv",
    "no_uei_resolution": "no_uei_resolution.csv",
    "dark_firm_liveness": "dark_firm_liveness.csv",
    "dark_firm_trademarks": "dark_firm_trademarks.csv",
    "ws5a_subawards": "ws5a_subawards.csv",
    "ws5c_sector_registries": "ws5c_sector_registries.csv",
    "sam_status": "sam_status.csv",
    "alias_expanded_evidence": "alias_expanded_evidence.csv",
    "firm_aliases": "firm_aliases.csv",
    "capture_recapture": "capture_recapture.csv",
    "capture_recapture_darkfirms": "capture_recapture_darkfirms.csv",
    "survey_frame": "survey_frame.csv",
    "subaward_leverage": "subaward_leverage.csv",
    "ma_signal": "ma_signal.csv",
    "prime_acquisitions": "prime_acquisitions.csv",
    "overlap_summary": "overlap_summary.json",
    "methodology_stub": "methodology_stub.md",
}

# Legacy PR #428 filenames under data/ (nanotech only)
LEGACY_NANO_STEMS = {
    "cohort_keyword": "nano_cohort_keyword.csv",
    "cohort_cet": "nano_cohort_cet.csv",
    "cohort_cpc": "nano_cohort_cpc.csv",
    "form_d_post_phase2": "nano_form_d_post_phase2.csv",
    "ws1_contract_evidence": "nano_ws1_contract_evidence.csv",
    "ws2_contract_evidence": "nano_ws2_contract_evidence.csv",
    "no_uei_resolution": "nano_no_uei_resolution.csv",
    "dark_firm_liveness": "nano_dark_firm_liveness.csv",
    "dark_firm_trademarks": "nano_dark_firm_trademarks.csv",
    "ws5a_subawards": "nano_ws5a_subawards.csv",
    "ws5c_sector_registries": "nano_ws5c_sector_registries.csv",
    "sam_status": "nano_sam_status.csv",
    "alias_expanded_evidence": "nano_alias_expanded_evidence.csv",
    "firm_aliases": "processed/firm_aliases.csv",  # was global
    "capture_recapture": "nano_capture_recapture.csv",
    "capture_recapture_darkfirms": "nano_capture_recapture_darkfirms.csv",
    "survey_frame": "nano_survey_frame.csv",
    "subaward_leverage": "nano_subaward_leverage.csv",
    "ma_signal": "nano_ma_signal.csv",
    "prime_acquisitions": "nano_prime_acquisitions.csv",
}


@dataclass(frozen=True)
class ReportPaths:
    """Resolve area-scoped (or legacy nano) artifact paths."""

    area_id: str
    legacy: bool = False

    @property
    def report_dir(self) -> Path:
        if self.legacy:
            return DATA
        return REPORTS / self.area_id

    @property
    def analysis_dir(self) -> Path:
        if self.legacy:
            return DATA / "analysis"
        return self.report_dir / "analysis"

    @property
    def config_path(self) -> Path:
        return CONFIG_DIR / f"{self.area_id}.yaml"

    def load_config(self) -> dict:
        """Load the area YAML config (config/transition_reports/<area>.yaml).

        Used by area-gated work streams (e.g. WS5c sector registries) to decide
        whether they apply to the area at all.
        """
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"No area config at {self.config_path}. "
                f"Add config/transition_reports/{self.area_id}.yaml"
            )
        cfg = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        cfg.setdefault("area_id", self.area_id)
        return cfg

    def artifact(self, stem: str) -> Path:
        """Return path for a logical artifact stem (see ARTIFACT_STEMS)."""
        if self.legacy:
            if self.area_id != "nanotechnology":
                raise ValueError("--legacy is only valid for area_id=nanotechnology")
            rel = LEGACY_NANO_STEMS.get(stem)
            if rel is None:
                raise KeyError(f"no legacy nano mapping for stem {stem!r}")
            return DATA / rel
        filename = ARTIFACT_STEMS.get(stem)
        if filename is None:
            raise KeyError(f"unknown artifact stem {stem!r}")
        return self.report_dir / filename

    def ensure_dirs(self) -> None:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.analysis_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def for_area(cls, area_id: str, *, legacy: bool = False) -> ReportPaths:
        return cls(area_id=area_id, legacy=legacy)

    @classmethod
    def legacy_nano(cls) -> ReportPaths:
        return cls(area_id="nanotechnology", legacy=True)


def add_area_args(parser) -> None:
    """Attach standard ``--area`` / ``--legacy`` flags to an argparse parser."""
    parser.add_argument(
        "--area",
        default="nanotechnology",
        help="area_id under config/transition_reports/ (default: nanotechnology)",
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Read/write PR #428 data/nano_*.csv paths (nanotechnology only)",
    )


def resolve_area_paths(args, argv: list[str] | None = None) -> ReportPaths:
    """Resolve ReportPaths from parsed args (Form D / WS1 / WS2 convention).

    Unflagged ``nano_*.py`` invocation (no ``--area``) keeps PR #428
    ``data/nano_*`` paths. Explicit ``--area X`` uses ``data/reports/X/``
    unless ``--legacy`` is also set.
    """
    argv = argv if argv is not None else sys.argv[1:]
    area_flagged = any(a == "--area" or a.startswith("--area=") for a in argv)
    legacy = bool(getattr(args, "legacy", False) or not area_flagged)
    area_id = "nanotechnology" if legacy else args.area
    paths = ReportPaths.for_area(area_id, legacy=legacy)
    paths.ensure_dirs()
    return paths
