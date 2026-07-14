"""Unit tests for the tech-area cohort matcher (scripts/data/build_tech_area_cohort.py).

The matching engine is what specs/tech-area-transition-report exists to validate,
so it gets direct coverage here: Method-A resolution, soft-pattern gating in both
modes, the negative veto on soft-only admits, overlap stats, and the negation
diagnostic.
"""

import importlib.util
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "data" / "build_tech_area_cohort.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("build_tech_area_cohort", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load_script()


# Minimal QIS-shaped taxonomy: one keyword + one negative.
TAXONOMY = {
    "qis": {
        "cet_id": "qis",
        "name": "QIS",
        "keywords": ["quantum information"],
        "negative_keywords": ["quantum dot"],
    }
}


def _award(award_id, title, abstract):
    return {
        "award_id": award_id,
        "title": title,
        "abstract": abstract,
        "company": f"Co-{award_id}",
        "uei": f"U-{award_id}",
        "agency": "Department of Defense",
        "award_year": 2019,
        "award_amount": 1_000_000.0,
    }


def _compile(patterns):
    return [re.compile(p, re.IGNORECASE) for p in patterns]


# --------------------------------------------------------------------------- #
# resolve_method_a
# --------------------------------------------------------------------------- #


def test_resolve_method_a_keyword_pack_pulls_taxonomy_negatives():
    cfg = {
        "area_id": "qis",
        "cet_id": "qis",
        "keyword_pack": {
            "patterns": [r"\bqubit\b"],
            "soft_patterns": [r"\bquantum computing\b"],
            "negative_patterns": [r"\bhandwave\b"],
        },
    }
    core, soft, negatives, source = mod.resolve_method_a(cfg, TAXONOMY)
    assert source == "keyword_pack"
    assert len(core) == 1 and len(soft) == 1
    neg_patterns = [p.pattern for p in negatives]
    # pack negative kept AND taxonomy negative merged in
    assert any("handwave" in p for p in neg_patterns)
    assert any("quantum\\ dot" in p or "quantum dot" in p for p in neg_patterns)


def test_resolve_method_a_taxonomy_fallback():
    cfg = {"area_id": "qis", "cet_id": "qis"}  # no keyword_pack
    core, soft, negatives, source = mod.resolve_method_a(cfg, TAXONOMY)
    assert source == "taxonomy"
    assert len(core) == 1 and soft == []
    assert core[0].search("we use quantum information processing")


def test_resolve_method_a_empty_raises():
    cfg = {"area_id": "orphan", "cet_id": "missing", "keyword_pack": {}}
    with pytest.raises(ValueError):
        mod.resolve_method_a(cfg, TAXONOMY)


# --------------------------------------------------------------------------- #
# build_keyword_cohort — core / soft gating
# --------------------------------------------------------------------------- #


def _qis_patterns():
    core = _compile([r"\bqubit\b", r"\bquantum information\b"])
    soft = _compile([r"\bquantum computing\b", r"\bquantum sensing\b"])
    negatives = _compile([r"\bquantum dot\b", r"\bquantum well\b"])
    return core, soft, negatives


def test_core_hit_admits():
    core, soft, neg = _qis_patterns()
    awards = [_award("A", "Qubit control electronics", "A cryostat for a qubit.")]
    out = mod.build_keyword_cohort(awards, core, soft, neg, "keyword_pack")
    assert len(out) == 1
    assert out[0]["admitted_by"] == "core"


def test_soft_in_title_admits():
    core, soft, neg = _qis_patterns()
    awards = [_award("B", "Quantum computing accelerator", "General purpose HPC work.")]
    out = mod.build_keyword_cohort(awards, core, soft, neg, "keyword_pack")
    assert len(out) == 1
    assert out[0]["admitted_by"] == "soft_corroborated"


def test_soft_single_non_title_rejected():
    core, soft, neg = _qis_patterns()
    awards = [_award("C", "Generic widget", "This could help quantum computing someday.")]
    out = mod.build_keyword_cohort(awards, core, soft, neg, "keyword_pack")
    assert out == []


def test_soft_two_distinct_hits_admits():
    core, soft, neg = _qis_patterns()
    awards = [
        _award(
            "D",
            "Generic widget",
            "Useful for quantum computing and quantum sensing alike.",
        )
    ]
    out = mod.build_keyword_cohort(awards, core, soft, neg, "keyword_pack")
    assert len(out) == 1
    assert out[0]["admitted_by"] == "soft_corroborated"


# --------------------------------------------------------------------------- #
# build_keyword_cohort — the negative veto (the §1 fix)
# --------------------------------------------------------------------------- #


def test_negative_vetoes_soft_only_admit():
    """The cryocooler case: soft title-drop over a quantum-dot abstract → rejected."""
    core, soft, neg = _qis_patterns()
    awards = [
        _award(
            "E",
            "A cryocooler for quantum computing systems",
            "We grow quantum dot emitters and quantum well laser diodes. No qubits.",
        )
    ]
    out = mod.build_keyword_cohort(awards, core, soft, neg, "keyword_pack")
    assert out == [], "soft-only admit with a negative hit must be vetoed"


def test_core_admit_not_vetoed_by_negative():
    """A real qubit award that also mentions a quantum well still admits."""
    core, soft, neg = _qis_patterns()
    awards = [
        _award(
            "F",
            "Superconducting qubit readout",
            "Our qubit couples to a resonator; we compare against quantum well devices.",
        )
    ]
    out = mod.build_keyword_cohort(awards, core, soft, neg, "keyword_pack")
    assert len(out) == 1
    assert out[0]["admitted_by"] == "core"


def test_negative_veto_off_when_no_negatives_configured():
    core, soft, _ = _qis_patterns()
    awards = [
        _award(
            "G",
            "Quantum computing platform",
            "We reference quantum dot displays only in passing.",
        )
    ]
    out = mod.build_keyword_cohort(awards, core, soft, [], "keyword_pack")
    assert len(out) == 1  # no negatives → soft-only admit survives


# --------------------------------------------------------------------------- #
# build_keyword_cohort — core_cooccur mode (hypersonics)
# --------------------------------------------------------------------------- #


def _hyp_patterns():
    core = _compile([r"\bscramjet\b", r"\bhypersonic\b"])
    soft = _compile([r"\bthermal protection system\b", r"\bMach\s*[5-9]\b"])
    negatives = _compile([r"\bsupersonic\b"])
    return core, soft, negatives


def test_core_cooccur_rejects_soft_only():
    core, soft, neg = _hyp_patterns()
    awards = [_award("H", "Thermal protection system tiles", "A TPS for reentry.")]
    out = mod.build_keyword_cohort(
        awards, core, soft, neg, "keyword_pack", soft_requires="core_cooccur"
    )
    assert out == []


def test_core_cooccur_admits_core_even_with_supersonic():
    core, soft, neg = _hyp_patterns()
    awards = [
        _award(
            "I",
            "Scramjet inlet with thermal protection system",
            "Operates from supersonic to hypersonic Mach 7 flight.",
        )
    ]
    out = mod.build_keyword_cohort(
        awards, core, soft, neg, "keyword_pack", soft_requires="core_cooccur"
    )
    assert len(out) == 1
    assert out[0]["admitted_by"] == "core"


def test_unknown_soft_requires_raises():
    core, soft, neg = _hyp_patterns()
    with pytest.raises(ValueError):
        mod.build_keyword_cohort([], core, soft, neg, "keyword_pack", soft_requires="bogus")


# --------------------------------------------------------------------------- #
# overlap_stats
# --------------------------------------------------------------------------- #


def test_overlap_stats_basic():
    a = {"1", "2", "3", "4"}
    b = {"3", "4", "5"}
    s = mod.overlap_stats(a, b)
    assert s["intersection_n"] == 2
    assert s["union_n"] == 5
    assert s["jaccard"] == pytest.approx(2 / 5)
    assert s["containment_a_in_b"] == pytest.approx(2 / 4)
    assert s["containment_b_in_a"] == pytest.approx(2 / 3)


def test_overlap_stats_empty_is_none_not_crash():
    s = mod.overlap_stats(set(), set())
    assert s["jaccard"] is None
    assert s["containment_a_in_b"] is None


# --------------------------------------------------------------------------- #
# negation_spotcheck (diagnostic, does not change admission)
# --------------------------------------------------------------------------- #


def test_negation_spotcheck_flags_negated_positive():
    core, soft, neg = _qis_patterns()
    # Admitted on core "quantum information" but the phrase is negated in context.
    awards = [_award("J", "Radar processor", "This system does not involve quantum information.")]
    admitted = mod.build_keyword_cohort(awards, core, soft, neg, "keyword_pack")
    assert len(admitted) == 1  # regex admits it (can't read negation)
    result = mod.negation_spotcheck(admitted, core, soft)
    assert result["method_a_with_negated_positive"] == 1
    assert "quantum information" in result["sample"][0]["negated_positive"]


def test_negation_spotcheck_ignores_plain_positive():
    core, soft, neg = _qis_patterns()
    awards = [_award("K", "Qubit device", "We build a qubit with quantum information.")]
    admitted = mod.build_keyword_cohort(awards, core, soft, neg, "keyword_pack")
    result = mod.negation_spotcheck(admitted, core, soft)
    assert result["method_a_with_negated_positive"] == 0


# --------------------------------------------------------------------------- #
# dedupe_by_award_id + aggregate_composition (the composition emitter)
# --------------------------------------------------------------------------- #


def _comp_row(award_id, agency, company, uei, year, amount, program):
    return {
        "award_id": award_id,
        "agency": agency,
        "company": company,
        "uei": uei,
        "award_year": year,
        "award_amount": amount,
        "program": program,
        "title": "t",
        "abstract": "a",
    }


def _fixture_cohort():
    return [
        _comp_row("1", "Department of Defense", "Acme Inc", "U1", 2019, 1_000_000, "SBIR"),
        _comp_row("2", "Department of Defense", "Acme Inc", "U1", 2021, 1_000_000, "STTR"),
        _comp_row("3", "Department of Defense", "Beta LLC", "U2", 2023, 2_000_000, "SBIR"),
        _comp_row("4", "NASA", "Gamma", "", 2015, 500_000, "SBIR"),
        _comp_row("4", "NASA", "Gamma", "", 2015, 500_000, "SBIR"),  # dup award_id
        _comp_row("5", "NASA", "Delta", "U4", 2009, 3_000_000, "STTR"),
    ]


def test_dedupe_drops_duplicate_award_id():
    out = mod.dedupe_by_award_id(_fixture_cohort())
    assert [r["award_id"] for r in out] == ["1", "2", "3", "4", "5"]


def test_dedupe_keeps_rows_without_award_id():
    rows = [_comp_row("", "NASA", "X", "", 2019, 1, "SBIR")] * 2
    assert len(mod.dedupe_by_award_id(rows)) == 2  # empty id is not deduped


def test_dedupe_keeps_same_award_id_different_award():
    # DOE reuses award_id across a Phase II continuation/renewal (different
    # year) and across a successor-company change (different company) —
    # both are real, distinct awards and must not be dropped as duplicates.
    rows = [
        _comp_row("DE-1", "Department of Energy", "Acme Inc", "U1", 2019, 1_000_000, "SBIR"),
        _comp_row("DE-1", "Department of Energy", "Acme Inc", "U1", 2021, 1_100_000, "SBIR"),
        _comp_row("DE-2", "Department of Energy", "Acme Inc", "U1", 2020, 900_000, "SBIR"),
        _comp_row("DE-2", "Department of Energy", "Successor Inc", "U9", 2020, 900_000, "SBIR"),
    ]
    out = mod.dedupe_by_award_id(rows)
    assert len(out) == 4


def test_aggregate_composition_full():
    comp = mod.aggregate_composition(_fixture_cohort())
    assert comp["n_unique_awards"] == 5
    assert comp["duplicate_award_id_rows"] == 1

    dod = comp["by_agency"]["Department of Defense"]
    assert dod["awards"] == 3
    assert dod["share_pct"] == 60.0
    assert dod["phase2_dollars_m"] == 4.0
    assert dod["unique_firms"] == 2  # Acme (twice, same firm) + Beta

    nasa = comp["by_agency"]["NASA"]
    assert nasa["awards"] == 2
    assert nasa["phase2_dollars_m"] == 3.5

    assert comp["program_split"] == {"SBIR": 3, "STTR": 2, "sttr_pct": 40.0}
    assert comp["by_decade"] == {"2000s": 1, "2010s": 2, "2020s": 2}
    assert comp["censoring"]["mature_awards"] == 4
    assert comp["censoring"]["censored_awards"] == 1
    assert comp["entity_resolution"] == {"no_uei_awards": 1, "no_uei_pct": 20.0}
    assert comp["firm_concentration"]["top10_award_share_pct"] == 100.0
    assert comp["totals"] == {"awards": 5, "phase2_dollars_m": 7.5, "unique_firms": 4}


def test_aggregate_composition_agency_sorted_desc():
    comp = mod.aggregate_composition(_fixture_cohort())
    counts = [v["awards"] for v in comp["by_agency"].values()]
    assert counts == sorted(counts, reverse=True)


# --- T20: policy_brief_stub emitter --------------------------------------------

_CFG = {"area_id": "hypersonics", "display_name": "Hypersonics", "audience": "NSC staff"}


def _summary(signals_absent):
    return {
        "area_id": "hypersonics",
        "display_name": "Hypersonics",
        "overlap": {"intersection_n": 12, "jaccard": 0.34, "method_b_n": 40},
        "signals_absent": signals_absent,
    }


def _composition():
    return {
        "n_unique_awards": 300,
        "totals": {"awards": 300, "phase2_dollars_m": 512.4, "unique_firms": 210},
        "by_agency": {  # already sorted desc by awards (aggregate_composition shape)
            "DoD": {"awards": 250, "phase2_dollars_m": 400.0, "unique_firms": 180},
            "NASA": {"awards": 50, "phase2_dollars_m": 112.4, "unique_firms": 30},
        },
        "program_split": {"SBIR": 270, "STTR": 30, "sttr_pct": 10.0},
        "censoring": {"censor_year": 2023, "mature_awards": 240, "censored_awards": 60},
        "entity_resolution": {"no_uei_awards": 15, "no_uei_pct": 5.0},
    }


def test_policy_brief_stub_signals_absent_reports_not_computed():
    md = mod.render_policy_brief_stub(
        _CFG, _summary(["form_d_post_phase2", "ma_signal"]), _composition()
    )
    # Title + audience + provisional status from publication-format.md
    assert md.startswith("# Hypersonics SBIR/STTR Phase II Outcomes")
    assert "**Prepared for:** NSC staff" in md
    assert "Provisional" in md
    # Data-derived headline table
    assert "| Phase II cohort (Method A keyword) | 300 awards |" in md
    assert "DoD 250, NASA 50" in md
    assert "$512.4M" in md
    assert "Jaccard 0.340" in md
    # Absent signals are Not computed — never zero
    assert "`form_d_post_phase2` | Not computed — not zero" in md
    assert "`ma_signal` | Not computed — not zero" in md
    # Scaffold placeholders present, not published as-is
    assert "_TODO" in md
    assert "do not publish as-is" in md


def test_policy_brief_stub_signals_present():
    md = mod.render_policy_brief_stub(_CFG, _summary([]), _composition())
    assert "All expected transition-signal artifacts were present this run." in md
    assert "Not computed" not in md


def test_policy_brief_stub_tolerates_missing_blocks():
    # Minimal summary/composition must not raise; scalars degrade to n/a.
    md = mod.render_policy_brief_stub({"area_id": "x"}, {"signals_absent": []}, {})
    assert md.startswith("# x SBIR/STTR Phase II Outcomes")
    assert "n/a" in md


# --- T8: Method C (CPC patent-assignee) cohort ---------------------------------

_CPC_HEADER = [
    "patent_id",
    "grant_date",
    "filing_date",
    "assignee_organization",
    "assignee_type",
    "cpc_subclasses",
    "patent_title",
]


def _write_cpc_csv(path, rows):
    import csv as _csv

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = _csv.writer(f)
        w.writerow(_CPC_HEADER)
        w.writerows(rows)


def test_build_cpc_cohort_matches_by_normalized_assignee(tmp_path):
    cpc = tmp_path / "g06n10_patents.csv"
    _write_cpc_csv(
        cpc,
        [
            ["11", "2021-03-01", "2019-06-01", "Acme Quantum LLC", "2", "G06N10/00", "Qubit"],
            ["12", "2022-05-01", "2020-01-01", "Acme Quantum LLC", "2", "G06N10/40", "Gate"],
            ["13", "2020-01-01", "2018-01-01", "Unrelated Corp", "2", "G06N10/00", "Other"],
        ],
    )
    awards = [
        {"award_id": "A1", "company": "Acme Quantum Inc"},  # normalizes to match
        {"award_id": "A2", "company": "Nobody Systems"},  # no patent
    ]
    cohort = mod.build_cpc_cohort(awards, cpc)
    assert [r["award_id"] for r in cohort] == ["A1"]
    r = cohort[0]
    assert r["cohort_cpc"] is True
    assert r["cpc_b82_patent_count"] == 2  # legacy column name kept for compat
    assert r["cpc_first_b82_grant"] == "2021-03-01"
    assert r["cpc_first_b82_filing"] == "2019-06-01"
    assert "G06N10/00" in r["cpc_subclasses"] and "G06N10/40" in r["cpc_subclasses"]


def test_build_cpc_cohort_absent_extract_returns_empty(tmp_path):
    # Absence of the extract is not absence of activity — empty, no side effects.
    assert (
        mod.build_cpc_cohort([{"award_id": "A1", "company": "X"}], tmp_path / "missing.csv") == []
    )
