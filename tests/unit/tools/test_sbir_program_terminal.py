import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TERMINAL = PROJECT_ROOT / "tools" / "sbir-program-terminal"


def test_terminal_exposes_accessible_search_screener_and_profile() -> None:
    html = (TERMINAL / "index.html").read_text(encoding="utf-8")

    assert '<html lang="en">' in html
    assert '<form id="search-form"' in html
    assert '<label class="sr-only" for="global-search">' in html
    assert 'aria-label="Program metrics"' in html
    assert 'aria-labelledby="firm-name"' in html
    assert "<th scope=\"col\">Organization</th>" in html


def test_terminal_demo_payload_is_explicitly_non_citable() -> None:
    payload = json.loads((TERMINAL / "data" / "demo.json").read_text(encoding="utf-8"))

    assert payload["schema_version"].endswith("-demo")
    assert payload["dataset"]["tier"] == "exploratory"
    assert payload["dataset"]["citable"] is False
    assert "invented" in payload["dataset"]["notice"].lower()
    assert payload["metrics"]
    assert payload["firms"]
    assert all(firm["uei"].startswith("DEMO-") for firm in payload["firms"])
    assert all(award["award_id"].startswith("DEMO-") for award in payload["awards"])


def test_terminal_preserves_evidence_and_provenance_boundaries() -> None:
    app = (TERMINAL / "app.js").read_text(encoding="utf-8")
    readme = (TERMINAL / "README.md").read_text(encoding="utf-8")

    assert 'payload.dataset.citable !== false' in app
    assert 'payload.dataset.tier !== "exploratory"' in app
    assert "metric.source" in app
    assert "metric.status" in app
    assert "synthetic demonstration data" in readme.lower()
    assert "not wired" in readme.lower()

