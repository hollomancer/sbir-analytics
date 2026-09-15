#!/usr/bin/env python3
"""Require an as-of data cut to be declared rather than read from the clock.

An as-of value fixes which slice of a source a run observed, so a published
number is reproducible only when that value is recorded. A generator whose
``--as-of`` default is ``date.today()`` observes a different cut every day and
cannot regenerate the figure it published, even from its own committed inputs.

The guard refuses a wall-clock default in the three places that fix a cut: an
``--as-of``-style argparse option, a module-level ``AS_OF`` or ``DEFAULT_AS_OF``
constant, and a function parameter named ``as_of``. Reading the clock for
anything else is fine — stamping ``generated_at``, timing a run, naming a log
file. Only the default that decides what data a run sees is refused.

A parameter declared ``as_of: date | None = None`` and then resolved in the body
with ``as_of or date.today()`` is the same wall-clock default written in two
statements, so the guard refuses that form too. The syntactic default alone is
not enough to tell whether a cut was declared.

``WALL_CLOCK_ALLOWLIST`` records the paths that predate this guard. It is a
burndown list, not an exemption: an entry that no longer violates the rule is
itself reported, so the list can only shrink. Every entry must carry a non-blank
reason, so an exemption cannot be added without saying what it defers.

This is admission control on how a cut is chosen. It does not check that a
recorded cut is correct, and it does not look at data.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

SCAN_ROOTS = ("scripts", "packages", "sbir_etl")
SKIP_DIRECTORY_NAMES = frozenset({"archive", "__pycache__", ".worktrees", ".venv", "tests"})

AS_OF_OPTIONS = frozenset({"--as-of", "--as-of-date", "--as-of-utc", "--asof", "--asof-date"})
AS_OF_PARAMETERS = frozenset({"as_of", "as_of_date", "as_of_utc", "as_of_timestamp"})
AS_OF_CONSTANT = re.compile(r"^(DEFAULT_)?AS_OF(_DATE|_UTC|_TIMESTAMP)?$")

# Callables that read the wall clock. Matched on the attribute or bare name, so
# ``date.today()``, ``datetime.datetime.now(UTC)`` and ``pd.Timestamp.today()``
# are all caught without importing anything.
WALL_CLOCK_NAMES = frozenset({"today", "now", "utcnow", "utcnow_iso", "time", "time_ns"})

# Paths that predate the guard. Burn these down rather than adding to them.
WALL_CLOCK_ALLOWLIST: dict[str, str] = {
    "scripts/data/build_dod_supply_chain_baseline.py": (
        "predates this guard; not yet migrated to a declared cut"
    ),
    "scripts/data/build_local_dod_research_inputs.py": (
        "predates this guard; not yet migrated to a declared cut"
    ),
    "scripts/data/download_sam_opportunities.py": (
        "predates this guard; not yet migrated to a declared cut"
    ),
    "sbir_etl/reporting/weekly/fetching.py": (
        "predates this guard; fetch_weekly_awards resolves a None as_of with "
        "datetime.now(UTC)"
    ),
    "sbir_etl/reporting/dod_supply_chain_baseline.py": (
        "predates this guard; build_baseline resolves a None as_of with "
        "datetime.now(UTC).date()"
    ),
    "sbir_etl/supply_chain/release_validation.py": (
        "predates this guard; validate_nsf_defense_lineage_release resolves a None "
        "as_of with datetime.now(UTC).date(), so release age moves with the clock"
    ),
}


@dataclass(frozen=True)
class Violation:
    """One refused wall-clock default, or one stale allowlist entry."""

    path: str
    line_number: int
    message: str

    def format(self) -> str:
        return f"  {self.path}:{self.line_number}: {self.message}"


def _reads_wall_clock(node: ast.AST) -> bool:
    """Whether evaluating ``node`` would call something that reads the clock."""
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Attribute) and func.attr in WALL_CLOCK_NAMES:
            return True
        if isinstance(func, ast.Name) and func.id in WALL_CLOCK_NAMES:
            return True
    return False


def _option_strings(call: ast.Call) -> list[str]:
    return [
        arg.value
        for arg in call.args
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
    ]


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _argparse_violations(tree: ast.AST, path: str) -> Iterator[Violation]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_argument"):
            continue
        options = {option for option in _option_strings(node) if option in AS_OF_OPTIONS}
        if not options:
            continue
        default = _keyword(node, "default")
        if default is None or not _reads_wall_clock(default):
            continue
        option = sorted(options)[0]
        yield Violation(
            path=path,
            line_number=node.lineno,
            message=(
                f"{option} defaults to the wall clock; make it required or read the cut "
                f"from the study manifest so the run is reproducible"
            ),
        )


def _constant_violations(tree: ast.Module, path: str) -> Iterator[Violation]:
    for node in tree.body:
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        else:
            continue
        for target in targets:
            if not isinstance(target, ast.Name) or not AS_OF_CONSTANT.match(target.id):
                continue
            if not _reads_wall_clock(value):
                continue
            yield Violation(
                path=path,
                line_number=node.lineno,
                message=(
                    f"{target.id} is initialised from the wall clock; declare the cut "
                    f"explicitly instead"
                ),
            )


def _references(node: ast.AST, name: str) -> bool:
    """Whether ``name`` is read anywhere inside ``node``."""
    return any(
        isinstance(child, ast.Name) and child.id == name for child in ast.walk(node)
    )


def _clock_fallback_line(
    function: ast.FunctionDef | ast.AsyncFunctionDef, name: str
) -> int | None:
    """Line where ``name`` falls back to the clock, or ``None`` if it never does.

    Covers the three ways a ``None`` default is resolved in the body:
    ``name or clock()``, ``name if name else clock()``, and
    ``if name is None: name = clock()``.
    """
    for node in ast.walk(function):
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            head, *rest = node.values
            if _references(head, name) and any(_reads_wall_clock(value) for value in rest):
                return node.lineno
        elif isinstance(node, ast.IfExp) and _references(node.test, name):
            if _reads_wall_clock(node.body) or _reads_wall_clock(node.orelse):
                return node.lineno
        elif isinstance(node, ast.If) and _references(node.test, name):
            if any(_reads_wall_clock(statement) for statement in node.body):
                return node.lineno
    return None


def _parameter_violations(tree: ast.AST, path: str) -> Iterator[Violation]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        arguments = node.args
        positional = arguments.posonlyargs + arguments.args
        pairs: list[tuple[ast.arg, ast.expr | None]] = []
        offset = len(positional) - len(arguments.defaults)
        for index, argument in enumerate(positional):
            default = arguments.defaults[index - offset] if index >= offset else None
            pairs.append((argument, default))
        pairs.extend(zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True))
        for argument, default in pairs:
            if argument.arg not in AS_OF_PARAMETERS or default is None:
                continue
            if _reads_wall_clock(default):
                yield Violation(
                    path=path,
                    line_number=default.lineno,
                    message=(
                        f"{node.name}() defaults {argument.arg} to the wall clock; require "
                        f"the caller to pass the cut it observed"
                    ),
                )
                continue
            # A `None` default is only a placeholder. If the body then reads the
            # clock for this parameter, the cut is still clock-derived.
            if not (isinstance(default, ast.Constant) and default.value is None):
                continue
            fallback = _clock_fallback_line(node, argument.arg)
            if fallback is None:
                continue
            yield Violation(
                path=path,
                line_number=fallback,
                message=(
                    f"{node.name}() falls back to the wall clock when {argument.arg} is "
                    f"None; require the caller to pass the cut it observed"
                ),
            )


def scan_source(text: str, path: str) -> list[Violation]:
    """Report every wall-clock as-of default in one module's source."""
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [
            Violation(
                path=path, line_number=exc.lineno or 1, message=f"cannot parse: {exc.msg}"
            )
        ]
    violations = [
        *_argparse_violations(tree, path),
        *_constant_violations(tree, path),
        *_parameter_violations(tree, path),
    ]
    return sorted(violations, key=lambda violation: (violation.line_number, violation.message))


def iter_python_files(root: Path, scan_roots: tuple[str, ...] = SCAN_ROOTS) -> Iterator[Path]:
    """Yield the modules in scope, skipping archives, caches, and tests."""
    for scan_root in scan_roots:
        base = root / scan_root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            if SKIP_DIRECTORY_NAMES & set(path.relative_to(root).parts[:-1]):
                continue
            yield path


def validate_repository(
    root: Path = REPOSITORY_ROOT,
    allowlist: dict[str, str] | None = None,
    scan_roots: tuple[str, ...] = SCAN_ROOTS,
) -> list[Violation]:
    """Scan the repository and report violations plus stale allowlist entries."""
    allowlist = WALL_CLOCK_ALLOWLIST if allowlist is None else allowlist
    violations: list[Violation] = []
    still_violating: set[str] = set()
    # An entry with no reason exempts a path while recording nothing to burn down.
    violations.extend(
        Violation(
            path=relative,
            line_number=1,
            message="allowlist entry has no reason; state why the cut is not yet declared",
        )
        for relative, reason in sorted(allowlist.items())
        if not reason.strip()
    )
    for path in iter_python_files(root, scan_roots):
        relative = path.relative_to(root).as_posix()
        found = scan_source(path.read_text(encoding="utf-8"), relative)
        if not found:
            continue
        if relative in allowlist:
            still_violating.add(relative)
            continue
        violations.extend(found)
    for relative, reason in sorted(allowlist.items()):
        if relative in still_violating:
            continue
        target = root / relative
        detail = "no longer reads the clock" if target.exists() else "no longer exists"
        violations.append(
            Violation(
                path=relative,
                line_number=1,
                message=(
                    f"stale allowlist entry ({reason}): the file {detail}; "
                    f"remove it from WALL_CLOCK_ALLOWLIST"
                ),
            )
        )
    return violations


def main() -> int:
    violations = validate_repository()
    if violations:
        print("An as-of data cut is taken from the wall clock:")
        print("\n".join(violation.format() for violation in violations))
        return 1
    allowed = len(WALL_CLOCK_ALLOWLIST)
    print(f"As-of cuts are declared, not clock-derived ({allowed} allowlisted path(s) remaining).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
