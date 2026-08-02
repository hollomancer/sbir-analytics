"""Tests for the firm-ranking lineage-feature helpers."""

import numpy as np

from scripts.phase3_benchmark.measure_firm_ranking import (
    _fusion_text,
    firm_bucket,
    normalize_name,
    notice_bucket,
)

_K = {"cw": 2.21, "cc": -0.71, "mw": 0.028, "mc": 0.204, "sw": 0.039, "sc": 0.131}


def test_normalize_and_buckets():
    assert normalize_name("Acme Photonics, Inc.") == "acme photonics"
    assert firm_bucket("Department of Defense", "Navy") == "NAVY"
    assert firm_bucket("Department of Health and Human Services", "") == "HHS"
    assert notice_bucket("DEPT OF DEFENSE", "DEPT OF THE ARMY") == "ARMY"
    assert notice_bucket("DEPT OF HEALTH", "") == "HHS"


def test_fusion_text_ranks_topical_firm_first():
    opp = "seeking a quantum radar system for electromagnetic sensing of aircraft"
    firms = [
        "quantum radar electromagnetic sensing platform for detecting aircraft",  # true
        "bioresorbable bone adhesive for cranial flap fixation",
        "logistics optimization software for supply chains",
    ]
    order = np.argsort(-_fusion_text(opp, firms, _K))
    assert int(order[0]) == 0
