"""Shared fixtures for transition E2E tests."""

from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture(scope="module")
def transition_awards_sample() -> pd.DataFrame:
    """Representative SBIR awards for transition smoke tests."""
    sample_size = 40
    agencies = ["NSF", "DoD", "DOE", "NIH"]
    cet_areas = ["AI", "Advanced Manufacturing", "Biotech", "Quantum"]

    return pd.DataFrame(
        {
            "award_id": [f"SBIR-2022-{i:05d}" for i in range(sample_size)],
            "company": [f"Company {i}" for i in range(sample_size)],
            "UEI": [f"UEI{i:09d}" for i in range(sample_size)],
            "Phase": ["I" if i % 2 == 0 else "II" for i in range(sample_size)],
            "awarding_agency_name": [agencies[i % len(agencies)] for i in range(sample_size)],
            "completion_date": pd.date_range("2022-01-01", periods=sample_size, freq="D"),
            "cet_area": [cet_areas[i % len(cet_areas)] for i in range(sample_size)],
            "award_amount": [100000 + (i * 2500) for i in range(sample_size)],
        }
    )


@pytest.fixture(scope="module")
def transition_contracts_sample(transition_awards_sample: pd.DataFrame) -> pd.DataFrame:
    """Contracts that reference the UEIs from the awards sample."""
    sample_size = len(transition_awards_sample) * 2
    agencies = ["NSF", "DoD", "DOE", "NIH"]

    return pd.DataFrame(
        {
            "contract_id": [f"CONTRACT-{i:05d}" for i in range(sample_size)],
            "vendor_uei": [
                transition_awards_sample.iloc[i % len(transition_awards_sample)]["UEI"]
                for i in range(sample_size)
            ],
            "action_date": pd.date_range("2022-06-01", periods=sample_size, freq="12H"),
            "description": [f"Contract {i}" for i in range(sample_size)],
            "awarding_agency_name": [agencies[i % len(agencies)] for i in range(sample_size)],
            "amount": [50000 + (i * 1500) for i in range(sample_size)],
        }
    )


@pytest.fixture
def transition_detector():
    """Instantiate the TransitionDetector for smoke tests."""
    from src.transition.detection.detector import TransitionDetector

    # Minimal config for smoke tests
    config = {
        "timing_window": {"min_days": 0, "max_days": 1825},
        "vendor_matching": {"require_match": False},
        "scoring": {"high_confidence_threshold": 0.75},
    }
    return TransitionDetector(config=config)


@pytest.fixture
def transition_detection_dataframe(
    transition_detector,
    transition_awards_sample: pd.DataFrame,
    transition_contracts_sample: pd.DataFrame,
) -> pd.DataFrame:
    """Run a lightweight detection pass to produce a detections DataFrame."""
    from src.models.transition_models import FederalContract

    detections: list[dict] = []

    # Convert contracts DataFrame to FederalContract objects
    contracts = [
        FederalContract(**row.to_dict()) for _, row in transition_contracts_sample.iterrows()
    ]

    for _, award in transition_awards_sample.iloc[:10].iterrows():
        records = transition_detector.detect_for_award(
            award=award.to_dict(),
            candidate_contracts=contracts,
        )
        detections.extend([r.to_dict() for r in records])

    return pd.DataFrame(detections or [{"award_id": None, "contract_id": None, "score": 0.0}])


@pytest.fixture(scope="module")
def cet_effectiveness_dataset() -> dict[str, pd.DataFrame]:
    """Bundle awards/detections/contracts/patents data for CET analytics tests."""
    cet_areas = ["AI", "Advanced Manufacturing", "Biotech", "Quantum", "Microelectronics"]

    awards = pd.DataFrame(
        {
            "award_id": [f"SBIR-{i:05d}" for i in range(200)],
            "company": [f"Company {i}" for i in range(200)],
            "UEI": [f"UEI{i:09d}" for i in range(200)],
            "cet_area": [cet_areas[i % len(cet_areas)] for i in range(200)],
            "completion_date": pd.date_range("2020-01-01", periods=200, freq="2D"),
        }
    )
    detections = pd.DataFrame(
        {
            "award_id": [f"SBIR-{i:05d}" for i in range(120)],
            "contract_id": [f"CONTRACT-{i:05d}" for i in range(120)],
            "score": [0.55 + (i % 20) / 100 for i in range(120)],
        }
    )
    contracts = pd.DataFrame(
        {
            "contract_id": [f"CONTRACT-{i:05d}" for i in range(120)],
            "action_date": pd.date_range("2021-01-01", periods=120, freq="3D"),
        }
    )
    patents = pd.DataFrame(
        {
            "award_id": [f"SBIR-{i:05d}" for i in range(60)],
            "patent_id": [f"US{i:08d}" for i in range(60)],
        }
    )

    return {"awards": awards, "detections": detections, "contracts": contracts, "patents": patents}
