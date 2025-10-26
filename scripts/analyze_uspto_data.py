"""
Quick analysis script for USPTO patent assignment data.

This script analyzes the structure and relationships of USPTO patent assignment
data files to inform ETL strategy development.
"""

import pandas as pd
from pathlib import Path
from typing import Dict, Any


def analyze_file(filepath: Path) -> Dict[str, Any]:
    """Analyze a single Stata file and return summary statistics."""
    print(f"\n{'=' * 60}")
    print(f"Analyzing: {filepath.name}")
    print('=' * 60)

    try:
        # Read first chunk to get structure
        iterator = pd.read_stata(filepath, iterator=True, chunksize=1000)
        first_chunk = next(iterator)

        # Count total rows (sample-based estimate)
        sample_count = sum(1 for _ in iterator)
        estimated_rows = (sample_count + 1) * 1000

        info = {
            'filename': filepath.name,
            'columns': list(first_chunk.columns),
            'num_columns': len(first_chunk.columns),
            'estimated_rows': estimated_rows,
            'dtypes': first_chunk.dtypes.to_dict(),
            'sample_data': first_chunk.head(3),
        }

        print(f"Columns ({info['num_columns']}): {', '.join(info['columns'][:10])}")
        if len(info['columns']) > 10:
            print(f"  ... and {len(info['columns']) - 10} more")
        print(f"Estimated rows: ~{estimated_rows:,}")

        # Check for key linking fields
        if 'rf_id' in info['columns']:
            print(f"✓ Contains rf_id (assignment record ID)")

        # Show data types
        print("\nKey data types:")
        for col, dtype in list(info['dtypes'].items())[:5]:
            print(f"  {col}: {dtype}")

        # Show sample
        print("\nSample data (first row):")
        print(first_chunk.iloc[0].to_dict())

        return info

    except Exception as e:
        print(f"Error analyzing {filepath.name}: {e}")
        return {'filename': filepath.name, 'error': str(e)}


def main():
    """Run analysis on all USPTO data files."""
    data_dir = Path('data/raw/uspto')

    print("USPTO Patent Assignment Data Analysis")
    print("=" * 60)

    # Focus on key relational tables
    key_files = [
        'assignment.dta',          # Main assignment records
        'assignee.dta',            # Entities receiving rights
        'assignor.dta',            # Entities giving up rights
        'documentid.dta',          # Patent identifiers
        'assignment_conveyance.dta',  # Conveyance types
    ]

    results = {}
    for filename in key_files:
        filepath = data_dir / filename
        if filepath.exists():
            results[filename] = analyze_file(filepath)
        else:
            print(f"\nFile not found: {filename}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY: Data Relationships")
    print("=" * 60)
    print("""
The USPTO patent assignment dataset consists of several related tables:

1. **assignment.dta** - Core assignment records
   - Primary key: rf_id (reel/frame ID)
   - Contains: correspondent info, filing dates, conveyance text, page counts

2. **assignee.dta** - Patent assignees (recipients)
   - Foreign key: rf_id → assignment.rf_id
   - Contains: entity names and addresses
   - Relationship: Many assignees per assignment

3. **assignor.dta** - Patent assignors (originators)
   - Foreign key: rf_id → assignment.rf_id
   - Contains: entity names, execution dates, acknowledgment dates
   - Relationship: Many assignors per assignment

4. **documentid.dta** - Patent document identifiers
   - Foreign key: rf_id → assignment.rf_id
   - Contains: application numbers, publication numbers, grant numbers
   - Relationship: Many patents per assignment

5. **assignment_conveyance.dta** - Conveyance metadata
   - Foreign key: rf_id → assignment.rf_id
   - Contains: conveyance type, employer assignment flag
   - Relationship: One per assignment

**Key Insight**: All tables link via `rf_id` (reel/frame identifier).
The data models patent ownership transfers over time.
""")

    print("\nETL Strategy Recommendations:")
    print("1. Use rf_id as the primary linking key across all tables")
    print("2. Process in stages: assignment → conveyance → assignee/assignor → documentid")
    print("3. Handle missing values in dates and address fields")
    print("4. Parse conveyance text for structured information")
    print("5. Link patents via grant_doc_num to SBIR companies")


if __name__ == '__main__':
    main()
