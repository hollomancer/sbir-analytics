"""The nano cohort script must set up sys.path before importing the repo."""

import ast
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "data" / "build_nano_cohort.py"
REPO_PACKAGES = ("sbir_etl", "sbir_analytics", "sbir_ml")


def _is_sys_path_insert(node: ast.AST) -> bool:
    """Match `sys.path.insert(...)` specifically, not any `*.path.insert(...)`."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "insert"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "path"
        and isinstance(node.func.value.value, ast.Name)
        and node.func.value.value.id == "sys"
    )


def _sys_path_insert_line(tree: ast.Module) -> int:
    # `ast.walk` is breadth-first, not source order, so take the earliest line
    # rather than the first node it happens to yield.
    lines = [node.lineno for node in ast.walk(tree) if _is_sys_path_insert(node)]
    if not lines:
        raise AssertionError("script no longer inserts the checkout root on sys.path")
    return min(lines)


def _repo_import_module(node: ast.AST) -> str | None:
    """Module name if `node` imports repo code, in either import form.

    `import sbir_etl.x` is an `ast.Import` and `from sbir_etl.x import y` is an
    `ast.ImportFrom`. Checking only the second lets the first reintroduce the
    defect this test exists to catch.
    """
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
    elif isinstance(node, ast.Import):
        module = node.names[0].name if node.names else ""
    else:
        return None
    return module if module.startswith(REPO_PACKAGES) else None


def test_repo_imports_follow_the_sys_path_insert() -> None:
    # `python scripts/data/build_nano_cohort.py` is a documented invocation, so
    # in a checkout where sbir_etl is not installed every repo-local import has
    # to come after the path setup — otherwise the import fails, or silently
    # resolves a stale site-packages copy instead of this checkout.
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    insert_line = _sys_path_insert_line(tree)

    early = sorted(
        f"{module} (line {node.lineno})"
        for node in ast.walk(tree)
        if (module := _repo_import_module(node)) is not None and node.lineno < insert_line
    )

    assert early == [], f"repo-local imports precede sys.path setup: {early}"
