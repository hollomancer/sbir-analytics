"""Probes for the STTR spinout-linkage exploratory kernel.

Exploratory tier: covers the behaviors task 1.2's definition-of-done calls
out -- the generic-token guard actually rejecting the discipline-note cases,
`SignalAbsentReason` mapping onto the D1-D5 typed-absence cases in
`design.md`, and `classify_linkage` producing the right label for each
Order 0-4 case, including "absence never advances a label" and "license
absence cannot create a SUBCONTRACT." Not a comprehensive matrix.
"""

from __future__ import annotations

import pytest

from scripts.sttr_spinout_linkage.kernel import (
    GENERIC_PERSON_TOKENS,
    ORG_GENERIC_TOKENS,
    D1Spine,
    D2PersonTrail,
    D3IpTrail,
    D4MoneyTrail,
    D5TextTrail,
    DimensionStatus,
    IdentityKind,
    LinkageLabel,
    ResolvedIdentity,
    SignalAbsentReason,
    classify_linkage,
    generic_token_guard,
    identity_similarity,
    resolve_identity,
)
from sbir_etl.identity import SUFFIX_TOKENS


pytestmark = pytest.mark.fast


# ---------------------------------------------------------------------------
# generic_token_guard
# ---------------------------------------------------------------------------


class TestGenericTokenGuard:
    def test_rejects_org_name_that_is_only_generic_tokens(self):
        # "The Institute" -> tokens {"the", "institute"}, both generic org tokens.
        assert generic_token_guard(["the", "institute"], generic_tokens=ORG_GENERIC_TOKENS) is False

    def test_rejects_org_name_that_is_only_center_alone(self):
        assert generic_token_guard(["center"], generic_tokens=ORG_GENERIC_TOKENS) is False

    def test_rejects_bare_suffix_token(self):
        assert generic_token_guard(["inc"], generic_tokens=SUFFIX_TOKENS) is False

    def test_accepts_org_name_with_substantive_token(self):
        # "Acme Robotics Inc" -> "acme", "robotics" survive the suffix strip.
        assert (
            generic_token_guard(["acme", "robotics", "inc"], generic_tokens=SUFFIX_TOKENS) is True
        )

    def test_rejects_person_name_that_is_only_a_title_and_suffix(self):
        assert generic_token_guard(["dr", "jr"], generic_tokens=GENERIC_PERSON_TOKENS) is False

    def test_accepts_person_name_with_substantive_token(self):
        assert generic_token_guard(["jane", "dr"], generic_tokens=GENERIC_PERSON_TOKENS) is True

    def test_empty_tokens_reject(self):
        assert generic_token_guard([], generic_tokens=SUFFIX_TOKENS) is False


# ---------------------------------------------------------------------------
# resolve_identity
# ---------------------------------------------------------------------------


class TestResolveIdentity:
    def test_blank_input_resolves_to_none(self):
        assert resolve_identity(None, kind=IdentityKind.ORGANIZATION) is None
        assert resolve_identity("", kind=IdentityKind.PERSON) is None

    def test_organization_uses_sbir_etl_identity_normalization(self):
        identity = resolve_identity("Acme Robotics, Inc.", kind=IdentityKind.ORGANIZATION)
        assert isinstance(identity, ResolvedIdentity)
        assert identity.kind is IdentityKind.ORGANIZATION
        # MATCHING_V1 lowercases and strips punctuation but keeps suffix tokens.
        assert "acme" in identity.normalized
        assert "robotics" in identity.normalized
        assert identity.guard_passed is True

    def test_organization_guard_fails_on_generic_only_name(self):
        identity = resolve_identity("The Institute", kind=IdentityKind.ORGANIZATION)
        assert identity is not None
        assert identity.guard_passed is False

    def test_person_name_splits_given_and_family(self):
        identity = resolve_identity("Jane Q. Smith", kind=IdentityKind.PERSON)
        assert identity is not None
        assert identity.family_name == "smith"
        assert identity.given_name == "jane q"
        assert identity.guard_passed is True

    def test_person_name_handles_family_comma_given_order(self):
        identity = resolve_identity("Smith, Jane", kind=IdentityKind.PERSON)
        assert identity is not None
        assert identity.given_name == "jane"
        assert identity.family_name == "smith"

    def test_person_name_strips_titles_before_given_family_split(self):
        identity = resolve_identity("Dr. Jane Smith", kind=IdentityKind.PERSON)
        assert identity is not None
        assert identity.given_name == "jane"
        assert identity.family_name == "smith"
        assert identity.normalized == "jane smith"
        assert identity.guard_passed is True

    def test_person_name_guard_fails_on_title_and_suffix_only(self):
        identity = resolve_identity("Dr. Jr.", kind=IdentityKind.PERSON)
        assert identity is not None
        assert identity.guard_passed is False

    def test_identity_similarity_reuses_company_name_similarity(self):
        left = resolve_identity("Jane Smith", kind=IdentityKind.PERSON)
        right = resolve_identity("Jane Smith", kind=IdentityKind.PERSON)
        assert identity_similarity(left, right) == pytest.approx(1.0)

    def test_identity_similarity_none_input_is_zero(self):
        assert identity_similarity(None, None) == 0.0


# ---------------------------------------------------------------------------
# signal_absent_reason (SignalAbsentReason enum -> D1-D5 typed absence cases)
# ---------------------------------------------------------------------------


class TestSignalAbsentReason:
    def test_d1_spine_incomplete_reason_exists(self):
        assert SignalAbsentReason.SPINE_INCOMPLETE == "spine_incomplete"

    def test_d2_generic_token_guard_failure_reason_exists(self):
        assert (
            SignalAbsentReason.NAME_GENERIC_TOKEN_GUARD_FAILED == "name_generic_token_guard_failed"
        )

    def test_d2_source_not_queried_reason_exists(self):
        assert SignalAbsentReason.SOURCE_NOT_QUERIED == "source_not_queried"

    def test_d3_license_records_sparse_reason_matches_design_doc_literal(self):
        # design.md's D3 row names this exact code: NOT_MEASURABLE (LICENSE_RECORDS_SPARSE).
        assert SignalAbsentReason.LICENSE_RECORDS_SPARSE == "license_records_sparse"

    def test_d4_non_grant_instrument_reason_exists(self):
        assert SignalAbsentReason.NON_GRANT_INSTRUMENT == "non_grant_instrument"

    def test_d4_d5_source_field_unavailable_reason_exists(self):
        assert SignalAbsentReason.SOURCE_FIELD_UNAVAILABLE == "source_field_unavailable"

    def test_all_members_are_distinct(self):
        values = [member.value for member in SignalAbsentReason]
        assert len(values) == len(set(values))


# ---------------------------------------------------------------------------
# classify_linkage
# ---------------------------------------------------------------------------


def _d1(*, ri: bool = True, pi: bool = True) -> D1Spine:
    return D1Spine(ri_present=ri, pi_present=pi)


def _measured_empty_d2() -> D2PersonTrail:
    return D2PersonTrail(status=DimensionStatus.MEASURED)


def _measured_empty_d3() -> D3IpTrail:
    return D3IpTrail(status=DimensionStatus.MEASURED)


def _measured_empty_d4() -> D4MoneyTrail:
    return D4MoneyTrail(status=DimensionStatus.MEASURED, ri_subaward_share=0.0)


def _measured_empty_d5() -> D5TextTrail:
    return D5TextTrail(status=DimensionStatus.MEASURED)


class TestClassifyLinkage:
    CUTOFF = 0.9

    def test_order_0_indeterminate_when_ri_absent(self):
        decision = classify_linkage(
            d1=_d1(ri=False),
            d2=_measured_empty_d2(),
            d3=_measured_empty_d3(),
            d4=_measured_empty_d4(),
            d5=_measured_empty_d5(),
            similarity_cutoff=self.CUTOFF,
        )
        assert decision.label is LinkageLabel.INDETERMINATE
        assert decision.cascade_order == 0

    def test_order_0_indeterminate_when_pi_absent(self):
        decision = classify_linkage(
            d1=_d1(pi=False),
            d2=_measured_empty_d2(),
            d3=_measured_empty_d3(),
            d4=_measured_empty_d4(),
            d5=_measured_empty_d5(),
            similarity_cutoff=self.CUTOFF,
        )
        assert decision.label is LinkageLabel.INDETERMINATE
        assert decision.cascade_order == 0

    def test_order_1_spinout_t1_on_exact_person_affiliation(self):
        decision = classify_linkage(
            d1=_d1(),
            d2=D2PersonTrail(status=DimensionStatus.MEASURED, exact_person_ri_affiliation=True),
            d3=_measured_empty_d3(),
            d4=_measured_empty_d4(),
            d5=_measured_empty_d5(),
            similarity_cutoff=self.CUTOFF,
        )
        assert decision.label is LinkageLabel.SPINOUT_T1
        assert decision.cascade_order == 1

    def test_order_1_spinout_t1_on_patent_assignment(self):
        decision = classify_linkage(
            d1=_d1(),
            d2=_measured_empty_d2(),
            d3=D3IpTrail(
                status=DimensionStatus.MEASURED, patent_assigned_to_ri_with_sbc_inventor=True
            ),
            d4=_measured_empty_d4(),
            d5=_measured_empty_d5(),
            similarity_cutoff=self.CUTOFF,
        )
        assert decision.label is LinkageLabel.SPINOUT_T1
        assert decision.cascade_order == 1

    def test_order_1_spinout_t1_on_recorded_license(self):
        decision = classify_linkage(
            d1=_d1(),
            d2=_measured_empty_d2(),
            d3=D3IpTrail(status=DimensionStatus.MEASURED, recorded_license_ri_to_sbc=True),
            d4=_measured_empty_d4(),
            d5=_measured_empty_d5(),
            similarity_cutoff=self.CUTOFF,
        )
        assert decision.label is LinkageLabel.SPINOUT_T1

    def test_order_2_spinout_t2_fuzzy_person_corroborated_by_form_d(self):
        decision = classify_linkage(
            d1=_d1(),
            d2=D2PersonTrail(
                status=DimensionStatus.MEASURED,
                person_similarity=0.95,
                person_guard_passed=True,
            ),
            d3=_measured_empty_d3(),
            d4=D4MoneyTrail(
                status=DimensionStatus.MEASURED,
                ri_subaward_share=0.0,
                form_d_officer_ri_affiliated=True,
            ),
            d5=_measured_empty_d5(),
            similarity_cutoff=self.CUTOFF,
        )
        assert decision.label is LinkageLabel.SPINOUT_T2
        assert decision.cascade_order == 2

    def test_order_2_fuzzy_person_below_cutoff_does_not_advance(self):
        decision = classify_linkage(
            d1=_d1(),
            d2=D2PersonTrail(
                status=DimensionStatus.MEASURED,
                person_similarity=0.5,
                person_guard_passed=True,
            ),
            d3=_measured_empty_d3(),
            d4=D4MoneyTrail(
                status=DimensionStatus.MEASURED,
                ri_subaward_share=0.0,
                form_d_officer_ri_affiliated=True,
            ),
            d5=_measured_empty_d5(),
            similarity_cutoff=self.CUTOFF,
        )
        assert decision.label is not LinkageLabel.SPINOUT_T2

    def test_order_2_fuzzy_person_failing_guard_does_not_advance(self):
        decision = classify_linkage(
            d1=_d1(),
            d2=D2PersonTrail(
                status=DimensionStatus.MEASURED,
                person_similarity=0.99,
                person_guard_passed=False,
            ),
            d3=_measured_empty_d3(),
            d4=D4MoneyTrail(
                status=DimensionStatus.MEASURED,
                ri_subaward_share=0.0,
                form_d_officer_ri_affiliated=True,
            ),
            d5=_measured_empty_d5(),
            similarity_cutoff=self.CUTOFF,
        )
        assert decision.label is not LinkageLabel.SPINOUT_T2

    def test_order_2_single_d5_phrase_cannot_corroborate_itself(self):
        # D5 alone supplies both the primary fuzzy positive and the only
        # candidate corroboration -- design.md: "a single D5.spinout_phrase
        # cannot corroborate itself."
        decision = classify_linkage(
            d1=_d1(),
            d2=_measured_empty_d2(),
            d3=_measured_empty_d3(),
            d4=_measured_empty_d4(),
            d5=D5TextTrail(status=DimensionStatus.MEASURED, spinout_phrase=True),
            similarity_cutoff=self.CUTOFF,
        )
        assert decision.label is not LinkageLabel.SPINOUT_T2
        assert decision.label is LinkageLabel.INDETERMINATE

    def test_order_2_d5_phrase_corroborated_by_d3_ip_link(self):
        decision = classify_linkage(
            d1=_d1(),
            d2=_measured_empty_d2(),
            d3=D3IpTrail(
                status=DimensionStatus.NOT_MEASURABLE,
                reason=SignalAbsentReason.LICENSE_RECORDS_SPARSE,
            ),
            d4=_measured_empty_d4(),
            d5=D5TextTrail(status=DimensionStatus.MEASURED, spinout_phrase=True),
            similarity_cutoff=self.CUTOFF,
        )
        # D3 is NOT_MEASURABLE here (license sparsity) so it cannot corroborate;
        # falls through to INDETERMINATE, not a false T2.
        assert decision.label is LinkageLabel.INDETERMINATE

    def test_order_3_subcontract_on_measured_negative_dims_and_subaward(self):
        decision = classify_linkage(
            d1=_d1(),
            d2=_measured_empty_d2(),
            d3=_measured_empty_d3(),
            d4=D4MoneyTrail(status=DimensionStatus.MEASURED, ri_subaward_share=0.3),
            d5=_measured_empty_d5(),
            similarity_cutoff=self.CUTOFF,
        )
        assert decision.label is LinkageLabel.SUBCONTRACT
        assert decision.cascade_order == 3

    def test_order_3_absence_never_advances_to_subcontract(self):
        # D3 is NOT_MEASURABLE (license absence) instead of measured-negative:
        # must fall through to Order 4 INDETERMINATE, not Order 3 SUBCONTRACT.
        decision = classify_linkage(
            d1=_d1(),
            d2=_measured_empty_d2(),
            d3=D3IpTrail(
                status=DimensionStatus.NOT_MEASURABLE,
                reason=SignalAbsentReason.LICENSE_RECORDS_SPARSE,
            ),
            d4=D4MoneyTrail(status=DimensionStatus.MEASURED, ri_subaward_share=0.3),
            d5=_measured_empty_d5(),
            similarity_cutoff=self.CUTOFF,
        )
        assert decision.label is LinkageLabel.INDETERMINATE
        assert decision.cascade_order == 4

    def test_order_3_license_absence_cannot_create_subcontract(self):
        # Explicit design.md discipline note: D3 license absence -> NOT_MEASURABLE,
        # never SUBCONTRACT evidence, even with a strong positive D4 subaward.
        decision = classify_linkage(
            d1=_d1(),
            d2=D2PersonTrail(
                status=DimensionStatus.NOT_MEASURABLE, reason=SignalAbsentReason.SOURCE_NOT_QUERIED
            ),
            d3=D3IpTrail(
                status=DimensionStatus.NOT_MEASURABLE,
                reason=SignalAbsentReason.LICENSE_RECORDS_SPARSE,
            ),
            d4=D4MoneyTrail(status=DimensionStatus.MEASURED, ri_subaward_share=1.0),
            d5=D5TextTrail(status=DimensionStatus.NOT_EVALUATED),
            similarity_cutoff=self.CUTOFF,
        )
        assert decision.label is LinkageLabel.INDETERMINATE

    def test_order_4_indeterminate_when_d4_not_applicable(self):
        decision = classify_linkage(
            d1=_d1(),
            d2=_measured_empty_d2(),
            d3=_measured_empty_d3(),
            d4=D4MoneyTrail(
                status=DimensionStatus.NOT_APPLICABLE,
                reason=SignalAbsentReason.NON_GRANT_INSTRUMENT,
            ),
            d5=_measured_empty_d5(),
            similarity_cutoff=self.CUTOFF,
        )
        assert decision.label is LinkageLabel.INDETERMINATE
        assert decision.cascade_order == 4

    def test_similarity_cutoff_has_no_default(self):
        import inspect

        signature = inspect.signature(classify_linkage)
        assert signature.parameters["similarity_cutoff"].default is inspect.Parameter.empty
