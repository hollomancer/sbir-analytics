from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TERMINAL = PROJECT_ROOT / "tools" / "sbir-program-terminal"


def test_terminal_exposes_accessible_search_and_dossier_controls() -> None:
    html = (TERMINAL / "index.html").read_text(encoding="utf-8")

    assert '<html lang="en">' in html
    assert '<form id="search-form"' in html
    assert '<label class="sr-only" for="global-search">' in html
    assert 'aria-label="Cohort metrics"' in html
    assert 'aria-live="polite"' in html
    assert '<select id="event-filter">' in html
    assert 'href="favicon.svg"' in html


def test_terminal_does_not_commit_a_default_payload() -> None:
    ignored = (TERMINAL / "data" / ".gitignore").read_text(encoding="utf-8")

    assert ignored == "*\n!.gitignore\n"
    assert not (TERMINAL / "data" / "demo.json").exists()


def test_terminal_preserves_evidence_and_provenance_boundaries() -> None:
    app = (TERMINAL / "app.js").read_text(encoding="utf-8")
    readme = (TERMINAL / "README.md").read_text(encoding="utf-8")

    assert "payload.dataset?.citable !== false" in app
    assert 'payload.dataset?.tier !== "exploratory"' in app
    assert "metric.source" in app
    assert "metric.status" in app
    assert '"None observed"' in app
    assert "firm.statuses.private_capital" in app
    assert 'window.addEventListener("hashchange", syncNavigation)' in app
    assert 'fetch("data/terminal.json"' in app
    assert "The terminal fails closed" in app
    assert "**Target epistemic tier:** `exploratory`" in readme
    assert "does not ship data" in readme
    assert "fails closed" in readme
    assert "`tools/style-guide/`" in readme
