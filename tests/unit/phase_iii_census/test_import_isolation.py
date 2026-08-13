import os
import shutil
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_census_import_does_not_load_scoring_path() -> None:
    script = """
import sys
import sbir_analytics.assets.phase_iii_census.assets  # noqa: F401

forbidden = {
    "sbir_analytics.assets.phase_iii_candidates.assets",
    "sbir_ml.transition.detection.scoring",
}
loaded = forbidden.intersection(sys.modules)
if loaded:
    raise SystemExit(f"census import loaded prohibited scoring modules: {sorted(loaded)}")
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_census_import_and_freeze_verification_work_in_shallow_container_layout(
    tmp_path: Path,
) -> None:
    install_root = tmp_path / "app"
    shutil.copytree(
        REPOSITORY_ROOT / "packages/sbir-analytics/sbir_analytics",
        install_root / "sbir_analytics",
    )
    shutil.copytree(REPOSITORY_ROOT / "sbir_etl", install_root / "sbir_etl")
    shutil.copytree(
        REPOSITORY_ROOT / "specs/phase-iii-census",
        install_root / "specs/phase-iii-census",
    )
    shutil.copytree(
        REPOSITORY_ROOT / "studies/phase-iii-census",
        install_root / "studies/phase-iii-census",
    )
    script = """
import sys
from pathlib import Path
from sbir_analytics.assets.phase_iii_census import assets

install_root = Path(sys.argv[1]).resolve()
assert Path(assets.__file__).resolve().is_relative_to(install_root)
assert assets.FROZEN_SPEC_PATH == install_root / "specs/phase-iii-census/design.md"
assert assets.AMENDMENTS_LOG_PATH == install_root / "specs/phase-iii-census/amendments.md"
assert assets.STUDY_MANIFEST_PATH == install_root / "studies/phase-iii-census/study.yaml"
record = assets.verify_frozen_spec()
assert record["spec_sha256"] == assets.FROZEN_SPEC_SHA256
assert record["amendments_sha256"] == assets.AMENDMENTS_LOG_SHA256
assert assets.verify_materialization_gate()["materialization_allowed"] is True
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(install_root)
    # pytest-cov instruments subprocesses through these environment variables.
    # This subprocess imports a copied installation tree, which must not be
    # counted as a second copy of the repository in the coverage report.
    for key in tuple(env):
        if key.startswith("COV_CORE_"):
            env.pop(key)

    result = subprocess.run(
        [sys.executable, "-c", script, str(install_root)],
        cwd=install_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    docker_copy = "COPY --chown=sbir:sbir specs/phase-iii-census/ ./specs/phase-iii-census/"
    study_copy = "COPY --chown=sbir:sbir studies/phase-iii-census/ ./studies/phase-iii-census/"
    docker_text = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert docker_copy in docker_text
    assert study_copy in docker_text
    dockerignore = (REPOSITORY_ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "!specs/phase-iii-census/design.md" in dockerignore
    assert "!specs/phase-iii-census/amendments.md" in dockerignore
