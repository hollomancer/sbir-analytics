"""Deterministic prerequisites for Phase III negative controls."""

from .february_mirror import FebruaryAwardSearchExtractor
from .covariates import (
    CONTRACT_COLUMNS,
    MATCH_COVARIATES,
    CovariateInputError,
    build_control_firm_frame,
    build_firm_covariates,
    build_treated_firm_frame,
    summarize_covariate_coverage,
)
from .identity import (
    IdentityRecoveryError,
    RecoveryStatus,
    reconcile_award_identity_attempts,
    resolve_award_identities,
)
from .nih_reporter import NIHReporterExtractor
from .quarantine import (
    QuarantineKeyCoverage,
    build_unresolved_quarantine_key_audit,
    quarantine_key_gate,
    require_complete_unresolved_quarantine_keys,
    summarize_quarantine_key_coverage,
)
from .sam_eligibility import (
    EligibilityStatus,
    build_sam_eligibility_table,
    exclude_fpds_coded_awardees,
    exclude_phase_ii_awardees,
    require_reliable_sam_eligibility,
    sam_eligibility_gate,
    summarize_sam_eligibility,
    summarize_sam_exclusion_reasons,
)
from .source_keys import (
    build_nih_official_keys,
    build_nih_sbir_attempts,
    build_usaspending_official_keys,
    build_usaspending_sbir_attempts,
)
from .matching import (
    build_balance_table,
    exact_match_controls,
    require_covariate_balance,
    summarize_matching,
)

__all__ = [
    "IdentityRecoveryError",
    "CovariateInputError",
    "CONTRACT_COLUMNS",
    "EligibilityStatus",
    "RecoveryStatus",
    "FebruaryAwardSearchExtractor",
    "NIHReporterExtractor",
    "MATCH_COVARIATES",
    "QuarantineKeyCoverage",
    "build_nih_official_keys",
    "build_nih_sbir_attempts",
    "build_usaspending_official_keys",
    "build_usaspending_sbir_attempts",
    "build_unresolved_quarantine_key_audit",
    "build_sam_eligibility_table",
    "exclude_fpds_coded_awardees",
    "exclude_phase_ii_awardees",
    "build_control_firm_frame",
    "build_firm_covariates",
    "build_treated_firm_frame",
    "build_balance_table",
    "exact_match_controls",
    "quarantine_key_gate",
    "reconcile_award_identity_attempts",
    "require_complete_unresolved_quarantine_keys",
    "resolve_award_identities",
    "require_reliable_sam_eligibility",
    "sam_eligibility_gate",
    "require_covariate_balance",
    "summarize_quarantine_key_coverage",
    "summarize_sam_eligibility",
    "summarize_sam_exclusion_reasons",
    "summarize_covariate_coverage",
    "summarize_matching",
]
