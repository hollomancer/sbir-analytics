#!/usr/bin/env python3
"""Consolidate the per-year self-labeled Phase III notices into a validated set.

Merges every ``FY*_phase3_selflabeled.parquet`` produced by
``extract_phase3_selflabeled``, re-classifies uniformly, resolves each firm-named
positive (award + intent) to its SBIR firm, and cross-validates against the #481
hand-collected set. Emits two committed artifacts under the spec's ``collected/``:

- ``sam_selflabeled_phase3_positives.csv`` — retrospective + forward positives
  (firm, award#, agency, notice_class, SBIR resolution, whether already in #481).
- ``sam_selflabeled_phase3_forward_feed.csv`` — the Sources Sought open-opportunity feed.

Pure post-processing of local parquets; no network.
"""

from __future__ import annotations

import argparse
import glob
import re
from pathlib import Path

import pandas as pd

from scripts.phase3_benchmark.extract_phase3_selflabeled import classify_notice

# Pre-award intent notices leave ``Awardee`` blank but name the firm in the
# Description: "...intends to award ... to <FIRM>, <street-number> <address>".
# Anchor on the street address ("<FIRM>, <digits> <word>") rather than an
# award keyword, so a stray "competition to award" earlier doesn't hijack the
# match; the optional legal-suffix segment keeps an internal comma ("Synoptos, Inc.").
_AWARD_TO = re.compile(
    r"\bto\s+([A-Za-z][^,]{1,60}(?:,\s*(?:inc|l\.?l\.?c|llc|corp\w*|co|company|ltd|lp)\.?)?)"
    r",\s+\d{1,6}\s",
    re.IGNORECASE,
)
# Fallback: "Notice of Intent to Sole-Source - <FIRM>" in the Title.
_TITLE_FIRM = re.compile(r"sole[\s-]*source\s*[-:]\s*(.+?)\s*$", re.IGNORECASE)


def firm_from_notice(row: dict) -> str:
    """Best firm name for a notice: Awardee, else parsed from Description/Title."""

    awardee = str(row.get("Awardee") or "").strip()
    if len(awardee) > 3:
        return awardee
    match = _AWARD_TO.search(str(row.get("Description") or ""))
    if match:
        firm = match.group(1).strip(" ,-\t")  # keep a trailing "Inc." period
        if 3 < len(firm) < 70 and "sbir" not in firm.lower():
            return firm
    match = _TITLE_FIRM.search(str(row.get("Title") or ""))
    if match:
        firm = match.group(1).strip()
        if 3 < len(firm) < 50 and not re.search(r"sbir|phase|program|contract", firm, re.IGNORECASE):
            return firm
    return ""


def _resolvers(award_csv: str):
    import sys

    sys.path.insert(0, str(Path("scripts/phase3_groundtruth")))
    # resolver lives with the ground-truth spec work; import defensively
    from resolve_firm_awards import normalize_name, resolve_firm  # type: ignore

    return normalize_name, resolve_firm


def consolidate(parquet_dir: Path, collected_glob: str, award_csv: str, out_dir: Path) -> dict:
    normalize_name, resolve_firm = _resolvers(award_csv)
    frames = [pd.read_parquet(f) for f in glob.glob(str(parquet_dir / "FY*_phase3_selflabeled.parquet"))]
    if not frames:
        raise SystemExit(f"no per-year parquets under {parquet_dir}")
    sl = pd.concat(frames, ignore_index=True)
    sl["notice_class"] = sl.apply(lambda r: classify_notice(r.to_dict()), axis=1)

    gt = pd.concat([pd.read_csv(f, dtype=str) for f in glob.glob(collected_glob)], ignore_index=True).fillna("")
    gt_firms = {normalize_name(f) for f in gt["firm"] if f.strip()}

    pos = sl[sl["notice_class"].isin(["award", "intent_sole_source"])].copy()
    pos["firm"] = pos.apply(lambda r: firm_from_notice(r.to_dict()), axis=1)
    pos = pos[pos["firm"].str.len() > 3].drop_duplicates(subset=["firm", "AwardNumber", "NoticeId"])

    records = []
    for _, r in pos.iterrows():
        res = resolve_firm(r["firm"], award_csv)
        matched = res.matched_company
        in_481 = normalize_name(r["firm"]) in gt_firms or (matched and normalize_name(matched) in gt_firms)
        records.append(
            {
                "firm": r["firm"],
                "matched_sbir_company": matched or "",
                "notice_class": r["notice_class"],
                "award_number": r["AwardNumber"],
                "agency": r["Department/Ind.Agency"],
                "posted_date": r["PostedDate"],
                "sbir_match": res.match_method,
                "n_prior_sbir": res.award_count,
                "in_481": bool(in_481),
                "title": str(r["Title"])[:160],
                "notice_id": r["NoticeId"],
            }
        )
    positives = pd.DataFrame(records)
    forward = sl[sl["notice_class"] == "sources_sought"][
        ["NoticeId", "PostedDate", "Department/Ind.Agency", "Sol#", "NaicsCode", "Title"]
    ].drop_duplicates("NoticeId")

    out_dir.mkdir(parents=True, exist_ok=True)
    positives.to_csv(out_dir / "sam_selflabeled_phase3_positives.csv", index=False)
    forward.to_csv(out_dir / "sam_selflabeled_phase3_forward_feed.csv", index=False)
    return {
        "positives": len(positives),
        "resolved_to_sbir": int((positives["sbir_match"] != "none").sum()),
        "agree_with_481": int(positives["in_481"].sum()),
        "net_new": int((~positives["in_481"]).sum()),
        "by_class": positives["notice_class"].value_counts().to_dict(),
        "forward_feed": len(forward),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--parquet-dir", type=Path, default=Path("data/derived/phase3_selflabeled")
    )
    parser.add_argument(
        "--collected-glob",
        default="specs/phase3-transition-groundtruth/collected/*.csv",
    )
    parser.add_argument("--award-csv", default="data/raw/sbir/award_data.csv")
    parser.add_argument(
        "--out-dir", type=Path, default=Path("specs/transition-coverage-expansion/collected")
    )
    args = parser.parse_args()
    summary = consolidate(args.parquet_dir, args.collected_glob, args.award_csv, args.out_dir)
    print("consolidated self-labeled Phase III set:")
    for key, value in summary.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
