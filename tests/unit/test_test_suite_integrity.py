"""Static safeguards against silently empty pytest suites."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AUDITED_TEST_ROOTS = (
    REPOSITORY_ROOT / "tests/integration",
    REPOSITORY_ROOT / "tests/e2e",
    REPOSITORY_ROOT / "tests/validation",
)

# Abstract test helpers may be registered here only with a concrete reason. Keeping this
# empty is intentional: every current ``Test*`` class in the audited suites is concrete.
ALLOWED_ABSTRACT_PASS_ONLY_CLASSES: dict[tuple[str, str], str] = {}

# These are operator-facing validation programs despite their historical test_ filenames.
# They are inventoried so the static check distinguishes them from accidentally emptied tests.
NON_PYTEST_VALIDATION_SCRIPTS = {
    "tests/validation/test_categorization_quick.py": "standalone quick-check program",
    "tests/validation/test_patentsview_enrichment.py": "standalone service-backed validation CLI",
}


def _test_modules() -> list[Path]:
    return sorted(path for root in AUDITED_TEST_ROOTS for path in root.rglob("test_*.py"))


def _relative(path: Path) -> str:
    return path.relative_to(REPOSITORY_ROOT).as_posix()


def _without_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        if isinstance(body[0].value.value, str):
            return body[1:]
    return body


def _is_pass_only_test_class(node: ast.ClassDef) -> bool:
    body = _without_docstring(node.body)
    return (
        node.name.startswith("Test")
        and bool(body)
        and all(isinstance(item, ast.Pass) for item in body)
    )


def _defines_executable_test(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
            "test_"
        ):
            return True
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            if any(
                isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name.startswith("test_")
                for item in node.body
            ):
                return True
    return False


def test_concrete_test_classes_are_not_pass_only():
    """Fail with class names and paths when a concrete test suite silently becomes empty."""
    violations: list[str] = []
    for path in _test_modules():
        relative_path = _relative(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or not _is_pass_only_test_class(node):
                continue
            key = (relative_path, node.name)
            if key not in ALLOWED_ABSTRACT_PASS_ONLY_CLASSES:
                violations.append(f"{relative_path}:{node.lineno} ({node.name})")

    assert not violations, "Concrete test classes containing only pass:\n" + "\n".join(violations)


def test_test_modules_define_executable_tests_or_are_documented_scripts():
    """Prevent principal pytest coverage from being removed without explicit reclassification."""
    empty_modules = []
    for path in _test_modules():
        relative_path = _relative(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)
        if (
            not _defines_executable_test(tree)
            and relative_path not in NON_PYTEST_VALIDATION_SCRIPTS
        ):
            empty_modules.append(relative_path)

    assert not empty_modules, "Test modules with zero executable tests:\n" + "\n".join(
        empty_modules
    )


@pytest.mark.parametrize("path, reason", NON_PYTEST_VALIDATION_SCRIPTS.items())
def test_documented_non_pytest_validation_scripts_remain_operator_programs(path: str, reason: str):
    """Keep zero-test exceptions narrow and documented rather than silently expanding them."""
    source = (REPOSITORY_ROOT / path).read_text(encoding="utf-8")
    assert reason
    assert 'if __name__ == "__main__"' in source or source.startswith("#!/usr/bin/env python3")
