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
    source = (
        Path(__file__).resolve().parents[3] / "studies/sbir-roi-comparative-tests/contracts.yaml"
    )
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    patent = next(item for item in raw["outcomes"] if item["outcome_id"] == "patents")
    patent["standalone_success_measure"] = True
    path = tmp_path / "contracts.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    with pytest.raises(ValidationError, match="patents cannot be a standalone success measure"):
        load_contract_bundle(path)


def test_attribution_weights_must_be_bounded(tmp_path: Path) -> None:
    source = (
        Path(__file__).resolve().parents[3] / "studies/sbir-roi-comparative-tests/contracts.yaml"
    )
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    raw["attribution"][0]["allowed_weight_range"] = [-0.1, 1.1]
    path = tmp_path / "contracts.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    with pytest.raises(ValidationError, match="ordered within zero and one"):
        load_contract_bundle(path)


def test_non_additive_scenario_item_is_refused_in_a_sum() -> None:
    """The alternative-mechanism comparison is a reported scenario, not a
    ledger line. A calculator that tries to subtract it into a net present
    value must be refused; summing it would relabel a difference between two
    programs as SBIR's own NPV.
    """

    bundle = load_contract_bundle()
    comparison = next(
        item for item in bundle.ledger if item.item_id == "alternative-mechanism-comparison"
    )
    assert comparison.additive is False
    additive_ids = {item.item_id for item in bundle.additive_ledger_items()}
    assert "alternative-mechanism-comparison" not in additive_ids
    assert "real-resource-cost" in additive_ids
    assert "excess-burden" in additive_ids

    with pytest.raises(ValueError, match="non-additive ledger items cannot enter a sum"):
        bundle.assert_summable(["real-resource-cost", "alternative-mechanism-comparison"])
    with pytest.raises(ValueError, match="unknown ledger items"):
        bundle.assert_summable(["no-such-item"])
    bundle.assert_summable(["real-resource-cost", "excess-burden"])


def test_ledger_separates_transfers_from_real_costs() -> None:
    """Taxes are fiscal benefits and zero-valued social transfers; the real
    social cost of raising them is the separate excess-burden item."""

    bundle = load_contract_bundle()
    by_id = {item.item_id: item for item in bundle.ledger}
    receipts = by_id["federal-receipts"]
    assert receipts.ledger == "fiscal"
    assert "valued at zero" in receipts.transfer_treatment
    burden = by_id["excess-burden"]
    assert burden.ledger == "domestic_social"
    assert burden.side == "cost"
    assert burden.additive is True
    # The double-count the review found: real-resource-cost no longer
    # instructs including the best alternative use as a second subtraction.
    assert "best alternative use" not in by_id["real-resource-cost"].transfer_treatment
