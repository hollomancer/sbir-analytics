#!/usr/bin/env python3
"""Quick test script for SBIR DuckDB extractor."""

from src.extractors.sbir import SbirDuckDBExtractor

print("=" * 70)
print("TESTING SBIR DUCKDB EXTRACTOR")
print("=" * 70)

# Initialize extractor
extractor = SbirDuckDBExtractor(
    csv_path="data/raw/sbir/awards_data.csv", duckdb_path=":memory:", table_name="sbir_awards"
)

print("\n1. Importing CSV to DuckDB...")
metadata = extractor.import_csv()
print(f"   ✓ Imported {metadata['row_count']:,} records in {metadata['import_duration_seconds']}s")
print(f"   ✓ Speed: {metadata['records_per_second']:,} records/second")
print(f"   ✓ File size: {metadata['file_size_mb']} MB")

print("\n2. Getting table statistics...")
stats = extractor.get_table_stats()
print(f"   ✓ Year range: {stats['year_range']}")
print(f"   ✓ Unique agencies: {stats['unique_agencies']}")
print("   ✓ Phase distribution:")
for phase_info in stats["phase_distribution"]:
    print(f"      - {phase_info['Phase']}: {phase_info['count']:,} awards")

print("\n3. Testing filtered extraction (2024-2025)...")
df_recent = extractor.extract_by_year(2024, 2025)
print(f"   ✓ Extracted {len(df_recent):,} records for 2024-2025")
print("   ✓ Sample record:")
if len(df_recent) > 0:
    sample = df_recent.iloc[0]
    print(f"      Company: {sample['Company']}")
    print(f"      Title: {sample['Award Title'][:60]}...")
    print(f"      Amount: ${sample['Award Amount']:,.2f}")

print("\n4. Analyzing duplicates...")
duplicates = extractor.analyze_duplicates()
print(f"   ✓ Found {len(duplicates)} contracts with multiple records")
if len(duplicates) > 0:
    top_dup = duplicates.iloc[0]
    print("   ✓ Top duplicate:")
    print(f"      Contract: {top_dup['Contract']}")
    print(f"      Company: {top_dup['Company']}")
    print(f"      Phases: {top_dup['phases']}")
    print(f"      Years: {top_dup['years']}")

print("\n5. Analyzing missing values...")
missing = extractor.analyze_missing_values()
high_missing = missing[missing["null_percentage"] > 10].head(10)
print("   ✓ Columns with >10% missing values:")
for _, row in high_missing.iterrows():
    print(f"      - {row['column_name']}: {row['null_percentage']:.1f}% missing")

print("\n6. Award amount statistics...")
amounts = extractor.analyze_award_amounts()
print("   ✓ Top 5 agency/phase combinations by total funding:")
for _, row in amounts.head(5).iterrows():
    print(
        f"      - {row['Agency']} {row['Phase']}: ${row['total_funding']:,.0f} ({row['award_count']:,} awards)"
    )

print("\n" + "=" * 70)
print("✓ ALL TESTS PASSED!")
print("=" * 70)
