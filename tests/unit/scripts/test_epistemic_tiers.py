from pathlib import Path

from scripts.ci import check_epistemic_tiers as tiers


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_requirements_file_is_rejected(tmp_path: Path) -> None:
    spec = tmp_path / "specs" / "example"
    spec.mkdir(parents=True)

    violations = tiers.validate_spec_directory(spec, repository_root=tmp_path)

    assert len(violations) == 1
    assert "missing requirements.md" in violations[0].message


def test_missing_declaration_is_rejected(tmp_path: Path) -> None:
    spec = tmp_path / "specs" / "example"
    _write(tmp_path, "specs/example/requirements.md", "# Example\n")

    violations = tiers.validate_spec_directory(spec, repository_root=tmp_path)

    assert len(violations) == 1
    assert "missing '**Target epistemic tier:** <tier>'" in violations[0].message


def test_invalid_or_duplicate_declarations_are_rejected(tmp_path: Path) -> None:
    invalid = tmp_path / "specs" / "invalid"
    duplicate = tmp_path / "specs" / "duplicate"
    _write(
        tmp_path,
        "specs/invalid/requirements.md",
        "# Invalid\n\n**Target epistemic tier:** useful\n",
    )
    _write(
        tmp_path,
        "specs/duplicate/requirements.md",
        "# Duplicate\n\n**Target epistemic tier:** pipelines\n"
        "**Target epistemic tier:** evidence\n",
    )

    invalid_violations = tiers.validate_spec_directory(invalid, repository_root=tmp_path)
    duplicate_violations = tiers.validate_spec_directory(duplicate, repository_root=tmp_path)

    assert "invalid target tier" in invalid_violations[0].message
    assert "multiple target tier" in duplicate_violations[0].message


def test_all_valid_tiers_are_accepted(tmp_path: Path) -> None:
    for tier in sorted(tiers.VALID_TIERS):
        spec = tmp_path / "specs" / tier
        _write(
            tmp_path,
            f"specs/{tier}/requirements.md",
            f"# {tier}\n\n**Target epistemic tier:** `{tier}`\n",
        )
        assert not tiers.validate_spec_directory(spec, repository_root=tmp_path)


def test_current_repository_spec_declarations_are_valid() -> None:
    assert tiers.scan_specs() == []


def test_capitalized_tier_is_reported_as_invalid_not_missing(tmp_path: Path) -> None:
    """A capitalization typo should name the real problem.

    The declaration pattern used to match lowercase only, so `Evidence` fell
    through to "missing declaration" and sent the author looking for a line
    that was already there.
    """

    spec = tmp_path / "specs" / "example"
    _write(
        tmp_path,
        "specs/example/requirements.md",
        "# Example\n\n**Target epistemic tier:** Evidence\n",
    )

    violations = tiers.validate_spec_directory(spec, repository_root=tmp_path)

    assert len(violations) == 1
    assert "invalid target tier 'Evidence'" in violations[0].message


def test_declaration_inside_fenced_code_is_ignored(tmp_path: Path) -> None:
    spec = tmp_path / "specs" / "example"
    _write(
        tmp_path,
        "specs/example/requirements.md",
        "# Example\n\n"
        "**Target epistemic tier:** pipelines\n\n"
        "```markdown\n"
        "**Target epistemic tier:** evidence\n"
        "```\n",
    )

    assert not tiers.validate_spec_directory(spec, repository_root=tmp_path)


def test_unterminated_fence_does_not_swallow_a_real_declaration(tmp_path: Path) -> None:
    spec = tmp_path / "specs" / "example"
    _write(
        tmp_path,
        "specs/example/requirements.md",
        "# Example\n\n```markdown\nunterminated example\n\n"
        "**Target epistemic tier:** pipelines\n",
    )

    assert not tiers.validate_spec_directory(spec, repository_root=tmp_path)


def test_unterminated_fence_still_reports_a_genuine_duplicate(tmp_path: Path) -> None:
    spec = tmp_path / "specs" / "example"
    _write(
        tmp_path,
        "specs/example/requirements.md",
        "**Target epistemic tier:** pipelines\n\n```markdown\nunterminated example\n\n"
        "**Target epistemic tier:** evidence\n",
    )

    violations = tiers.validate_spec_directory(spec, repository_root=tmp_path)

    assert len(violations) == 1
    assert "multiple target tier" in violations[0].message


def test_indented_fence_inside_list_hides_example_declaration(tmp_path: Path) -> None:
    spec = tmp_path / "specs" / "example"
    _write(
        tmp_path,
        "specs/example/requirements.md",
        "**Target epistemic tier:** pipelines\n\n"
        "- Example:\n"
        "    ```markdown\n"
        "    **Target epistemic tier:** evidence\n"
        "    ```\n",
    )

    assert not tiers.validate_spec_directory(spec, repository_root=tmp_path)


def test_closing_fence_with_info_string_does_not_close(tmp_path: Path) -> None:
    spec = tmp_path / "specs" / "example"
    _write(
        tmp_path,
        "specs/example/requirements.md",
        "**Target epistemic tier:** pipelines\n\n"
        "```markdown\n"
        "```python\n"
        "**Target epistemic tier:** evidence\n"
        "```\n",
    )

    assert not tiers.validate_spec_directory(spec, repository_root=tmp_path)


def test_inline_code_span_at_line_start_is_not_a_fence(tmp_path: Path) -> None:
    spec = tmp_path / "specs" / "example"
    _write(
        tmp_path,
        "specs/example/requirements.md",
        "```markdown``` is inline code\n\n**Target epistemic tier:** pipelines\n",
    )

    assert not tiers.validate_spec_directory(spec, repository_root=tmp_path)


def test_supported_fence_variants_hide_example_declarations(tmp_path: Path) -> None:
    for name, opener, closer in (
        ("tilde", "~~~markdown", "~~~"),
        ("long", "````markdown", "````"),
        ("tab", "\t```markdown", "\t```"),
        ("spaces", "   ```markdown", "   ```"),
    ):
        spec = tmp_path / "specs" / name
        _write(
            tmp_path,
            f"specs/{name}/requirements.md",
            "**Target epistemic tier:** pipelines\n\n"
            f"{opener}\n**Target epistemic tier:** evidence\n{closer}\n",
        )

        assert not tiers.validate_spec_directory(spec, repository_root=tmp_path)
