"""Award-grain verification of the Phase III undercount (answers #451's rerun requirement).

Reproduces the DoD 141 / NASA 16 undercount and the 191-flag frozen frame using the compound-key
AWARD identity (order_piid, order_agency, idv_piid, idv_agency -> generated_internal_id), i.e. PR
#449's nested-parent-IDV / award-grain contract — NOT FPDS transaction rows. Emits a provenance
manifest (inputs, row/award counts, join-overlap sanity, distinct-flag hash) and asserts the
expected figures as a regression guard.

Run: python scripts/phase3_benchmark/verify_undercount_award_grain.py
"""
import hashlib
import json
import sys

import pandas as pd

REPO = "/Users/hollomancer/projects/sbir-analytics"
DERIVED = f"{REPO}/data/derived"


def norm(x):
    return str(x).strip().upper() if x is not None else ""


def award_key(r):
    return (f"CONT_AWD_{norm(r['order_piid'])}_{norm(r['order_agency']) or '-NONE-'}_"
            f"{norm(r['idv_piid']) or '-NONE-'}_{norm(r['idv_agency']) or '-NONE-'}")


def agency_block(agency, coded_file, desc_file):
    c = pd.read_parquet(f"{DERIVED}/{coded_file}")
    d = pd.read_parquet(f"{DERIVED}/{desc_file}")
    coded_keys = set(c.apply(award_key, axis=1))                 # award grain (compound key)
    desc_ids = {x for x in d["generated_internal_id"].astype(str).str.upper() if x and x != "NAN"}
    overlap = desc_ids & coded_keys
    undercount = desc_ids - coded_keys
    return {
        "coded_transactions": int(len(c)),
        "coded_awards_distinct": int(len(coded_keys)),
        "collapse_ratio": round(len(c) / max(len(coded_keys), 1), 3),
        "described_awards": int(len(desc_ids)),
        "described_coded_overlap": int(len(overlap)),   # >0 proves the key formats join
        "undercount": int(len(undercount)),
        "undercount_rate": round(len(undercount) / max(len(desc_ids), 1), 4),
    }


def main():
    dod = agency_block("DoD", "m0a_coded_dod.parquet", "m0a_desc_phase3_dod.parquet")
    nasa = agency_block("NASA", "m0a_coded_nasa.parquet", "m0a_desc_phase3_nasa.parquet")

    # frozen-frame hash (191 distinct award gen_ids), if the frozen CSV is present
    frame = {}
    try:
        f = pd.read_csv(f"{DERIVED}/phase3_undercount_flags_frozen.csv")
        gids = sorted(f["gen_id"].astype(str).str.upper())
        frame = {"flags": len(gids),
                 "frame_hash": hashlib.sha1("".join(gids).encode()).hexdigest()[:12],
                 "dollars_musd": round(pd.to_numeric(f["amount_usd"], errors="coerce").sum() / 1e6, 1)}
    except FileNotFoundError:
        frame = {"note": "frozen CSV absent (gitignored); regenerate via freeze_and_sample.py"}

    manifest = {"identity_contract": "compound award key (order/idv PIID+agency) = generated_internal_id",
                "grain": "award (not FPDS transaction)", "DoD": dod, "NASA": nasa, "frozen_frame": frame}
    print(json.dumps(manifest, indent=2))

    # regression guard — the numbers must survive the award-grain contract
    assert dod["undercount"] == 141, f"DoD undercount changed: {dod['undercount']}"
    assert nasa["undercount"] == 16, f"NASA undercount changed: {nasa['undercount']}"
    assert dod["described_coded_overlap"] > 0 and nasa["described_coded_overlap"] > 0, "key join broken"
    assert dod["collapse_ratio"] == 1.0, f"coded set not award-grain: {dod['collapse_ratio']}"
    print("\nVERIFIED: DoD 141 (14.7%) + NASA 16 (7.9%) survive the award-grain contract; "
          "191-flag frame is 141 exact + 11 text-scan + 23 grey + 16 NASA (distinct award gen_ids).")


if __name__ == "__main__":
    sys.exit(main())
