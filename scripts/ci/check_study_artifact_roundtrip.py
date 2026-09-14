#!/usr/bin/env python3
"""Require a rendered study deliverable to reproduce from its committed sidecar.

A readout that ships both a machine-readable summary and a markdown write-up
keeps two copies of the same numbers, and they drift: the summary is
regenerated while the markdown is not, a sentence is hand-edited, or the
renderer starts reading a field the committed summary does not carry. The
reader cites the markdown, so the drift lands in the claim.

The guard re-renders each registered pair from its committed sidecar and
requires byte equality with the committed markdown. A renderer that raises on
its own committed summary fails here too — that is the same defect, caught one
step earlier.

Coverage is checked both ways, following the spec-registry pattern in
``specs/status.md``: a module that exposes a ``render_markdown`` entry point
must appear in ``REGISTERED_PAIRS`` or in ``WAIVED_RENDERERS`` with a reason,
so a new readout cannot ship unchecked. ``REGISTERED_PAIRS`` is empty until the
first readout with a pure renderer lands; the coverage half is what keeps it
from staying empty by accident.

This proves a deliverable matches the artifact it was rendered from. It does not
prove the artifact's numbers are right, and it does not read private inputs.
"""

from __future__ import annotations

import ast
import difflib
import importlib.util
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

RENDERER_SCAN_ROOTS = ("scripts", "packages")
SKIP_DIRECTORY_NAMES = frozenset({"archive", "__pycache__", ".worktrees", ".venv", "tests"})
RENDERER_FUNCTION_NAMES = frozenset({"render_markdown"})
MAX_DIFF_LINES = 20


@dataclass(frozen=True)
class RoundTripPair:
    """A committed markdown deliverable and the sidecar it renders from."""

    markdown: str
    sidecar: str
    renderer: str  # "<module path>:<function>", e.g. "scripts/data/build_x.py:render_markdown"

    @property
    def renderer_path(self) -> str:
        return self.renderer.split(":", 1)[0]

    @property
    def renderer_function(self) -> str:
        return self.renderer.split(":", 1)[1]


# Registered pairs. Add an entry with the readout that introduces the renderer.
REGISTERED_PAIRS: tuple[RoundTripPair, ...] = ()

# Renderers deliberately outside the round trip, with the reason they are exempt.
# The round trip needs a *committed* pair: an artifact in the tree to render from and a
# deliverable in the tree to compare against. A renderer whose output lands in untracked
# ``reports/`` or at an operator-supplied path has nothing to check.
WAIVED_RENDERERS: dict[str, str] = {
    "scripts/data/find_same_work_awards.py": (
        "renders into untracked reports/same-work-awards/; no committed pair"
    ),
    "scripts/data/profile_sbir_inputs.py": (
        "renders to an operator-supplied --output-md path; no committed pair"
    ),
    "scripts/data/sbir_ma_signal_counts_by_fy.py": (
        "renderer takes the dataset and computed result rather than a committed sidecar, "
        "and writes into untracked reports/"
    ),
}


@dataclass(frozen=True)
class Violation:
    """One drifted pair, one broken registry entry, or one uncovered renderer."""

    path: str
    message: str

    def format(self) -> str:
        return f"  {self.path}: {self.message}"


def _load_renderer(root: Path, pair: RoundTripPair) -> Any:
    module_path = root / pair.renderer_path
    spec = importlib.util.spec_from_file_location(
        f"_roundtrip_{module_path.stem}", module_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {pair.renderer_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, pair.renderer_function)


def _first_difference(expected: str, actual: str) -> str:
    diff = list(
        difflib.unified_diff(
            expected.splitlines(),
            actual.splitlines(),
            fromfile="committed",
            tofile="re-rendered",
            lineterm="",
            n=1,
        )
    )
    head = diff[:MAX_DIFF_LINES]
    if len(diff) > MAX_DIFF_LINES:
        head.append(f"... {len(diff) - MAX_DIFF_LINES} more diff line(s)")
    return "\n".join(f"    {line}" for line in head)


def validate_pair(pair: RoundTripPair, root: Path = REPOSITORY_ROOT) -> list[Violation]:
    """Re-render one pair and report any drift, missing file, or renderer failure."""
    markdown_path = root / pair.markdown
    sidecar_path = root / pair.sidecar
    for label, path in (("markdown", markdown_path), ("sidecar", sidecar_path)):
        if not path.exists():
            return [
                Violation(
                    path=pair.markdown, message=f"registered {label} is missing: {path}"
                )
            ]
    if not (root / pair.renderer_path).exists():
        return [
            Violation(
                path=pair.markdown,
                message=f"registered renderer is missing: {pair.renderer}",
            )
        ]
    try:
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [Violation(path=pair.sidecar, message=f"sidecar is not valid JSON: {exc}")]
    try:
        rendered = _load_renderer(root, pair)(payload)
    except Exception as exc:  # noqa: BLE001 - any failure to re-render is the finding
        return [
            Violation(
                path=pair.markdown,
                message=(
                    f"{pair.renderer} raised {type(exc).__name__} on the committed sidecar "
                    f"{pair.sidecar}: {exc}"
                ),
            )
        ]
    if not isinstance(rendered, str):
        return [
            Violation(
                path=pair.markdown,
                message=f"{pair.renderer} returned {type(rendered).__name__}, expected str",
            )
        ]
    committed = markdown_path.read_text(encoding="utf-8")
    if rendered == committed:
        return []
    return [
        Violation(
            path=pair.markdown,
            message=(
                f"does not reproduce from {pair.sidecar} via {pair.renderer}; regenerate both "
                f"together\n{_first_difference(committed, rendered)}"
            ),
        )
    ]


def _defines_renderer(text: str) -> bool:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    return any(
        isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name in RENDERER_FUNCTION_NAMES
        for node in tree.body
    )


def discover_renderers(
    root: Path = REPOSITORY_ROOT, scan_roots: tuple[str, ...] = RENDERER_SCAN_ROOTS
) -> list[str]:
    """Repository-relative paths of modules exposing a markdown renderer."""
    found: list[str] = []
    for scan_root in scan_roots:
        base = root / scan_root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            relative = path.relative_to(root)
            if SKIP_DIRECTORY_NAMES & set(relative.parts[:-1]):
                continue
            if _defines_renderer(path.read_text(encoding="utf-8")):
                found.append(relative.as_posix())
    return found


def validate_coverage(
    root: Path = REPOSITORY_ROOT,
    pairs: tuple[RoundTripPair, ...] = REGISTERED_PAIRS,
    waived: dict[str, str] | None = None,
    scan_roots: tuple[str, ...] = RENDERER_SCAN_ROOTS,
) -> list[Violation]:
    """Require every discovered renderer to be registered or waived, and vice versa."""
    waived = WAIVED_RENDERERS if waived is None else waived
    registered = {pair.renderer_path for pair in pairs}
    discovered = set(discover_renderers(root, scan_roots))
    violations = [
        Violation(
            path=path,
            message=(
                "exposes render_markdown but is not in REGISTERED_PAIRS; register the "
                "sidecar it renders from, or waive it with a reason"
            ),
        )
        for path in sorted(discovered - registered - set(waived))
    ]
    violations.extend(
        Violation(path=path, message=f"stale waiver ({waived[path]}): no renderer found here")
        for path in sorted(set(waived) - discovered)
    )
    return violations


def validate_repository(
    root: Path = REPOSITORY_ROOT,
    pairs: tuple[RoundTripPair, ...] = REGISTERED_PAIRS,
    waived: dict[str, str] | None = None,
    scan_roots: tuple[str, ...] = RENDERER_SCAN_ROOTS,
) -> list[Violation]:
    """Check every registered pair, then check registry coverage."""
    violations: list[Violation] = []
    for pair in pairs:
        violations.extend(validate_pair(pair, root))
    violations.extend(validate_coverage(root, pairs, waived, scan_roots))
    return violations


def _iter_pairs(pairs: tuple[RoundTripPair, ...]) -> Iterator[str]:
    for pair in pairs:
        yield f"{pair.markdown} <- {pair.sidecar}"


def main() -> int:
    violations = validate_repository()
    if violations:
        print("A rendered study deliverable does not match its committed sidecar:")
        print("\n".join(violation.format() for violation in violations))
        return 1
    print(
        f"Rendered study deliverables reproduce from their sidecars "
        f"({len(REGISTERED_PAIRS)} registered pair(s), {len(WAIVED_RENDERERS)} waived)."
    )
    for description in _iter_pairs(REGISTERED_PAIRS):
        print(f"  {description}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
