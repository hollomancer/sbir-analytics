from pathlib import Path

import pandas as pd

out = Path("tests/fixtures/naics_index_fixture.parquet")
out.parent.mkdir(parents=True, exist_ok=True)

rows = [
    {"key_type": "award", "key": "A12345", "naics_candidates": ["541330", "541519"]},
    {"key_type": "recipient", "key": "R-UEI-001", "naics_candidates": ["541330"]},
    {"key_type": "award", "key": "A98765", "naics_candidates": ["334510"]},
]

df = pd.DataFrame(rows)
df.to_parquet(out, index=False)
print(f"Wrote fixture to {out}")
