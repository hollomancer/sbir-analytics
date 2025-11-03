import csv
from pathlib import Path

import pandas as pd


class NAICSToBEAMapper:
    def __init__(self, mapping_path: str | None = None, bea_excel_path: str | None = None):
        self.mapping_path = mapping_path or "data/reference/naics_to_bea.csv"
        self.bea_excel_path = (
            bea_excel_path
            or "data/reference/BEA-Industry-and-Commodity-Codes-and-NAICS-Concordance.xlsx"
        )
        self.map = {}  # prefix -> bea_sector
        self.multi_map = {}  # bea_code -> List[naics_code]
        self._load()
        self._load_bea_excel()

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

    def _load_bea_excel(self):
        p = Path(self.bea_excel_path)
        if not p.exists():
            return
        try:
            df = pd.read_excel(p)
        except Exception:
            return
        # Expect columns: 'BEA Code', 'BEA Industry', 'NAICS Code', 'NAICS Description'
        # Some rows may have multiple NAICS codes per BEA code, separated by commas or semicolons
        for _, row in df.iterrows():
            bea_code = str(row.get("BEA Code", "")).strip()
            naics_codes = str(row.get("NAICS Code", "")).strip()
            if not bea_code or not naics_codes:
                continue
            # Split NAICS codes by comma, semicolon, or whitespace
            codes = [c.strip() for c in naics_codes.replace(";", ",").split(",") if c.strip()]
            if bea_code not in self.multi_map:
                self.multi_map[bea_code] = []
            self.multi_map[bea_code].extend(codes)

    def map_code(
        self, naics_code: str, vintage: str | None = None
    ) -> str | list[str] | None:
        """Map a NAICS code to BEA sector using longest-prefix match or multi-vintage mapping.

        If vintage is None, use default mapping. If vintage is 'bea', use BEA concordance spreadsheet.
        Returns BEA sector string or list of BEA codes if multi-mapping found.
        """
        if not naics_code:
            return None
        code = naics_code.strip()
        if vintage == "bea":
            # Search multi_map for BEA codes that include this NAICS code
            result = [bea for bea, naics_list in self.multi_map.items() if code in naics_list]
            return result if result else None
        # Default: try longest-prefix match
        for L in range(len(code), 1, -1):
            prefix = code[:L]
            if prefix in self.map:
                return self.map[prefix]
        if len(code) >= 2 and code[:2] in self.map:
            return self.map[code[:2]]
        return None


__all__ = ["NAICSToBEAMapper"]
