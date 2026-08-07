"""Observable supply-network relationships involving SBIR awardees.

Epistemic tier: pipelines. Modules normalize observed funding relationships
and build reproducible releases without asserting criticality. The exploratory
CET screen (``nsf_screen``) is deliberately not re-exported here: importing the
pipelines package must not pull in contestable inference, so its callers import
``sbir_etl.supply_chain.nsf_screen`` directly (spec epistemic-tier-enforcement
R3).
"""

from sbir_etl.supply_chain.defense_funding import (
    build_defense_funding_summary,
    build_nsf_award_defense_evidence,
    build_nsf_identity_registry,
    combine_prime_transactions,
    evaluate_defense_funding_quality,
    normalize_prime_api_transactions,
    normalize_prime_archive_transactions,
    normalize_subaward_transactions,
)
from sbir_etl.supply_chain.nsf_direct import (
    NSFReconciliationResult,
    build_nsf_sbir_baseline,
    classify_nsf_award_status,
    load_nsf_sbir_baseline,
    reconcile_nsf_sbir_awards,
    requested_nsf_award_ids,
)
from sbir_etl.supply_chain.release_validation import validate_nsf_defense_lineage_release
from sbir_etl.supply_chain.subaward_network import (
    aggregate_supplier_prime_edges,
    build_sbir_awardee_registry,
    build_supplier_customer_exposure,
    build_subaward_facts,
)


EPISTEMIC_TIER = "pipelines"

__all__ = [
    "NSFReconciliationResult",
    "aggregate_supplier_prime_edges",
    "build_defense_funding_summary",
    "build_nsf_award_defense_evidence",
    "build_nsf_identity_registry",
    "build_nsf_sbir_baseline",
    "build_sbir_awardee_registry",
    "build_supplier_customer_exposure",
    "build_subaward_facts",
    "classify_nsf_award_status",
    "combine_prime_transactions",
    "evaluate_defense_funding_quality",
    "load_nsf_sbir_baseline",
    "normalize_prime_api_transactions",
    "normalize_prime_archive_transactions",
    "normalize_subaward_transactions",
    "reconcile_nsf_sbir_awards",
    "requested_nsf_award_ids",
    "validate_nsf_defense_lineage_release",
]
