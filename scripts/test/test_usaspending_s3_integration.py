#!/usr/bin/env python3
"""Test script for USAspending S3 integration.

Tests that:
1. S3 file discovery works
2. DuckDB can import from S3
3. Assets can find and use S3 files
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.extractors.usaspending import DuckDBUSAspendingExtractor
from src.utils.cloud_storage import find_latest_usaspending_dump, resolve_data_path


def test_s3_file_discovery():
    """Test finding latest dump in S3."""
    print("=" * 60)
    print("Test 1: S3 File Discovery")
    print("=" * 60)

    bucket = os.getenv("S3_BUCKET", "sbir-etl-production-data")

    # Test test database
    print(f"\nFinding latest test database in s3://{bucket}...")
    test_dump = find_latest_usaspending_dump(bucket=bucket, database_type="test")
    if test_dump:
        print(f"✅ Found test dump: {test_dump}")
    else:
        print("⚠️ No test dump found")

    # Test full database
    print(f"\nFinding latest full database in s3://{bucket}...")
    full_dump = find_latest_usaspending_dump(bucket=bucket, database_type="full")
    if full_dump:
        print(f"✅ Found full dump: {full_dump}")
    else:
        print("⚠️ No full dump found")

    return test_dump or full_dump


def test_s3_resolution(s3_url: str):
    """Test resolving S3 URL to local path."""
    print("\n" + "=" * 60)
    print("Test 2: S3 Path Resolution")
    print("=" * 60)

    print(f"\nResolving S3 URL: {s3_url}")
    try:
        local_path = resolve_data_path(s3_url)
        print(f"✅ Resolved to: {local_path}")
        print(f"   File exists: {local_path.exists()}")
        if local_path.exists():
            size_mb = local_path.stat().st_size / 1024 / 1024
            print(f"   Size: {size_mb:.2f} MB")
        return local_path
    except Exception as e:
        print(f"❌ Resolution failed: {e}")
        return None


def test_duckdb_import(dump_path):
    """Test importing dump into DuckDB."""
    print("\n" + "=" * 60)
    print("Test 3: DuckDB Import")
    print("=" * 60)

    if not dump_path or not dump_path.exists():
        print("⚠️ Skipping - dump file not available")
        return False

    print(f"\nImporting dump: {dump_path}")
    extractor = DuckDBUSAspendingExtractor(db_path=":memory:")

    try:
        # Try importing recipient_lookup table (smaller, faster)
        success = extractor.import_postgres_dump(dump_path, table_name="recipient_lookup")

        if success:
            print("✅ Import successful")

            # Query a sample
            df = extractor.query_awards(table_name="recipient_lookup", limit=5)
            print(f"   Sample rows: {len(df)}")
            if len(df) > 0:
                print(f"   Columns: {list(df.columns)[:5]}...")
            return True
        else:
            print("❌ Import failed")
            return False
    except Exception as e:
        print(f"❌ Import error: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        extractor.close()


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("USAspending S3 Integration Tests")
    print("=" * 60)

    # Test 1: File discovery
    s3_url = test_s3_file_discovery()

    if not s3_url:
        print("\n❌ No S3 dump found. Please download one first:")
        print("   python scripts/usaspending/download_database.py --database-type test")
        sys.exit(1)

    # Test 2: Path resolution
    dump_path = test_s3_resolution(s3_url)

    # Test 3: DuckDB import
    if dump_path:
        test_duckdb_import(dump_path)

    print("\n" + "=" * 60)
    print("Tests Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
