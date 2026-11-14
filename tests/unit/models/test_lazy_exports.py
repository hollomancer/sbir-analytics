"""Every name that sbir_etl.models exports must resolve to a real object."""

import pytest

import sbir_etl.models as models


@pytest.mark.parametrize("name", models.__all__)
def test_lazy_export_resolves(name: str) -> None:
    assert getattr(models, name) is not None
