"""Adversarial tests for the exploratory research-institution resolver.

Every rule that can return a positive match has at least one input where it
must not fire. A false positive here reads as a collaboration, not as a crash.
"""

from __future__ import annotations

import pytest

from scripts.research_institutions.ri_resolver import (
    RULE_ALIAS,
    RULE_AMBIGUOUS,
    RULE_BLANK,
    RULE_EXACT,
    RULE_MAIN_CAMPUS,
    RULE_UNRESOLVED,
    ReferenceInstitution,
    RIResolver,
    alias_is_specific,
    build_default_resolver,
    is_placeholder,
    match_rate_table,
    resolution_frame,
    ri_key,
    split_aliases,
)


pytestmark = pytest.mark.fast


def _fixture_resolver() -> RIResolver:
    return RIResolver(
        [
            ReferenceInstitution(
                "ipeds:1", "Massachusetts Institute of Technology", "ipeds", "MA", ("MIT", "M.I.T.")
            ),
            ReferenceInstitution(
                "ipeds:2",
                "Georgia Institute of Technology-Main Campus",
                "ipeds",
                "GA",
                ("Georgia Tech",),
            ),
            ReferenceInstitution("ipeds:3", "The University of Texas at Austin", "ipeds", "TX"),
            ReferenceInstitution("ipeds:4", "Columbia College", "ipeds", "SC"),
            ReferenceInstitution("ipeds:5", "Columbia College", "ipeds", "MO"),
            ReferenceInstitution(
                "ipeds:6", "University of the Pacific", "ipeds", "CA", ("Pacific", "UOP")
            ),
            ReferenceInstitution("ipeds:7", "Arkansas Tech University", "ipeds", "AR", ("Tech",)),
            ReferenceInstitution("ipeds:8", "Glendale Community College", "ipeds", "CA", ("GCC",)),
            ReferenceInstitution("ipeds:9", "Glendale Community College", "ipeds", "AZ", ("GCC",)),
            # An alias that collides with another institution's exact name.
            ReferenceInstitution(
                "ipeds:10", "Prescott College", "ipeds", "AZ", ("Prescott University",)
            ),
            ReferenceInstitution("ipeds:11", "Prescott University", "ipeds", "AZ"),
            ReferenceInstitution("ffrdc:lincoln-laboratory", "Lincoln Laboratory", "ffrdc", "MA"),
        ]
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("The University of Texas at Austin", "UNIVERSITY OF TEXAS AT AUSTIN"),
        ("University of Texas at Austin", "UNIVERSITY OF TEXAS AT AUSTIN"),
        ("Georgia Tech Research Corp", "GEORGIA TECH RESEARCH"),
        ("  Oak Ridge National Laboratory  ", "OAK RIDGE NATIONAL LABORATORY"),
    ],
)
def test_ri_key_folds_the_leading_article_and_trailing_designators(
    value: str, expected: str
) -> None:
    assert ri_key(value) == expected


@pytest.mark.parametrize(
    "value", [None, "", "   ", "N/A", "n/a", "NA", "None", "null", "-", float("nan")]
)
def test_placeholders_are_typed_missingness(value: object) -> None:
    assert is_placeholder(value)
    assert _fixture_resolver().resolve(value).rule == RULE_BLANK


def test_split_aliases_handles_pipes_commas_and_double_spaces() -> None:
    assert split_aliases("AUM||Auburn University at Montgomery|Auburn Montgomery") == (
        "AUM",
        "Auburn University at Montgomery",
        "Auburn Montgomery",
    )
    assert split_aliases("Lurleen B. Wallace Community College, LBW Community College, LBWCC") == (
        "Lurleen B. Wallace Community College",
        "LBW Community College",
        "LBWCC",
    )
    assert split_aliases("UCSF  UC San Francisco  University of California at San Francisco") == (
        "UCSF",
        "UC San Francisco",
        "University of California at San Francisco",
    )
    assert split_aliases(None) == ()
    assert split_aliases(" ") == ()


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("MIT", True),
        ("UCSF", True),
        ("UT Austin", True),
        ("Georgia Tech", True),
        # Generic single words and two-letter codes must not become aliases.
        ("Tech", False),
        ("Pacific", False),
        ("Arkansas", False),
        ("the Hill", False),
        ("The Academy", False),
        ("UA", False),
        ("PC", False),
        ("", False),
    ],
)
def test_alias_specificity_guard(alias: str, expected: bool) -> None:
    assert alias_is_specific(alias) is expected


def test_exact_name_resolves_with_and_without_the_leading_article() -> None:
    resolver = _fixture_resolver()
    for surface in ("The University of Texas at Austin", "University of Texas at Austin"):
        outcome = resolver.resolve(surface)
        assert outcome.rule == RULE_EXACT
        assert outcome.reference_id == "ipeds:3"


def test_main_campus_suffix_is_a_derived_match_not_a_guess() -> None:
    outcome = _fixture_resolver().resolve("Georgia Institute of Technology")
    assert outcome.rule == RULE_MAIN_CAMPUS
    assert outcome.reference_id == "ipeds:2"


def test_declared_alias_resolves_including_dotted_acronym() -> None:
    resolver = _fixture_resolver()
    for surface in ("MIT", "M.I.T.", "Georgia Tech"):
        outcome = resolver.resolve(surface)
        assert outcome.rule == RULE_ALIAS, surface
    assert resolver.resolve("MIT").reference_id == "ipeds:1"


# --- Adversarial: inputs where no positive rule may fire ---------------------


@pytest.mark.parametrize(
    "surface",
    [
        "Georgia Tech Research Corp",  # a corporation, not the institute
        "Georgia Tech Research Corporation",
        "MIT Lincoln Laboratory",  # a unit; grain is not decided here
        "Massachusetts Institute of Technology Lincoln Laboratory",
        "University of Texas",  # system, not the Austin campus
        "University of Texas System",
        "Tech",  # generic alias rejected by the guard
        "Pacific",
        "Columbia University",  # not either Columbia College
    ],
)
def test_near_collisions_stay_unresolved(surface: str) -> None:
    outcome = _fixture_resolver().resolve(surface)
    assert outcome.rule == RULE_UNRESOLVED, (surface, outcome)
    assert outcome.reference_id is None


def test_duplicate_reference_names_are_ambiguous_not_first_wins() -> None:
    outcome = _fixture_resolver().resolve("Columbia College")
    assert outcome.rule == RULE_AMBIGUOUS
    assert outcome.reference_id is None
    assert outcome.candidate_count == 2


def test_shared_acronym_alias_is_ambiguous() -> None:
    outcome = _fixture_resolver().resolve("GCC")
    assert outcome.rule == RULE_AMBIGUOUS
    assert outcome.candidate_count == 2


def test_exact_name_of_one_institution_beats_alias_of_another() -> None:
    outcome = _fixture_resolver().resolve("Prescott University")
    assert outcome.rule == RULE_EXACT
    assert outcome.reference_id == "ipeds:11"


def test_ffrdc_row_resolves_as_its_own_node() -> None:
    outcome = _fixture_resolver().resolve("Lincoln Laboratory")
    assert outcome.rule == RULE_EXACT
    assert outcome.source == "ffrdc"
    assert outcome.reference_id == "ffrdc:lincoln-laboratory"


def test_duplicate_reference_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate reference id"):
        RIResolver(
            [
                ReferenceInstitution("ipeds:1", "A University", "ipeds"),
                ReferenceInstitution("ipeds:1", "B University", "ipeds"),
            ]
        )


def test_resolution_frame_and_match_rate_weight_by_awards() -> None:
    resolver = _fixture_resolver()
    names = ["MIT", "MIT", "N/A", "Columbia College", "Nowhere Institute"]
    weights = {"MIT": 10, "N/A": 3, "Columbia College": 2, "Nowhere Institute": 1}
    frame = resolution_frame(names, resolver, weights)

    assert len(frame) == 4  # distinct strings resolved once
    assert frame.loc[frame["surface_name"] == "MIT", "awards"].item() == 10
    table = match_rate_table(frame).set_index("rule")
    assert table.loc[RULE_ALIAS, "distinct_strings"] == 1
    assert table.loc[RULE_ALIAS, "award_share"] == pytest.approx(10 / 16)
    assert table.loc[RULE_BLANK, "awards"] == 3
    assert table.loc[RULE_AMBIGUOUS, "distinct_strings"] == 1
    assert table.loc[RULE_UNRESOLVED, "distinct_strings"] == 1
    assert table.loc[RULE_EXACT, "distinct_strings"] == 0
    assert table["distinct_share"].sum() == pytest.approx(1.0)
    assert table["award_share"].sum() == pytest.approx(1.0)


def test_empty_match_rate_table_has_the_schema() -> None:
    frame = resolution_frame([], _fixture_resolver())
    assert list(match_rate_table(frame).columns) == [
        "rule",
        "distinct_strings",
        "distinct_share",
        "awards",
        "award_share",
    ]


# --- Smoke test on the pinned reference lists in the repository --------------


@pytest.fixture(scope="module")
def default_resolver() -> RIResolver:
    return build_default_resolver()


def test_default_resolver_loads_both_seed_lists(default_resolver: RIResolver) -> None:
    assert len(default_resolver) > 6000
    assert default_resolver.institution("ffrdc:jet-propulsion-laboratory").source == "ffrdc"


@pytest.mark.parametrize(
    ("surface", "rule", "reference_id"),
    [
        ("Massachusetts Institute of Technology", RULE_EXACT, "ipeds:166683"),
        ("M.I.T.", RULE_ALIAS, "ipeds:166683"),
        ("Georgia Institute of Technology", RULE_MAIN_CAMPUS, "ipeds:139755"),
        ("The University of Texas at Austin", RULE_EXACT, "ipeds:228778"),
        ("University of Texas at Austin", RULE_EXACT, "ipeds:228778"),
        ("Stanford University", RULE_EXACT, "ipeds:243744"),
        ("Lincoln Laboratory", RULE_EXACT, "ffrdc:lincoln-laboratory"),
        ("Oak Ridge National Laboratory", RULE_EXACT, "ffrdc:oak-ridge-national-laboratory"),
    ],
)
def test_default_resolver_positive_cases(
    default_resolver: RIResolver, surface: str, rule: str, reference_id: str
) -> None:
    outcome = default_resolver.resolve(surface)
    assert (outcome.rule, outcome.reference_id) == (rule, reference_id)


@pytest.mark.parametrize(
    "surface",
    [
        "Georgia Tech Research Corp",
        "MIT Lincoln Laboratory",
        "Tech",
        "Pacific",
        "University of Texas",
    ],
)
def test_default_resolver_near_collisions_do_not_resolve(
    default_resolver: RIResolver, surface: str
) -> None:
    outcome = default_resolver.resolve(surface)
    assert outcome.rule in {RULE_UNRESOLVED, RULE_AMBIGUOUS}, (surface, outcome)
    assert outcome.reference_id is None


def test_default_resolver_duplicate_ipeds_names_are_ambiguous(default_resolver: RIResolver) -> None:
    outcome = default_resolver.resolve("Columbia College")
    assert outcome.rule == RULE_AMBIGUOUS
    assert outcome.candidate_count >= 2
