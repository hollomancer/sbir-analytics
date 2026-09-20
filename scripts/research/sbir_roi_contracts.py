#!/usr/bin/env python3
"""Validate the shared contracts for the SBIR return-on-investment studies.

Epistemic tier: exploratory. These contracts define planned studies.
They do not produce or authorize a program-performance finding.
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sbir_etl.config.yaml_io import read_yaml_mapping


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPOSITORY_ROOT / "studies" / "sbir-roi-comparative-tests" / "contracts.yaml"

IDENTIFICATION_BRIDGE_STUDY = "sbir-marginal-award-identification"
NIH_COMPARATOR_STUDY = "nih-sbir-vs-r01-outcomes"
NASA_COMPARATOR_STUDY = "nasa-sbir-vs-external-rd"
WELFARE_BREAK_EVEN_STUDY = "sbir-social-return-break-even"


class ComparatorContract(BaseModel):
    """One mechanism included in Test Two."""

    model_config = ConfigDict(extra="forbid")

    comparator_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    comparability: Literal["mechanism_matched", "context_only"]
    funding_mechanism: str = Field(min_length=1)
    selection_rule: str = Field(min_length=1)
    counterfactual: str = Field(min_length=1)
    primary_use: str = Field(min_length=1)
    confounds: list[str] = Field(min_length=1)


class OutcomeContract(BaseModel):
    """One outcome and its allowed taxpayer-return interpretation."""

    model_config = ConfigDict(extra="forbid")

    outcome_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    category: Literal[
        "operating_firm",
        "private_capital",
        "licensing",
        "exit",
        "revenue",
        "productivity",
        "mission",
        "spillover",
        "knowledge",
    ]
    grain: str = Field(min_length=1)
    measure: str = Field(min_length=1)
    taxpayer_treatment: Literal[
        "direct_benefit",
        "validation_signal",
        "intermediate_output",
        "requires_incremental_value_added",
    ]
    standalone_success_measure: bool

    @model_validator(mode="after")
    def patents_are_not_standalone_success(self) -> "OutcomeContract":
        if self.outcome_id == "patents" and self.standalone_success_measure:
            raise ValueError("patents cannot be a standalone success measure")
        return self


class AttributionContract(BaseModel):
    """One evidence label and its minimum identification requirement."""

    model_config = ConfigDict(extra="forbid")

    evidence_class: Literal["causal", "descriptive", "inference"]
    allowed_weight_range: tuple[float, float]
    minimum_design: str = Field(min_length=1)
    prohibited_claim: str = Field(min_length=1)

    @model_validator(mode="after")
    def weight_range_is_ordered(self) -> "AttributionContract":
        low, high = self.allowed_weight_range
        if not (0 <= low <= high <= 1):
            raise ValueError("allowed_weight_range must be ordered within zero and one")
        return self


class LedgerItem(BaseModel):
    """One fiscal or domestic-social ledger line."""

    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    ledger: Literal["fiscal", "domestic_social"]
    side: Literal["benefit", "cost"]
    #: A non-additive item is a reported scenario, never a summand. A ledger
    #: calculator must draw its terms from ``additive_ledger_items`` so a
    #: comparison line cannot be subtracted into a net present value.
    additive: bool = True
    measure: str = Field(min_length=1)
    transfer_treatment: str = Field(min_length=1)
    overlap_group: str | None = None


class RoiContractBundle(BaseModel):
    """Shared, machine-readable assumptions for all four planned studies."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    contract_id: Literal["sbir-roi-comparative-tests-v1"]
    comparators: list[ComparatorContract] = Field(min_length=1)
    outcomes: list[OutcomeContract] = Field(min_length=1)
    attribution: list[AttributionContract] = Field(min_length=3)
    ledger: list[LedgerItem] = Field(min_length=1)

    @model_validator(mode="after")
    def ids_and_evidence_classes_are_unique(self) -> "RoiContractBundle":
        for label, values in (
            ("comparator_id", [item.comparator_id for item in self.comparators]),
            ("outcome_id", [item.outcome_id for item in self.outcomes]),
            ("item_id", [item.item_id for item in self.ledger]),
        ):
            duplicates = sorted({value for value in values if values.count(value) > 1})
            if duplicates:
                raise ValueError(f"duplicate {label}: {duplicates}")

        classes = [item.evidence_class for item in self.attribution]
        if sorted(classes) != ["causal", "descriptive", "inference"]:
            raise ValueError("attribution must define causal, descriptive, and inference once")
        return self

    def additive_ledger_items(self) -> list[LedgerItem]:
        """Return the only ledger items a net-present-value sum may include."""

        return [item for item in self.ledger if item.additive]

    def assert_summable(self, item_ids: list[str]) -> None:
        """Refuse a sum that includes a non-additive (scenario) item."""

        by_id = {item.item_id: item for item in self.ledger}
        unknown = sorted(set(item_ids) - set(by_id))
        if unknown:
            raise ValueError(f"unknown ledger items: {unknown}")
        non_additive = sorted(item_id for item_id in item_ids if not by_id[item_id].additive)
        if non_additive:
            raise ValueError(
                f"non-additive ledger items cannot enter a sum: {non_additive}; "
                "report them beside the net present value instead"
            )


def load_contract_bundle(path: Path = CONTRACT_PATH) -> RoiContractBundle:
    """Load and validate the shared SBIR ROI contract bundle."""

    raw = read_yaml_mapping(path, description="SBIR ROI contract bundle")
    return RoiContractBundle.model_validate(raw)


def validate_registry_bundle(path: Path = CONTRACT_PATH) -> int:
    """Validate the contract bundle and return the number of registered items."""

    bundle = load_contract_bundle(path)
    return (
        len(bundle.comparators)
        + len(bundle.outcomes)
        + len(bundle.attribution)
        + len(bundle.ledger)
    )


def main() -> int:
    """Validate the committed bundle for local and CI use."""

    validate_registry_bundle()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
