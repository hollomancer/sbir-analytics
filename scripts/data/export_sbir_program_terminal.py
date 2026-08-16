#!/usr/bin/env python3
"""Export a fail-closed, exploratory firm-dossier snapshot for the SBIR terminal."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from sbir_etl.capital_events._common import data_path
from sbir_etl.capital_events.schema import EVENT_TABLE_COLUMNS


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=data_path("capital_events.parquet"))
    parser.add_argument(
        "--summary",
        type=Path,
        default=data_path("capital_events_per_firm.parquet"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tools/sbir-program-terminal/data/terminal.json"),
    )
    return parser


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _value(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    return value.isoformat() if hasattr(value, "isoformat") else value


def _sum_amount(events: pd.DataFrame, event_type: str) -> float:
    selected = events.loc[events["event_type"] == event_type, "amount_usd"]
    return float(pd.to_numeric(selected, errors="coerce").fillna(0).sum())


def build_terminal_payload(
    events: pd.DataFrame,
    summary: pd.DataFrame,
    *,
    events_path: Path,
    summary_path: Path,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Project canonical capital-event artifacts into the terminal's read-only contract."""
    missing_events = set(EVENT_TABLE_COLUMNS) - set(events.columns)
    if missing_events:
        raise ValueError(f"events artifact missing columns: {sorted(missing_events)}")
    if "company_name" not in summary.columns:
        raise ValueError("summary artifact missing column: company_name")

    events = events.copy()
    events["company_name"] = events["company_name"].fillna("").astype(str)
    events = events[events["company_name"].str.strip() != ""]
    summary = summary.copy()
    summary["company_name"] = summary["company_name"].fillna("").astype(str)
    summary = summary[summary["company_name"].str.strip() != ""]

    company_names = sorted(set(summary["company_name"]) | set(events["company_name"]))
    summary_rows = {
        str(row["company_name"]): row
        for row in summary.drop_duplicates("company_name").to_dict("records")
    }
    events_by_company = {
        name: group.sort_values(["event_date", "event_type"], ascending=[False, True])
        for name, group in events.groupby("company_name", sort=False)
    }

    firms: list[dict[str, Any]] = []
    for index, company_name in enumerate(company_names):
        row = summary_rows.get(company_name, {})
        firm_events = events_by_company.get(company_name, events.iloc[0:0])
        event_records = [
            {
                "date": _value(event["event_date"]),
                "type": _value(event["event_type"]),
                "subtype": _value(event["event_subtype"]),
                "amount": _value(event["amount_usd"]),
                "counterparty": _value(event["counterparty"]),
                "source_id": _value(event["source_id"]),
            }
            for event in firm_events.to_dict("records")
        ]
        source_ids = [record["source_id"] for record in event_records if record["source_id"]]
        firms.append(
            {
                "id": f"firm-{index + 1}",
                "name": company_name,
                "event_count": len(event_records),
                "event_type_count": int(_value(row.get("event_type_count")) or 0),
                "sbir_award_count": int(_value(row.get("sbir_award_count")) or 0),
                "total_sbir_amount": float(_value(row.get("total_sbir_amount")) or 0),
                "form_d_filing_count": int(_value(row.get("form_d_filing_count")) or 0),
                "total_form_d_raised": float(_value(row.get("total_form_d_raised")) or 0),
                "usaspending_contract_count": int(
                    _value(row.get("usaspending_contract_count")) or 0
                ),
                "total_usaspending_obligated": float(
                    _value(row.get("total_usaspending_obligated")) or 0
                ),
                "patent_count": int(_value(row.get("patent_count")) or 0),
                "ma_event_count": int(_value(row.get("ma_event_count")) or 0),
                "ucc_filing_count": int(_value(row.get("ucc_filing_count")) or 0),
                "latest_activity": _value(row.get("last_event_date")),
                "statuses": {
                    "sbir_awards": "observed",
                    "private_capital": "lower bound",
                    "contracts": "observed",
                    "patents": "observed",
                    "ma_events": "lower bound",
                },
                "source_ids": source_ids,
                "events": event_records,
            }
        )

    dated_events = pd.to_datetime(events["event_date"], errors="coerce").dropna()
    as_of = dated_events.max().date().isoformat() if not dated_events.empty else None
    created = generated_at or datetime.now(UTC)

    return {
        "schema_version": "1.0",
        "dataset": {
            "label": "Form D high-confidence cohort capital-event timeline",
            "research_question": "F1 unified capital-event timeline",
            "as_of": as_of,
            "generated_at": created.isoformat(),
            "tier": "exploratory",
            "citable": False,
            "interpretation": (
                "Observed public records for a bounded cohort; missing events are not negative findings."
            ),
            "sources": [
                {
                    "path": str(events_path),
                    "sha256": _sha256(events_path),
                    "role": "long-format capital events",
                },
                {
                    "path": str(summary_path),
                    "sha256": _sha256(summary_path),
                    "role": "per-firm summary",
                },
            ],
        },
        "metrics": [
            {
                "id": "firms",
                "label": "Cohort firms",
                "value": len(company_names),
                "status": "observed",
                "source": "capital_events_per_firm.parquet",
            },
            {
                "id": "events",
                "label": "Observed events",
                "value": len(events),
                "status": "observed",
                "source": "capital_events.parquet",
            },
            {
                "id": "sbir",
                "label": "SBIR award amount",
                "value": _sum_amount(events, "sbir_award"),
                "format": "currency",
                "status": "observed",
                "source": "capital_events.parquet",
            },
            {
                "id": "private-capital",
                "label": "Disclosed private capital",
                "value": _sum_amount(events, "form_d_filing"),
                "format": "currency",
                "status": "lower bound",
                "source": "capital_events.parquet",
            },
        ],
        "firms": firms,
    }


def export_terminal(events_path: Path, summary_path: Path, output_path: Path) -> dict[str, Any]:
    """Read canonical artifacts, fail closed, and write the browser payload."""
    missing = [path for path in (events_path, summary_path) if not path.exists()]
    if missing:
        rendered = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(
            f"capital-event artifacts not found: {rendered}; "
            "run scripts/data/build_capital_events.py first"
        )

    payload = build_terminal_payload(
        pd.read_parquet(events_path),
        pd.read_parquet(summary_path),
        events_path=events_path,
        summary_path=summary_path,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False))
    return payload


def main() -> int:
    args = _parser().parse_args()
    payload = export_terminal(args.events, args.summary, args.output)
    print(
        f"Wrote {args.output}: {len(payload['firms']):,} firms, "
        f"{payload['metrics'][1]['value']:,} observed events"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
