import pytest

from sbir_etl.identity.geography import (
    US_JURISDICTION_NAMES_V1,
    US_JURISDICTION_VARIATIONS_V1,
    USJurisdictionProfile,
    VALID_US_JURISDICTION_CODES_V1,
    normalize_us_jurisdiction,
    us_jurisdiction_name,
)


def test_every_canonical_code_and_name_round_trips() -> None:
    assert set(US_JURISDICTION_NAMES_V1) == set(VALID_US_JURISDICTION_CODES_V1)
    for code, name in US_JURISDICTION_NAMES_V1.items():
        assert normalize_us_jurisdiction(code.lower()) == code
        assert normalize_us_jurisdiction(name.lower()) == code
        assert us_jurisdiction_name(code) == name


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("D.C.", "DC"),
        ("Washington DC", "DC"),
        ("U.S. Virgin Islands", "VI"),
        ("Commonwealth of the Northern Mariana Islands", "MP"),
        ("Mass", "MA"),
        ("N.Y.", "NY"),
    ],
)
def test_strict_profile_accepts_only_declared_aliases(value: str, expected: str) -> None:
    assert normalize_us_jurisdiction(value) == expected


@pytest.mark.parametrize("value", [None, "", "XY", "New H", "not a state"])
def test_strict_profile_rejects_unknown_or_partial_values(value: object) -> None:
    assert normalize_us_jurisdiction(value) is None


def test_permissive_profile_freezes_legacy_patent_behavior() -> None:
    profile = USJurisdictionProfile.PERMISSIVE_PREFIX_V1

    assert normalize_us_jurisdiction("XY", profile=profile) == "XY"
    assert normalize_us_jurisdiction("NEW H", profile=profile) == "NH"
    # First-match behavior is deliberate compatibility, not a strict claim.
    assert normalize_us_jurisdiction("NEW", profile=profile) == "NH"


def test_versioned_maps_are_immutable() -> None:
    with pytest.raises(TypeError):
        US_JURISDICTION_NAMES_V1["XX"] = "Example"  # type: ignore[index]
    with pytest.raises(TypeError):
        US_JURISDICTION_VARIATIONS_V1["EXAMPLE"] = "XX"  # type: ignore[index]
