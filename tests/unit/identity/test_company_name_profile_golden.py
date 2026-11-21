"""Golden table: every company-name profile against one fixed input set.

Epistemic tier: primitives. The fixture pins the current output of
``normalize_company_name`` for every ``CompanyNameProfile``. Profiles are
frozen policies, so any change to an expected value means the behavior changed
and needs a new profile version, not an edit to this fixture.

Expected values were generated from the code at the time the fixture was added.
They record behavior, including outputs that look wrong; they do not endorse it.
"""

import json
import math
from pathlib import Path

import pandas as pd
import pytest

from sbir_etl.identity import CompanyNameProfile, normalize_company_name


GOLDEN_PATH = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "identity"
    / "company_name_profile_golden.json"
)
GOLDEN = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
INPUTS: dict[str, str] = GOLDEN["inputs"]
EXPECTED: dict[str, dict[str, str]] = GOLDEN["expected"]

# None and missing values cannot be stored in JSON; every profile maps them to "".
BLANK_VALUES = [None, math.nan, float("nan"), pd.NA, pd.NaT, "", "   ", "\t\n"]


def test_every_profile_has_a_golden_entry() -> None:
    """A new profile must add a golden column before it can ship."""
    assert set(EXPECTED) == {profile.value for profile in CompanyNameProfile}


@pytest.mark.parametrize("profile_value", sorted(EXPECTED))
def test_every_golden_entry_covers_every_input(profile_value: str) -> None:
    assert set(EXPECTED[profile_value]) == set(INPUTS)


@pytest.mark.parametrize(
    ("profile", "case_id"),
    [(profile, case_id) for profile in CompanyNameProfile for case_id in INPUTS],
    ids=lambda value: value.value if isinstance(value, CompanyNameProfile) else value,
)
def test_profile_matches_golden(profile: CompanyNameProfile, case_id: str) -> None:
    actual = normalize_company_name(INPUTS[case_id], profile=profile)
    assert actual == EXPECTED[profile.value][case_id]


@pytest.mark.parametrize("profile", list(CompanyNameProfile), ids=lambda p: p.value)
@pytest.mark.parametrize("value", BLANK_VALUES, ids=repr)
def test_blank_values_normalize_to_empty(profile: CompanyNameProfile, value: object) -> None:
    assert normalize_company_name(value, profile=profile) == ""
