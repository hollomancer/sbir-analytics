import os
import sys
import json
from pathlib import Path

# ensure workspace root is on sys.path so `src` can be imported when running as a script
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import importlib.util

# load the naics_enricher module directly to avoid package-level import dependencies
naics_path = ROOT / "src" / "enrichers" / "naics_enricher.py"
spec = importlib.util.spec_from_file_location("naics_enricher_mod", str(naics_path))
naics_mod = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = naics_mod
spec.loader.exec_module(naics_mod)

NAICSEnricher = naics_mod.NAICSEnricher
NAICSEnricherConfig = naics_mod.NAICSEnricherConfig


def main():
    zip_path = Path("data/raw/usaspending/usaspending-db-subset_20251006.zip")
    if not zip_path.exists():
        print(f"USASPENDING ZIP not found at {zip_path}")
        return

    out_dir = Path("data/processed/usaspending")
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_path = out_dir / "naics_index.parquet"

    cfg = NAICSEnricherConfig(
        zip_path=str(zip_path),
        cache_path=str(cache_path),
        sample_only=True,
        max_files=3,
        max_lines_per_file=500,
    )

    enr = NAICSEnricher(cfg)
    # pandas parquet requires pyarrow/fastparquet; if not available, monkeypatch to write JSON fallback
    try:
        import pyarrow  # type: ignore
    except Exception:
        def _df_to_parquet(self, path, index=False, **kwargs):
            path = str(path)
            alt = path + ".json"
            self.to_json(alt, orient="records", lines=True)
            print(f"Wrote fallback JSON to {alt}")

        import pandas as _pd

        _pd.DataFrame.to_parquet = _df_to_parquet

    enr.load_usaspending_index(force=True)

    award_count = len(enr.award_map)
    recip_count = len(enr.recipient_map)

    # aggregate top NAICS
    from collections import Counter

    c = Counter()
    for vals in enr.award_map.values():
        for v in vals:
            c[v] += 1
    for vals in enr.recipient_map.values():
        for v in vals:
            c[v] += 1

    top = c.most_common(10)

    summary = {
        "award_entries": award_count,
        "recipient_entries": recip_count,
        "top_naics": top,
        "cache_path": str(cache_path),
    }

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
