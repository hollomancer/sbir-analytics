#!/usr/bin/env python3
"""Verify that required dependencies are installed."""
import sys

try:
    import pandas
    import duckdb
    import pyreadstat
    
    print("pandas", pandas.__version__)
    print("duckdb", duckdb.__version__)
    print("pyreadstat", pyreadstat.__version__)
except Exception as e:
    print("Dependency verification failed:", e)
    raise




