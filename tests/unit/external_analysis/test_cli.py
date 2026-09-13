from __future__ import annotations

from pathlib import Path

from scripts.research.run_external_analysis import build_parser, main


def test_cli_upload_flag_defaults_off() -> None:
    args = build_parser().parse_args(
        ["--provider", "edison", "--study", "example-study", "--dataset", "x.csv"]
    )
    assert args.allow_external_upload is False
    assert args.bundle_only is False


def test_cli_bundle_only_exits_zero(repo: Path, monkeypatch, capsys) -> None:
    import scripts.research.run_external_analysis as cli

    monkeypatch.setattr(cli, "REPO", repo)
    monkeypatch.setattr(
        "sbir_analytics.external_analysis.bundle.current_git_commit",
        lambda root: "abc123",
    )
    code = main(
        [
            "--provider",
            "edison",
            "--study",
            "example-study",
            "--dataset",
            str(repo / "data" / "derived" / "cohort.csv"),
            "--bundle-only",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert '"citable": false' in out
    assert '"status": "bundled"' in out


def test_cli_fails_closed_without_upload_flag(repo: Path, monkeypatch, capsys) -> None:
    import scripts.research.run_external_analysis as cli

    monkeypatch.setattr(cli, "REPO", repo)
    monkeypatch.setattr(
        "sbir_analytics.external_analysis.bundle.current_git_commit",
        lambda root: "abc123",
    )
    code = main(
        [
            "--provider",
            "edison",
            "--study",
            "example-study",
            "--dataset",
            str(repo / "data" / "derived" / "cohort.csv"),
        ]
    )
    assert code == 1
    err = capsys.readouterr().err
    assert "--allow-external-upload" in err
