"""Unit tests for the generalized CPC patent extractor (T8).

The extractor is data-heavy (streams ~60M PatentsView CPC rows), so we cover its
one generalization-critical pure function — the CPC prefix predicate that lets it
serve nanotech (B82 subclass) and quantum (G06N10 group) from the same code.
"""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "data" / "extract_b82_patents.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("extract_b82_patents", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load_script()


def test_cpc_matches_b82_subclass_default():
    # Nanotech default: B82 prefix over the cpc_subclass field.
    assert mod.cpc_matches("B82Y", ("B82",))
    assert mod.cpc_matches("B82B", ("B82",))
    assert not mod.cpc_matches("G06N", ("B82",))


def test_cpc_matches_g06n10_group():
    # Quantum: G06N10 is a CPC group, matched over the cpc_group field
    # (e.g. "G06N10/00"); the narrower prefix must not catch sibling G06N groups.
    assert mod.cpc_matches("G06N10/00", ("G06N10",))
    assert mod.cpc_matches("G06N10/40", ("G06N10",))
    assert not mod.cpc_matches("G06N3/00", ("G06N10",))  # neural nets, not QIS
    assert not mod.cpc_matches("G06N20/00", ("G06N10",))


def test_cpc_matches_multiple_prefixes():
    assert mod.cpc_matches("B82Y", ("B82Y", "B82B"))
    assert not mod.cpc_matches("H01L", ("B82Y", "B82B"))


def test_extractor_defaults_are_backward_compatible():
    # Sanity: the module still targets the nanotech B82 output by default so an
    # unflagged run reproduces the original extract.
    assert mod.OUT_CSV.name == "b82_patents.csv"
