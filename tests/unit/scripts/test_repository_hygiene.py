from pathlib import Path

from scripts.ci import check_removed_src_references as hygiene


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_live_doc_stale_content_scans_all_non_archived_docs(tmp_path: Path):
    live_doc = _write(
        tmp_path,
        "docs/transition/example.md",
        "Run `poetry run old-task` and inspect `src/assets/example.py`.\n",
    )
    archive_doc = _write(
        tmp_path,
        "docs/archive/example.md",
        "Run `poetry run old-task` and inspect `src/assets/example.py`.\n",
    )

    violations = hygiene.scan_live_doc_stale_content([live_doc, archive_doc], root=tmp_path)

    assert [violation.message for violation in violations] == [
        "removed source-root file path",
    ]
    assert violations[0].path == "docs/transition/example.md"


def test_live_doc_link_audit_resolves_relative_links(tmp_path: Path):
    source = _write(
        tmp_path,
        "docs/development/example.md",
        "[good](../target.md)\n[missing](../missing.md)\n[external](https://example.com)\n",
    )
    target = _write(tmp_path, "docs/target.md", "ok\n")

    violations = hygiene.scan_missing_live_doc_links([source, target], root=tmp_path)

    assert len(violations) == 1
    assert violations[0].message == "missing local Markdown link ../missing.md"
    assert violations[0].path == "docs/development/example.md"


def test_live_doc_link_audit_validates_file_and_same_page_anchors(tmp_path: Path):
    source = _write(
        tmp_path,
        "docs/development/example.md",
        "# Local Heading\n"
        "[same](#local-heading)\n"
        "[other](../target.md#repeated-heading-1)\n"
        "[explicit](../target.md#stable-id)\n"
        "[missing](../target.md#old-heading)\n",
    )
    target = _write(
        tmp_path,
        "docs/target.md",
        "# Repeated heading\n"
        "# Repeated heading\n"
        "# Research & development\n"
        '<a id="stable-id"></a>\n',
    )

    violations = hygiene.scan_missing_live_doc_links([source, target], root=tmp_path)

    assert len(violations) == 1
    assert violations[0].message == "missing Markdown anchor #old-heading in ../target.md"
    assert hygiene._github_heading_slug("Research & development") == "research--development"


def test_archive_guard_ignores_archive_scripts_and_flags_live_references(tmp_path: Path):
    live_code = _write(
        tmp_path,
        "sbir_etl/example.py",
        "HELPER = 'scripts/archive/data/old.py'\n",
    )
    archive_script = _write(
        tmp_path,
        "scripts/archive/data/old.py",
        "HELPER = 'scripts/archive/data/old.py'\n",
    )
    archive_test = _write(
        tmp_path,
        "tests/unit/scripts/archive/test_old.py",
        "from scripts.archive.data import old\n",
    )

    violations = hygiene.scan_archive_references(
        [live_code, archive_script, archive_test],
        root=tmp_path,
    )

    assert len(violations) == 1
    assert violations[0].path == "sbir_etl/example.py"


def test_archive_guard_checks_deployment_docs_but_allows_research_history(tmp_path: Path):
    runbook = _write(
        tmp_path,
        "docs/deployment/server.md",
        "Run `python scripts/archive/data/old.py` on the live server.\n",
    )
    research_note = _write(
        tmp_path,
        "docs/research/example.md",
        "The original analysis used `scripts/archive/data/old.py`.\n",
    )

    violations = hygiene.scan_archive_references([runbook, research_note], root=tmp_path)

    assert len(violations) == 1
    assert violations[0].path == "docs/deployment/server.md"


def test_archive_guard_ignores_identity_guard_self_reference(tmp_path: Path):
    identity_guard = _write(
        tmp_path,
        "scripts/ci/check_identity_boundaries.py",
        'EXCLUDED = ("scripts/archive/", "tests/unit/scripts/archive/")\n',
    )

    violations = hygiene.scan_archive_references([identity_guard], root=tmp_path)

    assert violations == []


def test_removed_src_guard_scans_automation_paths(tmp_path: Path):
    workflow = _write(
        tmp_path,
        ".github/workflows/ci.yml",
        "run: uv run dagster job execute -f src.definitions\n",
    )

    violations = hygiene.scan_removed_src_references([workflow], root=tmp_path)

    assert len(violations) == 1
    assert violations[0].message == "removed src source-root reference"
