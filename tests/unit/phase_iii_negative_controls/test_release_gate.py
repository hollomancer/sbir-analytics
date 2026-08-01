import pytest


pytestmark = pytest.mark.fast


def test_negative_controls_and_placebo_release_gate_is_closed() -> None:
    pytest.fail(
        "Release gate intentionally closed: replace this sentinel only with "
        "evidence-backed tests after both negative-control and placebo artifacts exist."
    )
