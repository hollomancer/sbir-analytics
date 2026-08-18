from pathlib import Path

from sbir_etl.quality.study_manifest import EvidenceStatus

from scripts.ci import check_research_question_status as guard


def test_denial_phrases_are_not_status_claims() -> None:
    text = (
        "Not computable. Phase 0 design only (exploratory, non-citable); "
        "not validated, and not approved for citation. No citable study "
        "manifest exists."
    )

    assert guard.claimed_ranks(text) == ()
    assert guard.claimed_ranks("Not currently computable.") == ()
    assert guard.claimed_ranks("Never computable from public data.") == ()
    assert guard.claimed_ranks("Cannot be validated without a hand-labelled sample.") == ()
    assert guard.claimed_ranks("This is not yet a citable result.") == ()


def test_citable_claim_and_citable_study_are_rank_claims() -> None:
    assert guard.claimed_ranks("Citable claim: the DoD follow-on multiplier is 4.1:1.") == (
        "citable",
    )
    assert guard.claimed_ranks("Citable study result approved for external reporting.") == (
        "citable",
    )
    assert guard.claimed_ranks("A citable study manifest backs this line.") == ("citable",)


def test_partially_computable_and_validated_are_claims() -> None:
    assert guard.claimed_ranks("Partially computable for the classified subset.") == ("computable",)
    assert guard.claimed_ranks("Validated against the frozen design.") == ("validated",)
    assert guard.claimed_ranks("Citable under the approved study contract.") == ("citable",)
    assert guard.claimed_ranks("Validated under the approved study contract.") == ("validated",)


def test_validates_verb_is_not_a_rank_claim() -> None:
    assert guard.claimed_ranks("The Phase 1 review validates the cohort component.") == ()
    assert guard.claimed_ranks("Partial and non-citable. The review validates the cohort.") == ()


def test_leading_negations_generalize_beyond_fixed_phrases() -> None:
    denials = (
        "No longer computable.",
        "Not fully validated.",
        "This is not computable.",
        "It isn't computable.",
        "No citable claim is authorized until the gates pass.",
        "Non-citable pending review.",
        "Coverage remains unvalidated.",
    )

    for text in denials:
        assert guard.claimed_ranks(text) == (), text


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


def test_section_id_resets_at_a_non_numbered_sibling_heading() -> None:
    markdown = """
### F4. Predictive (Tier 4)

- **Modelled outcome**
  **Status:** Research target.

#### A deeper sub-heading

- **Nested question**
  **Status:** Computable under the study.

### Form D fundraising analysis (published)

**Status:** Computable from the dated note.
"""

    blocks = list(guard.iter_status_blocks(markdown))

    assert blocks[0][1] == "F4"
    # A #### sub-heading is inside its ### section, so the section ID survives.
    assert blocks[1][1] == "F4"
    # A sibling ### heading with no A–F ID ends the section.
    assert blocks[2][1] is None


def test_claim_outside_numbered_section_is_rejected() -> None:
    markdown = (
        "### F4. Predictive (Tier 4)\n\n"
        "- **Modelled outcome**\n"
        "  **Status:** Research target.\n\n"
        "### Form D fundraising analysis (published)\n\n"
        "**Status:** Computable from the dated note.\n"
    )

    violations = guard.validate_inventory(markdown, {"F4": EvidenceStatus.CITABLE})

    assert len(violations) == 1
    assert "outside a numbered A–F section" in violations[0].message


def test_non_question_heading_clears_inherited_section_id() -> None:
    markdown = (
        "### F4. Predictive (Tier 4)\n\n"
        "## Output products & audiences\n\n"
        "### Form D fundraising analysis (published)\n\n"
        "**Status:** Citable for the 2024 vintage.\n"
    )

    blocks = list(guard.iter_status_blocks(markdown))
    violations = guard.validate_inventory(markdown, {"F4": EvidenceStatus.REPRODUCIBLE})

    assert blocks[0][1] is None
    assert violations and "outside a numbered A–F section" in violations[0].message


def test_repository_inventory_matches_live_studies() -> None:
    assert guard.validate_repository() == []


def test_start_here_requires_explicit_anchor_and_legal_status() -> None:
    markdown = """
### Start here

- See [leverage](#f3-form-d-leverage) and [watchlist](#a-cp13).

### F3. Inferential

- <a id="f3-form-d-leverage"></a>**Leverage**
  **Status:** Computable as a Form D lower bound.
  *Deps: ER*
"""

    violations = guard.validate_start_here(markdown)

    assert any("a-cp13" in item.message and "no explicit" in item.message for item in violations)
    assert not any("f3-form-d-leverage" in item.message for item in violations)


def test_start_here_rejects_research_target_status() -> None:
    markdown = """
### Start here

- [Watchlist](#a-cp13)

### A4. Risk

- <a id="a-cp13"></a>**Watchlist**
  **Status:** Research target — not yet scoped.
  *Deps: CET*
"""

    violations = guard.validate_start_here(markdown)

    assert violations
    assert "reserved Status" in violations[0].message


def test_start_here_allows_not_estimable_refusal() -> None:
    markdown = """
### Start here

- [Crowd-in](#f3-crowd-in-vs-crowd-out)

### F3. Inferential

- <a id="f3-crowd-in-vs-crowd-out"></a>**Crowd-in**
  **Status:** Not estimable from the Form D study design.
  *Deps: ER*
"""

    assert guard.validate_start_here(markdown) == []


def test_load_question_study_ranks_reads_census() -> None:
    ranks = guard.load_question_study_ranks(repository_root=Path(__file__).resolve().parents[3])

    assert ranks["B2"] is EvidenceStatus.REPRODUCIBLE
    assert ranks["B3"] is EvidenceStatus.REPRODUCIBLE
    assert ranks["E1"] is EvidenceStatus.REPRODUCIBLE
