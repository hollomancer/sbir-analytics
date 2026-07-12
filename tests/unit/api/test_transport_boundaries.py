"""Architecture guardrails for API-first, MCP-adapter-only integrations."""

import ast
from pathlib import Path


PACKAGE_ROOT = Path("packages/sbir-analytics/sbir_analytics")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def _forbidden_mcp_imports(path: Path) -> set[str]:
    imports = _imports(path)
    forbidden_roots = {"neo4j", "dagster", "sbir_graph", "duckdb"}
    forbidden_internal = {
        "sbir_analytics.api.repository",
        "sbir_analytics.api.snapshots",
        "api.repository",
        "api.snapshots",
    }
    return {
        module
        for module in imports
        if module.split(".", maxsplit=1)[0] in forbidden_roots
        or any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_internal)
    }


def test_domain_layers_do_not_depend_on_fastapi() -> None:
    """The repository and service remain reusable by HTTP and future MCP transports."""

    for name in ("repository.py", "service.py", "snapshots.py"):
        assert not any(
            module == "fastapi" or module.startswith("fastapi.")
            for module in _imports(PACKAGE_ROOT / "api" / name)
        )


def test_future_mcp_adapter_cannot_bypass_service_boundary() -> None:
    """Any future MCP package must not access storage or orchestration directly."""

    mcp_root = PACKAGE_ROOT / "mcp"
    if not mcp_root.exists():
        return

    for path in mcp_root.rglob("*.py"):
        forbidden = _forbidden_mcp_imports(path)
        assert not forbidden, f"{path} bypasses the API/service boundary via {forbidden}"


def test_mcp_boundary_detects_fully_qualified_internal_bypass(tmp_path: Path) -> None:
    bypass = tmp_path / "tool.py"
    bypass.write_text(
        "from sbir_analytics.api.repository import AnalyticsRepository\n", encoding="utf-8"
    )
    assert _forbidden_mcp_imports(bypass) == {"sbir_analytics.api.repository"}

    allowed = tmp_path / "allowed.py"
    allowed.write_text(
        "from sbir_analytics.api.service import AnalyticsService\n", encoding="utf-8"
    )
    assert not _forbidden_mcp_imports(allowed)
