"""Shared transition-signal enrichment for technology-area cohorts.

Extracted from ``scripts/data/build_nano_cohort.py`` so area-parameterized
runners (and dark-majority WS scripts) can enrich a Method-A cohort with
FPDS / M&A / Form D channels and ``deficiency_class`` without importing the
nanotech script (which pulls in matplotlib).

Dark-majority WS1/WS2/liveness **require** ``deficiency_class`` on the cohort.
"""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

# Awards younger than this are censored observations, not transition failures.
INSUFFICIENT_TIME_YEAR = date.today().year - 3

NON_DOD_AGENCIES = frozenset(
    {
        "National Science Foundation",
        "Department of Energy",
        "Department of Agriculture",
        "Environmental Protection Agency",
        "Department of Transportation",
        "National Aeronautics and Space Administration",
    }
)

DEFAULT_DIGEST = Path("data/processed/sbir_phase3/fy25_phase3_prospect_digest.csv")
DEFAULT_MA = Path("data/enriched_sbir_ma_events.jsonl")
DEFAULT_FORM_D = Path("data/form_d_high_conf_cohort.jsonl")


def _safe_float(v: str) -> float:
    try:
        return float(v.replace("$", "").replace(",", "")) if v else 0.0
    except ValueError:
        return 0.0


def _safe_int(v: str) -> int:
    try:
        return int(float(v.replace("$", "").replace(",", ""))) if v else 0
    except ValueError:
        return 0


def load_phase3_digest(digest_csv: Path) -> dict[str, dict]:
    """Load fy25_phase3_prospect_digest.csv keyed by UEI."""
    by_uei: dict[str, dict] = {}
    if not digest_csv.exists():
        return by_uei
    with open(digest_csv, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            uei = row.get("uei", "").strip()
            if uei:
                by_uei[uei] = {
                    "firm_name": row.get("firm_name", ""),
                    "phase3_awards_n": _safe_int(row.get("phase3_awards_n", "")),
                    "phase3_total_usd": _safe_float(row.get("phase3_total_usd", "")),
                    "has_fy_phase3": row.get("has_fy_phase3", "").strip().lower()
                    in ("true", "1", "yes"),
                    "fy_contracts_in_fpds": _safe_int(row.get("fy_contracts_in_fpds", "")),
                    "fy_grants_in_fabs": _safe_int(row.get("fy_grants_in_fabs", "")),
                }
    return by_uei


def load_ma_signals(jsonl_path: Path) -> dict[str, dict]:
    """Load M&A signals from enriched_sbir_ma_events.jsonl keyed by company name."""
    by_name: dict[str, dict] = {}
    if not jsonl_path.exists():
        return by_name
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                name = rec.get("company_name", "").strip().upper()
                if not name:
                    continue
                sc = rec.get("signal_count", 0)
                existing = by_name.get(name)
                if existing is None or sc > existing.get("signal_count", 0):
                    by_name[name] = {
                        "ma_signal_count": sc,
                        "ma_confidence": rec.get("confidence", ""),
                        "ma_event_date": rec.get("event_date", ""),
                        "ma_acquirer": rec.get("acquirer", ""),
                    }
            except json.JSONDecodeError:
                pass
    return by_name


def load_form_d_signals(jsonl_path: Path) -> dict[str, dict]:
    """Load Form D high-confidence matches keyed by company name."""
    by_name: dict[str, dict] = {}
    if not jsonl_path.exists():
        return by_name
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                name = rec.get("company_name", "").strip().upper()
                if not name:
                    continue
                by_name[name] = {
                    "form_d_total_raised": _safe_float(
                        str(rec.get("form_d_total_raised", "") or "")
                    ),
                    "form_d_filing_count": _safe_int(str(rec.get("form_d_filing_count", "") or "")),
                    "form_d_latest_date": "",
                    "form_d_confidence": "high",
                }
            except json.JSONDecodeError:
                pass
    return by_name


def classify_deficiency(row: dict) -> str:
    """Classify why Phase III transition status is indeterminate (FPDS-coded lens)."""
    if not row.get("uei"):
        return "ENTITY_RESOLUTION_FAILURE"
    if row.get("award_year", 0) >= INSUFFICIENT_TIME_YEAR:
        return "INSUFFICIENT_TIME"
    if not row.get("digest_found"):
        return "FIRM_ACTIVITY_ABSENT"
    if not row.get("sig_fpds_phase3_coded"):
        if row.get("agency", "") in NON_DOD_AGENCIES:
            return "DATA_GAP_FPDS_NONDOD"
        return "NO_FPDS_CODING"
    return "INDETERMINATE"


def enrich_cohort_with_signals(
    cohort: list[dict],
    digest: dict[str, dict],
    ma_signals: dict[str, dict],
    form_d_signals: dict[str, dict],
) -> list[dict]:
    """Attach transition signal channels and deficiency classification to cohort rows."""
    enriched = []
    for row in cohort:
        r = dict(row)
        uei = r.get("uei", "")
        company_upper = r.get("company", "").upper()

        dig = digest.get(uei, {})
        r["digest_found"] = bool(dig)
        r["sig_fpds_phase3_coded"] = dig.get("has_fy_phase3", False)
        r["sig_fpds_phase3_awards_n"] = dig.get("phase3_awards_n", 0)
        r["sig_fpds_phase3_usd"] = dig.get("phase3_total_usd", 0.0)
        r["sig_any_federal_obligation"] = (
            dig.get("fy_contracts_in_fpds", 0) > 0 or dig.get("fy_grants_in_fabs", 0) > 0
        )

        ma = ma_signals.get(company_upper, {})
        # Require a positive signal_count so empty enrichment rows don't inflate.
        r["sig_ma_detected"] = bool(ma) and int(ma.get("ma_signal_count") or 0) > 0
        r["sig_ma_confidence"] = ma.get("ma_confidence", "") if r["sig_ma_detected"] else ""
        r["sig_ma_high_conf"] = r["sig_ma_confidence"] == "high"
        r["sig_ma_medium_high"] = r["sig_ma_confidence"] in ("medium", "high")
        r["sig_ma_event_date"] = ma.get("ma_event_date", "") if r["sig_ma_detected"] else ""
        r["sig_ma_acquirer"] = ma.get("ma_acquirer", "") if r["sig_ma_detected"] else ""

        fd = form_d_signals.get(company_upper, {})
        r["sig_form_d_detected"] = bool(fd)
        r["sig_form_d_total_raised"] = fd.get("form_d_total_raised", 0.0)
        r["sig_form_d_latest_date"] = fd.get("form_d_latest_date", "")

        r["sig_any_positive"] = any(
            [
                r["sig_fpds_phase3_coded"],
                r["sig_any_federal_obligation"],
                r["sig_ma_detected"],
                r["sig_form_d_detected"],
            ]
        )

        # FPDS-deficiency taxonomy; clear when other channels are positive so
        # dark-majority buckets aren't labeled "activity absent" for Form D+ firms.
        if r["sig_fpds_phase3_coded"]:
            r["deficiency_class"] = ""
        elif r["sig_any_positive"]:
            r["deficiency_class"] = "SUPPLEMENTED_BY_OTHER_CHANNEL"
        else:
            r["deficiency_class"] = classify_deficiency(r)

        enriched.append(r)
    return enriched


def missing_signal_artifacts(
    repo: Path,
    digest: Path | None = None,
    ma: Path | None = None,
    form_d: Path | None = None,
) -> list[str]:
    """Return relative paths of required signal inputs that are absent."""
    absent = []
    for label, path in [
        ("prospect_digest", repo / (digest or DEFAULT_DIGEST)),
        ("ma_enrichment", repo / (ma or DEFAULT_MA)),
        ("form_d_high_conf", repo / (form_d or DEFAULT_FORM_D)),
    ]:
        del label
        if not path.exists():
            try:
                absent.append(str(path.relative_to(repo)))
            except ValueError:
                absent.append(str(path))
    return absent


def enrich_from_artifacts(
    cohort: list[dict],
    repo: Path,
    *,
    require_signals: bool = False,
) -> tuple[list[dict], list[str], dict | None]:
    """Load global signal artifacts and enrich. Returns (rows, absent, channel_summary)."""
    digest_path = repo / DEFAULT_DIGEST
    ma_path = repo / DEFAULT_MA
    fd_path = repo / DEFAULT_FORM_D
    absent = missing_signal_artifacts(repo)
    if absent:
        if require_signals:
            raise FileNotFoundError(
                "Signal artifacts required for dark-majority enrichment but missing:\n  - "
                + "\n  - ".join(absent)
            )
        # Still attach empty-signal deficiency classes so WS scripts have a column.
        empty = enrich_cohort_with_signals(cohort, {}, {}, {})
        return empty, absent, None

    digest = load_phase3_digest(digest_path)
    ma = load_ma_signals(ma_path)
    fd = load_form_d_signals(fd_path)
    enriched = enrich_cohort_with_signals(cohort, digest, ma, fd)
    summary = {}
    for field, label in [
        ("sig_fpds_phase3_coded", "FPDS Phase III coded"),
        ("sig_any_federal_obligation", "Any federal obligation"),
        ("sig_ma_detected", "M&A detected"),
        ("sig_form_d_detected", "Form D (high-conf)"),
        ("sig_any_positive", "Union (any)"),
    ]:
        n = sum(1 for r in enriched if r.get(field))
        pct = 100.0 * n / max(1, len(enriched))
        summary[label] = f"{n:,} ({pct:.1f}%)"
    return enriched, [], summary
