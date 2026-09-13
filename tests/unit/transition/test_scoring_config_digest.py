"""The score-determining config must be identifiable by digest.

`config/transition/detection.yaml` is a live, editable file. Without a digest,
the same code against the same inputs produces different scores after anyone
edits it and nothing detects the change -- which is what keeps the
`transition-scoring` study below `reproducible`.
"""

from pathlib import Path

import pytest
import yaml

from sbir_ml.transition import DEFAULTS, Config, scoring_config_digest

DETECTION_CONFIG_PATH = Path("config/transition/detection.yaml")

# The digest of the committed detection.yaml, which currently equals the digest
# of the code DEFAULTS. studies/transition-scoring/study.yaml pins this value.
PINNED_SCORING_DIGEST = "779cf5bc662997c83da3080b747372b9556821c0f23bd0d3362606c3fba15009"


def _config_from_file(path: Path) -> Config:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Config(
        fuzzy_threshold=raw.get("fuzzy_threshold", DEFAULTS["fuzzy_threshold"]),
        fuzzy_secondary_threshold=raw.get(
            "fuzzy_secondary_threshold", DEFAULTS["fuzzy_secondary_threshold"]
        ),
        batch_size_contracts=raw.get("batch_size_contracts", DEFAULTS["batch_size_contracts"]),
        detection_timing_window_months=raw.get(
            "detection_timing_window_months", DEFAULTS["detection_timing_window_months"]
        ),
        scoring={**DEFAULTS["scoring"], **(raw.get("scoring") or {})},
        vendor_matching={**DEFAULTS["vendor_matching"], **(raw.get("vendor_matching") or {})},
        confidence_thresholds={
            **DEFAULTS["confidence_thresholds"],
            **(raw.get("confidence_thresholds") or {}),
        },
    )


def test_digest_is_stable_for_the_same_config() -> None:
    assert Config().scoring_digest() == Config().scoring_digest()
    assert len(Config().scoring_digest()) == 64


def test_committed_detection_yaml_matches_the_pinned_digest() -> None:
    """The study pins the weights it was measured under; this is that gate.

    A change to any scoring weight, threshold, or timing window in
    detection.yaml fails here, which is the point: the study's recorded result
    was produced under these values and no others.
    """
    assert _config_from_file(DETECTION_CONFIG_PATH).scoring_digest() == PINNED_SCORING_DIGEST


def test_committed_file_agrees_with_code_defaults() -> None:
    """detection.yaml documents itself as mirroring the DEFAULTS dict."""
    assert _config_from_file(DETECTION_CONFIG_PATH).scoring_digest() == Config().scoring_digest()


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda c: c.scoring.update({"agency_same": 0.26}), id="scoring-weight"),
        pytest.param(lambda c: c.scoring.update({"timing_0_3": 0.99}), id="timing-score"),
        pytest.param(
            lambda c: c.confidence_thresholds.update({"high": 0.86}), id="confidence-threshold"
        ),
        pytest.param(
            lambda c: c.vendor_matching.update({"require_match": False}), id="vendor-matching"
        ),
    ],
)
def test_any_score_determining_change_moves_the_digest(mutate) -> None:
    config = Config()
    baseline = config.scoring_digest()
    mutate(config)
    assert config.scoring_digest() != baseline


def test_timing_window_change_moves_the_digest() -> None:
    baseline = Config().scoring_digest()
    assert Config(detection_timing_window_months=36).scoring_digest() != baseline


def test_fuzzy_thresholds_move_the_digest() -> None:
    baseline = Config().scoring_digest()
    assert Config(fuzzy_threshold=0.91).scoring_digest() != baseline
    assert Config(fuzzy_secondary_threshold=0.81).scoring_digest() != baseline


def test_operational_keys_do_not_move_the_digest() -> None:
    """Batch size cannot change a score, so it must not invalidate a pinned run."""
    assert Config(batch_size_contracts=1).scoring_digest() == Config().scoring_digest()


def test_key_order_does_not_change_the_digest() -> None:
    detector_config = Config().to_detector_config()
    reordered = dict(reversed(list(detector_config.items())))
    assert scoring_config_digest(reordered) == scoring_config_digest(detector_config)
