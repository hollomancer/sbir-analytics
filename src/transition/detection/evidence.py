"""
Evidence bundle generation for transition detections.

This module creates comprehensive audit trails for each detected transition,
documenting all signals, scores, and supporting data to ensure transparency
and reproducibility.

Evidence bundles are serialized to JSON and stored on Neo4j relationship
properties for query-time inspection and verification.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from src.models.transition_models import (
    AgencySignal,
    CETSignal,
    CompetitionSignal,
    CompetitionType,
    EvidenceBundle,
    EvidenceItem,
    FederalContract,
    PatentSignal,
    TimingSignal,
    TransitionSignals,
    VendorMatch,
)


class EvidenceGenerator:
    """
    Generates comprehensive evidence bundles for transition detections.

    Creates structured, auditable evidence trails documenting all signals,
    scores, and supporting data that contributed to the detection.

    Example:
        ```python
        generator = EvidenceGenerator()

        # Generate evidence for all signals
        bundle = generator.generate_bundle(
            signals=signals,
            award_data={"award_id": "ABC123", ...},
            contract_data={"contract_id": "XYZ789", ...},
            vendor_match=vendor_match
        )

        # Serialize to JSON for storage
        json_str = generator.serialize_bundle(bundle)

        # Validate bundle completeness
        is_valid = generator.validate_bundle(bundle)
        ```
    """

    def __init__(self):
        """Initialize evidence generator."""
        logger.debug("Initialized EvidenceGenerator")

    def generate_agency_evidence(
        self,
        signal: AgencySignal,
        award_agency: Optional[str],
        contract_agency: Optional[str],
        award_department: Optional[str] = None,
        contract_department: Optional[str] = None,
    ) -> EvidenceItem:
        """
        Generate evidence item for agency continuity signal.

        Args:
            signal: Computed AgencySignal
            award_agency: SBIR award agency code
            contract_agency: Contract agency code
            award_department: Optional award department
            contract_department: Optional contract department

        Returns:
            EvidenceItem documenting agency continuity
        """
        metadata = {
            "award_agency": award_agency,
            "contract_agency": contract_agency,
            "same_agency": signal.same_agency,
        }

        if award_department and contract_department:
            metadata.update(
                {
                    "award_department": award_department,
                    "contract_department": contract_department,
                    "same_department": signal.same_department,
                }
            )

        if signal.same_agency:
            snippet = f"Award and contract both from {award_agency}"
        elif signal.same_department:
            snippet = (
                f"Award ({award_agency}) and contract ({contract_agency}) "
                f"within same department ({award_department})"
            )
        else:
            snippet = (
                f"Award agency ({award_agency}) differs from contract agency ({contract_agency})"
            )

        return EvidenceItem(
            source="sbir_award_data",
            signal="agency",
            snippet=snippet,
            score=signal.agency_score,
            metadata=metadata,
        )

    def generate_timing_evidence(
        self,
        signal: TimingSignal,
        award_completion_date: Optional[date],
        contract_start_date: Optional[date],
        award_id: Optional[str] = None,
        contract_id: Optional[str] = None,
    ) -> EvidenceItem:
        """
        Generate evidence item for timing proximity signal.

        Args:
            signal: Computed TimingSignal
            award_completion_date: Date SBIR award completed
            contract_start_date: Date contract started
            award_id: Optional award identifier for citation
            contract_id: Optional contract identifier for citation

        Returns:
            EvidenceItem documenting timing relationship
        """
        metadata = {
            "award_completion_date": (
                award_completion_date.isoformat() if award_completion_date else None
            ),
            "contract_start_date": contract_start_date.isoformat() if contract_start_date else None,
            "days_between": signal.days_between_award_and_contract,
            "months_between": signal.months_between_award_and_contract,
        }

        if award_id:
            metadata["award_id"] = award_id
        if contract_id:
            metadata["contract_id"] = contract_id

        if signal.days_between_award_and_contract is not None:
            days = signal.days_between_award_and_contract
            months = signal.months_between_award_and_contract or 0

            if days < 0:
                snippet = f"Contract started {abs(days)} days before award completion (anomaly)"
            elif days <= 90:
                snippet = f"Contract started {days} days ({months:.1f} months) after award completion (high proximity)"
            elif days <= 365:
                snippet = f"Contract started {days} days ({months:.1f} months) after award completion (moderate proximity)"
            else:
                snippet = (
                    f"Contract started {days} days ({months:.1f} months) after award completion"
                )
        else:
            snippet = "Timing data incomplete"

        return EvidenceItem(
            source="timing_analysis",
            signal="timing",
            snippet=snippet,
            score=signal.timing_score,
            metadata=metadata,
        )

    def generate_competition_evidence(
        self,
        signal: CompetitionSignal,
        contract_id: Optional[str] = None,
    ) -> EvidenceItem:
        """
        Generate evidence item for competition type signal.

        Args:
            signal: Computed CompetitionSignal
            contract_id: Optional contract identifier

        Returns:
            EvidenceItem documenting competition type
        """
        comp_type = signal.competition_type
        metadata = {
            "competition_type": comp_type.value if comp_type else "unknown",
        }

        if contract_id:
            metadata["contract_id"] = contract_id

        # Map competition type to description
        comp_descriptions = {
            CompetitionType.SOLE_SOURCE: "Sole source (vendor specifically targeted)",
            CompetitionType.LIMITED: "Limited competition (restricted vendor pool)",
            CompetitionType.FULL_AND_OPEN: "Full and open competition",
            CompetitionType.OTHER: "Other/unknown competition type",
        }

        snippet = comp_descriptions.get(comp_type, "Unknown competition type")

        return EvidenceItem(
            source="usaspending",
            signal="competition",
            snippet=snippet,
            score=signal.competition_score,
            metadata=metadata,
        )

    def generate_patent_evidence(
        self,
        signal: PatentSignal,
        vendor_id: Optional[str] = None,
        contract_start_date: Optional[date] = None,
    ) -> EvidenceItem:
        """
        Generate evidence item for patent signal.

        Args:
            signal: Computed PatentSignal
            vendor_id: Optional vendor identifier
            contract_start_date: Optional contract start date for context

        Returns:
            EvidenceItem documenting patent indicators
        """
        metadata = {
            "patent_count": signal.patent_count,
            "patents_pre_contract": signal.patents_pre_contract,
            "patent_topic_similarity": signal.patent_topic_similarity,
        }

        if vendor_id:
            metadata["vendor_id"] = vendor_id

        if contract_start_date:
            metadata["contract_start_date"] = contract_start_date.isoformat()

        # Build descriptive snippet
        parts = []
        if signal.patent_count > 0:
            parts.append(f"{signal.patent_count} patent(s) found")

            if signal.patents_pre_contract > 0:
                parts.append(f"{signal.patents_pre_contract} filed before contract")

            if signal.patent_topic_similarity is not None:
                parts.append(f"topic similarity: {signal.patent_topic_similarity:.2f}")

        snippet = "; ".join(parts) if parts else "No patents found"

        return EvidenceItem(
            source="patentsview",
            signal="patent",
            snippet=snippet,
            score=signal.patent_score,
            metadata=metadata,
        )

    def generate_cet_evidence(
        self,
        signal: CETSignal,
    ) -> EvidenceItem:
        """
        Generate evidence item for CET area alignment signal.

        Args:
            signal: Computed CETSignal

        Returns:
            EvidenceItem documenting CET alignment
        """
        metadata = {
            "award_cet": signal.award_cet,
            "contract_cet": signal.contract_cet,
        }

        if signal.award_cet and signal.contract_cet:
            if signal.award_cet.upper() == signal.contract_cet.upper():
                snippet = f"Award and contract both in CET area: {signal.award_cet}"
            else:
                snippet = (
                    f"Award CET ({signal.award_cet}) differs from "
                    f"contract CET ({signal.contract_cet})"
                )
        elif signal.award_cet:
            snippet = f"Award in CET area {signal.award_cet}; contract CET unknown"
        elif signal.contract_cet:
            snippet = f"Contract in CET area {signal.contract_cet}; award CET unknown"
        else:
            snippet = "CET area data not available"

        return EvidenceItem(
            source="cet_classification",
            signal="cet",
            snippet=snippet,
            score=signal.cet_alignment_score,
            metadata=metadata,
        )

    def generate_vendor_match_evidence(
        self,
        vendor_match: VendorMatch,
    ) -> EvidenceItem:
        """
        Generate evidence item for vendor matching.

        Args:
            vendor_match: VendorMatch result from resolution

        Returns:
            EvidenceItem documenting vendor matching
        """
        metadata = {
            "vendor_id": vendor_match.vendor_id,
            "method": vendor_match.method,
            "matched_name": vendor_match.matched_name,
            **vendor_match.metadata,
        }

        # Build snippet based on match method
        method_descriptions = {
            "uei": "exact UEI match",
            "cage": "exact CAGE code match",
            "duns": "exact DUNS match",
            "name_fuzzy": f"fuzzy name match (score: {vendor_match.score:.2f})",
        }

        method_desc = method_descriptions.get(vendor_match.method, vendor_match.method)

        snippet = f"Vendor matched via {method_desc}"
        if vendor_match.matched_name:
            snippet += f": {vendor_match.matched_name}"

        return EvidenceItem(
            source="vendor_crosswalk",
            signal="vendor_match",
            snippet=snippet,
            score=vendor_match.score,
            metadata=metadata,
        )

    def generate_contract_details_evidence(
        self,
        contract: FederalContract,
    ) -> EvidenceItem:
        """
        Generate evidence item for contract details.

        Args:
            contract: FederalContract model instance

        Returns:
            EvidenceItem documenting contract details
        """
        metadata = {
            "contract_id": contract.contract_id,
            "agency": contract.agency,
            "sub_agency": contract.sub_agency,
            "vendor_name": contract.vendor_name,
            "start_date": contract.start_date.isoformat() if contract.start_date else None,
            "end_date": contract.end_date.isoformat() if contract.end_date else None,
            "obligation_amount": contract.obligation_amount,
        }

        # Build contract summary snippet
        parts = [f"Contract {contract.contract_id}"]

        if contract.agency:
            parts.append(f"with {contract.agency}")

        if contract.obligation_amount:
            amount_str = f"${contract.obligation_amount:,.0f}"
            parts.append(f"for {amount_str}")

        if contract.start_date:
            parts.append(f"starting {contract.start_date.isoformat()}")

        snippet = " ".join(parts)

        return EvidenceItem(
            source="usaspending",
            signal="contract_details",
            snippet=snippet,
            metadata=metadata,
        )

    def generate_bundle(
        self,
        signals: TransitionSignals,
        award_data: Dict[str, Any],
        contract: FederalContract,
        vendor_match: Optional[VendorMatch] = None,
        patent_data: Optional[Dict[str, Any]] = None,
        cet_data: Optional[Dict[str, Any]] = None,
    ) -> EvidenceBundle:
        """
        Generate complete evidence bundle for a transition detection.

        Args:
            signals: Computed TransitionSignals with all signal scores
            award_data: Award information dict
            contract: FederalContract model
            vendor_match: Optional VendorMatch result
            patent_data: Optional patent information
            cet_data: Optional CET alignment data

        Returns:
            Complete EvidenceBundle with all evidence items
        """
        bundle = EvidenceBundle()

        # Generate agency evidence
        if signals.agency:
            agency_evidence = self.generate_agency_evidence(
                signal=signals.agency,
                award_agency=award_data.get("agency"),
                contract_agency=contract.agency,
                award_department=award_data.get("department"),
                contract_department=contract.sub_agency,
            )
            bundle.add_item(agency_evidence)

        # Generate timing evidence
        if signals.timing:
            timing_evidence = self.generate_timing_evidence(
                signal=signals.timing,
                award_completion_date=award_data.get("completion_date"),
                contract_start_date=contract.start_date,
                award_id=award_data.get("award_id"),
                contract_id=contract.contract_id,
            )
            bundle.add_item(timing_evidence)

        # Generate competition evidence
        if signals.competition:
            competition_evidence = self.generate_competition_evidence(
                signal=signals.competition,
                contract_id=contract.contract_id,
            )
            bundle.add_item(competition_evidence)

        # Generate patent evidence
        if signals.patent:
            patent_evidence = self.generate_patent_evidence(
                signal=signals.patent,
                vendor_id=vendor_match.vendor_id if vendor_match else None,
                contract_start_date=contract.start_date,
            )
            bundle.add_item(patent_evidence)

        # Generate CET evidence
        if signals.cet:
            cet_evidence = self.generate_cet_evidence(signal=signals.cet)
            bundle.add_item(cet_evidence)

        # Generate vendor match evidence
        if vendor_match:
            vendor_evidence = self.generate_vendor_match_evidence(vendor_match)
            bundle.add_item(vendor_evidence)

        # Generate contract details evidence
        if contract:
            contract_evidence = self.generate_contract_details_evidence(contract)
            bundle.add_item(contract_evidence)

        # Generate summary
        signal_count = len(bundle.items)
        total_score = bundle.total_score()
        bundle.summary = (
            f"Transition detection with {signal_count} evidence items "
            f"(avg score: {total_score:.2f})"
        )

        logger.debug(
            "Generated evidence bundle",
            extra={
                "evidence_items": signal_count,
                "total_score": total_score,
                "award_id": award_data.get("award_id"),
                "contract_id": contract.contract_id,
            },
        )

        return bundle

    def serialize_bundle(self, bundle: EvidenceBundle) -> str:
        """
        Serialize evidence bundle to JSON string.

        Args:
            bundle: EvidenceBundle to serialize

        Returns:
            JSON string representation
        """
        return bundle.model_dump_json(indent=2)

    def deserialize_bundle(self, json_str: str) -> EvidenceBundle:
        """
        Deserialize evidence bundle from JSON string.

        Args:
            json_str: JSON string representation

        Returns:
            EvidenceBundle instance

        Raises:
            ValidationError: If JSON is invalid or doesn't match schema
        """
        return EvidenceBundle.model_validate_json(json_str)

    def validate_bundle(self, bundle: EvidenceBundle) -> bool:
        """
        Validate evidence bundle completeness and consistency.

        Checks:
        - Has at least one evidence item
        - All items have required fields
        - Scores are in valid range (0.0-1.0)
        - Created timestamp is present

        Args:
            bundle: EvidenceBundle to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            # Check has items
            if not bundle.items:
                logger.warning("Evidence bundle has no items")
                return False

            # Check each item
            for i, item in enumerate(bundle.items):
                if not item.source:
                    logger.warning(f"Evidence item {i} missing source")
                    return False

                if not item.signal:
                    logger.warning(f"Evidence item {i} missing signal")
                    return False

                if item.score is not None and not (0.0 <= item.score <= 1.0):
                    logger.warning(f"Evidence item {i} score out of range: {item.score}")
                    return False

            # Check timestamp
            if not bundle.created_at:
                logger.warning("Evidence bundle missing created_at timestamp")
                return False

            return True

        except Exception as e:
            logger.error(f"Evidence bundle validation error: {e}")
            return False


__all__ = ["EvidenceGenerator"]
