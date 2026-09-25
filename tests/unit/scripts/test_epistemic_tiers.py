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
        body = f"# {tier}\n\n**Target epistemic tier:** `{tier}`\n"
        if tier == "evidence":
            body += "\n**Declared estimand:** unit-test placeholder estimand.\n"
            _write(
                tmp_path,
                f"specs/{tier}/amendments.md",
                "# Amendments\n\n"
                "SHA-256: `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`\n",
            )
        _write(tmp_path, f"specs/{tier}/requirements.md", body)
        assert not tiers.validate_spec_directory(spec, repository_root=tmp_path)


def test_evidence_tier_requires_amendments_sha_and_estimand(tmp_path: Path) -> None:
    spec = tmp_path / "specs" / "example"
    _write(
        tmp_path,
        "specs/example/requirements.md",
        "# Example\n\n**Target epistemic tier:** evidence\n",
    )

    violations = tiers.validate_spec_directory(spec, repository_root=tmp_path)
    messages = " ".join(v.message for v in violations)
    assert "amendments.md" in messages
    assert "Declared estimand" in messages or "Estimand" in messages


def test_evidence_tier_rejects_amendments_without_sha_language(tmp_path: Path) -> None:
    spec = tmp_path / "specs" / "example"
    _write(
        tmp_path,
        "specs/example/requirements.md",
        "# Example\n\n**Target epistemic tier:** evidence\n\n"
        "**Declared estimand:** the unit-test estimand.\n",
    )
    _write(tmp_path, "specs/example/amendments.md", "# Amendments\n\nNo freeze recorded.\n")

    violations = tiers.validate_spec_directory(spec, repository_root=tmp_path)

    assert len(violations) == 1
    assert "SHA-256 freeze digest" in violations[0].message


def test_evidence_tier_rejects_missing_estimand_when_sha_present(tmp_path: Path) -> None:
    spec = tmp_path / "specs" / "example"
    _write(
        tmp_path,
        "specs/example/requirements.md",
        "# Example\n\n**Target epistemic tier:** evidence\n",
    )
    _write(
        tmp_path,
        "specs/example/amendments.md",
        "Frozen file SHA-256: `cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc`\n",
    )

    violations = tiers.validate_spec_directory(spec, repository_root=tmp_path)

    assert len(violations) == 1
    assert "Declared estimand" in violations[0].message or "Estimand" in violations[0].message


def test_evidence_tier_ignores_fenced_sha_digest(tmp_path: Path) -> None:
    spec = tmp_path / "specs" / "example"
    _write(
        tmp_path,
        "specs/example/requirements.md",
        "# Example\n\n**Target epistemic tier:** evidence\n\n"
        "**Declared estimand:** the unit-test estimand.\n",
    )
    _write(
        tmp_path,
        "specs/example/amendments.md",
        "# Amendments\n\n"
        "```\n"
        "SHA-256: `dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd`\n"
        "```\n",
    )

    violations = tiers.validate_spec_directory(spec, repository_root=tmp_path)

    assert len(violations) == 1
    assert "SHA-256 freeze digest" in violations[0].message


def test_evidence_tier_accepts_complete_contract(tmp_path: Path) -> None:
    spec = tmp_path / "specs" / "example"
    _write(
        tmp_path,
        "specs/example/requirements.md",
        "# Example\n\n**Target epistemic tier:** evidence\n\n"
        "**Declared estimand:** the unit-test estimand.\n",
    )
    _write(
        tmp_path,
        "specs/example/amendments.md",
        "Frozen file SHA-256: `bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb`\n",
    )

    assert not tiers.validate_spec_directory(spec, repository_root=tmp_path)


def test_evidence_tier_accepts_raw_byte_freeze_language_without_hex(tmp_path: Path) -> None:
    """Census-style freezes compile digests into the asset, not amendments.md."""

    spec = tmp_path / "specs" / "example"
    _write(
        tmp_path,
        "specs/example/requirements.md",
        "# Example\n\n**Target epistemic tier:** evidence\n\n"
        "**Declared estimand:** the unit-test estimand.\n",
    )
    _write(
        tmp_path,
        "specs/example/amendments.md",
        "The census asset verifies and records the raw-byte SHA-256 of both files "
        "before materialization.\n",
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
        "# Example\n\n```markdown\nunterminated example\n\n**Target epistemic tier:** pipelines\n",
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
