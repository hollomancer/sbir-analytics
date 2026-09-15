from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from scripts.research.sbir_roi_contracts import load_contract_bundle


def test_committed_sbir_roi_contract_bundle_is_valid() -> None:
    bundle = load_contract_bundle()

    assert {item.evidence_class for item in bundle.attribution} == {
        "causal",
        "descriptive",
        "inference",
    }
    assert any(item.comparability == "mechanism_matched" for item in bundle.comparators)
    assert any(item.comparability == "context_only" for item in bundle.comparators)
    assert {item.ledger for item in bundle.ledger} == {"fiscal", "domestic_social"}
    treatment = {item.outcome_id: item.taxpayer_treatment for item in bundle.outcomes}
    assert treatment["operating-status"] == "validation_signal"
    assert treatment["follow-on-private-capital"] == "validation_signal"
    assert treatment["mergers-acquisitions-ipo"] == "validation_signal"
    assert treatment["non-sbir-revenue"] == "requires_incremental_value_added"


def test_patents_cannot_be_a_standalone_success_measure(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[3] / "studies/sbir-roi-comparative-tests/contracts.yaml"
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    patent = next(item for item in raw["outcomes"] if item["outcome_id"] == "patents")
    patent["standalone_success_measure"] = True
    path = tmp_path / "contracts.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    with pytest.raises(ValidationError, match="patents cannot be a standalone success measure"):
        load_contract_bundle(path)


def test_attribution_weights_must_be_bounded(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[3] / "studies/sbir-roi-comparative-tests/contracts.yaml"
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    raw["attribution"][0]["allowed_weight_range"] = [-0.1, 1.1]
    path = tmp_path / "contracts.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    with pytest.raises(ValidationError, match="ordered within zero and one"):
        load_contract_bundle(path)
