#!/usr/bin/env python3
"""Assemble the frozen Phase III notice corpus from the recovered archive pulls.

Joins the seed PIIDs to their recovered GSA notices (rich Description / J&A
text), attaches each firm's Phase I/II abstract as the retrieval query, and
builds same-office hard-negative candidate sets — mirroring the transition-ranker
study ("diff-firm SAME contracting office"). Output is one row per
(firm-award, candidate-notice) with the structural features the fusion ladder
consumes, plus a provenance manifest with a frame hash.

Research utility (specs/phase3-notice-corpus-fusion), fully offline given the
filtered archive pulls, the join seed, and a firm→abstract lookup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from scripts.phase3_benchmark.pull_gsa_archive import KEEP_COLUMNS, normalize_key


CORPUS_COLUMNS: tuple[str, ...] = (
    "candidate_id",
    "firm_uei",
    "firm_name",
    "award_piid",
    "notice_id",
    "office",
    "query_abstract",
    "notice_text",
    "notice_type",
    "posted_date",
    "naics_code",
    "match_rule",
    "id_cited",
    "label",
    "label_channel",
    "owner",
)


def load_filtered_notices(archive_dir: Path) -> pd.DataFrame:
    """Concatenate every ``FY*_filtered.parquet`` under the archive dir."""

    parts = sorted(archive_dir.glob("FY*_filtered.parquet"))
    if not parts:
        return pd.DataFrame(columns=[*KEEP_COLUMNS, "match_rule"])
    frame = pd.concat((pd.read_parquet(part) for part in parts), ignore_index=True)
    frame["award_key"] = frame["AwardNumber"].map(normalize_key)
    frame["sol_key"] = frame["Sol#"].map(normalize_key)
    return frame


def _abstract_lookup(abstracts: pd.DataFrame) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for _, row in abstracts.iterrows():
        text = str(row.get("abstract") or "").strip()
        if not text:
            continue
        for key_col in ("uei", "firm"):
            key = normalize_key(row.get(key_col))
            if len(key) >= 4:
                lookup.setdefault(key, text)
    return lookup


def _match_notice(seed_row: pd.Series, notices: pd.DataFrame) -> pd.Series | None:
    piid = seed_row["piid_key"]
    hit = notices.loc[notices["award_key"] == piid]
    if hit.empty:
        hit = notices.loc[notices["sol_key"] == piid]
    if hit.empty:
        # text_citation rows: the PIID appears inside the description.
        cite = notices.loc[notices["match_rule"] == "text_citation"]
        mask = cite["Description"].map(lambda d: piid in normalize_key(d))
        hit = cite.loc[mask]
    if hit.empty:
        return None
    # Prefer the richest description when a PIID maps to several notices.
    return hit.loc[hit["Description"].str.len().idxmax()]


def build_corpus(
    seed: pd.DataFrame,
    notices: pd.DataFrame,
    abstracts: pd.DataFrame,
    *,
    negatives_per_positive: int = 5,
) -> pd.DataFrame:
    """One row per (firm-award, candidate-notice); same-office hard negatives."""

    lookup = _abstract_lookup(abstracts)
    rows: list[dict[str, object]] = []
    positives: list[dict[str, object]] = []

    for _, seed_row in seed.iterrows():
        notice = _match_notice(seed_row, notices)
        if notice is None:
            continue
        firm_key = normalize_key(seed_row.get("firm"))
        abstract = lookup.get(firm_key) or lookup.get(seed_row["piid_key"], "")
        if not abstract:
            continue
        positives.append(
            {
                "firm_uei": firm_key,
                "firm_name": str(seed_row.get("firm") or ""),
                "award_piid": seed_row["piid_key"],
                "query_abstract": abstract,
                "label_channel": seed_row.get("label_channel", "description"),
                "_notice": notice,
            }
        )

    for positive in positives:
        positive["_office"] = str(positive["_notice"].get("Office") or "")

    for positive in positives:
        notice = positive["_notice"]
        office = positive["_office"]
        owner = f"{positive['firm_uei']}:{positive['award_piid']}"

        def _emit(cand_notice: pd.Series, label: int) -> None:
            rows.append(
                {
                    "candidate_id": hashlib.sha256(
                        f"{owner}|{cand_notice.get('NoticeId')}|{label}".encode()
                    ).hexdigest()[:20],
                    "firm_uei": positive["firm_uei"],
                    "firm_name": positive["firm_name"],
                    "award_piid": positive["award_piid"],
                    "notice_id": str(cand_notice.get("NoticeId") or ""),
                    "office": str(cand_notice.get("Office") or ""),
                    "query_abstract": positive["query_abstract"],
                    "notice_text": str(cand_notice.get("Description") or ""),
                    "notice_type": str(
                        cand_notice.get("BaseType") or cand_notice.get("Type") or ""
                    ),
                    "posted_date": str(cand_notice.get("PostedDate") or ""),
                    "naics_code": str(cand_notice.get("NaicsCode") or ""),
                    "match_rule": str(cand_notice.get("match_rule") or ""),
                    "id_cited": int(
                        positive["award_piid"] in normalize_key(cand_notice.get("Description"))
                    ),
                    "label": label,
                    "label_channel": positive["label_channel"],
                    "owner": owner,
                }
            )

        _emit(notice, 1)
        # Hard negatives = other firms' recovered notices in the SAME office
        # (mirrors the study's "diff-firm SAME contracting office"). Drawn from
        # the positives pool so firm identity is known; deterministic order.
        negatives = [
            other
            for other in positives
            if other["_office"] == office and other["firm_uei"] != positive["firm_uei"]
        ]
        for other in negatives[:negatives_per_positive]:
            _emit(other["_notice"], 0)

    return pd.DataFrame(rows, columns=CORPUS_COLUMNS)


def frame_hash(frame: pd.DataFrame) -> str:
    payload = frame.sort_values("candidate_id").to_csv(index=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_corpus(corpus: pd.DataFrame, output_dir: Path, sources: Sequence[str]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    corpus_path = output_dir / "phase3_notice_corpus.parquet"
    corpus.to_parquet(corpus_path, index=False)
    positives = corpus.loc[corpus["label"] == 1]
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "rows": len(corpus),
        "positives": int(len(positives)),
        "firms": int(positives["firm_uei"].nunique()),
        "label_channels": positives["label_channel"].value_counts().to_dict(),
        "match_rules": positives["match_rule"].value_counts().to_dict(),
        "id_cited_positives": int(positives["id_cited"].sum()),
        "frame_hash": frame_hash(corpus),
        "sources": list(sources),
    }
    (output_dir / "phase3_notice_corpus.manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return corpus_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seed", type=Path, default=Path("data/derived/phase3_notice_join_seed.parquet")
    )
    parser.add_argument("--archive-dir", type=Path, default=Path("data/raw/gsa_falextracts"))
    parser.add_argument(
        "--abstracts",
        type=Path,
        default=Path("data/derived/phase3_match_benchmark_pairs.parquet"),
        help="Firm→abstract source (needs uei/firm + abstract columns).",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/derived"))
    parser.add_argument("--negatives-per-positive", type=int, default=5)
    args = parser.parse_args()

    seed = pd.read_parquet(args.seed)
    notices = load_filtered_notices(args.archive_dir)
    abstracts = pd.read_parquet(args.abstracts)
    corpus = build_corpus(
        seed, notices, abstracts, negatives_per_positive=args.negatives_per_positive
    )
    corpus_path = write_corpus(
        corpus,
        args.output_dir,
        sources=[str(args.seed), str(args.archive_dir), str(args.abstracts)],
    )
    positives = int((corpus["label"] == 1).sum())
    print(f"corpus: {len(corpus)} rows, {positives} positives -> {corpus_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
