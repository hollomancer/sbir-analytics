from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXPLORER = PROJECT_ROOT / "tools" / "sbir-dib-network-explorer"


def test_explorer_has_accessible_non_canvas_controls() -> None:
    html = (EXPLORER / "index.html").read_text(encoding="utf-8")

    assert '<html lang="en">' in html
    assert '<form id="search-form"' in html
    assert '<label for="node-search">' in html
    assert 'aria-label="Graph controls"' in html
    assert 'aria-label="Interactive graph of NSF awards, legal entities, and DoD funding"' in html
    assert html.count('aria-live="polite"') >= 2


def test_explorer_bounds_default_payload_and_exports_current_filter_slice() -> None:
    app = (EXPLORER / "app.js").read_text(encoding="utf-8")

    assert "overview: 500" in app
    assert "expanded: 1800" in app
    assert ".slice(0, densityLimits[graphDensity.value])" in app
    assert "function downloadVisibleRelationships()" in app
    assert "state.visibleEdges.forEach" in app
    assert "source_record_ids" in app
