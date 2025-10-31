"""
Transition detection pipeline for SBIR Phase III commercialization tracking.

This module implements the complete detection pipeline that identifies
federal contracts likely resulting from SBIR awards. The detector:

1. Selects candidate contracts for vendors with SBIR awards
2. Resolves vendor identities using cross-walk
3. Filters contracts by timing window
4. Extracts and scores all signals
5. Generates evidence bundles
6. Classifies confidence levels

The pipeline supports batch processing for efficiency and provides
comprehensive logging and metrics.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4

from loguru import logger
from tqdm import tqdm

from src.models.transition_models import (
    ConfidenceLevel,
    FederalContract,
    Transition,
    VendorMatch,
)
from src.transition.detection.evidence import EvidenceGenerator
from src.transition.detection.scoring import TransitionScorer
from src.transition.features.vendor_resolver import VendorResolver


class TransitionDetector:
    """
    End-to-end pipeline for detecting SBIR → Federal Contract transitions.

    The detector orchestrates the complete workflow:
    - Candidate selection and filtering
    - Vendor matching and resolution
    - Multi-signal scoring
    - Evidence generation
    - Confidence classification

    Example:
        ```python
        # Load configuration
        config = load_yaml_config("config/transition/detection.yaml")

        # Initialize detector
        detector = TransitionDetector(
            config=config,
            vendor_resolver=vendor_resolver
        )

        # Detect transitions for an award
        detections = detector.detect_for_award(
            award=award,
            candidate_contracts=contracts
        )

        # Batch process multiple awards
        all_detections = detector.detect_batch(
            awards=awards,
            contracts=all_contracts,
            batch_size=1000
        )
        ```
    """

    def __init__(
        self,
        config: dict[str, Any],
        vendor_resolver: VendorResolver | None = None,
        scorer: TransitionScorer | None = None,
        evidence_generator: EvidenceGenerator | None = None,
    ):
        """
        Initialize transition detector with configuration and dependencies.

        Args:
            config: Configuration dict with timing windows, scoring weights, etc.
            vendor_resolver: Optional VendorResolver instance (created if not provided)
            scorer: Optional TransitionScorer instance (created if not provided)
            evidence_generator: Optional EvidenceGenerator (created if not provided)
        """
        self.config = config

        # Extract timing configuration
        timing_config = config.get("timing_window", {})
        self.min_days_after = timing_config.get("min_days_after_completion", 0)
        self.max_days_after = timing_config.get("max_days_after_completion", 730)  # 24 months

        # Extract vendor matching configuration
        self.vendor_config = config.get("vendor_matching", {})
        self.require_vendor_match = self.vendor_config.get("require_match", True)

        # Initialize dependencies
        self.vendor_resolver = vendor_resolver or VendorResolver.from_records([])
        self.scorer = scorer or TransitionScorer(config)
        self.evidence_generator = evidence_generator or EvidenceGenerator()

        # Metrics tracking
        self.metrics = {
            "total_awards_processed": 0,
            "total_contracts_evaluated": 0,
            "total_detections": 0,
            "high_confidence": 0,
            "likely_confidence": 0,
            "possible_confidence": 0,
            "vendor_matches": 0,
            "vendor_match_failures": 0,
        }

        logger.info(
            "Initialized TransitionDetector",
            extra={
                "timing_window_days": f"{self.min_days_after}-{self.max_days_after}",
                "require_vendor_match": self.require_vendor_match,
            },
        )

    def filter_by_timing_window(
        self,
        award_completion_date: date,
        contracts: Iterable[FederalContract],
    ) -> list[FederalContract]:
        """
        Filter contracts to those within configured timing window.

        Args:
            award_completion_date: Date SBIR award was completed
            contracts: Candidate contracts to filter

        Returns:
            List of contracts within timing window
        """
        min_date = award_completion_date + timedelta(days=self.min_days_after)
        max_date = award_completion_date + timedelta(days=self.max_days_after)

        filtered = []
        for contract in contracts:
            if not contract.start_date:
                continue

            if min_date <= contract.start_date <= max_date:
                filtered.append(contract)

        logger.debug(
            "Filtered contracts by timing window",
            extra={
                "total_contracts": len(list(contracts))
                if isinstance(contracts, list)
                else "unknown",
                "filtered_count": len(filtered),
                "window": f"{self.min_days_after}-{self.max_days_after} days",
            },
        )

        return filtered

    def match_vendor(
        self,
        contract: FederalContract,
        award_vendor_id: str | None = None,
    ) -> VendorMatch | None:
        """
        Match contract vendor to award vendor using resolver.

        Tries multiple matching methods in priority order:
        1. UEI (primary)
        2. CAGE code
        3. DUNS number
        4. Fuzzy name matching

        Args:
            contract: Contract to match vendor for
            award_vendor_id: Optional known vendor ID from award

        Returns:
            VendorMatch (from transition_models) if successful, None otherwise
        """
        from src.transition.features.vendor_resolver import VendorMatch as ResolverMatch

        # Try UEI first
        if contract.vendor_uei:
            resolver_match: ResolverMatch = self.vendor_resolver.resolve_by_uei(contract.vendor_uei)
            if resolver_match.record:
                self.metrics["vendor_matches"] += 1
                from src.models.transition_models import VendorMatch

                return VendorMatch(
                    vendor_id=resolver_match.record.metadata.get("vendor_id")
                    or contract.vendor_uei,
                    method="uei",
                    score=1.0,
                    matched_name=resolver_match.record.name,
                    metadata={"uei": contract.vendor_uei},
                )

        # Try CAGE code
        if contract.vendor_cage:
            resolver_match = self.vendor_resolver.resolve_by_cage(contract.vendor_cage)
            if resolver_match.record:
                self.metrics["vendor_matches"] += 1
                from src.models.transition_models import VendorMatch

                return VendorMatch(
                    vendor_id=resolver_match.record.metadata.get("vendor_id")
                    or contract.vendor_cage,
                    method="cage",
                    score=1.0,
                    matched_name=resolver_match.record.name,
                    metadata={"cage": contract.vendor_cage},
                )

        # Try DUNS number
        if contract.vendor_duns:
            resolver_match = self.vendor_resolver.resolve_by_duns(contract.vendor_duns)
            if resolver_match.record:
                self.metrics["vendor_matches"] += 1
                from src.models.transition_models import VendorMatch

                return VendorMatch(
                    vendor_id=resolver_match.record.metadata.get("vendor_id")
                    or contract.vendor_duns,
                    method="duns",
                    score=1.0,
                    matched_name=resolver_match.record.name,
                    metadata={"duns": contract.vendor_duns},
                )

        # Try fuzzy name matching
        if contract.vendor_name:
            resolver_match = self.vendor_resolver.resolve_by_name(contract.vendor_name)
            if resolver_match.record and resolver_match.score >= self.vendor_config.get(
                "fuzzy_threshold", 0.85
            ):
                self.metrics["vendor_matches"] += 1
                from src.models.transition_models import VendorMatch

                return VendorMatch(
                    vendor_id=resolver_match.record.metadata.get("vendor_id", "unknown"),
                    method="name_fuzzy",
                    score=resolver_match.score,
                    matched_name=resolver_match.record.name,
                    metadata={
                        "input_name": contract.vendor_name,
                        "fuzzy_score": resolver_match.score,
                    },
                )

        # No match found
        self.metrics["vendor_match_failures"] += 1
        logger.debug(
            "Vendor match failed",
            extra={
                "contract_id": contract.contract_id,
                "vendor_name": contract.vendor_name,
                "uei": contract.vendor_uei,
                "cage": contract.vendor_cage,
                "duns": contract.vendor_duns,
            },
        )
        return None

    def detect_for_award(
        self,
        award: dict[str, Any],
        candidate_contracts: list[FederalContract],
        patent_data: dict[str, Any] | None = None,
        cet_data: dict[str, Any] | None = None,
    ) -> list[Transition]:
        """
        Detect transitions for a single SBIR award.

        Args:
            award: Award data dict with award_id, completion_date, agency, etc.
            candidate_contracts: List of contracts to evaluate
            patent_data: Optional patent information for vendor
            cet_data: Optional CET classification data

        Returns:
            List of Transition objects for detected transitions
        """
        award_id = award.get("award_id")
        completion_date = award.get("completion_date")

        if not completion_date:
            logger.warning(f"Award {award_id} missing completion_date, skipping")
            return []

        detections = []
        self.metrics["total_awards_processed"] += 1

        # Filter contracts by timing window
        filtered_contracts = self.filter_by_timing_window(completion_date, candidate_contracts)

        # Process each candidate contract
        for contract in filtered_contracts:
            self.metrics["total_contracts_evaluated"] += 1

            # Match vendor
            vendor_match = self.match_vendor(contract, award.get("vendor_id"))

            if not vendor_match and self.require_vendor_match:
                logger.debug(
                    f"Skipping contract {contract.contract_id}: vendor match required but not found"
                )
                continue

            # Score transition
            signals, likelihood_score, confidence = self.scorer.score_and_classify(
                award_data=award,
                contract=contract,
                patent_data=patent_data,
                cet_data=cet_data,
            )

            # Generate evidence bundle
            evidence_bundle = self.evidence_generator.generate_bundle(
                signals=signals,
                award_data=award,
                vendor_match=vendor_match,
                contract=contract,
                patent_data=patent_data,
                cet_data=cet_data,
            )

            # Create transition object
            transition = Transition(
                transition_id=str(uuid4()),
                award_id=award_id,
                detected_at=datetime.utcnow(),
                likelihood_score=likelihood_score,
                confidence=confidence,
                primary_contract=contract,
                signals=signals,
                evidence=evidence_bundle,
                metadata={
                    "vendor_match": vendor_match.model_dump() if vendor_match else None,
                },
            )

            detections.append(transition)
            self.metrics["total_detections"] += 1

            # Track by confidence level
            if confidence == ConfidenceLevel.HIGH:
                self.metrics["high_confidence"] += 1
            elif confidence == ConfidenceLevel.LIKELY:
                self.metrics["likely_confidence"] += 1
            else:
                self.metrics["possible_confidence"] += 1

            logger.debug(
                "Detected transition",
                extra={
                    "transition_id": transition.transition_id,
                    "award_id": award_id,
                    "contract_id": contract.contract_id,
                    "likelihood_score": likelihood_score,
                    "confidence": confidence.value,
                },
            )

        logger.info(
            f"Processed award {award_id}",
            extra={
                "detections": len(detections),
                "candidate_contracts": len(candidate_contracts),
                "filtered_contracts": len(filtered_contracts),
            },
        )

        return detections

    def detect_batch(
        self,
        awards: list[dict[str, Any]],
        contracts: list[FederalContract],
        batch_size: int = 1000,
        show_progress: bool = True,
    ) -> Iterator[Transition]:
        """
        Detect transitions for multiple awards in batches.

        Yields detections as they're produced to support streaming processing.

        Args:
            awards: List of award data dicts
            contracts: List of all candidate contracts
            batch_size: Number of awards to process per batch
            show_progress: Whether to show progress bar

        Yields:
            Transition objects as they're detected
        """
        # Index contracts by vendor for efficient lookup
        # (In production, this would use DuckDB or similar for larger datasets)
        contract_map: dict[str, list[FederalContract]] = {}
        for contract in contracts:
            vendor_id = (
                contract.vendor_uei
                or contract.vendor_cage
                or contract.vendor_duns
                or contract.vendor_name
            )
            if vendor_id:
                if vendor_id not in contract_map:
                    contract_map[vendor_id] = []
                contract_map[vendor_id].append(contract)

        logger.info(
            "Indexed contracts by vendor",
            extra={
                "total_contracts": len(contracts),
                "unique_vendors": len(contract_map),
            },
        )

        # Process awards in batches
        total_awards = len(awards)
        pbar = tqdm(total=total_awards, desc="Detecting transitions") if show_progress else None

        for i in range(0, total_awards, batch_size):
            batch = awards[i : i + batch_size]

            for award in batch:
                # Get candidate contracts for this award's vendor
                vendor_id = (
                    award.get("vendor_uei")
                    or award.get("vendor_cage")
                    or award.get("vendor_duns")
                    or award.get("vendor_name")
                )

                candidate_contracts = contract_map.get(vendor_id, [])

                # Detect transitions
                detections = self.detect_for_award(
                    award=award,
                    candidate_contracts=candidate_contracts,
                    patent_data=award.get("patent_data"),
                    cet_data=award.get("cet_data"),
                )

                # Yield each detection
                for detection in detections:
                    yield detection

                if pbar:
                    pbar.update(1)

        if pbar:
            pbar.close()

        # Log final metrics
        logger.info(
            "Batch detection complete",
            extra={
                "metrics": self.metrics,
            },
        )

    def get_metrics(self) -> dict[str, Any]:
        """
        Get current detection metrics.

        Returns:
            Dict with metrics including counts, rates, and performance stats
        """
        total_detections = self.metrics["total_detections"]
        total_awards = self.metrics["total_awards_processed"]

        metrics = {
            **self.metrics,
            "detection_rate": (total_detections / total_awards if total_awards > 0 else 0.0),
            "vendor_match_rate": (
                self.metrics["vendor_matches"]
                / (self.metrics["vendor_matches"] + self.metrics["vendor_match_failures"])
                if (self.metrics["vendor_matches"] + self.metrics["vendor_match_failures"]) > 0
                else 0.0
            ),
            "high_confidence_rate": (
                self.metrics["high_confidence"] / total_detections if total_detections > 0 else 0.0
            ),
        }

        return metrics

    def reset_metrics(self) -> None:
        """Reset all metrics counters."""
        for key in self.metrics:
            self.metrics[key] = 0
        logger.debug("Reset detection metrics")


__all__ = ["TransitionDetector"]
