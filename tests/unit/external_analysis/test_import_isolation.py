from __future__ import annotations

import ast
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
ANALYTICS = REPO / "packages" / "sbir-analytics" / "sbir_analytics"


def _imported_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_definitions_does_not_import_edison_or_external_analysis() -> None:
    names = _imported_names(ANALYTICS / "definitions.py")
    assert all("edison" not in name.lower() for name in names)
    assert all("external_analysis" not in name for name in names)


def test_package_init_does_not_import_edison() -> None:
    names = _imported_names(ANALYTICS / "__init__.py")
    assert all("edison" not in name.lower() for name in names)
    assert all("external_analysis" not in name for name in names)


def test_external_analysis_package_does_not_import_edison_client() -> None:
    import sys

    sys.modules.pop("edison_client", None)
    for name in list(sys.modules):
        if name.startswith("edison_client."):
            sys.modules.pop(name)
    import sbir_analytics.external_analysis as package

    assert package.EPISTEMIC_TIER == "exploratory"
    assert "edison_client" not in sys.modules


def test_normal_package_import_does_not_load_edison() -> None:
    import sys

    sys.modules.pop("edison_client", None)
    import sbir_analytics

    assert "edison_client" not in sys.modules
    assert sbir_analytics.EPISTEMIC_TIER == "pipelines"
