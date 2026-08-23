"""Tests for the epistemic-tier import guard."""

from pathlib import Path

import pytest

from scripts.ci import check_tier_boundaries as guard


def write(root: Path, relative: str, content: str = "") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def scan(root: Path, allowlist: dict[str, frozenset[str]] | None = None):
    return guard.scan_repository(
        repository_root=root,
        package_roots={"pkg": Path("pkg"), "other": Path("other")},
        allowlist=allowlist or {},
    )


def declare(tier: str) -> str:
    return f'EPISTEMIC_TIER = "{tier}"\n'


def test_undeclared_modules_default_to_exploratory_and_import_freely(tmp_path):
    write(tmp_path, "pkg/__init__.py")
    write(tmp_path, "pkg/a.py", "from pkg import b\n")
    write(tmp_path, "pkg/b.py", "import pkg.a\n")
    assert scan(tmp_path) == []


def test_own_constant_beats_package_default(tmp_path):
    write(tmp_path, "pkg/__init__.py", declare("pipelines"))
    write(tmp_path, "pkg/model.py", declare("primitives") + "import pkg.mover\n")
    write(tmp_path, "pkg/mover.py")  # inherits pipelines
    violations = scan(tmp_path)
    assert len(violations) == 1
    assert "primitives module may not import pipelines module pkg.mover" in violations[0].message


def test_nested_package_default_uses_nearest_ancestor(tmp_path):
    write(tmp_path, "pkg/__init__.py", declare("pipelines"))
    write(tmp_path, "pkg/sub/__init__.py", declare("exploratory"))
    write(tmp_path, "pkg/sub/deep.py")  # exploratory via pkg.sub, not pipelines via pkg
    write(tmp_path, "pkg/consumer.py", "import pkg.sub.deep\n")
    violations = scan(tmp_path)
    assert len(violations) == 1
    assert violations[0].path == "pkg/consumer.py"
    assert "exploratory module pkg.sub.deep" in violations[0].message


def test_policy_rows(tmp_path):
    write(tmp_path, "pkg/__init__.py")
    write(tmp_path, "pkg/prim.py", declare("primitives"))
    write(tmp_path, "pkg/pipe.py", declare("pipelines") + "import pkg.prim\n")
    write(tmp_path, "pkg/evid.py", declare("evidence") + "import pkg.pipe\nimport pkg.expl\n")
    write(tmp_path, "pkg/expl.py", declare("exploratory") + "import pkg.evid\n")
    violations = scan(tmp_path)
    assert [v.path for v in violations] == ["pkg/evid.py"]
    assert "evidence module may not import exploratory module pkg.expl" in violations[0].message


def test_relative_imports_are_resolved(tmp_path):
    write(tmp_path, "pkg/__init__.py", declare("pipelines"))
    write(tmp_path, "pkg/expl.py", declare("exploratory"))
    write(tmp_path, "pkg/sub/__init__.py")
    write(tmp_path, "pkg/sub/mod.py", "from ..expl import thing\n")
    violations = scan(tmp_path)
    assert len(violations) == 1
    assert violations[0].path == "pkg/sub/mod.py"
    assert "pkg.expl" in violations[0].message


def test_from_package_import_resolves_submodule_not_init(tmp_path):
    write(tmp_path, "pkg/__init__.py", declare("pipelines"))
    write(tmp_path, "pkg/expl.py", declare("exploratory"))
    write(tmp_path, "pkg/user.py", "from pkg import expl\n")
    violations = scan(tmp_path)
    assert len(violations) == 1
    assert "exploratory module pkg.expl" in violations[0].message


def test_cross_root_edges_are_checked(tmp_path):
    write(tmp_path, "pkg/__init__.py", declare("pipelines"))
    write(tmp_path, "pkg/user.py", "import other.expl\n")
    write(tmp_path, "other/__init__.py")
    write(tmp_path, "other/expl.py")  # undeclared -> exploratory
    violations = scan(tmp_path)
    assert len(violations) == 1
    assert "other.expl" in violations[0].message


def test_dynamic_literal_import_is_caught(tmp_path):
    write(tmp_path, "pkg/__init__.py", declare("pipelines"))
    write(tmp_path, "pkg/expl.py", declare("exploratory"))
    write(
        tmp_path,
        "pkg/user.py",
        "import importlib\n\n\ndef load():\n    return importlib.import_module('pkg.expl')\n",
    )
    violations = scan(tmp_path)
    assert len(violations) == 1
    assert "pkg.expl" in violations[0].message


def test_allowlist_suppresses_and_stale_entry_fails(tmp_path):
    write(tmp_path, "pkg/__init__.py", declare("pipelines"))
    write(tmp_path, "pkg/expl.py", declare("exploratory"))
    write(tmp_path, "pkg/user.py", "import pkg.expl\n")

    allowed = {"pkg/user.py": frozenset({"pkg.expl"})}
    assert scan(tmp_path, allowed) == []

    stale = {
        "pkg/user.py": frozenset({"pkg.expl"}),
        "pkg/gone.py": frozenset({"pkg.expl"}),
    }
    violations = scan(tmp_path, stale)
    assert len(violations) == 1
    assert violations[0].path == "pkg/gone.py"
    assert "stale tier allowlist entry" in violations[0].message


def test_allowlisted_edge_that_became_legal_is_stale(tmp_path):
    write(tmp_path, "pkg/__init__.py", declare("pipelines"))
    write(tmp_path, "pkg/fine.py", declare("pipelines"))
    write(tmp_path, "pkg/user.py", "import pkg.fine\n")
    violations = scan(tmp_path, {"pkg/user.py": frozenset({"pkg.fine"})})
    assert len(violations) == 1
    assert "stale tier allowlist entry" in violations[0].message


def test_invalid_tier_constant_is_reported(tmp_path):
    write(tmp_path, "pkg/__init__.py")
    write(tmp_path, "pkg/bad.py", 'EPISTEMIC_TIER = "useful"\n')
    violations = scan(tmp_path)
    assert len(violations) == 1
    assert "EPISTEMIC_TIER must be a literal" in violations[0].message


def test_violation_format_includes_path_and_line(tmp_path):
    write(tmp_path, "pkg/__init__.py", declare("pipelines"))
    write(tmp_path, "pkg/expl.py", declare("exploratory"))
    write(tmp_path, "pkg/user.py", "import pkg.expl\n")
    violation = scan(tmp_path)[0]
    assert violation.format() == (
        "pkg/user.py:1: pipelines module may not import exploratory module pkg.expl"
    )


# The whole-repo scan parses every tracked Python file; the same invariant is
# enforced on every PR by the CI quality job running the script directly.
@pytest.mark.slow
def test_real_repository_passes():
    assert guard.scan_repository() == []
