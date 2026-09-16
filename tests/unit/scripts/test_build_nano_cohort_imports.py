"""The nano cohort script must set up sys.path before importing the repo."""

import ast
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "data" / "build_nano_cohort.py"


def _sys_path_insert_line(tree: ast.Module) -> int:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "insert"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "path"
        ):
            return node.lineno
    raise AssertionError("script no longer inserts the checkout root on sys.path")


def test_repo_imports_follow_the_sys_path_insert() -> None:
    # `python scripts/data/build_nano_cohort.py` is a documented invocation, so
    # in a checkout where sbir_etl is not installed every repo-local import has
    # to come after the path setup — otherwise the import fails, or silently
    # resolves a stale site-packages copy instead of this checkout.
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    insert_line = _sys_path_insert_line(tree)

    early = [
        f"{node.module} (line {node.lineno})"
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and (node.module or "").startswith(("sbir_etl", "sbir_analytics", "sbir_ml"))
        and node.lineno < insert_line
    ]

    assert early == [], f"repo-local imports precede sys.path setup: {early}"
