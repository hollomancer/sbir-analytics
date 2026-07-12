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

    forbidden_roots = {"neo4j", "dagster", "sbir_graph", "duckdb"}
    for path in mcp_root.rglob("*.py"):
        roots = {module.split(".", maxsplit=1)[0] for module in _imports(path)}
        assert roots.isdisjoint(forbidden_roots), (
            f"{path} bypasses the API/service boundary via {roots & forbidden_roots}"
        )
