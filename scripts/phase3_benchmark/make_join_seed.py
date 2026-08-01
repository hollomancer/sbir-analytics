#!/usr/bin/env python3
"""Assemble the Phase III firm seed for notice recovery.

Collects every Phase III firm from the frozen frames (M0a description-captured
DoD/NASA, verified-undercount flags, benchmark pairs), then resolves each to its
SBIR award record in ``award_data.csv`` — by UEI when known, else by normalized
name — to attach the retrieval-query abstract and the firm's contract PIIDs.

Emits ``phase3_firm_seed.parquet``: one row per firm with
``firm, name_key, uei, piids (";"-joined), abstract, label_channel``. Firms
without a resolvable abstract are kept (they still serve as attribution targets
/ hard negatives) but cannot be query positives.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from scripts.phase3_benchmark.notice_matching import normalize_firm_name, normalize_key


def _collect_firms(m0a_dod: Path, m0a_nasa: Path, undercount: Path, pairs: Path) -> pd.DataFrame:
    """One row per (firm, piid, uei?, abstract?) from every frozen source."""

    frames: list[pd.DataFrame] = []

    def _add(path: Path, firm_col: str, piid_col: str, channel: str, **extra: str) -> None:
        if not path.exists():
            return
        df = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
        out = pd.DataFrame({"firm": df.get(firm_col), "piid": df.get(piid_col)})
        out["uei"] = df.get(extra["uei"]) if "uei" in extra else None
        out["abstract"] = df.get(extra["abstract"]) if "abstract" in extra else None
        out["label_channel"] = channel
        frames.append(out)

    _add(m0a_dod, "recipient_name", "Award ID", "description")
    _add(m0a_nasa, "Recipient Name", "Award ID", "description")
    _add(undercount, "firm", "award_id", "description")
    _add(pairs, "firm_sbir", "piid", "description", uei="uei_sbir", abstract="abstract")
    collected = pd.concat(frames, ignore_index=True)
    collected = collected.loc[collected["firm"].astype(str).str.strip() != ""]
    return collected


def _award_data_index(award_data: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    """Build UEI→ and name_key→ lookups of {abstract, uei} from award_data.csv.

    Keeps the longest abstract per firm as the retrieval query.
    """

    columns = ["UEI", "Company", "Abstract"]
    df = pd.read_csv(award_data, usecols=columns, dtype=str, low_memory=False)
    df["abstract_len"] = df["Abstract"].fillna("").str.len()
    df = df.sort_values("abstract_len", ascending=False)
    by_uei: dict[str, dict] = {}
    by_name: dict[str, dict] = {}
    for _, row in df.iterrows():
        payload = {"abstract": row.get("Abstract") or "", "uei": str(row.get("UEI") or "")}
        uei = str(row.get("UEI") or "").strip()
        if uei and uei not in by_uei:
            by_uei[uei] = payload
        name_key = normalize_firm_name(row.get("Company"))
        if len(name_key) >= 8 and name_key not in by_name:
            by_name[name_key] = payload
    return by_uei, by_name


def build_firm_seed(
    m0a_dod: Path, m0a_nasa: Path, undercount: Path, pairs: Path, award_data: Path
) -> pd.DataFrame:
    collected = _collect_firms(m0a_dod, m0a_nasa, undercount, pairs)
    by_uei, by_name = _award_data_index(award_data)

    collected["name_key"] = collected["firm"].map(normalize_firm_name)
    collected["piid_key"] = collected["piid"].map(normalize_key)
    rows: list[dict[str, object]] = []
    for name_key_value, group in collected.groupby("name_key"):
        name_key = str(name_key_value)
        if not name_key:
            continue
        firm = str(group["firm"].iloc[0])
        piids = sorted({p for p in group["piid_key"] if len(p) >= 10})
        uei = next(
            (str(u) for u in group["uei"].dropna().astype(str) if u.strip() and u != "nan"), ""
        )
        # Prefer a seed-provided abstract, else resolve via UEI, else via name.
        abstract = next(
            (str(a) for a in group["abstract"].dropna().astype(str) if len(str(a)) > 50), ""
        )
        if not abstract and uei and uei in by_uei:
            abstract = by_uei[uei]["abstract"]
        if not abstract and name_key in by_name:
            resolved = by_name[name_key]
            abstract = resolved["abstract"]
            uei = uei or resolved["uei"]
        rows.append(
            {
                "firm": firm,
                "name_key": name_key,
                "uei": uei,
                "piids": ";".join(piids),
                "abstract": abstract,
                "label_channel": group["label_channel"].iloc[0],
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--m0a-dod", type=Path, default=Path("data/derived/m0a_desc_phase3_dod.parquet")
    )
    parser.add_argument(
        "--m0a-nasa", type=Path, default=Path("data/derived/m0a_desc_phase3_nasa.parquet")
    )
    parser.add_argument(
        "--undercount", type=Path, default=Path("data/derived/phase3_undercount_flags_frozen.csv")
    )
    parser.add_argument(
        "--pairs", type=Path, default=Path("data/derived/phase3_match_benchmark_pairs.parquet")
    )
    parser.add_argument("--award-data", type=Path, default=Path("data/raw/sbir/award_data.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/derived"))
    args = parser.parse_args()

    seed = build_firm_seed(
        args.m0a_dod, args.m0a_nasa, args.undercount, args.pairs, args.award_data
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    seed_path = args.output_dir / "phase3_firm_seed.parquet"
    seed.to_parquet(seed_path, index=False)
    with_abstract = int((seed["abstract"].str.len() > 50).sum())
    print(
        f"seed: {len(seed)} firms ({with_abstract} with a query abstract) -> {seed_path}\n"
        f"  channels: {seed['label_channel'].value_counts().to_dict()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
