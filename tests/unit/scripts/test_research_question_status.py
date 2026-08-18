from pathlib import Path

from sbir_etl.quality.study_manifest import EvidenceStatus

from scripts.ci import check_research_question_status as guard


def test_denial_phrases_are_not_status_claims() -> None:
    text = (
        "Not computable. Phase 0 design only (exploratory, non-citable); "
        "not validated, and not approved for citation. A citable study "
        "manifest is absent."
    )

    assert guard.claimed_ranks(text) == ()


def test_partially_computable_and_validates_are_claims() -> None:
    assert guard.claimed_ranks("Partially computable for the classified subset.") == ("computable",)
    assert guard.claimed_ranks("The Phase 1 review validates the cohort component.") == (
        "validated",
    )
    assert guard.claimed_ranks("Citable under the approved study contract.") == ("citable",)


def test_iter_status_blocks_tracks_section_headings() -> None:
    markdown = """
### B2. Relational (Tier 2)

- **Follow-on**
  **Status:** Computable as a proxy.
  *Deps: ER*

### E5. External data source evaluation (Tier 2)

**Status:** Research agenda.
"""

    blocks = list(guard.iter_status_blocks(markdown))

    assert blocks[0][1] == "B2"
    assert "Computable as a proxy" in blocks[0][2]
    assert blocks[1][1] == "E5"
    assert blocks[1][2] == "Research agenda."


def test_computable_requires_reproducible_study() -> None:
    markdown = (
        "### A1. Descriptive\n\n"
        "- **Concentration**\n"
        "  **Status:** Computable for the classified subset.\n"
        "  *Deps: CET*\n"
    )

    missing = guard.validate_inventory(markdown, {})
    exploratory = guard.validate_inventory(markdown, {"A1": EvidenceStatus.EXPLORATORY})
    reproducible = guard.validate_inventory(markdown, {"A1": EvidenceStatus.REPRODUCIBLE})

    assert missing and "need 'reproducible'" in missing[0].message
    assert exploratory and "highest matching study is 'exploratory'" in exploratory[0].message
    assert reproducible == []


def test_validated_and_citable_require_matching_ranks() -> None:
    markdown = "### B3. Inferential\n\n**Status:** Validated and citable.\n*Deps: ID*\n"

    only_validated = guard.validate_inventory(markdown, {"B3": EvidenceStatus.VALIDATED})
    citable = guard.validate_inventory(markdown, {"B3": EvidenceStatus.CITABLE})

    assert len(only_validated) == 1
    assert "claims 'citable'" in only_validated[0].message
    assert citable == []


def test_retired_study_does_not_authorize_computable() -> None:
    markdown = (
        "### F3. Inferential\n\n**Status:** Computable as a leverage ratio.\n*Deps: SEC EDGAR*\n"
    )

    violations = guard.validate_inventory(markdown, {"F3": EvidenceStatus.RETIRED})

    assert violations and "highest matching study is 'retired'" in violations[0].message


def test_claim_outside_numbered_section_is_rejected() -> None:
    markdown = "## Output products\n\n**Status:** Computable from the dated note.\n"

    violations = guard.validate_inventory(markdown, {})

    assert violations
    assert "outside a numbered A–F section" in violations[0].message


def test_repository_inventory_matches_live_studies() -> None:
    assert guard.validate_repository() == []


def test_load_question_study_ranks_reads_census() -> None:
    ranks = guard.load_question_study_ranks(repository_root=Path(__file__).resolve().parents[3])

    assert ranks["B2"] is EvidenceStatus.REPRODUCIBLE
    assert ranks["B3"] is EvidenceStatus.REPRODUCIBLE
    assert ranks["E1"] is EvidenceStatus.REPRODUCIBLE
