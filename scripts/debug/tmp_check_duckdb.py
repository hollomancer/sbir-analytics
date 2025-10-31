#!/usr/bin/env python3
"""
Diagnostic script for investigating DuckDB `read_csv_auto` behavior on the
tests/fixtures/sbir_sample.csv fixture.

This script tries a few variants of DuckDB's CSV reader and falls back to
pandas.read_csv to verify parseability. It prints shapes, column names and
the first few rows for quick inspection.

Usage:
    python sbir-etl/scripts/debug/tmp_check_duckdb.py
"""

import reprlib
import sys
from pathlib import Path

try:
    import duckdb
except Exception as e:
    print("duckdb import failed:", repr(e))
    print("Make sure you're running inside the project virtualenv where duckdb is installed.")
    sys.exit(2)

try:
    import pandas as pd
except Exception as e:
    print("pandas import failed:", repr(e))
    print("Make sure pandas is installed in the environment.")
    sys.exit(2)


CSV_PATH = Path("tests/fixtures/sbir_sample.csv")


def short_repr(obj, maxlen=200):
    """Safe, shortened repr for large objects."""
    return reprlib.repr(obj)[:maxlen]


def try_read(label, fn):
    """Run a read function and print diagnostics."""
    print("\n---", label)
    try:
        df = fn()
        # Some duckdb functions may return duckdb.DuckDBPyRelation or a pandas.DataFrame.
        # Coerce to pandas.DataFrame for consistent introspection if possible.
        try:
            import pandas as _pd

            if not isinstance(df, _pd.DataFrame):
                # duckdb.read_csv_auto returns a pandas DataFrame in many builds,
                # but relations can also be returned depending on API usage.
                try:
                    df = df.to_df()
                except Exception:
                    # fallback: attempt fetchdf via an in-memory connection if relation-like
                    pass
        except Exception:
            pass

        # Print summary
        try:
            rows = len(df)
        except Exception:
            rows = "<unknown>"

        try:
            cols = list(df.columns)
        except Exception:
            cols = "<unable to list columns>"

        print("shape:", rows, "rows")
        print("columns count:", (len(cols) if isinstance(cols, list) else cols))
        print("columns:", short_repr(cols))
        # Print first 3 rows if possible
        try:
            head = df.head(3)
            print("head:\n", head.to_string(index=False))
        except Exception as e:
            print("could not print head:", repr(e))

    except Exception as exc:
        print("ERROR:", repr(exc))


def read_with_duckdb_auto_default(path_str):
    """Call duckdb.read_csv_auto with default options."""
    return duckdb.read_csv_auto(path_str)


def read_with_duckdb_auto_quote(path_str, quotechar):
    """Call duckdb.read_csv_auto specifying a quotechar."""
    return duckdb.read_csv_auto(path_str, delim=",", header=True, quotechar=quotechar)


def sql_read_csv_auto_count(path_str, quote_sql='"""'):
    """
    Run a simple SQL query using read_csv_auto to get a row count and describe.
    `quote_sql` should be the SQL-level quote token to use in the `quote=` parameter.
    We format the SQL string carefully to avoid nested-quote issues.
    """
    conn = duckdb.connect(":memory:")
    try:
        # Build SQL snippet. We pass the file path directly into the SQL string and
        # use a quoted value for the quote char parameter. Example:
        # read_csv_auto('some.csv', delim=',', header=true, quote='"')
        sql = (
            "SELECT COUNT(*) AS c FROM read_csv_auto('{path}', delim=',', header=true, quote={quote})"
        ).format(path=path_str.replace("'", "''"), quote=quote_sql)
        res = conn.execute(sql).fetchall()
        return {"sql": sql, "count_result": res, "describe": None}
    finally:
        conn.close()


def sql_create_table_and_describe(path_str, quote_sql='"""'):
    """
    Create a table from read_csv_auto and return count and first few column descriptors.
    Note: this tries to be defensive; if DuckDB errors it raises and the caller will catch.
    """
    conn = duckdb.connect(":memory:")
    try:
        create_sql = (
            "CREATE TABLE tmp_sbir AS SELECT * FROM read_csv_auto('{path}', delim=',', header=true, quote={quote})"
        ).format(path=path_str.replace("'", "''"), quote=quote_sql)
        conn.execute(create_sql)
        cnt = conn.execute("SELECT COUNT(*) FROM tmp_sbir").fetchone()[0]
        desc = conn.execute("DESCRIBE tmp_sbir").fetchall()
        # Return a small summary
        return {"count": cnt, "describe_first": desc[:10]}
    finally:
        conn.close()


def main():
    if not CSV_PATH.exists():
        print("CSV file not found at:", CSV_PATH)
        sys.exit(1)

    path_str = str(CSV_PATH)

    # 1) duckdb.read_csv_auto default
    try_read("duckdb.read_csv_auto (default)", lambda: read_with_duckdb_auto_default(path_str))

    # 2) duckdb.read_csv_auto with explicit double-quote quotechar
    try_read(
        "duckdb.read_csv_auto (quotechar='\"')", lambda: read_with_duckdb_auto_quote(path_str, '"')
    )

    # 3) duckdb.read_csv_auto with explicit single-quote quotechar
    try_read(
        'duckdb.read_csv_auto (quotechar="\'")', lambda: read_with_duckdb_auto_quote(path_str, "'")
    )

    # 4) Run a SQL-level read_csv_auto COUNT() with quote set to the double-quote character.
    #    To express the SQL parameter quote='"' we set quote_sql='"' (we'll wrap it properly below)
    print("\n--- SQL-level read_csv_auto COUNT() attempts")
    try:
        # Build quote token in SQL as a single-quoted string containing a double-quote character:
        # quote = '"'
        sql_quote_token = "'\"'"
        result = sql_read_csv_auto_count(path_str, quote_sql=sql_quote_token)
        print("SQL count query executed. SQL:", result["sql"])
        print("Result:", result["count_result"])
    except Exception as e:
        print("SQL read_csv_auto COUNT() ERROR:", repr(e))

    # 5) Try creating a table from read_csv_auto and DESCRIBE it (double-quote as quote).
    print("\n--- SQL-level CREATE TABLE from read_csv_auto")
    try:
        sql_quote_token = "'\"'"
        res = sql_create_table_and_describe(path_str, quote_sql=sql_quote_token)
        print("Created table row count:", res["count"])
        print("Describe (first rows):", short_repr(res["describe_first"]))
    except Exception as e:
        print("SQL create table ERROR:", repr(e))

    # 6) pandas fallback to validate parseability
    print("\n--- pandas.read_csv fallback")
    try:
        dfp = pd.read_csv(path_str)
        print("pandas shape:", dfp.shape)
        try:
            print("pandas columns:", dfp.columns.tolist())
        except Exception:
            print("pandas columns: <unable to list>")
        try:
            print("pandas head:\n", dfp.head(3).to_string(index=False))
        except Exception as e:
            print("could not print pandas head:", repr(e))
    except Exception as e:
        print("pandas.read_csv ERROR:", repr(e))


if __name__ == "__main__":
    main()
