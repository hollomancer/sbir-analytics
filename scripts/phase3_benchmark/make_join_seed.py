#!/usr/bin/env python3
"""Assemble the notice-recovery join seed from the frozen Phase III frames.

Emits (a) ``join_keys.txt`` — newline-delimited PIIDs for the archive pull's
stream filter — and (b) ``join_seed.parquet`` — one row per (piid, firm,
label_channel) for the corpus builder's link step.

Channels (specs/phase3-notice-corpus-fusion §3):
- ``description``: contracts whose FPDS description self-identifies as Phase III
  (M0a description-captured frames + the frozen verified-undercount flags).
- ``coded``: SR3/ST3-coded contracts pulled via ``pull_fpds_10q.py`` — optional
  input; absent until the FPDS pull runs.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from scripts.phase3_benchmark.pull_gsa_archive import normalize_key


def _frame(path: Path, piid_column: str, firm_column: str | None, channel: str) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["piid", "firm", "label_channel"])
    df = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    out = pd.DataFrame(
        {
            "piid": df[piid_column].astype(str),
            "firm": df[firm_column].astype(str) if firm_column in df.columns else None,
            "label_channel": channel,
        }
    )
    return out


def build_seed(
    m0a_dod: Path,
    m0a_nasa: Path,
    undercount: Path,
    coded: Path | None,
) -> pd.DataFrame:
    frames = [
        _frame(m0a_dod, "Award ID", "recipient_name", "description"),
        _frame(m0a_nasa, "Award ID", "Recipient Name", "description"),
        _frame(undercount, "award_id", "firm", "description"),
    ]
    if coded is not None and coded.exists():
        frames.append(_frame(coded, "PIID", "vendorName", "coded"))
    seed = pd.concat(frames, ignore_index=True)
    seed["piid_key"] = seed["piid"].map(normalize_key)
    seed = seed.loc[seed["piid_key"].str.len() >= 6]
    # coded outranks description when the same PIID appears in both.
    seed["_channel_rank"] = (seed["label_channel"] == "coded").astype(int)
    seed = (
        seed.sort_values("_channel_rank", ascending=False)
        .drop_duplicates(subset=["piid_key"], keep="first")
        .drop(columns=["_channel_rank"])
        .reset_index(drop=True)
    )
    return seed


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
    parser.add_argument("--coded", type=Path, default=None, help="Optional pull_fpds_10q output.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/derived"))
    args = parser.parse_args()

    seed = build_seed(args.m0a_dod, args.m0a_nasa, args.undercount, args.coded)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    seed_path = args.output_dir / "phase3_notice_join_seed.parquet"
    keys_path = args.output_dir / "phase3_notice_join_keys.txt"
    seed.to_parquet(seed_path, index=False)
    keys_path.write_text("\n".join(sorted(set(seed["piid_key"]))) + "\n", encoding="utf-8")
    channels = seed["label_channel"].value_counts().to_dict()
    print(f"seed: {len(seed)} unique PIIDs ({channels}) -> {seed_path}")
    print(f"keys: {keys_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
