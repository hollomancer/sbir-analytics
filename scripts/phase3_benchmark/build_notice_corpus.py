#!/usr/bin/env python3
"""Assemble the frozen Phase III notice corpus from firm-attributed archive pulls.

The archive pull (``pull_gsa_archive``) already attributed each SBIR-mentioning
notice to a seed firm. This step attaches each firm's Phase I/II abstract as the
retrieval query, builds same-office diff-firm hard-negative candidate sets
(mirroring the transition-ranker study), and freezes the corpus with a
provenance manifest and frame hash. Fully offline given the filtered pulls and
the firm seed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from scripts.phase3_benchmark.notice_matching import normalize_firm_name, normalize_key
from scripts.phase3_benchmark.pull_gsa_archive import KEEP_COLUMNS


CORPUS_COLUMNS: tuple[str, ...] = (
    "candidate_id",
    "firm_name",
    "name_key",
    "notice_id",
    "office",
    "query_abstract",
    "notice_text",
    "notice_type",
    "posted_date",
    "naics_code",
    "match_rule",
    "label",
    "label_channel",
    "owner",
)


def load_filtered_notices(archive_dir: Path) -> pd.DataFrame:
    """Concatenate every firm-tagged ``FY*_filtered.parquet`` under the archive dir."""

    parts = sorted(archive_dir.glob("FY*_filtered.parquet"))
    if not parts:
        return pd.DataFrame(columns=[*KEEP_COLUMNS, "firm", "match_rule"])
    return pd.concat((pd.read_parquet(part) for part in parts), ignore_index=True)


def _abstract_by_name(seed: pd.DataFrame) -> dict[str, tuple[str, str]]:
    """name_key → (query_abstract, label_channel) for firms with a usable abstract."""

    lookup: dict[str, tuple[str, str]] = {}
    for _, row in seed.iterrows():
        abstract = str(row.get("abstract") or "")
        if len(abstract) <= 50:
            continue
        name_key = str(row.get("name_key") or "")
        if name_key:
            lookup.setdefault(name_key, (abstract, str(row.get("label_channel") or "description")))
    return lookup


def build_corpus(
    notices: pd.DataFrame,
    seed: pd.DataFrame,
    *,
    negatives_per_positive: int = 5,
) -> pd.DataFrame:
    """One row per (attributed notice, candidate); same-office diff-firm hard negatives."""

    if notices.empty:
        return pd.DataFrame(columns=CORPUS_COLUMNS)
    abstracts = _abstract_by_name(seed)
    notices = notices.copy()
    notices["name_key"] = notices["firm"].map(normalize_firm_name)
    notices["office_key"] = notices["Office"].map(normalize_key)

    # Positives: each attributed notice whose firm has a query abstract.
    positives = notices.loc[notices["name_key"].isin(abstracts)].reset_index(drop=True)
    rows: list[dict[str, object]] = []

    for _, positive in positives.iterrows():
        name_key = str(positive["name_key"])
        abstract, channel = abstracts[name_key]
        owner_firm = str(positive["firm"])
        owner = f"{name_key}:{positive['NoticeId']}"

        rows.append(_corpus_row(owner, owner_firm, name_key, positive, abstract, channel, 1))
        # Hard negatives: other firms' attributed notices in the SAME office.
        pool = positives.loc[
            (positives["office_key"] == positive["office_key"])
            & (positives["name_key"] != name_key)
        ]
        for _, negative in pool.head(negatives_per_positive).iterrows():
            rows.append(_corpus_row(owner, owner_firm, name_key, negative, abstract, channel, 0))

    return pd.DataFrame(rows, columns=CORPUS_COLUMNS)


def _corpus_row(
    owner: str,
    owner_firm: str,
    name_key: str,
    candidate: pd.Series,
    query_abstract: str,
    label_channel: str,
    label: int,
) -> dict[str, object]:
    """Build one corpus row; firm/abstract identify the OWNER, notice_* the candidate."""

    return {
        "candidate_id": hashlib.sha256(
            f"{owner}|{candidate['NoticeId']}|{label}".encode()
        ).hexdigest()[:20],
        "firm_name": owner_firm,
        "name_key": name_key,
        "notice_id": str(candidate.get("NoticeId") or ""),
        "office": str(candidate.get("Office") or ""),
        "query_abstract": query_abstract,
        "notice_text": str(candidate.get("Description") or ""),
        "notice_type": str(candidate.get("BaseType") or candidate.get("Type") or ""),
        "posted_date": str(candidate.get("PostedDate") or ""),
        "naics_code": str(candidate.get("NaicsCode") or ""),
        "match_rule": str(candidate.get("match_rule") or ""),
        "label": label,
        "label_channel": label_channel,
        "owner": owner,
    }


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
        "firms": int(positives["name_key"].nunique()) if len(positives) else 0,
        "label_channels": positives["label_channel"].value_counts().to_dict(),
        "match_rules": positives["match_rule"].value_counts().to_dict(),
        "notice_type_counts": positives["notice_type"].value_counts().to_dict(),
        "notice_text_median_chars": (
            int(positives["notice_text"].str.len().median()) if len(positives) else 0
        ),
        "frame_hash": frame_hash(corpus),
        "sources": list(sources),
    }
    (output_dir / "phase3_notice_corpus.manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return corpus_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-dir", type=Path, default=Path("data/raw/gsa_falextracts"))
    parser.add_argument("--seed", type=Path, default=Path("data/derived/phase3_firm_seed.parquet"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/derived"))
    parser.add_argument("--negatives-per-positive", type=int, default=5)
    args = parser.parse_args()

    notices = load_filtered_notices(args.archive_dir)
    seed = pd.read_parquet(args.seed)
    corpus = build_corpus(notices, seed, negatives_per_positive=args.negatives_per_positive)
    corpus_path = write_corpus(
        corpus, args.output_dir, sources=[str(args.archive_dir), str(args.seed)]
    )
    positives = int((corpus["label"] == 1).sum())
    print(f"corpus: {len(corpus)} rows, {positives} positives -> {corpus_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
