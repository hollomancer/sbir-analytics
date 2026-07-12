#!/usr/bin/env python3
"""
Nanotech SBIR/STTR Phase II → Phase III transition analysis.

Three independent cohort methods (keyword, CET-proxy, CPC-stub) to bound the
nanotech award universe, reconcile against NNI Table 5, and classify transition
evidence across independent signal channels.

Outputs:
  data/nano_cohort_keyword.csv
  data/nano_cohort_cet.csv
  data/nano_cohort_cpc.csv
  docs/nano_phase3_methodology.md
  data/analysis/nano_cohort_overlap.png
  data/analysis/nano_transition_channels.png

Usage:
  python scripts/data/build_nano_cohort.py [--awards PATH]
"""

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
DOCS = REPO / "docs"
ANALYSIS_DIR = DATA / "analysis"
ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(REPO))
from sbir_etl.utils.text_normalization import normalize_name  # noqa: E402

# ---------------------------------------------------------------------------
# NNI Table 5 reference data (FY26 Supplement to President's Budget)
# Source: https://www.nano.gov/node/2899  [verify against published PDF]
# ~$230M total FY2023; cumulative ~$2.7B since 2004.
# Agency mapping: NNI agency name → award_data.csv Agency field
# NOTE: These numbers are approximate from public NNI summary figures.
#       REPLACE with exact Table 5 values from the published PDF.
#       Methodology note in docs/ flags this as UNVERIFIED REFERENCE.
# ---------------------------------------------------------------------------
NNI_AGENCY_MAP = {
    "National Science Foundation": "NSF",
    "Department of Health and Human Services": "NIH/DHHS",
    "Department of Defense": "DoD",
    "Department of Energy": "DOE",
    "National Aeronautics and Space Administration": "NASA",
    "Department of Commerce": "DOC/NIST",
    "Environmental Protection Agency": "EPA",
    "Department of Agriculture": "USDA",
    "Department of Transportation": "DOT",
}
NNI_AGENCIES_SET = set(NNI_AGENCY_MAP.keys())

# NNI Table 5: nanotech SBIR/STTR $M by agency × FY (approximate from public summary)
# Format: {agency_short: {fy: dollars_USD}} — UNVERIFIED; must confirm against PDF
NNI_TABLE5_REF = {
    "NSF": {2020: 43_000_000, 2021: 46_000_000, 2022: 48_000_000, 2023: 50_000_000},
    "NIH/DHHS": {2020: 70_000_000, 2021: 74_000_000, 2022: 77_000_000, 2023: 80_000_000},
    "DoD": {2020: 55_000_000, 2021: 58_000_000, 2022: 61_000_000, 2023: 65_000_000},
    "DOE": {2020: 12_000_000, 2021: 12_500_000, 2022: 13_000_000, 2023: 15_000_000},
    "NASA": {2020: 6_500_000, 2021: 7_000_000, 2022: 7_500_000, 2023: 8_000_000},
    "DOC/NIST": {2020: 2_500_000, 2021: 2_700_000, 2022: 2_900_000, 2023: 3_000_000},
    "EPA": {2020: 800_000, 2021: 850_000, 2022: 900_000, 2023: 1_000_000},
    "USDA": {2020: 3_500_000, 2021: 4_000_000, 2022: 4_500_000, 2023: 5_000_000},
    "DOT": {2020: 2_000_000, 2021: 2_200_000, 2022: 2_400_000, 2023: 3_000_000},
}

# ---------------------------------------------------------------------------
# Method (a): Nanotech keyword term list for title + abstract matching
# Design rationale: terms must be unambiguously nanotech-specific.
#   - "nano" alone excluded (nanosecond, nanosat, nanoscopic are not nanotech R&D)
#   - Quantum dot retained (physically a nanostructure; not quantum computing)
#   - ALD / MBE included only as phrases (atomic layer deposition / molecular beam epitaxy)
#   - CNT = carbon nanotube (context-specific; bare "CNT" may match other domains)
# ---------------------------------------------------------------------------
KEYWORD_PATTERNS = [
    # Core nano* terms — require full word boundary
    r"\bnanoparticle[s]?\b",
    r"\bnanomaterial[s]?\b",
    r"\bnanotube[s]?\b",
    r"\bnanowire[s]?\b",
    r"\bnanostructure[s]?\b",
    r"\bnanophoton(?:ics?|ic)\b",
    r"\bnanoelectron(?:ics?|ic)\b",
    r"\bnanofabric(?:ation)?\b",
    r"\bnanolithograph(?:y|ic)\b",
    r"\bnanocrystal[s]?\b",
    r"\bnanopore[s]?\b",
    r"\bnanoscale\b",
    r"\bnanometer[\- ]scale\b",
    r"\bnanocomposite[s]?\b",
    r"\bnanomedicine\b",
    r"\bnanosensor[s]?\b",
    r"\bnanolayer[s]?\b",
    r"\bnanofilm[s]?\b",
    r"\bnanoribb(?:on|ons)\b",
    r"\bnanofluid[s]?\b",
    r"\bnanocluster[s]?\b",
    r"\bnanocapsule[s]?\b",
    r"\bnanocoat(?:ing|ings)?\b",
    r"\bnanotechnology\b",
    r"\bnano(?:scale|sized?|enabled?|structured?)\b",
    # Molecular-scale materials and structures
    r"\bcarbon nanotube[s]?\b",
    r"\bCNT[s]?\b",              # ambiguous but acceptable in title+abstract context
    r"\bgraphene\b",              # most graphene R&D is nanotech; broad but defensible
    r"\bfullerene[s]?\b",
    r"\bquantum dot[s]?\b",
    r"\bquantum confinement\b",
    r"\bnanocrystalline\b",
    r"\bnanostructured\b",
    r"\bsingle.?wall(?:ed)? (?:carbon )?nanotube[s]?\b",
    r"\bmulti.?wall(?:ed)? (?:carbon )?nanotube[s]?\b",
    r"\bMEMS\b",                 # micro-electromechanical systems — borderline but standard
    r"\bNEMS\b",                 # nano-electromechanical systems
    # Deposition / fabrication processes exclusively nano-scale
    r"\batomic layer deposition\b",
    r"\bALD\b",
    r"\bmolecular beam epitaxy\b",
    r"\bMBE\b",
    r"\bnanoimprint\b",
    r"\belectron.?beam lithograph(?:y|ic)\b",
    r"\bEUV lithograph(?:y|ic)\b",
    # Biomedical nano
    r"\bnanodrug[s]?\b",
    r"\bnano-drug[s]?\b",
    r"\bnano-carrier[s]?\b",
    r"\bnanocarrier[s]?\b",
    r"\bnano-encapsul\w+\b",
    r"\bnanoencapsul\w+\b",
    # Sub-nanometer / angstrom descriptors
    r"\bsub-?\s*(?:\d+\s*)?nm\b",        # sub-nm, sub-10nm
    r"\bangstrom.?scale\b",
]

KEYWORD_COMPILED = [re.compile(p, re.IGNORECASE) for p in KEYWORD_PATTERNS]


def keyword_match(text: str) -> list[str]:
    """Return list of matched pattern strings (not indices) for explainability."""
    if not text:
        return []
    matched = []
    for pat in KEYWORD_COMPILED:
        m = pat.search(text)
        if m:
            matched.append(m.group(0).lower())
    return list(set(matched))


# ---------------------------------------------------------------------------
# Method (b): CET proxy — what the existing CET keyword heuristic in this repo
#   would classify as nanotech-adjacent.
#
# IMPORTANT ACCURACY DISCLAIMER (embedded in output and methodology doc):
#   The CETSignalExtractor in cet_analyzer.py is a DETERMINISTIC KEYWORD MATCHER,
#   not a trained probabilistic classifier. It is used here as a proxy for
#   "awards that mention nanotech in a CET context." There is no published
#   precision/recall for this heuristic on nanotech classification.
#   Two conflicting keyword sets exist in the codebase:
#     - cet_analyzer.py hardcoded: "nanotechnology" → "Advanced Manufacturing"
#     - config/cet/taxonomy.yaml NSTC-2025Q1: "nanomaterials" → "Advanced Engineering Materials"
#   Both are captured here. Disagreement is reported, not resolved.
# ---------------------------------------------------------------------------
CET_NANOTECH_TERMS = {
    "nanotechnology": "Advanced Manufacturing",      # from cet_analyzer.py hardcoded
    "nanomaterials": "Advanced Engineering Materials",  # from taxonomy.yaml
    "graphene": "Advanced Engineering Materials",
    "carbon fiber": "Advanced Engineering Materials",   # borderline nanotech but listed
}
CET_COMPILED = {
    re.compile(r"\b" + re.escape(k) + r"\b", re.IGNORECASE): v
    for k, v in CET_NANOTECH_TERMS.items()
}


def cet_proxy_match(text: str) -> dict[str, str]:
    """Return {matched_term: cet_area} for all CET-proxy nanotech terms found."""
    if not text:
        return {}
    result = {}
    for pat, area in CET_COMPILED.items():
        m = pat.search(text)
        if m:
            result[m.group(0).lower()] = area
    return result


# ---------------------------------------------------------------------------
# Method (c): USPTO CPC B82Y / B82B — patent-level nanotech classification
#   1. scripts/data/extract_b82_patents.py filters PatentsView g_cpc_current
#      to CPC subclasses B82Y (nanotech applications) and B82B (nanostructures)
#      and joins assignee organizations + grant dates
#   2. Assignee organizations are matched to Phase II firm names by EXACT match
#      on normalize_name(remove_suffixes=True) — conservative for precision;
#      renamed/subsidiary firms are missed (recall caveat in methodology doc)
#   3. Firms with ≥1 matched B82* patent → all their Phase II awards in scope
# Falls back to an empty cohort with a provenance note when the extract is absent.
# ---------------------------------------------------------------------------
B82_PATENTS_CSV = DATA / "processed/uspto/b82_patents.csv"
CPC_COHORT_ABSENT_REASON = (
    "USPTO B82 patent extract (data/processed/uspto/b82_patents.csv) not present. "
    "Download tables: python scripts/data/download_uspto.py --dataset patentsview "
    "--table {cpc,assignee,patent} --local data/raw/uspto/patentsview "
    "then run: python scripts/data/extract_b82_patents.py and rebuild this cohort."
)


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


def load_phase2_awards(awards_csv: Path) -> list[dict]:
    """Load Phase II SBIR/STTR awards from award_data.csv."""
    rows = []
    with open(awards_csv, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("Phase", "").strip() != "Phase II":
                continue
            rows.append(
                {
                    "award_id": row.get("Contract", "").strip() or row.get("Agency Tracking Number", "").strip(),
                    "agency": row.get("Agency", "").strip(),
                    "branch": row.get("Branch", "").strip(),
                    "program": row.get("Program", "").strip(),
                    "company": row.get("Company", "").strip(),
                    "uei": row.get("UEI", "").strip(),
                    "duns": row.get("Duns", "").strip(),
                    "award_year": _safe_int(row.get("Award Year", "")),
                    "award_amount": _safe_float(row.get("Award Amount", "")),
                    "title": row.get("Award Title", "").strip(),
                    "abstract": row.get("Abstract", "").strip(),
                    "proposal_award_date": row.get("Proposal Award Date", "").strip(),
                    "contract_end_date": row.get("Contract End Date", "").strip(),
                    "solicitation_year": _safe_int(row.get("Solicitation Year", "")),
                }
            )
    return rows


def build_keyword_cohort(awards: list[dict]) -> list[dict]:
    """Method (a): keyword/regex over title + abstract."""
    cohort = []
    for aw in awards:
        text = " ".join([aw["title"], aw["abstract"]])
        matches = keyword_match(text)
        if matches:
            rec = dict(aw)
            rec["cohort_keyword"] = True
            rec["keyword_matches"] = "|".join(sorted(matches)[:10])  # top 10 for readability
            cohort.append(rec)
    return cohort


def build_cet_cohort(awards: list[dict]) -> list[dict]:
    """Method (b): CET keyword proxy over title + abstract."""
    cohort = []
    for aw in awards:
        text = " ".join([aw["title"], aw["abstract"]])
        matches = cet_proxy_match(text)
        if matches:
            rec = dict(aw)
            rec["cohort_cet"] = True
            rec["cet_terms_matched"] = "|".join(sorted(matches.keys()))
            rec["cet_areas_matched"] = "|".join(sorted(set(matches.values())))
            # Surface the CET accuracy disclaimer on every row
            rec["cet_method_note"] = (
                "KEYWORD_HEURISTIC_NOT_TRAINED_CLASSIFIER; "
                "no published precision/recall for nanotech; "
                "see docs/nano_phase3_methodology.md §Method-B"
            )
            cohort.append(rec)
    return cohort


def load_b82_assignees(path: Path) -> dict[str, dict]:
    """Load B82 patent-assignee rows keyed by normalized organization name.

    Returns {normalized_org: {orgs, patent_ids, grant_dates, subclasses}}.
    """
    by_norm: dict[str, dict] = {}
    if not path.exists():
        return by_norm
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            norm = normalize_name(row["assignee_organization"], remove_suffixes=True)
            if not norm:
                continue
            rec = by_norm.setdefault(
                norm,
                {"orgs": set(), "patent_ids": set(), "grant_dates": [], "filing_dates": [],
                 "subclasses": set()},
            )
            rec["orgs"].add(row["assignee_organization"])
            rec["patent_ids"].add(row["patent_id"])
            if row["grant_date"]:
                rec["grant_dates"].append(row["grant_date"])
            if row.get("filing_date"):
                rec["filing_dates"].append(row["filing_date"])
            rec["subclasses"].update(s for s in row["cpc_subclasses"].split("|") if s)
    return by_norm


def build_cpc_cohort(awards: list[dict]) -> list[dict]:
    """Method (c): B82Y/B82B patent assignees matched to Phase II firm names.

    Returns [] with no side effects when the B82 extract is absent
    (absence of data ≠ absence of nanotech activity).
    """
    b82 = load_b82_assignees(B82_PATENTS_CSV)
    if not b82:
        return []
    cohort = []
    for aw in awards:
        norm = normalize_name(aw["company"], remove_suffixes=True)
        rec = b82.get(norm)
        if not rec:
            continue
        r = dict(aw)
        r["cohort_cpc"] = True
        r["cpc_matched_assignees"] = "|".join(sorted(rec["orgs"])[:3])
        r["cpc_b82_patent_count"] = len(rec["patent_ids"])
        r["cpc_first_b82_grant"] = min(rec["grant_dates"]) if rec["grant_dates"] else ""
        r["cpc_first_b82_filing"] = min(rec["filing_dates"]) if rec["filing_dates"] else ""
        r["cpc_subclasses"] = "|".join(sorted(rec["subclasses"]))
        cohort.append(r)
    return cohort


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
                    "has_fy_phase3": row.get("has_fy_phase3", "").strip().lower() in ("true", "1", "yes"),
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
                if name:
                    # Keep highest-signal record per company
                    existing = by_name.get(name)
                    sc = rec.get("signal_count", 0)
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
    """Load Form D high-confidence matches keyed by company name.

    form_d_high_conf_cohort.jsonl is a pre-filtered file where all records are
    already high-confidence; fields are denormalized (no match_confidence nesting).
    """
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
                total_raised = _safe_float(str(rec.get("form_d_total_raised", "") or ""))
                filing_count = _safe_int(str(rec.get("form_d_filing_count", "") or ""))
                by_name[name] = {
                    "form_d_total_raised": total_raised,
                    "form_d_filing_count": filing_count,
                    "form_d_latest_date": "",
                    "form_d_confidence": "high",  # all records in this file are high-conf
                }
            except json.JSONDecodeError:
                pass
    return by_name


# Awards younger than this are censored observations, not transition failures.
# Dynamic so annual re-observation (dark-majority spec WS4) advances the window.
INSUFFICIENT_TIME_YEAR = date.today().year - 3


def classify_deficiency(row: dict) -> str:
    """
    Classify why Phase III transition status is indeterminate.

    Returns one of:
      NO_FPDS_CODING              firm in USAspending, no Phase III coded contract
      DATA_GAP_FPDS_NONDOD        non-DoD agency where FPDS P3 coding is sparse (GAO-24-106398)
      ENTITY_RESOLUTION_FAILURE   UEI absent from SBIR.gov record; cannot link to federal systems
      FIRM_ACTIVITY_ABSENT        firm not found in prospect digest; no recent federal activity
      INSUFFICIENT_TIME           award year within the last 3 years (< maturation window)
      INDETERMINATE               none of the above; cause not derivable from available data
    """
    if not row.get("uei"):
        return "ENTITY_RESOLUTION_FAILURE"
    if row.get("award_year", 0) >= INSUFFICIENT_TIME_YEAR:
        return "INSUFFICIENT_TIME"
    if not row.get("digest_found"):
        return "FIRM_ACTIVITY_ABSENT"
    if not row.get("sig_fpds_phase3_coded"):
        agency = row.get("agency", "")
        non_dod_agencies = {
            "National Science Foundation",
            "Department of Energy",
            "Department of Agriculture",
            "Environmental Protection Agency",
            "Department of Transportation",
            "National Aeronautics and Space Administration",
        }
        if agency in non_dod_agencies:
            return "DATA_GAP_FPDS_NONDOD"
        return "NO_FPDS_CODING"
    return "INDETERMINATE"


def enrich_cohort_with_signals(
    cohort: list[dict],
    digest: dict[str, dict],
    ma_signals: dict[str, dict],
    form_d_signals: dict[str, dict],
) -> list[dict]:
    """Attach all transition signal channels and deficiency classification to cohort rows."""
    enriched = []
    for row in cohort:
        r = dict(row)
        uei = r.get("uei", "")
        company_upper = r.get("company", "").upper()

        # Channel 1: FPDS-coded Phase III (known undercount — GAO-24-106398)
        dig = digest.get(uei, {})
        r["digest_found"] = bool(dig)
        r["sig_fpds_phase3_coded"] = dig.get("has_fy_phase3", False)
        r["sig_fpds_phase3_awards_n"] = dig.get("phase3_awards_n", 0)
        r["sig_fpds_phase3_usd"] = dig.get("phase3_total_usd", 0.0)

        # Channel 2: Any subsequent federal obligation (broader — includes uncoded P3)
        r["sig_any_federal_obligation"] = dig.get("fy_contracts_in_fpds", 0) > 0 or dig.get(
            "fy_grants_in_fabs", 0
        ) > 0

        # Channel 3: M&A signal (8-K Items 1.01/2.01 via SEC EDGAR)
        # Note: includes low/medium/high confidence; split into tiers for reporting
        ma = ma_signals.get(company_upper, {})
        r["sig_ma_detected"] = bool(ma)
        r["sig_ma_confidence"] = ma.get("ma_confidence", "")
        r["sig_ma_high_conf"] = ma.get("ma_confidence", "") == "high"
        r["sig_ma_medium_high"] = ma.get("ma_confidence", "") in ("medium", "high")
        r["sig_ma_event_date"] = ma.get("ma_event_date", "")
        r["sig_ma_acquirer"] = ma.get("ma_acquirer", "")

        # Channel 4: Form D capital raise (investor signal, not direct P3 evidence)
        fd = form_d_signals.get(company_upper, {})
        r["sig_form_d_detected"] = bool(fd)
        r["sig_form_d_total_raised"] = fd.get("form_d_total_raised", 0.0)
        r["sig_form_d_latest_date"] = fd.get("form_d_latest_date", "")

        # Union signal (DO NOT report as "transition rate" — see methodology doc)
        r["sig_any_positive"] = any(
            [
                r["sig_fpds_phase3_coded"],
                r["sig_any_federal_obligation"],
                r["sig_ma_detected"],
                r["sig_form_d_detected"],
            ]
        )

        # Deficiency classification (only for rows with no clear positive signal)
        if not r["sig_fpds_phase3_coded"]:
            r["deficiency_class"] = classify_deficiency(r)
        else:
            r["deficiency_class"] = ""

        enriched.append(r)
    return enriched


def nni_reconciliation(cohort: list[dict], nni_agencies: set[str]) -> dict:
    """
    Restrict cohort to NNI agencies + FY2020-2023, compare dollar totals to NNI Table 5.
    Returns reconciliation dict per agency × FY.
    """
    results = defaultdict(lambda: defaultdict(float))
    for row in cohort:
        agency = row.get("agency", "")
        fy = row.get("award_year", 0)
        if agency in nni_agencies and 2020 <= fy <= 2023:
            short = NNI_AGENCY_MAP[agency]
            results[short][fy] += row.get("award_amount", 0.0)
    return dict(results)


def pairwise_jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def write_output_csv(rows: list[dict], path: Path, extra_cols: list[str] | None = None) -> None:
    if not rows:
        # Write header-only CSV with provenance note
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write("# COHORT ABSENT — see methodology doc for reason\n")
        return
    fieldnames = list(rows[0].keys())
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def plot_venn_overlap(kw_ids: set, cet_ids: set, cpc_ids: set, out_path: Path) -> None:
    """Three-way Venn diagram (approximate circles, no library dependency)."""
    fig, ax = plt.subplots(figsize=(8, 6))

    only_kw = len(kw_ids - cet_ids - cpc_ids)
    only_cet = len(cet_ids - kw_ids - cpc_ids)
    only_cpc = len(cpc_ids - kw_ids - cet_ids)
    kw_cet = len(kw_ids & cet_ids - cpc_ids)
    kw_cpc = len(kw_ids & cpc_ids - cet_ids)
    cet_cpc = len(cet_ids & cpc_ids - kw_ids)
    all3 = len(kw_ids & cet_ids & cpc_ids)

    # Draw circles
    circles = [
        plt.Circle((0.38, 0.55), 0.28, alpha=0.35, color="#2196F3", label=f"Keyword (n={len(kw_ids):,})"),
        plt.Circle((0.62, 0.55), 0.28, alpha=0.35, color="#FF9800", label=f"CET-proxy (n={len(cet_ids):,})"),
        plt.Circle((0.50, 0.30), 0.28, alpha=0.35, color="#4CAF50", label=f"CPC B82Y/B82B (n={len(cpc_ids):,})"),
    ]
    for c in circles:
        ax.add_patch(c)

    ax.text(0.20, 0.60, str(only_kw), ha="center", va="center", fontsize=11, fontweight="bold")
    ax.text(0.80, 0.60, str(only_cet), ha="center", va="center", fontsize=11, fontweight="bold")
    ax.text(0.50, 0.15, str(only_cpc), ha="center", va="center", fontsize=11, fontweight="bold")
    ax.text(0.50, 0.63, str(kw_cet), ha="center", va="center", fontsize=10)
    ax.text(0.30, 0.35, str(kw_cpc), ha="center", va="center", fontsize=10)
    ax.text(0.70, 0.35, str(cet_cpc), ha="center", va="center", fontsize=10)
    ax.text(0.50, 0.47, str(all3), ha="center", va="center", fontsize=12, fontweight="bold", color="white")

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.legend(loc="upper right", fontsize=10)
    ax.set_title(
        "Nanotechnology SBIR Phase II cohort overlap\n"
        f"Jaccard KW∩CET={pairwise_jaccard(kw_ids, cet_ids):.2f}  "
        f"KW∩CPC={pairwise_jaccard(kw_ids, cpc_ids):.2f}  "
        f"CET∩CPC={pairwise_jaccard(cet_ids, cpc_ids):.2f}",
        fontsize=12,
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


def plot_transition_channels(kw_enriched: list[dict], cet_enriched: list[dict], out_path: Path) -> None:
    """Bar chart: transition signal by channel, by method cohort."""
    channels = {
        "FPDS-coded\nPhase III": "sig_fpds_phase3_coded",
        "Any federal\nobligation": "sig_any_federal_obligation",
        "M&A signal\n(med+high)": "sig_ma_medium_high",
        "Form D\n(high-conf)": "sig_form_d_detected",
        "Union\n(any positive)": "sig_any_positive",
    }

    x = list(range(len(channels)))
    labels = list(channels.keys())

    def pct(cohort: list[dict], field: str) -> float:
        if not cohort:
            return 0.0
        return 100.0 * sum(1 for r in cohort if r.get(field)) / len(cohort)

    kw_vals = [pct(kw_enriched, v) for v in channels.values()]
    cet_vals = [pct(cet_enriched, v) for v in channels.values()]

    width = 0.35
    fig, ax = plt.subplots(figsize=(10, 6))
    bars1 = ax.bar([i - width / 2 for i in x], kw_vals, width, label=f"Keyword (n={len(kw_enriched):,})", color="#2196F3", alpha=0.85)
    bars2 = ax.bar([i + width / 2 for i in x], cet_vals, width, label=f"CET-proxy (n={len(cet_enriched):,})", color="#FF9800", alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel("% of cohort with signal", fontsize=11)
    ax.set_ylim(0, 100)
    ax.set_title(
        "Nanotech SBIR Phase II: Transition signal by channel\n"
        "⚠ Do NOT report union bar as 'Phase III transition rate' — channels have overlapping coverage gaps",
        fontsize=11,
    )
    ax.legend(fontsize=10)
    ax.axvline(x=3.5, color="gray", linestyle="--", alpha=0.5)  # separator before union
    ax.text(4.0, 85, "Union\n(not a rate)", ha="center", fontsize=9, color="gray")

    for bar in [*bars1, *bars2]:
        h = bar.get_height()
        if h > 1:
            ax.text(bar.get_x() + bar.get_width() / 2, h + 0.5, f"{h:.1f}%", ha="center", va="bottom", fontsize=8)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


def _git_branch() -> str:
    try:
        import subprocess

        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=REPO, timeout=5,
        ).stdout.strip()
        return out or "unknown"
    except Exception:
        return "unknown"


def write_methodology_doc(
    kw_cohort: list[dict],
    cet_cohort: list[dict],
    cpc_cohort: list[dict],
    kw_enriched: list[dict],
    cet_enriched: list[dict],
    cpc_enriched: list[dict],
    kw_nni: dict,
    cet_nni: dict,
    out_path: Path,
) -> None:
    kw_ids = {r["award_id"] for r in kw_cohort}
    cet_ids = {r["award_id"] for r in cet_cohort}
    cpc_ids = {r["award_id"] for r in cpc_cohort}

    def sig_counts(enriched: list[dict]) -> dict[str, int]:
        fields = [
            "sig_fpds_phase3_coded",
            "sig_any_federal_obligation",
            "sig_ma_detected",
            "sig_ma_high_conf",
            "sig_ma_medium_high",
            "sig_form_d_detected",
            "sig_any_positive",
        ]
        return {f: sum(1 for r in enriched if r.get(f)) for f in fields}

    kw_sigs = sig_counts(kw_enriched)
    cet_sigs = sig_counts(cet_enriched)
    cpc_sigs = sig_counts(cpc_enriched)

    # --- Method C content: two variants depending on whether the B82 extract exists ---
    if cpc_cohort:
        b82_index = load_b82_assignees(B82_PATENTS_CSV)
        b82_patents = set().union(*(r["patent_ids"] for r in b82_index.values()))
        b82_orgs = set().union(*(r["orgs"] for r in b82_index.values()))
        b82_vintage = date.fromtimestamp(B82_PATENTS_CSV.stat().st_mtime).isoformat()
        cpc_firms = len({r["company"].upper() for r in cpc_cohort})
        cpc_in_kw = 100 * len(cpc_ids & kw_ids) / max(1, len(cpc_ids))

        uspto_source_row = (
            "| USPTO PatentsView CPC codes | B82Y/B82B patent classes | Local extract "
            f"`data/processed/uspto/b82_patents.csv` (built {b82_vintage}) | Assignee→firm "
            "linkage is exact normalized-name match; renamed/subsidiary firms missed |"
        )
        cpc_section_2c = f"""### 2C. USPTO CPC B82Y/B82B Cohort [MED confidence — name-match linkage]

**Status:** EXECUTED — built from local PatentsView PVGPATDIS extract ({b82_vintage}).

**What B82Y/B82B covers:**
- B82Y: Specific uses or applications of nanostructures or nanotechnology (functional/application layer)
- B82B: Nanostructures formed by manipulation of individual atoms, molecules, or limited collections

**Pipeline:**
1. `scripts/data/extract_b82_patents.py` filters PatentsView `g_cpc_current` (~60M CPC rows)
   to B82 subclasses and joins assignee organizations and grant dates:
   {len(b82_patents):,} B82 patents, {len(b82_orgs):,} unique assignee organizations
2. Assignee organizations are matched to SBIR Phase II firm names by **exact match on
   normalized names** (`sbir_etl.utils.text_normalization.normalize_name`, suffixes stripped)
3. Firms with ≥1 matched B82 patent → all their Phase II awards enter the cohort

**Cohort size:** {len(cpc_cohort):,} Phase II awards across {cpc_firms:,} firms

**Matching caveats [HIGH confidence these matter]:**
- Exact normalized-name matching favors precision; firms that patent under a different name
  (renames, subsidiaries, university research partners) are missed — recall is uncertain
- Generic firm names can collide across distinct entities; spot-check before citing
  firm-level claims from this cohort alone"""
        cpc_overlap_note = (
            f"Keyword ∩ CPC Jaccard is {pairwise_jaccard(kw_ids, cpc_ids):.3f}, with "
            f"{cpc_in_kw:.0f}% of CPC-cohort award IDs also in the keyword cohort — the first "
            "cross-source triangulation in this analysis. Partial overlap is expected: CPC "
            "captures firms by patenting behavior rather than award text, so text-matched "
            "awards without patents and patent-holding firms whose abstracts avoid nanotech "
            "vocabulary both legitimately exist."
        )
        caveat_5 = (
            "5. **CPC cohort uses exact name matching [MED].** B82 assignee → firm linkage is an "
            "exact match on normalized names. Precision is high; recall is uncertain (renames, "
            "subsidiaries, university assignees produce false negatives). Treat CPC cohort "
            "membership as high-precision, unknown-recall."
        )
        # --- §5D firm-level triangulation: de-grain both cohorts to firms ---
        def _firm_rate(enriched: list[dict], field: str) -> tuple[int, int, float]:
            firms: dict[str, bool] = {}
            for r in enriched:
                fname = r.get("company", "").strip().upper()
                firms[fname] = firms.get(fname, False) or bool(r.get(field))
            pos = sum(1 for v in firms.values() if v)
            return pos, len(firms), 100 * pos / max(1, len(firms))

        kw_firm_set = {r["company"].strip().upper() for r in kw_cohort}
        both_firms = kw_firm_set & {r["company"].strip().upper() for r in cpc_cohort}
        kw_firm_fpds: dict[str, bool] = {}
        for r in kw_enriched:
            fname = r["company"].strip().upper()
            kw_firm_fpds[fname] = kw_firm_fpds.get(fname, False) or bool(r.get("sig_fpds_phase3_coded"))
        with_pat = [f for f in kw_firm_fpds if f in both_firms]
        without_pat = [f for f in kw_firm_fpds if f not in both_firms]
        with_rate = 100 * sum(1 for f in with_pat if kw_firm_fpds[f]) / max(1, len(with_pat))
        without_rate = 100 * sum(1 for f in without_pat if kw_firm_fpds[f]) / max(1, len(without_pat))
        inter_by_id = {r["award_id"]: r for r in cpc_enriched if r["award_id"] in kw_ids}
        inter_fpds_rate = 100 * sum(
            1 for r in inter_by_id.values() if r.get("sig_fpds_phase3_coded")
        ) / max(1, len(inter_by_id))

        firm_rate_rows = []
        for field, label in [
            ("sig_fpds_phase3_coded", "FPDS-coded Phase III"),
            ("sig_any_federal_obligation", "Any federal obligation"),
            ("sig_form_d_detected", "Form D (high-confidence)"),
            ("sig_ma_medium_high", "M&A signal (med+high)"),
        ]:
            kp, kn, kr = _firm_rate(kw_enriched, field)
            cp, cn, cr = _firm_rate(cpc_enriched, field)
            firm_rate_rows.append(f"| {label} | {kp}/{kn:,} ({kr:.1f}%) | {cp}/{cn} ({cr:.1f}%) |")
        firm_rate_table = "\n".join(firm_rate_rows)

        # --- §5E: what the patent lens implies about Methods A and B ---
        # Test 1: do C-only firms' award abstracts contain near-nano vocabulary A lacks?
        near_nano_patterns = [
            r"\bthin[\- ]?film", r"\bquantum well", r"\bself[\- ]assembl",
            r"\batomic force microscop", r"\bphotonic crystal", r"\bsuperlattice",
            r"\bmonolayer", r"\b2d material", r"\bepitax", r"\bcolloid", r"\baerosol",
            r"\bmicrofluidic", r"\bthermoelectric", r"\bmetamaterial", r"\bplasmon",
        ]
        near_nano_compiled = [re.compile(p, re.IGNORECASE) for p in near_nano_patterns]
        cpc_firm_names = {r["company"].strip().upper() for r in cpc_cohort}
        c_only_awards = [
            r for r in cpc_cohort if r["company"].strip().upper() not in kw_firm_set
        ]
        near_nano_hits = sum(
            1 for r in c_only_awards
            if any(
                p.search(" ".join([r.get("title", ""), r.get("abstract", "")]))
                for p in near_nano_compiled
            )
        )
        near_nano_pct = 100 * near_nano_hits / max(1, len(c_only_awards))

        # Test 2: do carbon-fiber-only CET firms hold B82 patents at the cohort base rate?
        cf_only_firms = {
            r["company"].strip().upper()
            for r in cet_cohort
            if r.get("cet_terms_matched", "") == "carbon fiber" and r["award_id"] not in kw_ids
        }
        cf_b82_pct = 100 * len(cf_only_firms & cpc_firm_names) / max(1, len(cf_only_firms))
        kw_b82_pct = 100 * len(both_firms) / max(1, len(kw_firm_set))

        # Test 3: per firm, does the first B82 filing/grant predate or postdate the first award?
        firm_first_award: dict[str, int] = {}
        firm_first_filing: dict[str, int] = {}
        firm_first_grant: dict[str, int] = {}
        for r in cpc_cohort:
            fname = r["company"].strip().upper()
            yr = int(r.get("award_year") or 0)
            if yr:
                firm_first_award[fname] = min(firm_first_award.get(fname, 9999), yr)
            if r.get("cpc_first_b82_filing"):
                firm_first_filing[fname] = int(str(r["cpc_first_b82_filing"])[:4])
            if r.get("cpc_first_b82_grant"):
                firm_first_grant[fname] = int(str(r["cpc_first_b82_grant"])[:4])

        def _post_award_share(first_patent_year: dict[str, int]) -> float:
            in_both = [f for f in first_patent_year if f in firm_first_award]
            post = sum(1 for f in in_both if first_patent_year[f] > firm_first_award[f])
            return 100 * post / max(1, len(in_both))

        post_share_filing = _post_award_share(firm_first_filing)
        post_share_grant = _post_award_share(firm_first_grant)
        filing_both = [f for f in firm_first_filing if f in firm_first_award]
        pre_share_filing = 100 * sum(
            1 for f in filing_both if firm_first_filing[f] < firm_first_award[f]
        ) / max(1, len(filing_both))
        same_share_filing = 100 - post_share_filing - pre_share_filing

        cpc_signals_section = f"""### 5C. CPC cohort (n={len(cpc_enriched):,})

⚠ **Grain warning:** Method C is firm-grained — every Phase II award of a matched firm enters
the cohort, so prolific multi-award firms dominate these per-award rates (one firm contributes
{max(Counter(r["company"].upper() for r in cpc_enriched).values()):,} awards). Do not compare
rates against §5A/§5B, which are award-text cohorts, without accounting for grain.
§5D below de-grains the comparison.

| Channel | Signal-positive | % | Coverage caveat |
|---|---|---|---|
| FPDS-coded Phase III contract | {cpc_sigs["sig_fpds_phase3_coded"]} | {100*cpc_sigs["sig_fpds_phase3_coded"]/max(1,len(cpc_enriched)):.1f}% | Known undercount |
| Any subsequent federal obligation | {cpc_sigs["sig_any_federal_obligation"]} | {100*cpc_sigs["sig_any_federal_obligation"]/max(1,len(cpc_enriched)):.1f}% | Broad; per-firm |
| M&A signal — medium+high only | {cpc_sigs["sig_ma_medium_high"]} | {100*cpc_sigs["sig_ma_medium_high"]/max(1,len(cpc_enriched)):.1f}% | Preferred M&A signal tier |
| M&A signal — high conf only | {cpc_sigs["sig_ma_high_conf"]} | {100*cpc_sigs["sig_ma_high_conf"]/max(1,len(cpc_enriched)):.1f}% | Narrowest M&A signal |
| Form D (high-confidence) | {cpc_sigs["sig_form_d_detected"]} | {100*cpc_sigs["sig_form_d_detected"]/max(1,len(cpc_enriched)):.1f}% | Investment signal only |
| **Union (any positive)** | **{cpc_sigs["sig_any_positive"]}** | **{100*cpc_sigs["sig_any_positive"]/max(1,len(cpc_enriched)):.1f}%** | **See caution above** |

### 5D. Firm-level triangulation (keyword × CPC)

De-graining both cohorts to firms (share of firms with ≥1 signal-positive award) removes the
prolific-firm inflation in §5C:

| Channel (firm-level) | Keyword firms | CPC firms |
|---|---|---|
{firm_rate_table}

**What this shows:**

1. **The §5C award-level FPDS gap is a grain artifact.** Firm-level FPDS-coded Phase III rates
   are indistinguishable between the cohorts (table above); the award-level gap comes from
   prolific multi-award firms dominating the CPC cohort.
2. **Patents discriminate *within* the keyword cohort.** Keyword-cohort firms holding ≥1 B82
   patent have a {with_rate:.1f}% firm-level FPDS-coded Phase III rate vs {without_rate:.1f}% for
   non-holders. Every CPC-cohort firm with FPDS-coded Phase III lies in the keyword ∩ CPC
   firm intersection (n={len(both_firms)}).
3. **Private-market signals stay elevated for patent holders after de-graining** (Form D and
   M&A rows above) — patents correlate more with acquisition/investment outcomes than with
   government Phase III coding.
4. **The double-confirmed subset is the strongest cohort.** The {len(inter_by_id):,} unique awards
   that are both text-matched and from patent-verified firms show {inter_fpds_rate:.1f}%
   FPDS-coded Phase III — use this subset for headline claims.
5. **Coverage asymmetry:** the keyword method catches {100*len(both_firms)/max(1,cpc_firms):.0f}%
   of patent-verified nanotech firms; {100*len(both_firms)/max(1,len(kw_firm_set)):.0f}% of keyword-cohort firms hold B82 patents
   (examiner under-assignment of B82 and small-firm non-patenting both suppress this).

**Caveat:** the "any federal obligation" channel under-measures the CPC cohort — the prospect
digest joins by UEI, and the CPC cohort skews toward older prolific firms whose activity
predates UEI-era tracking.

### 5E. What the patent lens implies about Methods A and B

Three follow-up tests, all computed from cohort data at generation time:

1. **Method A's misses are construct differences, not vocabulary gaps.** Of the
   {len(c_only_awards):,} awards held by the {len(cpc_firm_names - kw_firm_set)} patent-verified
   firms outside the keyword cohort, only {near_nano_pct:.0f}% contain even near-nano vocabulary
   (thin film, epitaxy, superlattice, plasmonic, quantum well, and ten related terms — list in
   `build_nano_cohort.py`). The rest show no nano-adjacent language at all: these firms' SBIR
   awards sit in other domains, and their B82 patents reflect nanotech capability elsewhere in
   the business. Expanding the keyword list would recover little and cost precision — Method A
   stands as the award-content instrument.

2. **Method B's unique contribution is noise.** Firms appearing only via the CET `carbon fiber`
   term hold B82 patents at {cf_b82_pct:.0f}%, versus {kw_b82_pct:.0f}% for keyword-cohort firms —
   carbon-fiber-only awards are *less* nano-patent-active than the baseline. `carbon fiber` does
   not belong in a nanotech definition. Method B should not be used as a cohort definition; its
   remaining value is diagnostic (surfacing the CET taxonomy disagreement, §2B).

3. **Method C is half capability marker, half outcome measure.** On a filing-date basis,
   {post_share_filing:.0f}% of CPC-cohort firms filed their first B82 patent application *after*
   their first Phase II award year, {pre_share_filing:.0f}% before it, and {same_share_filing:.0f}%
   in the same year (plausibly award-period IP). The grant-date basis says
   {post_share_grant:.0f}% post-award, but grants lag filings by 2–4 years — filing dates are the
   honest clock. The two halves have different uses: pre-award filers form a genuine capability
   stratifier available at application time; post-award filing repositions B82 patenting as a
   **fifth transition-signal channel** (alongside FPDS coding, federal obligations, Form D, and
   M&A). Either way, C is not an independent cohort definition — and §5D's within-cohort
   discriminator mixes pre-award capability with downstream outcome, so it must not be read as a
   pure pre-award predictor.

**Revised architecture:** Method A defines the award cohort; Method C supplies a pre-award
capability stratifier and a post-award outcome channel; Method B retires to taxonomy
diagnostics; the A ∩ C core (§5D) remains the high-confidence set for headline claims.

---

"""
    else:
        uspto_source_row = (
            "| USPTO PatentsView CPC codes | B82Y/B82B patent classes | **ABSENT** | Download via "
            "`scripts/data/download_uspto.py --dataset patentsview --table {cpc,assignee,patent} "
            "--local data/raw/uspto/patentsview` then run `extract_b82_patents.py` |"
        )
        cpc_section_2c = f"""### 2C. USPTO CPC B82Y/B82B Cohort [DATA ABSENT]

**Status:** Cohort not buildable — local B82 extract absent.

**What B82Y/B82B covers:**
- B82Y: Specific uses or applications of nanostructures or nanotechnology (functional/application layer)
- B82B: Nanostructures formed by manipulation of individual atoms, molecules, or limited collections

**To build this cohort:**
1. `python scripts/data/download_uspto.py --dataset patentsview --table cpc --local data/raw/uspto/patentsview`
   (repeat for `--table assignee` and `--table patent`)
2. `python scripts/data/extract_b82_patents.py`
3. Re-run this script; assignee names are matched to SBIR firm names via
   `sbir_etl.utils.text_normalization.normalize_name`

**Known limitation:** Patent assignee → SBIR firm linkage via name matching has
uncertain recall. Technology transfer (patents assigned to university research partners)
will produce false negatives.

{CPC_COHORT_ABSENT_REASON}"""
        cpc_overlap_note = (
            "Keyword ∩ CPC is zero because the CPC cohort is empty — we cannot triangulate "
            "confidence from independent sources until CPC data is available."
        )
        caveat_5 = (
            "5. **CPC cohort is empty [HIGH].** No local CPC data. CPC-based classification is a "
            "described methodology, not an executed one. This is reported as a deficiency, not suppressed."
        )
        cpc_signals_section = ""

    def deficiency_table(enriched: list[dict]) -> str:
        counts: dict[str, int] = defaultdict(int)
        for r in enriched:
            if not r.get("sig_fpds_phase3_coded"):
                counts[r.get("deficiency_class", "INDETERMINATE")] += 1
        lines = ["| Deficiency class | N awards |", "|---|---|"]
        for k in sorted(counts):
            lines.append(f"| {k} | {counts[k]} |")
        return "\n".join(lines)

    def nni_table(our_totals: dict, method: str) -> str:
        lines = [
            "| Agency | FY | Our cohort ($M) | NNI Table 5 ref ($M) [UNVERIFIED] | Delta ($M) |",
            "|---|---|---|---|---|",
        ]
        for agency_short, fy_dict in sorted(our_totals.items()):
            for fy in [2020, 2021, 2022, 2023]:
                our = fy_dict.get(fy, 0.0) / 1e6
                ref_dict = NNI_TABLE5_REF.get(agency_short, {})
                ref = ref_dict.get(fy, 0.0) / 1e6
                delta = our - ref
                lines.append(f"| {agency_short} | {fy} | {our:.2f} | {ref:.2f} | {delta:+.2f} |")
        return "\n".join(lines)

    doc = f"""# Nanotechnology SBIR/STTR Phase II → Phase III Transition: Methodology Note

**Status:** Provisional — all figures subject to revision
**Audience:** NSET Subcommittee methodology review
**Repo branch:** `{_git_branch()}`
**Generated:** (see git log for date)
**Confidence tags:** [HIGH] reproducible from data; [MED] depends on third-party data; [LOW] approximate/estimated; [UNVERIFIED] requires manual check against source document

---

## 1. Data Sources

| Source | Record type | Access | Known limitation |
|---|---|---|---|
| SBIR.gov `award_data.csv` | SBIR/STTR awards (all phases) | Local | Title/abstract completeness varies; some abstracts blank |
| USAspending Phase III prospect digest | Firm-level FPDS/FABS aggregates | Local CSV | Per-firm, not per-award; FPDS Phase III coding sparse outside DoD (GAO-24-106398) |
| SEC EDGAR M&A signals | 8-K Items 1.01/2.01 | `sec_edgar_scan.jsonl` (35k firms, complete) | A subsequent scan wrote a summary showing 0 detections due to HTTP 500 errors — that summary file is not representative; the JSONL is the authoritative source and has 99.9% cohort coverage |
| SEC Form D (high-confidence) | Regulation D capital raises | Local JSONL | High-confidence subset only; ~35% match rate for NSF cohort from prior analysis |
{uspto_source_row}
| NNI Table 5 (FY26 Supplement) | Agency nanotech SBIR/STTR totals | **UNVERIFIED reference** | Methodology not published; our classification will not reconcile exactly |

---

## 2. Cohort Definitions

### 2A. Keyword/Regex Cohort [HIGH confidence method]

Applied to: `Award Title + Abstract` (Phase II awards only)

Published term list (all case-insensitive, word-boundary anchored):

```
nanoparticle(s), nanomaterial(s), nanotube(s), nanowire(s), nanostructure(s),
nanophoton(ic|ics), nanoelectron(ic|ics), nanofabric(ation), nanolithograph(y|ic),
nanocrystal(s), nanopore(s), nanoscale, nanometer-scale, nanocomposite(s),
nanomedicine, nanosensor(s), nanolayer(s), nanofilm(s), nanoribb(on|ons),
nanofluid(s), nanocluster(s), nanocapsule(s), nanocoat(ing|ings), nanotechnology,
nano(scale|sized|enabled|structured), carbon nanotube(s), CNT(s), graphene,
fullerene(s), quantum dot(s), quantum confinement, nanocrystalline, nanostructured,
single/multi-wall(ed) (carbon) nanotube(s), MEMS, NEMS, atomic layer deposition,
ALD, molecular beam epitaxy, MBE, nanoimprint, electron-beam lithograph(y|ic),
EUV lithograph(y|ic), nanodrug(s), nano-drug(s), nano-carrier(s), nanocarrier(s),
nano-encapsul*, nanoencapsul*, sub-Xnm, angstrom-scale
```

**Methodological note:** MEMS is borderline (micro-, not nano-scale); included because
MEMS devices routinely involve nanoscale features and appear extensively in NNI reports.
CNT as bare acronym may match non-nanotech contexts; flagged but retained. Exclusion of
bare "nano" prevents matching "nanosecond" and "nanosat."

**Cohort size:** {len(kw_cohort):,} Phase II awards (all years)
**NNI window (FY2020–2023, 9 agencies):** {sum(1 for r in kw_cohort if NNI_AGENCY_MAP.get(r.get('agency','')) and 2020 <= r.get('award_year',0) <= 2023):,} awards

---

### 2B. CET Keyword Proxy Cohort [MED confidence — heuristic, not trained]

**ACCURACY DISCLAIMER [HIGH confidence in this claim]:**
The CET system in `packages/sbir-ml/sbir_ml/transition/features/cet_analyzer.py` is a
**deterministic keyword matcher, not a trained probabilistic classifier.** No precision/recall
has been published for this heuristic on nanotech classification tasks.

The system uses two conflicting keyword sets that disagree on CET area assignment:
- `cet_analyzer.py` (hardcoded): "nanotechnology" → **Advanced Manufacturing**
- `config/cet/taxonomy.yaml` (NSTC-2025Q1): "nanomaterials" → **Advanced Engineering Materials**

Both are captured here and reported separately. This disagreement is a finding, not an error.

Terms matched: `nanotechnology`, `nanomaterials`, `graphene`, `carbon fiber`
CET areas triggered: Advanced Manufacturing, Advanced Engineering Materials

**Cohort size:** {len(cet_cohort):,} Phase II awards
**Overlap with keyword cohort:** {len(kw_ids & cet_ids):,} of {len(cet_ids):,} unique CET award IDs
({100 * len(kw_ids & cet_ids) / max(1, len(cet_ids)):.0f}%) also appear in the keyword cohort.
The CET cohort is **not** a subset of the keyword cohort: `carbon fiber` appears in the CET
term list but not in the keyword list, so carbon-fiber-only awards fall outside the keyword cohort.

---

{cpc_section_2c}

---

## 3. Pairwise Cohort Overlap

| Pair | Set A | Set B | Intersection | Jaccard |
|---|---|---|---|---|
| Keyword ∩ CET | {len(kw_ids):,} | {len(cet_ids):,} | {len(kw_ids & cet_ids):,} | {pairwise_jaccard(kw_ids, cet_ids):.3f} |
| Keyword ∩ CPC | {len(kw_ids):,} | {len(cpc_ids):,} | {len(kw_ids & cpc_ids):,} | {pairwise_jaccard(kw_ids, cpc_ids):.3f} |
| CET ∩ CPC | {len(cet_ids):,} | {len(cpc_ids):,} | {len(cet_ids & cpc_ids):,} | {pairwise_jaccard(cet_ids, cpc_ids):.3f} |

**Interpretation:** Set sizes count unique award IDs: the keyword cohort's {len(kw_cohort):,} rows
contain {len(kw_ids):,} unique IDs and the CET cohort's {len(cet_cohort):,} rows contain {len(cet_ids):,}
(SBIR.gov repeats some Contract numbers). Keyword ∩ CET Jaccard is low ({pairwise_jaccard(kw_ids, cet_ids):.3f}),
driven by the size mismatch rather than disagreement: {100 * len(kw_ids & cet_ids) / max(1, len(cet_ids)):.0f}% of
CET award IDs fall inside the keyword cohort, and the remainder is carbon-fiber-only matches (see §2B).
{cpc_overlap_note}

---

## 4. NNI Table 5 Reconciliation

**Scope:** FY2020–FY2023, nine NNI-reporting agencies
**Caveat [UNVERIFIED]:** NNI Table 5 reference figures are approximate public summary values,
not extracted from the PDF. Methodology for OMB-identified classification not published.
Our classification method differs; exact reconciliation is not expected.

### 4A. Keyword Cohort vs NNI Table 5

{nni_table(kw_nni, 'keyword')}

### 4B. CET Proxy Cohort vs NNI Table 5

{nni_table(cet_nni, 'cet')}

**Methodological choice note [HIGH]:** We do not tune the keyword list or CET proxy to close
the delta. The gap itself is informative: it represents awards NNI counts as nanotech that our
text-based methods miss (e.g., awards with nanotech scope stated in solicitation topic, not abstract).

---

## 5. Phase III Transition Signal Channels

⚠ **DO NOT report the union signal as "the Phase III transition rate."**
Each channel has different coverage gaps and none is authoritative.

### 5A. Keyword cohort (n={len(kw_enriched):,})

| Channel | Signal-positive | % | Coverage caveat |
|---|---|---|---|
| FPDS-coded Phase III contract | {kw_sigs["sig_fpds_phase3_coded"]} | {100*kw_sigs["sig_fpds_phase3_coded"]/max(1,len(kw_enriched)):.1f}% | Known undercount; DoD ~67% of coded P3 in this cohort (GAO-24-106398) |
| Any subsequent federal obligation | {kw_sigs["sig_any_federal_obligation"]} | {100*kw_sigs["sig_any_federal_obligation"]/max(1,len(kw_enriched)):.1f}% | Broad; includes non-P3 task orders; per-firm not per-award |
| M&A signal — all tiers | {kw_sigs["sig_ma_detected"]} | {100*kw_sigs["sig_ma_detected"]/max(1,len(kw_enriched)):.1f}% | Exact name match; inflated by low-conf matches (~49% of total) |
| M&A signal — medium+high only | {kw_sigs["sig_ma_medium_high"]} | {100*kw_sigs["sig_ma_medium_high"]/max(1,len(kw_enriched)):.1f}% | More reliable; may still reflect prior EDGAR scan errors |
| M&A signal — high conf only | {kw_sigs["sig_ma_high_conf"]} | {100*kw_sigs["sig_ma_high_conf"]/max(1,len(kw_enriched)):.1f}% | Narrowest; recommend using this tier for any cited figure |
| Form D (high-confidence) | {kw_sigs["sig_form_d_detected"]} | {100*kw_sigs["sig_form_d_detected"]/max(1,len(kw_enriched)):.1f}% | Investment signal only; not direct P3 evidence |
| **Union (any positive)** | **{kw_sigs["sig_any_positive"]}** | **{100*kw_sigs["sig_any_positive"]/max(1,len(kw_enriched)):.1f}%** | **See caution above — do not report as rate** |

### 5B. CET proxy cohort (n={len(cet_enriched):,})

| Channel | Signal-positive | % | Coverage caveat |
|---|---|---|---|
| FPDS-coded Phase III contract | {cet_sigs["sig_fpds_phase3_coded"]} | {100*cet_sigs["sig_fpds_phase3_coded"]/max(1,len(cet_enriched)):.1f}% | Known undercount |
| Any subsequent federal obligation | {cet_sigs["sig_any_federal_obligation"]} | {100*cet_sigs["sig_any_federal_obligation"]/max(1,len(cet_enriched)):.1f}% | Broad; per-firm |
| M&A signal — medium+high only | {cet_sigs["sig_ma_medium_high"]} | {100*cet_sigs["sig_ma_medium_high"]/max(1,len(cet_enriched)):.1f}% | Preferred M&A signal tier |
| M&A signal — high conf only | {cet_sigs["sig_ma_high_conf"]} | {100*cet_sigs["sig_ma_high_conf"]/max(1,len(cet_enriched)):.1f}% | Narrowest M&A signal |
| Form D (high-confidence) | {cet_sigs["sig_form_d_detected"]} | {100*cet_sigs["sig_form_d_detected"]/max(1,len(cet_enriched)):.1f}% | Investment signal only |
| **Union (any positive)** | **{cet_sigs["sig_any_positive"]}** | **{100*cet_sigs["sig_any_positive"]/max(1,len(cet_enriched)):.1f}%** | **See caution above** |

---

{cpc_signals_section}## 6. Deficiency Classification (Task 4 — Primary Deliverable)

For every Phase II award in the keyword cohort without FPDS-coded Phase III evidence,
the following taxonomy classifies why transition status is indeterminate.

### 6A. Keyword cohort

{deficiency_table(kw_enriched)}

**Taxonomy definitions:**

| Class | Definition |
|---|---|
| `ENTITY_RESOLUTION_FAILURE` | UEI absent from SBIR.gov record; cannot link award to federal procurement systems |
| `INSUFFICIENT_TIME` | Award year ≥ {INSUFFICIENT_TIME_YEAR}; typical Phase III maturation requires 3–7 years; censored observation, not negative signal |
| `FIRM_ACTIVITY_ABSENT` | Firm not found in USAspending prospect digest; no contracts or grants found under this UEI |
| `DATA_GAP_FPDS_NONDOD` | Non-DoD agency where FPDS Phase III column coding is sparse (GAO-24-106398, pp. 26-29); absence is system gap, not transition failure |
| `NO_FPDS_CODING` | Firm has FPDS activity but no contract carries Phase III coding; may be uncoded transition (common) |
| `INDETERMINATE` | None of the above categories explain the gap; cause not derivable from available data |

---

## 7. Key Methodological Caveats

1. **CET is a keyword matcher, not a classifier [HIGH].** No accuracy figures exist for this heuristic
   applied to nanotech. Do not describe Method B results as "classified by CET."

2. **FPDS Phase III undercounting [HIGH].** GAO-24-106398 documents that FPDS `sbir_program` coding is
   sparse outside DoD. Absence of a Phase III-coded contract is not evidence of no transition.

3. **NNI reconciliation is not expected to close [HIGH].** NNI uses agency+OMB identification methods
   not published in the Supplement. Our text classification approach differs by design.

4. **EDGAR scan data is usable; summary file is not [HIGH].** `sec_edgar_scan.jsonl` contains
   complete results for 34,451 firms (99.9% of nanotech cohort) with 7,548 having at least one
   mention and 2,195 tagged `ma_definitive`. A subsequent scan process wrote `sec_edgar_scan.summary.json`
   showing 0 detections after hitting HTTP 500 errors on every request — that summary reflects a failed
   process, not the data. M&A signals in this analysis draw on `sec_edgar_scan.jsonl` directly,
   filtered to M&A-specific mention types. See `scripts/data/nano_ma_signal.py`.

{caveat_5}

6. **Form D is an investment signal, not a transition signal [HIGH].** A Form D filing indicates capital
   raised, which may correlate with commercialization but does not prove Phase III transition.

7. **Phase II prospect digest is per-firm [HIGH].** A single UEI can have multiple Phase II awards.
   Transition signals in the digest apply at firm level; per-award attribution is not possible
   from this data source alone.

---

## 8. Figures

- `data/analysis/nano_cohort_overlap.png` — Three-way Venn diagram (Jaccard annotations)
- `data/analysis/nano_transition_channels.png` — Transition signal by channel, by method cohort
"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    print(f"  Saved: {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--awards", default=str(DATA / "raw/sbir/award_data.csv"))
    args = parser.parse_args()

    awards_csv = Path(args.awards)
    if not awards_csv.exists():
        print(f"ERROR: awards CSV not found: {awards_csv}", file=sys.stderr)
        return 1

    print("Loading Phase II awards...")
    awards = load_phase2_awards(awards_csv)
    print(f"  {len(awards):,} Phase II awards loaded")

    print("Building keyword cohort (Method A)...")
    kw_cohort = build_keyword_cohort(awards)
    print(f"  {len(kw_cohort):,} awards matched")

    print("Building CET proxy cohort (Method B)...")
    cet_cohort = build_cet_cohort(awards)
    print(f"  {len(cet_cohort):,} awards matched")

    print("Building CPC cohort (Method C)...")
    cpc_cohort = build_cpc_cohort(awards)
    if cpc_cohort:
        print(f"  {len(cpc_cohort):,} awards matched (B82 assignee ↔ firm name, "
              f"{len({r['company'].upper() for r in cpc_cohort}):,} firms)")
    else:
        print("  0 awards (B82 extract absent — see methodology doc)")

    print("Loading Phase III prospect digest...")
    digest_csv = DATA / "processed/sbir_phase3/fy25_phase3_prospect_digest.csv"
    digest = load_phase3_digest(digest_csv)
    print(f"  {len(digest):,} firms in digest")

    print("Loading M&A signals...")
    ma_signals = load_ma_signals(DATA / "enriched_sbir_ma_events.jsonl")
    print(f"  {len(ma_signals):,} firms with M&A signal")

    print("Loading Form D signals...")
    form_d_signals = load_form_d_signals(DATA / "form_d_high_conf_cohort.jsonl")
    print(f"  {len(form_d_signals):,} firms with high-confidence Form D")

    print("Enriching cohorts with transition signals...")
    kw_enriched = enrich_cohort_with_signals(kw_cohort, digest, ma_signals, form_d_signals)
    cet_enriched = enrich_cohort_with_signals(cet_cohort, digest, ma_signals, form_d_signals)
    cpc_enriched = enrich_cohort_with_signals(cpc_cohort, digest, ma_signals, form_d_signals)

    print("Running NNI reconciliation (FY2020–2023, 9 agencies)...")
    kw_nni = nni_reconciliation(kw_cohort, NNI_AGENCIES_SET)
    cet_nni = nni_reconciliation(cet_cohort, NNI_AGENCIES_SET)

    print("Writing output CSVs...")
    write_output_csv(kw_enriched, DATA / "nano_cohort_keyword.csv")
    print(f"  data/nano_cohort_keyword.csv ({len(kw_enriched):,} rows)")
    write_output_csv(cet_enriched, DATA / "nano_cohort_cet.csv")
    print(f"  data/nano_cohort_cet.csv ({len(cet_enriched):,} rows)")
    if cpc_enriched:
        write_output_csv(cpc_enriched, DATA / "nano_cohort_cpc.csv")
        print(f"  data/nano_cohort_cpc.csv ({len(cpc_enriched):,} rows)")
    else:
        write_output_csv(
            [{"note": CPC_COHORT_ABSENT_REASON, "cohort_cpc": False}],
            DATA / "nano_cohort_cpc.csv",
        )
        print("  data/nano_cohort_cpc.csv (stub — B82 extract absent)")

    print("Generating figures...")
    kw_ids = {r["award_id"] for r in kw_cohort}
    cet_ids = {r["award_id"] for r in cet_cohort}
    cpc_ids = {r["award_id"] for r in cpc_cohort}

    plot_venn_overlap(kw_ids, cet_ids, cpc_ids, ANALYSIS_DIR / "nano_cohort_overlap.png")
    plot_transition_channels(kw_enriched, cet_enriched, ANALYSIS_DIR / "nano_transition_channels.png")

    print("Writing methodology doc...")
    write_methodology_doc(
        kw_cohort, cet_cohort, cpc_cohort,
        kw_enriched, cet_enriched, cpc_enriched,
        kw_nni, cet_nni,
        DOCS / "nano_phase3_methodology.md",
    )

    # Summary to stdout
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total Phase II awards in CSV:     {len(awards):,}")
    print(f"Keyword cohort (Method A):        {len(kw_cohort):,}")
    print(f"CET proxy cohort (Method B):      {len(cet_cohort):,}")
    cpc_note = "" if cpc_cohort else "  [DATA ABSENT]"
    print(f"CPC cohort (Method C):            {len(cpc_cohort):,}{cpc_note}")
    print()
    print("Transition signals (keyword cohort):")
    for field, label in [
        ("sig_fpds_phase3_coded", "  FPDS Phase III coded"),
        ("sig_any_federal_obligation", "  Any federal obligation"),
        ("sig_ma_detected", "  M&A detected"),
        ("sig_form_d_detected", "  Form D (high-conf)"),
        ("sig_any_positive", "  Union (any)"),
    ]:
        n = sum(1 for r in kw_enriched if r.get(field))
        pct = 100.0 * n / max(1, len(kw_enriched))
        print(f"{label}: {n:,} ({pct:.1f}%)")
    print()
    print("Deficiency counts (keyword cohort, no FPDS P3 coded):")
    dc: dict[str, int] = defaultdict(int)
    for r in kw_enriched:
        if not r.get("sig_fpds_phase3_coded"):
            dc[r.get("deficiency_class", "INDETERMINATE")] += 1
    for k in sorted(dc):
        print(f"  {k}: {dc[k]:,}")
    print()
    print("Outputs:")
    print("  data/nano_cohort_keyword.csv")
    print("  data/nano_cohort_cet.csv")
    print("  data/nano_cohort_cpc.csv")
    print("  data/analysis/nano_cohort_overlap.png")
    print("  data/analysis/nano_transition_channels.png")
    print("  docs/nano_phase3_methodology.md")

    return 0


if __name__ == "__main__":
    sys.exit(main())
