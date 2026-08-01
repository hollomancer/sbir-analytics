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
    shutil.copytree(
        REPOSITORY_ROOT / "specs/phase-iii-census",
        install_root / "specs/phase-iii-census",
    )
    script = """
import sys
from pathlib import Path
from sbir_analytics.assets.phase_iii_census import assets

install_root = Path(sys.argv[1]).resolve()
assert Path(assets.__file__).resolve().is_relative_to(install_root)
assert assets.FROZEN_SPEC_PATH == install_root / "specs/phase-iii-census/design.md"
assert assets.AMENDMENTS_LOG_PATH == install_root / "specs/phase-iii-census/amendments.md"
record = assets.verify_frozen_spec()
assert record["spec_sha256"] == assets.FROZEN_SPEC_SHA256
assert record["amendments_sha256"] == assets.AMENDMENTS_LOG_SHA256
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(install_root)

    result = subprocess.run(
        [sys.executable, "-c", script, str(install_root)],
        cwd=install_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    docker_copy = "COPY specs/phase-iii-census/ /app/specs/phase-iii-census/"
    for dockerfile in (REPOSITORY_ROOT / "Dockerfile", REPOSITORY_ROOT / "Dockerfile.full"):
        assert docker_copy in dockerfile.read_text(encoding="utf-8")
    dockerignore = (REPOSITORY_ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "!specs/phase-iii-census/design.md" in dockerignore
    assert "!specs/phase-iii-census/amendments.md" in dockerignore
