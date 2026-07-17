"""Award-grain Phase III undercount, computed through PR #449's identity contract.

Reproduces the bounded DoD 141 / NASA 16 undercount (described-as-"SBIR PHASE III" but not `SR3`/`ST3`
coded) at **award grain** using ``sbir_etl.utils.award_identity.award_key_series`` — the same
compound-key / nested-parent-IDV rules as the benchmark — rather than raw FPDS transaction rows.

The coded (FPDS-derived) frame carries its award identity as ``order_piid / order_agency / idv_piid /
idv_agency``; the described (USAspending) frame carries ``generated_internal_id``. Both are supplied to
``award_key_series`` as a precomputed ``unique_award_key`` (the contract's preferred path), so the join
is exact and standalone contracts (no parent IDV) are handled without fabricating identities.

Run: ``python scripts/phase3_benchmark/undercount_award_grain.py --derived data/derived``
Requires the M0a derived frames (``m0a_coded_{dod,nasa}.parquet``, ``m0a_desc_phase3_{dod,nasa}.parquet``);
the compound-key logic itself is covered by ``tests/unit/scripts/test_undercount_award_grain.py`` on a
self-contained fixture.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from sbir_etl.utils.award_identity import award_key_series


def _norm(value: object) -> str:
    return str(value).strip().upper() if value is not None else ""


def reconstruct_coded_award_key(frame: pd.DataFrame) -> pd.Series:
    """USAspending-form unique award key for an FPDS-derived coded frame."""

    def row_key(row: pd.Series) -> str:
        return (
            f"CONT_AWD_{_norm(row['order_piid'])}_{_norm(row['order_agency']) or '-NONE-'}_"
            f"{_norm(row['idv_piid']) or '-NONE-'}_{_norm(row['idv_agency']) or '-NONE-'}"
        )

    return frame.apply(row_key, axis=1)


def undercount(coded: pd.DataFrame, described: pd.DataFrame) -> dict[str, int]:
    """Distinct described-but-not-coded awards, keyed through #449's contract."""
    coded = coded.assign(unique_award_key=reconstruct_coded_award_key(coded))
    described = described.assign(
        unique_award_key=described["generated_internal_id"].astype(str).str.upper()
    )
    coded_keys = set(award_key_series(coded))
    described_keys = set(award_key_series(described))
    return {
        "coded_transactions": len(coded),
        "coded_awards": len(coded_keys),
        "described_awards": len(described_keys),
        "described_coded_overlap": len(described_keys & coded_keys),
        "undercount": len(described_keys - coded_keys),
    }


def _block(derived: Path, coded_file: str, described_file: str) -> dict[str, object]:
    stats = undercount(
        pd.read_parquet(derived / coded_file),
        pd.read_parquet(derived / described_file),
    )
    stats["undercount_rate"] = round(stats["undercount"] / max(stats["described_awards"], 1), 4)
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--derived", type=Path, default=Path("data/derived"),
                        help="directory holding the M0a coded/described parquet frames")
    args = parser.parse_args(argv)

    manifest = {
        "identity_contract": "sbir_etl.utils.award_identity.award_key_series (PR #449)",
        "grain": "award (not FPDS transaction)",
        "DoD": _block(args.derived, "m0a_coded_dod.parquet", "m0a_desc_phase3_dod.parquet"),
        "NASA": _block(args.derived, "m0a_coded_nasa.parquet", "m0a_desc_phase3_nasa.parquet"),
    }
    print(json.dumps(manifest, indent=2))

    assert manifest["DoD"]["undercount"] == 141, manifest["DoD"]
    assert manifest["NASA"]["undercount"] == 16, manifest["NASA"]
    assert manifest["DoD"]["described_coded_overlap"] > 0, "coded/described key formats do not join"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
