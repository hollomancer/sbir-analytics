"""The vendor-resolution fuzzy threshold comes from transition.vendor_resolution.fuzzy_threshold."""

from pathlib import Path

import pandas as pd
import pytest
import yaml
from dagster import Output, build_asset_context

from sbir_analytics.assets.transition.vendor_resolution import enriched_vendor_resolution
from sbir_etl.config.loader import get_config, reload_config


pytestmark = pytest.mark.unit

NEW_ENV = "SBIR_ETL__TRANSITION__VENDOR_RESOLUTION__FUZZY_THRESHOLD"
OLD_ENV = "SBIR_ETL__TRANSITION__FUZZY__THRESHOLD"
BASE_YAML = Path(__file__).resolve().parents[3] / "config" / "base.yaml"


@pytest.fixture
def run_asset(monkeypatch, tmp_path):
    """Load config from the repo root, then run the asset with outputs under tmp_path."""
    monkeypatch.delenv(NEW_ENV, raising=False)
    monkeypatch.delenv(OLD_ENV, raising=False)

    def _run(env: dict[str, str] | None = None) -> pd.DataFrame:
        for key, value in (env or {}).items():
            monkeypatch.setenv(key, value)
        reload_config()
        get_config()  # load config/base.yaml before leaving the repo root
        monkeypatch.chdir(tmp_path)
        # "Acme Robotics" scores about 0.76 against "Acme Robotics Systems":
        # unresolved at 0.85, resolved by name at 0.70.
        contracts = pd.DataFrame(
            [{"contract_id": "C1", "vendor_uei": None, "vendor_name": "Acme Robotics"}]
        )
        awards = pd.DataFrame([{"Company": "Acme Robotics Systems", "UEI": None, "Duns": None}])
        result = enriched_vendor_resolution(
            context=build_asset_context(),
            validated_contracts_sample=contracts,
            enriched_sbir_awards=awards,
        )
        assert isinstance(result, Output)
        return result.value

    yield _run
    reload_config()


def test_default_comes_from_base_yaml(run_asset):
    expected = yaml.safe_load(BASE_YAML.read_text())["transition"]["vendor_resolution"][
        "fuzzy_threshold"
    ]
    df = run_asset()
    assert get_config().transition["vendor_resolution"]["fuzzy_threshold"] == expected
    assert df.loc[0, "match_method"] == "unresolved"


def test_standard_env_override_lowers_threshold(run_asset):
    df = run_asset({NEW_ENV: "0.7"})
    assert df.loc[0, "match_method"] == "name_fuzzy"


def test_retired_env_var_raises_and_names_new_var(run_asset):
    with pytest.raises(ValueError, match=NEW_ENV):
        run_asset({OLD_ENV: "0.7"})


@pytest.mark.parametrize("raw", ["1.5", "-0.1", "nan", "inf", "abc", "true"])
def test_invalid_threshold_raises_and_names_key(run_asset, raw):
    with pytest.raises(ValueError, match=r"transition\.vendor_resolution\.fuzzy_threshold"):
        run_asset({NEW_ENV: raw})
