#!/usr/bin/env python3
"""
Analyze SBIR data dictionary (Excel) and a CSV fixture to produce a
summary report that helps guide model and validator design.

This script performs:
- Heuristic parsing of the Excel data dictionary to extract expected
  columns, suggested data types, and descriptions.
- Reading the CSV fixture (robust to common quoting/formatting issues)
  and computing summary statistics per column:
    - example values (up to N)
    - dtype inference
    - missingness / null percentage
    - unique ratio / top values
    - heuristics for numeric/date/UEI/DUNS/ZIP/phone
- Comparison between data-dictionary columns and CSV columns:
    - missing in CSV
    - extra in CSV
    - column ordering differences
- Suggests coercion/validator rules for columns (e.g., coerce "Award Amount"
  from strings with commas, parse dates in common formats, enforce UEI length)
- Writes a Markdown report to `reports/sbir_data_dictionary_analysis.md`
  (and a JSON diagnostics file) for easy review.

Usage:
    python sbir-analytics/scripts/analyze_data_dictionary_and_csv.py \
        --dict docs/data/dictionaries/sbir_awards_data_dictionary.xlsx \
        --csv tests/fixtures/sbir_sample.csv \
        --out reports/sbir_data_dictionary_analysis.md

Notes:
- This script requires `pandas` and an engine capable of reading Excel files
  (openpyxl or xlrd). If they're not installed, the script will print an
  explanatory message and exit.
- The Excel data dictionary layout varies across projects. This script uses
  heuristics to find the sheet and header columns that look like a data
  dictionary (common header names: 'column', 'field', 'name', 'description',
  'type', 'data type', 'example', 'required').
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


# Try imports that may not be present in minimal environments.
try:
    import pandas as pd
except Exception:
    pd = None  # type: ignore

# ---- Helpers / Heuristics -------------------------------------------------


COMMON_FIELD_NAME_KEYS = [
    "column",
    "field",
    "name",
    "column name",
    "field name",
    "variable",
]
COMMON_DESC_KEYS = ["description", "desc", "notes"]
COMMON_TYPE_KEYS = ["type", "data type", "dtype"]
COMMON_EXAMPLE_KEYS = ["example", "examples", "sample"]
COMMON_REQUIRED_KEYS = ["required", "is required", "mandatory"]


def _normalize_header(h: str) -> str:
    return re.sub(r"\s+", " ", str(h).strip().lower())


def _choose_best_sheet(xls: pd.ExcelFile) -> str:
    """
    Choose the most likely sheet containing the data dictionary.
    Strategy:
      - Prefer sheets with names containing 'data', 'dictionary', or 'spec'
      - Otherwise choose the sheet with the most columns / non-empty cells
    """
    sheet_names = list(xls.sheet_names)
    [s.lower() for s in sheet_names]
    for keyword in ("data", "dictionary", "spec", "schema", "fields"):
        for s in sheet_names:
            if keyword in s.lower():
                return s
    # fallback: choose largest sheet (by cell count)
    best = None
    best_count = -1
    for s in sheet_names:
        try:
            df = xls.parse(s, nrows=50)  # small sample
            count = df.size
            if count > best_count:
                best_count = count
                best = s
        except Exception:
            continue
    return best or sheet_names[0]


def _find_column_by_keys(cols: list[str], keys: list[str]) -> str | None:
    """
    Return the first column name that matches any of the candidate keys heuristically.
    """
    normalized = {_normalize_header(c): c for c in cols}
    for key in keys:
        for k, orig in normalized.items():
            if key == k or key in k or k in key:
                return orig
    return None


def _is_date_like(series: pd.Series, sample_n: int = 20) -> bool:
    """
    Heuristic: check a sample of non-null values for date-like patterns.
    """
    if pd is None:
        return False
    vals = series.dropna().astype(str).head(sample_n).tolist()
    if not vals:
        return False
    date_like = 0
    for v in vals:
        v = v.strip()
        # common date patterns
        if re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            date_like += 1
        elif re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}$", v):
            date_like += 1
        elif re.match(r"^\d{1,2}-\d{1,2}-\d{2,4}$", v):
            date_like += 1
        else:
            # attempt parse with dateutil if installed
            try:
                from dateutil import parser as _parser  # type: ignore

                _parser.parse(v)
                date_like += 1
            except Exception:
                pass
    return date_like >= max(1, len(vals) // 2)


def _is_numeric_like(series: pd.Series, sample_n: int = 20) -> bool:
    """
    Heuristic: check if most sample values are numeric (allow commas, $).
    """
    if pd is None:
        return False
    vals = series.dropna().astype(str).head(sample_n).tolist()
    if not vals:
        return False
    numeric_like = 0
    for v in vals:
        v = v.strip()
        v_clean = re.sub(r"[,\$\s]", "", v)
        try:
            float(v_clean)
            numeric_like += 1
        except Exception:
            continue
    return numeric_like >= max(1, len(vals) // 2)


def _is_uei_like(series: pd.Series) -> bool:
    """UEI heuristic: after stripping non-alnum, length 12 for many samples."""
    if pd is None:
        return False
    vals = series.dropna().astype(str).head(50).tolist()
    if not vals:
        return False
    matches = 0
    for v in vals:
        cleaned = "".join(ch for ch in v if ch.isalnum())
        if len(cleaned) == 12:
            matches += 1
    return matches >= max(1, len(vals) // 3)


def _is_duns_like(series: pd.Series) -> bool:
    """DUNS heuristic: digits-only and 9 digits after cleaning."""
    if pd is None:
        return False
    vals = series.dropna().astype(str).head(50).tolist()
    if not vals:
        return False
    matches = 0
    for v in vals:
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) == 9:
            matches += 1
    return matches >= max(1, len(vals) // 3)


def _is_zip_like(series: pd.Series) -> bool:
    if pd is None:
        return False
    vals = series.dropna().astype(str).head(50).tolist()
    if not vals:
        return False
    matches = 0
    for v in vals:
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) in (5, 9):
            matches += 1
    return matches >= max(1, len(vals) // 3)


# ---- Core analysis functions ----------------------------------------------


@dataclass
class ColumnSpec:
    name: str
    dtype_hint: str | None = None
    description: str | None = None
    required: bool | None = None
    example: str | None = None


def parse_data_dictionary(xlsx_path: Path) -> tuple[list[ColumnSpec], dict[str, Any]]:
    """
    Parse the Excel data dictionary and return an ordered list of ColumnSpec.

    The function is heuristic: tries to find column-name, description, type and example
    columns based on common header names.
    """
    if pd is None:
        raise RuntimeError(
            "pandas is required to run this script. Please install pandas and an Excel engine (openpyxl)."
        )

    xlsx_path = Path(xlsx_path)
    if not xlsx_path.exists():
        raise FileNotFoundError(f"Data dictionary not found at: {xlsx_path}")

    xl = pd.ExcelFile(xlsx_path)
    sheet = _choose_best_sheet(xl)
    df = xl.parse(sheet, dtype=str)  # read everything as strings for heuristics
    df_columns = list(df.columns)

    # identify candidate columns
    col_name_col = _find_column_by_keys(df_columns, COMMON_FIELD_NAME_KEYS)
    desc_col = _find_column_by_keys(df_columns, COMMON_DESC_KEYS)
    type_col = _find_column_by_keys(df_columns, COMMON_TYPE_KEYS)
    example_col = _find_column_by_keys(df_columns, COMMON_EXAMPLE_KEYS)
    required_col = _find_column_by_keys(df_columns, COMMON_REQUIRED_KEYS)

    specs: list[ColumnSpec] = []
    for _, row in df.iterrows():
        name = None
        if col_name_col:
            name = str(row.get(col_name_col)).strip()
        else:
            # fallback: first non-null cell in the row
            for c in df_columns[:5]:
                val = row.get(c)
                if pd.notna(val) and str(val).strip():
                    name = str(val).strip()
                    break
        if not name or name.lower() in ("nan", "<na>"):
            continue

        desc = str(row.get(desc_col)).strip() if desc_col and pd.notna(row.get(desc_col)) else None
        dtype = str(row.get(type_col)).strip() if type_col and pd.notna(row.get(type_col)) else None
        example = (
            str(row.get(example_col)).strip()
            if example_col and pd.notna(row.get(example_col))
            else None
        )
        required = None
        if required_col and pd.notna(row.get(required_col)):
            rv = str(row.get(required_col)).strip().lower()
            required = rv in ("y", "yes", "true", "required", "1")

        specs.append(
            ColumnSpec(
                name=name, dtype_hint=dtype, description=desc, required=required, example=example
            )
        )

    meta = {
        "sheet": sheet,
        "col_name_col": col_name_col,
        "desc_col": desc_col,
        "type_col": type_col,
        "example_col": example_col,
        "required_col": required_col,
        "raw_header": df_columns,
    }
    return specs, meta


def analyze_csv(csv_path: Path, max_preview: int = 5) -> dict[str, Any]:
    """
    Read CSV using pandas with conservative options and compute per-column statistics.

    Returns a dictionary keyed by column name with summary stats.
    """
    if pd is None:
        raise RuntimeError("pandas is required to run this script.")

    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV fixture not found at: {csv_path}")

    # Try a forgiving read
    read_kwargs = {
        "encoding": "utf-8",
        "dtype": str,  # read as strings for robust inspection
        "keep_default_na": False,
        "na_values": ["", "NA", "N/A", "None"],
    }

    # Attempt read; if it fails, attempt a more permissive approach
    try:
        df = pd.read_csv(csv_path, **read_kwargs)
    except Exception as exc:
        # Second attempt: allow python engine and more tolerant parsing
        try:
            df = pd.read_csv(csv_path, engine="python", **read_kwargs)
        except Exception as exc2:
            raise RuntimeError(f"Failed to read CSV fixture: {exc} / {exc2}")

    summary: dict[str, Any] = {}
    summary["row_count"] = len(df)
    summary["columns"] = list(df.columns)
    summary["preview_rows"] = df.head(max_preview).to_dict(orient="records")
    per_column: dict[str, dict[str, Any]] = {}

    for col in df.columns:
        ser = df[col]
        non_null_count = ser.replace("", pd.NA).dropna().shape[0]
        total = len(ser)
        pct_missing = round(100.0 * (total - non_null_count) / total, 2) if total > 0 else 0.0
        unique_count = ser.nunique(dropna=True)
        top_values = ser.value_counts(dropna=True).head(5).to_dict()
        examples = ser.dropna().astype(str).head(5).tolist()

        dtype_suggestion = "string"
        if _is_date_like(ser):
            dtype_suggestion = "date"
        elif _is_numeric_like(ser):
            dtype_suggestion = "numeric"
        elif _is_uei_like(ser):
            dtype_suggestion = "uei"
        elif _is_duns_like(ser):
            dtype_suggestion = "duns"
        elif _is_zip_like(ser):
            dtype_suggestion = "zip"

        per_column[col] = {
            "total": total,
            "non_null": non_null_count,
            "pct_missing": pct_missing,
            "unique": unique_count,
            "top_values": top_values,
            "examples": examples,
            "dtype_suggestion": dtype_suggestion,
        }

    summary["per_column"] = per_column
    return summary


def compare_dictionary_and_csv(
    dict_specs: list[ColumnSpec], csv_summary: dict[str, Any]
) -> dict[str, Any]:
    """Compare data dictionary specs against CSV columns and return a comparison summary."""
    csv_cols = csv_summary.get("columns", [])
    dict_cols = [spec.name for spec in dict_specs]
    missing_in_csv = [c for c in dict_cols if c not in csv_cols]
    extra_in_csv = [c for c in csv_cols if c not in dict_cols]
    [c for c in dict_cols if c in csv_cols and dict_cols.index(c) != csv_cols.index(c)]
    # order_mismatches above is simplistic; instead compute positional diffs
    positional_diff = []
    for i, c in enumerate(dict_cols):
        if c in csv_cols:
            j = csv_cols.index(c)
            if i != j:
                positional_diff.append({"column": c, "dict_idx": i, "csv_idx": j})

    return {
        "dict_cols": dict_cols,
        "csv_cols": csv_cols,
        "missing_in_csv": missing_in_csv,
        "extra_in_csv": extra_in_csv,
        "positional_diff": positional_diff,
    }


def suggest_validators(dict_specs: list[ColumnSpec], csv_summary: dict[str, Any]) -> dict[str, Any]:
    """
    Based on dictionary hints and CSV analysis, produce suggestions for validators.
    """
    suggestions: dict[str, dict[str, Any]] = {}
    per_col = csv_summary.get("per_column", {})
    for spec in dict_specs:
        name = spec.name
        col_summary = per_col.get(name)
        s: dict[str, Any] = {}
        if spec.dtype_hint:
            s["dtype_hint"] = spec.dtype_hint
        if col_summary:
            s["pct_missing"] = col_summary["pct_missing"]
            s["dtype_suggestion"] = col_summary["dtype_suggestion"]
            if col_summary["dtype_suggestion"] == "numeric":
                s["coerce"] = "strip commas, cast to float"
                s["validator"] = "positive and reasonable range (domain specific)"
            elif col_summary["dtype_suggestion"] == "date":
                s["coerce"] = "parse ISO, YYYY-MM-DD, MM/DD/YYYY, MM-DD-YYYY, etc."
            elif col_summary["dtype_suggestion"] == "uei":
                s["coerce"] = "strip non-alnum, uppercase; expect 12 chars"
                s["validator"] = "warn if not 12 chars"
            elif col_summary["dtype_suggestion"] == "duns":
                s["coerce"] = "strip non-digits; expect 9 digits"
            elif col_summary["dtype_suggestion"] == "zip":
                s["coerce"] = "strip non-digits; expect 5 or 9 digits"
        else:
            s["note"] = "column not present in CSV or no data summary available"
        suggestions[name] = s
    return suggestions


def render_markdown_report(
    out_path: Path,
    dict_specs: list[ColumnSpec],
    dict_meta: dict[str, Any],
    csv_summary: dict[str, Any],
    compare_summary: dict[str, Any],
    validator_suggestions: dict[str, Any],
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write("# SBIR Data Dictionary & CSV Analysis\n\n")
        f.write(f"Generated: {datetime.utcnow().isoformat()} UTC\n\n")
        f.write("## Summary\n\n")
        f.write(f"- CSV rows: **{csv_summary.get('row_count', 'N/A')}**\n")
        f.write(f"- CSV columns: **{len(csv_summary.get('columns', []))}**\n")
        f.write(f"- Dictionary columns: **{len(dict_specs)}**\n\n")

        f.write("## Comparison\n\n")
        f.write("### Missing in CSV (present in data dictionary)\n\n")
        if compare_summary["missing_in_csv"]:
            for c in compare_summary["missing_in_csv"]:
                f.write(f"- {c}\n")
        else:
            f.write("- None\n")
        f.write("\n### Extra columns in CSV (not in data dictionary)\n\n")
        if compare_summary["extra_in_csv"]:
            for c in compare_summary["extra_in_csv"]:
                f.write(f"- {c}\n")
        else:
            f.write("- None\n")
        f.write("\n")

        f.write("## Column Summaries (CSV)\n\n")
        for col in csv_summary.get("columns", []):
            pc = csv_summary["per_column"].get(col, {})
            f.write(f"### `{col}`\n\n")
            f.write(f"- Missing: {pc.get('pct_missing', 'N/A')}%\n")
            f.write(f"- Unique values: {pc.get('unique', 'N/A')}\n")
            f.write(f"- Type suggestion: {pc.get('dtype_suggestion', 'N/A')}\n")
            f.write(f"- Top values: {json.dumps(pc.get('top_values', {}))}\n")
            ex = pc.get("examples", [])
            if ex:
                f.write(f"- Examples: {', '.join(repr(x) for x in ex)}\n")
            f.write("\n")

        f.write("## Data Dictionary Extract (first 50 entries)\n\n")
        for spec in dict_specs[:50]:
            f.write(f"- **{spec.name}**")
            if spec.dtype_hint:
                f.write(f" — _{spec.dtype_hint}_")
            if spec.required:
                f.write(" — **REQUIRED**")
            if spec.description:
                f.write(f"\n  - {spec.description}\n")
            if spec.example:
                f.write(f"  - Example: {spec.example}\n")
            f.write("\n")

        f.write("## Suggested Validators / Coercions\n\n")
        for col, s in validator_suggestions.items():
            f.write(f"### `{col}`\n\n")
            for k, v in s.items():
                f.write(f"- **{k}**: {v}\n")
            f.write("\n")

        f.write("## Notes & Next Steps\n\n")
        f.write(
            "- Review columns marked 'missing in CSV' to determine whether they are optional or upstream is missing data.\n"
        )
        f.write(
            "- Implement coercion helpers for numeric/date fields, and add explicit validators for UEI/DUNS/ZIP based on suggestions above.\n"
        )
        f.write(
            "- Expand CSV fixtures with edge cases (missing UEI, varied date formats, amount strings with commas) for robust unit tests.\n"
        )
        f.write("\n---\n")
        f.write("Report generated by sbir-analytics/scripts/analyze_data_dictionary_and_csv.py\n")


def write_json_diagnostics(out_path: Path, payload: dict[str, Any]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)


# ---- CLI -----------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze SBIR data dictionary (Excel) and CSV fixture."
    )
    parser.add_argument(
        "--dict",
        "-d",
        default="docs/data/dictionaries/sbir_awards_data_dictionary.xlsx",
        help="Path to data dictionary Excel file.",
    )
    parser.add_argument(
        "--csv", "-c", default="tests/fixtures/sbir_sample.csv", help="Path to CSV fixture."
    )
    parser.add_argument(
        "--out",
        "-o",
        default="reports/sbir_data_dictionary_analysis.md",
        help="Output markdown report path.",
    )
    parser.add_argument(
        "--json",
        default="reports/sbir_data_dictionary_analysis.json",
        help="Output JSON diagnostics",
    )
    args = parser.parse_args(argv)

    dict_path = Path(args.dict)
    csv_path = Path(args.csv)
    out_md = Path(args.out)
    out_json = Path(args.json)

    try:
        dict_specs, dict_meta = parse_data_dictionary(dict_path)
    except Exception as e:
        print(f"ERROR parsing data dictionary: {e}")
        return 2

    try:
        csv_summary = analyze_csv(csv_path)
    except Exception as e:
        print(f"ERROR analyzing CSV: {e}")
        return 3

    compare = compare_dictionary_and_csv(dict_specs, csv_summary)
    suggestions = suggest_validators(dict_specs, csv_summary)

    # Render outputs
    render_markdown_report(out_md, dict_specs, dict_meta, csv_summary, compare, suggestions)
    diagnostics = {
        "dict_meta": dict_meta,
        "compare": compare,
        "suggestions": suggestions,
        "csv_summary_preview": {
            k: v for k, v in csv_summary.items() if k in ("row_count", "columns")
        },
    }
    write_json_diagnostics(out_json, diagnostics)

    print(f"Analysis complete. Report written to: {out_md}")
    print(f"Diagnostics written to: {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
