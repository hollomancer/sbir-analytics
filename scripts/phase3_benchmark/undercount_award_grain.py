"""Award-grain description-only Phase III flags with explicit list strata."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

PROGRAM_CODES = {"SBIR": "SR3", "STTR": "ST3"}


def _norm(value: object) -> str:
    if value is None or value is pd.NA or value is pd.NaT:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip().upper()


def reconstruct_coded_award_key(frame: pd.DataFrame) -> pd.Series:
    """Reconstruct a validation-only USAspending key from FPDS components."""
    required = {"order_piid", "order_agency", "idv_piid", "idv_agency"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"cannot reconstruct award key; missing columns {missing}")

    def row_key(row: pd.Series) -> str:
        return (
            f"CONT_AWD_{_norm(row['order_piid'])}_{_norm(row['order_agency']) or '-NONE-'}_"
            f"{_norm(row['idv_piid']) or '-NONE-'}_{_norm(row['idv_agency']) or '-NONE-'}"
        )

    return frame.apply(row_key, axis=1)


def authoritative_coded_keys(frame: pd.DataFrame) -> pd.Series:
    """Return native keys and fail if reconstruction disagrees where available."""
    column = next((name for name in ("contract_award_unique_key", "contractAwardUniqueKey")
                   if name in frame), None)
    if column is None:
        raise ValueError("coded frame lacks native contractAwardUniqueKey coverage")
    native = frame[column].map(_norm)
    if native.eq("").any():
        raise ValueError("coded frame has missing native contractAwardUniqueKey values")
    components = {"order_piid", "order_agency", "idv_piid", "idv_agency"}
    if components.issubset(frame.columns):
        reconstructed = reconstruct_coded_award_key(frame)
        disagreement = native.ne(reconstructed)
        if disagreement.any():
            rows = list(frame.index[disagreement][:5])
            raise ValueError(f"native/reconstructed award key disagreement at rows {rows}")
    return native.rename("award_key")


def _described_contract_keys(frame: pd.DataFrame, signal: str | None = None) -> set[str]:
    working = frame.copy()
    if "award_type_group" in working:
        working = working[working["award_type_group"] == "contract"]
    else:
        ids = working["generated_internal_id"].astype(str).str.upper()
        working = working[ids.str.startswith("CONT_AWD_")]
    if signal is not None:
        if "description_signal" not in working:
            raise ValueError("described frame lacks description_signal stratum")
        working = working[working["description_signal"] == signal]
    return set(working["generated_internal_id"].map(_norm))


def _stats(coded_keys: set[str], described_keys: set[str]) -> dict[str, int | float]:
    overlap = described_keys & coded_keys
    flags = described_keys - coded_keys
    observed_union = described_keys | coded_keys
    return {
        "coded_awards": len(coded_keys),
        "described_contract_awards": len(described_keys),
        "overlap": len(overlap),
        "description_only_flags": len(flags),
        "description_conditional_miss_rate": (
            len(flags) / len(described_keys) if described_keys else 0.0
        ),
        "observed_union_miss_rate": len(flags) / len(observed_union) if observed_union else 0.0,
    }


def undercount(coded: pd.DataFrame, described: pd.DataFrame) -> dict[str, object]:
    """Compute unadjudicated description-only flags by SBIR/STTR stratum."""
    native = authoritative_coded_keys(coded)
    research_column = next((name for name in ("research", "_research_code", "code")
                            if name in coded), None)
    if research_column is None:
        raise ValueError("coded frame lacks SR3/ST3 research-code stratum")
    strata: dict[str, dict[str, int | float]] = {}
    for program, code in PROGRAM_CODES.items():
        coded_keys = set(native[coded[research_column].map(_norm) == code])
        described_keys = _described_contract_keys(described, program)
        strata[program] = _stats(coded_keys, described_keys)
    all_coded = set(native[coded[research_column].map(_norm).isin(PROGRAM_CODES.values())])
    all_described = _described_contract_keys(described)
    return {
        "status": "provisional",
        "label_semantics": "unadjudicated description-only flags",
        "coded_rows": len(coded),
        "contract_rows_only": True,
        "strata": strata,
        "combined": _stats(all_coded, all_described),
        "idv_rows_excluded": int(
            (described.get("award_type_group", pd.Series(dtype=str)) == "idv").sum()
        ),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coded", type=Path, required=True)
    parser.add_argument("--described", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    missing = [str(path) for path in (args.coded, args.described) if not path.exists()]
    if missing:
        result: dict[str, object] = {"status": "blocked_missing_inputs", "missing": missing}
    else:
        result = undercount(pd.read_parquet(args.coded), pd.read_parquet(args.described))
        result["inputs"] = {
            "coded": {"path": str(args.coded), "sha256": _sha256(args.coded)},
            "described": {"path": str(args.described), "sha256": _sha256(args.described)},
        }
    payload = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload)
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
