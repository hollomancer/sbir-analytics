"""Contract tests for candidate transition assertions (ADR-005).

The first two classes are regression tests against the legacy producer in
``packages/sbir-analytics/sbir_analytics/assets/transition/utils.py``:
non-deterministic identity, and a fabricated 0.5 score standing in for a
missing measurement.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from sbir_etl.assertions import (
    ActionReference,
    ActionRole,
    AssertionIdentityError,
    AssertionRecord,
    AssertionValidationError,
    ClaimStatus,
    ContractKeyMethod,
    DimensionAssessment,
    DimensionStatus,
    InputReference,
    PermittedUse,
    SignalAbsentReason,
    SnapshotExistsError,
    SupportClass,
    assertion_id,
    build_assertion_record,
    contract_key_method_counts,
    read_snapshot,
    resolve_contract_key,
    snapshot_id_for,
    validate_snapshot_cardinality,
    validate_v1_semantics,
    write_snapshot,
)

CREATED_AT = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)

MEASURED = DimensionAssessment(
    dimension="d1_award_linkage", status=DimensionStatus.MEASURED, score=0.82
)
ABSENT = DimensionAssessment(
    dimension="d2_text_similarity",
    status=DimensionStatus.NOT_EVALUATED,
    absent_reason=SignalAbsentReason.DETECTOR_NOT_RUN,
)
ACTIONS = (
    ActionReference(
        action_key="ACT-1",
        role=ActionRole.DETECTOR_SELECTED,
        action_date=date(2024, 5, 1),
        obligation=250000.0,
    ),
    ActionReference(
        action_key="ACT-0",
        role=ActionRole.EARLIEST_AWARD,
        action_date=date(2024, 1, 15),
        obligation=0.0,
    ),
)


def make_record(**overrides):
    kwargs = {
        "source_row_key": "SBIR-PH2-0001",
        "detector_method": "transition_detector_v3",
        "method_run_id": "RUN-2026-09-19-01",
        "dimensions": (MEASURED, ABSENT),
        "actions": ACTIONS,
        "detector_selected_action_key": "ACT-1",
        "earliest_award_action_key": "ACT-0",
        "earliest_award_action_date": date(2024, 1, 15),
        "created_at": CREATED_AT,
        "generated_unique_award_id": "CONT_AWD_1234_9700_ABC_9700",
    }
    kwargs.update(overrides)
    return build_assertion_record(**kwargs)


class TestDeterministicIdentity:
    """Replaces ``f"TRANS-{uuid4().hex[:12].upper()}"``."""

    def test_same_inputs_yield_same_identity(self):
        first = make_record()
        second = make_record()
        assert first.assertion_id == second.assertion_id
        assert first.assertion_revision_id == second.assertion_revision_id

    def test_identity_is_stable_across_detector_method(self):
        base = make_record()
        other = make_record(detector_method="transition_detector_v4")
        assert other.assertion_id == base.assertion_id
        assert other.assertion_revision_id != base.assertion_revision_id

    def test_identity_changes_with_contract_key(self):
        base = make_record()
        other = make_record(generated_unique_award_id="CONT_AWD_9999_9700_XYZ_9700")
        assert other.assertion_id != base.assertion_id

    def test_payload_change_forces_new_revision(self):
        base = make_record()
        changed = make_record(
            dimensions=(
                DimensionAssessment(
                    dimension="d1_award_linkage",
                    status=DimensionStatus.MEASURED,
                    score=0.83,
                ),
                ABSENT,
            )
        )
        assert changed.assertion_id == base.assertion_id
        assert changed.assertion_revision_id != base.assertion_revision_id

    def test_identity_cannot_be_minted(self):
        base = make_record()
        with pytest.raises(ValueError, match="deterministic, never minted"):
            AssertionRecord.model_validate({**base.model_dump(), "assertion_id": "f" * 64})


class TestTypedAbsence:
    """Replaces the ``df[col] = 0.5`` default and its ``"possible"`` label."""

    def test_measured_requires_a_score(self):
        with pytest.raises(ValueError, match="MEASURED but carries no score"):
            DimensionAssessment(dimension="d1", status=DimensionStatus.MEASURED)

    def test_measured_zero_is_a_measurement(self):
        dimension = DimensionAssessment(dimension="d1", status=DimensionStatus.MEASURED, score=0.0)
        assert dimension.status.is_measured
        assert dimension.score == 0.0
        assert dimension.absent_reason is None

    def test_absent_dimension_cannot_carry_a_placeholder_score(self):
        with pytest.raises(ValueError, match="must not carry a score"):
            DimensionAssessment(
                dimension="d1",
                status=DimensionStatus.NOT_MEASURABLE,
                score=0.5,
                absent_reason=SignalAbsentReason.SPINE_INCOMPLETE,
            )

    def test_absent_dimension_requires_a_typed_reason(self):
        with pytest.raises(ValueError, match="requires a typed absent_reason"):
            DimensionAssessment(dimension="d1", status=DimensionStatus.NOT_EVALUATED)

    def test_measured_dimension_rejects_an_absent_reason(self):
        with pytest.raises(ValueError, match="must not carry an absent_reason"):
            DimensionAssessment(
                dimension="d1",
                status=DimensionStatus.MEASURED,
                score=0.4,
                absent_reason=SignalAbsentReason.DETECTOR_ERROR,
            )

    @pytest.mark.parametrize("score", [-0.01, 1.01, float("nan"), float("inf")])
    def test_measured_score_must_be_bounded_and_finite(self, score):
        with pytest.raises(ValueError):
            DimensionAssessment(dimension="d1", status=DimensionStatus.MEASURED, score=score)


class TestContractKeyResolution:
    def test_generated_key_is_canonical(self):
        key, method = resolve_contract_key(generated_unique_award_id="cont_awd_1234_9700_abc_9700")
        assert key == "USASPENDING:CONT_AWD_1234_9700_ABC_9700"
        assert method is ContractKeyMethod.GENERATED_UNIQUE_AWARD_ID

    def test_generated_key_preferred_over_legacy_components(self):
        key, method = resolve_contract_key(
            generated_unique_award_id="CONT_AWD_1",
            awarding_agency_code="9700",
            parent_award_id="IDV1",
            piid="P1",
        )
        assert key.startswith("USASPENDING:")
        assert method is ContractKeyMethod.GENERATED_UNIQUE_AWARD_ID

    def test_legacy_composite_is_namespaced_and_method_tagged(self):
        key, method = resolve_contract_key(
            awarding_agency_code="9700", parent_award_id="IDV1", piid="P1"
        )
        assert key == "LEGACY:legacy_composite|9700|IDV1|P1"
        assert method is ContractKeyMethod.LEGACY_COMPOSITE

    def test_bare_piid_is_refused(self):
        with pytest.raises(AssertionIdentityError, match="bare PIID is never"):
            resolve_contract_key(piid="P1")

    def test_unresolved_identity_blocks_publication(self):
        with pytest.raises(AssertionIdentityError, match="cannot resolve contract key"):
            resolve_contract_key()

    def test_legacy_and_generated_keys_never_collide(self):
        generated, _ = resolve_contract_key(generated_unique_award_id="9700|IDV1|P1")
        legacy, _ = resolve_contract_key(
            awarding_agency_code="9700", parent_award_id="IDV1", piid="P1"
        )
        assert generated != legacy
        assert assertion_id(source_row_key="S1", contract_key=generated) != assertion_id(
            source_row_key="S1", contract_key=legacy
        )

    def test_namespace_must_match_method(self):
        record = make_record()
        with pytest.raises(ValueError, match="requires the 'LEGACY:' namespace"):
            AssertionRecord.model_validate(
                {
                    **record.model_dump(),
                    "contract_key_method": ContractKeyMethod.LEGACY_COMPOSITE,
                }
            )


class TestActionRolesAndLatency:
    def test_anchors_must_be_backed_by_retained_actions(self):
        with pytest.raises(ValueError, match="not present in actions"):
            make_record(detector_selected_action_key="ACT-MISSING")

    def test_detector_selected_action_is_required(self):
        with pytest.raises(AssertionValidationError, match="detector-selected action"):
            make_record(actions=(ACTIONS[1],), detector_selected_action_key="ACT-0")

    def test_negative_latency_is_preserved(self):
        record = make_record(award_anchor_latency_days=-45)
        assert record.award_anchor_latency_days == -45

    def test_positive_obligation_date_requires_its_key(self):
        with pytest.raises(ValueError, match="requires its action key"):
            make_record(earliest_positive_obligation_action_date=date(2024, 6, 1))


class TestV1Semantics:
    def test_defaults_are_candidate_only(self):
        record = make_record()
        assert record.claim_status is ClaimStatus.CANDIDATE
        assert record.support_class is SupportClass.C
        assert record.permitted_use is PermittedUse.INVESTIGATIVE_ONLY

    @pytest.mark.parametrize(
        "field,value",
        [
            ("claim_status", ClaimStatus.ACCEPTED),
            ("support_class", SupportClass.A),
            ("permitted_use", PermittedUse.CITABLE),
        ],
    )
    def test_reserved_values_cannot_be_emitted(self, field, value):
        record = make_record()
        escalated = AssertionRecord.model_construct(**{**record.model_dump(), field: value})
        with pytest.raises(AssertionValidationError, match="V1 may only emit"):
            validate_v1_semantics(escalated)

    def test_duplicate_logical_revisions_are_rejected(self):
        first = make_record()
        second = make_record(detector_method="transition_detector_v4")
        validate_snapshot_cardinality([first])
        with pytest.raises(AssertionValidationError, match="multiple current revisions"):
            validate_snapshot_cardinality([first, second])

    def test_identical_revisions_are_idempotent(self):
        record = make_record()
        validate_snapshot_cardinality([record, make_record()])

    def test_legacy_key_use_is_counted_not_coalesced(self):
        generated = make_record()
        legacy = make_record(
            source_row_key="SBIR-PH2-0002",
            generated_unique_award_id=None,
            awarding_agency_code="9700",
            parent_award_id="IDV1",
            piid="P1",
        )
        counts = contract_key_method_counts([generated, legacy])
        assert counts == {"generated_unique_award_id": 1, "legacy_composite": 1}


def make_inputs(sha: str = "a" * 64, *, n: int = 1, name: str = "phase_ii_source"):
    return (InputReference(name=name, path="data/ph2.parquet", sha256=sha, n=n),)


RULES = {"identity_cascade": "corroborated-person-v2"}


class TestSnapshotIdentity:
    """ADR-005 §8: identity covers revisions, input digests, and rule versions."""

    def test_snapshot_id_is_order_independent(self):
        first = make_record()
        second = make_record(source_row_key="SBIR-PH2-0002")
        common = {"inputs": make_inputs(), "rule_versions": RULES}
        assert snapshot_id_for([first, second], **common) == snapshot_id_for(
            [second, first], **common
        )

    def test_snapshot_id_is_independent_of_input_order(self):
        records = [make_record()]
        one = InputReference(name="a", path="data/a.parquet", sha256="a" * 64, n=1)
        two = InputReference(name="b", path="data/b.parquet", sha256="b" * 64, n=2)
        assert snapshot_id_for(records, inputs=(one, two), rule_versions=RULES) == snapshot_id_for(
            records, inputs=(two, one), rule_versions=RULES
        )

    def test_identical_records_from_a_different_vintage_get_a_different_id(self):
        """The collision this clause exists to prevent.

        A later vintage that adds only rows this claim family ignores yields an
        identical record set. Under a revisions-only id the two runs collided on
        one snapshot, the second was refused as a duplicate, and no study could
        pin the second vintage.
        """
        records = [make_record()]
        first = snapshot_id_for(records, inputs=make_inputs("a" * 64, n=1), rule_versions=RULES)
        second = snapshot_id_for(records, inputs=make_inputs("b" * 64, n=1), rule_versions=RULES)
        assert first != second

    def test_a_row_count_change_alone_gets_a_different_id(self):
        records = [make_record()]
        first = snapshot_id_for(records, inputs=make_inputs(n=1), rule_versions=RULES)
        second = snapshot_id_for(records, inputs=make_inputs(n=2), rule_versions=RULES)
        assert first != second

    def test_a_rule_version_change_gets_a_different_id(self):
        records = [make_record()]
        first = snapshot_id_for(records, inputs=make_inputs(), rule_versions=RULES)
        second = snapshot_id_for(
            records, inputs=make_inputs(), rule_versions={"identity_cascade": "v3"}
        )
        assert first != second

    def test_input_path_does_not_affect_identity(self):
        """A path records where bytes were read, not which bytes they were."""
        records = [make_record()]
        here = (InputReference(name="src", path="data/ph2.parquet", sha256="a" * 64, n=1),)
        there = (InputReference(name="src", path="/mnt/scratch/ph2.parquet", sha256="a" * 64, n=1),)
        assert snapshot_id_for(records, inputs=here, rule_versions=RULES) == snapshot_id_for(
            records, inputs=there, rule_versions=RULES
        )

    def test_as_of_utc_does_not_affect_identity(self, tmp_path):
        """A rerun of byte-identical pinned inputs must not fork identity."""
        records = [make_record()]
        _, first = write_snapshot(
            records,
            root=tmp_path / "monday",
            rule_versions=RULES,
            inputs=make_inputs(),
            as_of_utc=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
        )
        _, second = write_snapshot(
            records,
            root=tmp_path / "friday",
            rule_versions=RULES,
            inputs=make_inputs(),
            as_of_utc=datetime(2026, 9, 19, 12, 0, tzinfo=UTC),
        )
        assert first.snapshot_id == second.snapshot_id
        assert first.as_of_utc != second.as_of_utc

    def test_two_vintages_can_both_be_written_under_one_root(self, tmp_path):
        """End to end: the second vintage is publishable, not refused."""
        records = [make_record()]
        common = {"root": tmp_path, "rule_versions": RULES, "as_of_utc": CREATED_AT}
        first_dir, first = write_snapshot(records, inputs=make_inputs("a" * 64), **common)
        second_dir, second = write_snapshot(records, inputs=make_inputs("b" * 64), **common)
        assert first.snapshot_id != second.snapshot_id
        assert first_dir != second_dir
        assert first_dir.exists() and second_dir.exists()


class TestSnapshots:
    def test_write_then_read_round_trips(self, tmp_path):
        records = [make_record(), make_record(source_row_key="SBIR-PH2-0002")]
        inputs = (
            InputReference(
                name="phase_ii_source",
                path="data/ph2.parquet",
                sha256="a" * 64,
                n=2,
                gitignored=True,
            ),
        )
        directory, manifest = write_snapshot(
            records,
            root=tmp_path,
            rule_versions={"identity_cascade": "corroborated-person-v2"},
            inputs=inputs,
            as_of_utc=CREATED_AT,
        )
        frame, read_manifest = read_snapshot(directory)
        assert len(frame) == 2
        assert read_manifest.snapshot_id == manifest.snapshot_id
        assert read_manifest.rule_versions == {"identity_cascade": "corroborated-person-v2"}
        assert read_manifest.citable is False
        assert read_manifest.assertion_count == 2
        assert read_manifest.logical_assertion_count == 2
        assert set(frame.columns) >= {
            "assertion_id",
            "assertion_revision_id",
            "dimensions_json",
            "contract_key_method",
            "award_anchor_latency_days",
        }

    def test_snapshots_are_immutable(self, tmp_path):
        records = [make_record()]
        inputs = (
            InputReference(name="phase_ii_source", path="data/ph2.parquet", sha256="a" * 64, n=1),
        )
        kwargs = {
            "root": tmp_path,
            "rule_versions": {"identity_cascade": "corroborated-person-v2"},
            "inputs": inputs,
            "as_of_utc": CREATED_AT,
        }
        write_snapshot(records, **kwargs)
        with pytest.raises(SnapshotExistsError, match="immutable"):
            write_snapshot(records, **kwargs)

    def test_observed_cut_is_required(self, tmp_path):
        """ADR-005 §8: the cut is an input, never read from the clock here."""
        inputs = (
            InputReference(name="phase_ii_source", path="data/ph2.parquet", sha256="a" * 64, n=1),
        )
        with pytest.raises(TypeError, match="as_of_utc"):
            write_snapshot(
                [make_record()],
                root=tmp_path,
                rule_versions={"identity_cascade": "v2"},
                inputs=inputs,
            )

    def test_observed_cut_must_be_timezone_aware(self, tmp_path):
        inputs = (
            InputReference(name="phase_ii_source", path="data/ph2.parquet", sha256="a" * 64, n=1),
        )
        with pytest.raises(AssertionValidationError, match="timezone-aware"):
            write_snapshot(
                [make_record()],
                root=tmp_path,
                rule_versions={"identity_cascade": "v2"},
                inputs=inputs,
                as_of_utc=datetime(2026, 9, 19, 12, 0),
            )

    def test_same_records_yield_same_snapshot_id(self, tmp_path):
        inputs = (
            InputReference(name="phase_ii_source", path="data/ph2.parquet", sha256="a" * 64, n=1),
        )
        _, first = write_snapshot(
            [make_record()],
            root=tmp_path / "a",
            rule_versions={"identity_cascade": "v2"},
            inputs=inputs,
            as_of_utc=CREATED_AT,
        )
        _, second = write_snapshot(
            [make_record()],
            root=tmp_path / "b",
            rule_versions={"identity_cascade": "v2"},
            inputs=inputs,
            as_of_utc=CREATED_AT,
        )
        assert first.snapshot_id == second.snapshot_id

    def test_digest_mismatch_is_detected(self, tmp_path):
        inputs = (
            InputReference(name="phase_ii_source", path="data/ph2.parquet", sha256="a" * 64, n=1),
        )
        directory, _ = write_snapshot(
            [make_record()],
            root=tmp_path,
            rule_versions={"identity_cascade": "v2"},
            inputs=inputs,
            as_of_utc=CREATED_AT,
        )
        (directory / "assertions.parquet").write_bytes(b"tampered")
        with pytest.raises(AssertionValidationError, match="digest verification"):
            read_snapshot(directory)
