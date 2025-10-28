import pandas as pd
import pytest
from src.enrichers.transition_detector import TransitionDetector
from src.models.transitions import TransitionType


@pytest.fixture
def sample_company_data():
    data = {
        "company_id": [1, 2, 3],
        "company_name": ["TestCo1", "TestCo2", "TestCo3"],
        "description": [
            "TestCo1 was acquired by BigCorp",
            "TestCo2 is a regular company",
            "TestCo3 filed for bankruptcy",
        ],
    }
    return pd.DataFrame(data)


def test_transition_detector(sample_company_data):
    detector = TransitionDetector()
    transitions = detector.detect(sample_company_data)
    assert len(transitions) == 2
    assert transitions[0].company_id == 1
    assert transitions[0].transition_type == TransitionType.ACQUISITION
    assert transitions[1].company_id == 3
    assert transitions[1].transition_type == TransitionType.BANKRUPTCY
