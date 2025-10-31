from pathlib import Path
from typing import Dict, Optional
import csv


class NAICSToBEAMapper:
    def __init__(self, mapping_path: Optional[str] = None):
        self.mapping_path = mapping_path or "data/reference/naics_to_bea.csv"
        self.map = {}  # prefix -> bea_sector
        self._load()

    def _load(self):
        p = Path(self.mapping_path)
        if not p.exists():
            return
        with p.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for r in reader:
                pref = r.get("naics_prefix")
                bea = r.get("bea_sector")
                if pref and bea:
                    self.map[pref.strip()] = bea.strip()

    def map_code(self, naics_code: str) -> Optional[str]:
        """Map a NAICS code (string) to a BEA sector using longest-prefix match.

        Returns BEA sector string or None if not found.
        """
        if not naics_code:
            return None
        code = naics_code.strip()
        # try longest-prefix match: check full code down to 2-digit
        for L in range(len(code), 1, -1):
            prefix = code[:L]
            if prefix in self.map:
                return self.map[prefix]
        # also try 2-digit fallback
        if len(code) >= 2 and code[:2] in self.map:
            return self.map[code[:2]]
        return None


__all__ = ["NAICSToBEAMapper"]
