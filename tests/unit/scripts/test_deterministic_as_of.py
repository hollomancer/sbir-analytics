"""Tests for the deterministic as-of guard."""

from __future__ import annotations

from pathlib import Path

from scripts.ci import check_deterministic_as_of as guard


def _write(root: Path, relative: str, source: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_argparse_wall_clock_default_is_refused() -> None:
    source = (
        "from datetime import date\n"
        "\n"
        "def build(parser):\n"
        '    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())\n'
    )

    violations = guard.scan_source(source, "scripts/data/example.py")

    assert len(violations) == 1
    assert violations[0].line_number == 4
    assert "--as-of defaults to the wall clock" in violations[0].message


def test_utc_now_default_is_refused() -> None:
    source = (
        "from datetime import UTC, datetime\n"
        "\n"
        "def build(parser):\n"
        '    parser.add_argument("--as-of", default=datetime.now(UTC).date())\n'
    )

    assert len(guard.scan_source(source, "scripts/data/example.py")) == 1


def test_required_and_manifest_backed_defaults_pass() -> None:
    source = (
        "from datetime import date\n"
        "\n"
        "def build(parser, manifest):\n"
        '    parser.add_argument("--as-of", type=date.fromisoformat, required=True)\n'
        '    parser.add_argument("--as-of-date", default=manifest.as_of)\n'
        '    parser.add_argument("--until", default=date.today())\n'
    )

    assert guard.scan_source(source, "scripts/data/example.py") == []


def test_module_constant_is_refused() -> None:
    source = "from datetime import date\n\nDEFAULT_AS_OF = date.today()\n"

    violations = guard.scan_source(source, "scripts/data/example.py")

    assert len(violations) == 1
    assert "DEFAULT_AS_OF is initialised from the wall clock" in violations[0].message


def test_function_parameter_default_is_refused() -> None:
    source = (
        "from datetime import date\n"
        "\n"
        "def summarise(rows, as_of=date.today(), *, as_of_utc=None):\n"
        "    return rows\n"
    )

    violations = guard.scan_source(source, "scripts/data/example.py")

    assert len(violations) == 1
    assert "summarise() defaults as_of to the wall clock" in violations[0].message


def test_generated_at_stamp_is_not_refused() -> None:
    source = (
        "from datetime import UTC, datetime\n"
        "\n"
        "def summary(as_of):\n"
        '    return {"as_of": as_of.isoformat(), "generated_at": datetime.now(UTC).isoformat()}\n'
    )

    assert guard.scan_source(source, "scripts/data/example.py") == []


def test_allowlisted_path_is_skipped(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "scripts/data/legacy.py",
        "from datetime import date\n\n"
        "def build(p):\n"
        '    p.add_argument("--as-of", default=date.today())\n',
    )

    violations = guard.validate_repository(
        root=tmp_path,
        allowlist={"scripts/data/legacy.py": "predates this guard"},
        scan_roots=("scripts",),
    )

    assert violations == []


def test_stale_allowlist_entry_is_reported(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "scripts/data/fixed.py",
        'def build(p):\n    p.add_argument("--as-of", required=True)\n',
    )

    violations = guard.validate_repository(
        root=tmp_path,
        allowlist={"scripts/data/fixed.py": "predates this guard"},
        scan_roots=("scripts",),
    )

    assert len(violations) == 1
    assert "stale allowlist entry" in violations[0].message
    assert "no longer reads the clock" in violations[0].message


def test_archived_and_test_paths_are_out_of_scope(tmp_path: Path) -> None:
    for relative in ("scripts/archive/old.py", "scripts/tests/helper.py"):
        _write(
            tmp_path,
            relative,
            "from datetime import date\n\n"
            "def build(p):\n"
            '    p.add_argument("--as-of", default=date.today())\n',
        )

    assert guard.validate_repository(root=tmp_path, allowlist={}, scan_roots=("scripts",)) == []


def test_repository_has_no_unlisted_wall_clock_cuts() -> None:
    violations = guard.validate_repository()

    assert violations == [], "\n".join(violation.format() for violation in violations)


def test_none_default_resolved_from_the_clock_is_refused(tmp_path: Path) -> None:
    """`as_of: X | None = None` plus `as_of or clock()` is a wall-clock default."""
    _write(
        tmp_path,
        "scripts/data/semantic.py",
        "from datetime import UTC, datetime\n\n"
        "def build(as_of: datetime | None = None):\n"
        "    as_of = as_of or datetime.now(UTC)\n"
        "    return as_of\n",
    )

    violations = guard.validate_repository(root=tmp_path, allowlist={}, scan_roots=("scripts",))

    assert len(violations) == 1
    assert "falls back to the wall clock when as_of is None" in violations[0].message


def test_none_default_resolved_by_an_if_statement_is_refused(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "scripts/data/branch.py",
        "from datetime import date\n\n"
        "def build(as_of: date | None = None):\n"
        "    if as_of is None:\n"
        "        as_of = date.today()\n"
        "    return as_of\n",
    )

    violations = guard.validate_repository(root=tmp_path, allowlist={}, scan_roots=("scripts",))

    assert len(violations) == 1
    assert "falls back to the wall clock when as_of is None" in violations[0].message


def test_none_default_resolved_by_a_ternary_is_refused(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "scripts/data/ternary.py",
        "from datetime import date\n\n"
        "def build(as_of: date | None = None):\n"
        "    return as_of if as_of is not None else date.today()\n",
    )

    violations = guard.validate_repository(root=tmp_path, allowlist={}, scan_roots=("scripts",))

    assert len(violations) == 1
    assert "falls back to the wall clock when as_of is None" in violations[0].message


def test_none_default_with_a_declared_fallback_is_allowed(tmp_path: Path) -> None:
    """Only a clock fallback is refused, not every None default."""
    _write(
        tmp_path,
        "scripts/data/declared.py",
        "from datetime import date\n\n"
        "DECLARED_CUT = date(2026, 9, 10)\n\n"
        "def build(as_of: date | None = None):\n"
        "    as_of = as_of or DECLARED_CUT\n"
        "    return as_of\n",
    )

    assert guard.validate_repository(root=tmp_path, allowlist={}, scan_roots=("scripts",)) == []


def test_clock_read_unrelated_to_the_cut_is_allowed(tmp_path: Path) -> None:
    """Stamping `generated_at` in a function that takes `as_of` is not a violation."""
    _write(
        tmp_path,
        "scripts/data/stamped.py",
        "from datetime import UTC, date, datetime\n\n"
        "def build(as_of: date | None = None):\n"
        "    generated_at = datetime.now(UTC).isoformat()\n"
        "    return {'as_of': as_of, 'generated_at': generated_at}\n",
    )

    assert guard.validate_repository(root=tmp_path, allowlist={}, scan_roots=("scripts",)) == []


def test_blank_allowlist_reason_is_refused(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "scripts/data/clocked.py",
        "from datetime import date\n\n"
        "def build(p):\n"
        '    p.add_argument("--as-of", default=date.today())\n',
    )

    violations = guard.validate_repository(
        root=tmp_path,
        allowlist={"scripts/data/clocked.py": "   "},
        scan_roots=("scripts",),
    )

    assert [violation.message for violation in violations] == [
        "allowlist entry has no reason; state why the cut is not yet declared"
    ]
