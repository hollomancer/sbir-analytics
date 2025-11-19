#!/usr/bin/env python3
"""Gate on transition MVP validation summary."""
import json
import sys
from pathlib import Path


def main():
    """Check transition MVP validation gates and exit with appropriate code."""
    summary_path = Path("reports/validation/transition_mvp.json")
    
    if not summary_path.exists():
        print(f"::error file={summary_path}::Validation summary not found. Make sure the MVP run produced reports/validation/transition_mvp.json")
        sys.exit(2)
    
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    
    gates = data.get("gates", {})
    cs = gates.get("contracts_sample", {})
    vr = gates.get("vendor_resolution", {})
    
    cs_pass = bool(cs.get("passed", False))
    vr_pass = bool(vr.get("passed", False))
    
    print("Transition MVP validation summary:")
    print(json.dumps(data, indent=2))
    
    failures = []
    if not cs_pass:
        failures.append("contracts_sample coverage gate failed")
    if not vr_pass:
        failures.append("vendor_resolution rate gate failed")
    
    if failures:
        for f in failures:
            print(f"::error::{f}")
        sys.exit(1)
    else:
        print("All gates passed.")


if __name__ == '__main__':
    main()

