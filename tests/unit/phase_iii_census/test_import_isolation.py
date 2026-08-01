import subprocess
import sys


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
