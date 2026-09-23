import copy
import hashlib
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from sbir_etl.quality.study_manifest import (
    EvidenceStatus,
    LiveSource,
    ReproductionTolerance,
    ThresholdBasis,
    ValidationDesign,
    ValidationResult,
    load_study_manifest,
)
from scripts.ci.validate_study_manifests import validate_manifest_file


def _write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _manifest(artifact_sha256: str) -> dict:
    return {
        "schema_version": 1,
        "study_id": "example-study",
        "title": "Example study",
        "evidence_status": "reproducible",
        "research_questions": ["B2"],
        "estimand": "Count observable examples.",
        "frozen_artifacts": [
            {"path": "specs/example.md", "sha256": artifact_sha256},
        ],
        "implementation": [
            {"path": "sbir_etl/example.py", "symbol": "run_study"},
        ],
        "identity_policy": {
            "strategy": "exact identifier",
            "version": "v1",
            "negative_evidence_allowed": False,
        },
        "materialization": {"allowed": False, "blockers": ["Validation is incomplete."]},
        "permitted_claims": ["The study can be reproduced."],
        "limitations": ["The result is not approved evidence."],
    }


def test_load_study_manifest_parses_versioned_contract(tmp_path: Path) -> None:
    artifact_sha256 = "a" * 64
    path = _write(
        tmp_path,
        "example-study/study.yaml",
        yaml.safe_dump(_manifest(artifact_sha256)),
    )

    manifest = load_study_manifest(path)

    assert manifest.schema_version == 1
    assert manifest.evidence_status is EvidenceStatus.REPRODUCIBLE
    assert manifest.frozen_artifacts[0].sha256 == artifact_sha256


def test_closed_materialization_gate_requires_a_blocker(tmp_path: Path) -> None:
    raw = _manifest("a" * 64)
    raw["materialization"] = {"allowed": False, "blockers": []}
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))

    with pytest.raises(ValidationError, match="must name at least one blocker"):
        load_study_manifest(path)


def test_open_materialization_gate_rejects_stale_blockers(tmp_path: Path) -> None:
    raw = _manifest("a" * 64)
    raw["materialization"] = {"allowed": True, "blockers": ["Stale blocker."]}
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))

    with pytest.raises(ValidationError, match="open materialization gate cannot name blockers"):
        load_study_manifest(path)


def test_manifest_reference_validation_checks_hash_and_symbol(tmp_path: Path) -> None:
    artifact = _write(tmp_path, "specs/example.md", "frozen design\n")
    _write(tmp_path, "sbir_etl/example.py", "def run_study():\n    return None\n")
    raw = _manifest(hashlib.sha256(artifact.read_bytes()).hexdigest())
    manifest_path = _write(
        tmp_path,
        "studies/example-study/study.yaml",
        yaml.safe_dump(raw),
    )

    assert validate_manifest_file(manifest_path, repository_root=tmp_path) == []

    raw["frozen_artifacts"][0]["sha256"] = "0" * 64
    raw["implementation"][0]["symbol"] = "missing"
    manifest_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    errors = validate_manifest_file(manifest_path, repository_root=tmp_path)
    assert any("hash mismatch" in error for error in errors)
    assert any("symbol 'missing' is missing" in error for error in errors)


def test_external_frozen_source_does_not_have_to_be_committed(tmp_path: Path) -> None:
    artifact = _write(tmp_path, "specs/example.md", "frozen design\n")
    _write(tmp_path, "sbir_etl/example.py", "def run_study():\n    return None\n")
    raw = _manifest(hashlib.sha256(artifact.read_bytes()).hexdigest())
    raw["frozen_artifacts"].append(
        {
            "path": "data/raw/exact-source.csv",
            "sha256": "b" * 64,
            "external_source": True,
        }
    )
    manifest_path = _write(
        tmp_path,
        "studies/example-study/study.yaml",
        yaml.safe_dump(raw),
    )

    manifest = load_study_manifest(manifest_path)

    assert manifest.frozen_artifacts[-1].external_source is True
    assert validate_manifest_file(manifest_path, repository_root=tmp_path) == []


@pytest.mark.parametrize(
    "module_source",
    [
        "def run_study():\n    return None\n",
        "async def run_study():\n    return None\n",
        "class run_study:\n    pass\n",
        "from factory import build\n\nrun_study = build('census')\n",
        "from factory import Asset, build\n\nrun_study: Asset = build('census')\n",
        "import dagster\n\n@dagster.asset\ndef run_study():\n    return None\n",
    ],
    ids=["def", "async_def", "class", "assign", "annotated_assign", "decorated"],
)
def test_implementation_symbol_accepts_every_module_level_binding_form(
    tmp_path: Path, module_source: str
) -> None:
    """A factory-built or annotated asset is present, not a missing implementation."""

    artifact = _write(tmp_path, "specs/example.md", "frozen design\n")
    _write(tmp_path, "sbir_etl/example.py", module_source)
    raw = _manifest(hashlib.sha256(artifact.read_bytes()).hexdigest())
    manifest_path = _write(tmp_path, "studies/example-study/study.yaml", yaml.safe_dump(raw))

    assert validate_manifest_file(manifest_path, repository_root=tmp_path) == []


def test_implementation_symbol_still_rejects_names_bound_only_inside_a_function(
    tmp_path: Path,
) -> None:
    artifact = _write(tmp_path, "specs/example.md", "frozen design\n")
    _write(
        tmp_path, "sbir_etl/example.py", "def outer():\n    run_study = 1\n    return run_study\n"
    )
    raw = _manifest(hashlib.sha256(artifact.read_bytes()).hexdigest())
    manifest_path = _write(tmp_path, "studies/example-study/study.yaml", yaml.safe_dump(raw))

    errors = validate_manifest_file(manifest_path, repository_root=tmp_path)
    assert any("symbol 'run_study' is missing" in error for error in errors)


def test_repository_study_manifests_are_valid() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    manifests = sorted((repository_root / "studies").glob("*/study.yaml"))

    assert manifests
    assert all(
        validate_manifest_file(path, repository_root=repository_root) == [] for path in manifests
    )


def test_validation_design_requires_all_four_fields() -> None:
    """A threshold with no derivation is incomplete by construction."""
    complete = ValidationDesign(
        addressable_population="1,514 Form-D-missing pairs naming an acquirer",
        expected_yield="~2.3% of eligible pairs, from pilot 9/342 and confirmatory 13/503",
        decision_threshold="10 distinct strict medium/high pairs",
        threshold_derivation="95% CI lower bound clears 1.5% at n=362 when k>=10",
    )
    assert complete.decision_threshold == "10 distinct strict medium/high pairs"

    for missing in (
        "addressable_population",
        "expected_yield",
        "decision_threshold",
        "threshold_derivation",
    ):
        fields = {
            "addressable_population": "x",
            "expected_yield": "x",
            "decision_threshold": "x",
            "threshold_derivation": "x",
        }
        del fields[missing]
        with pytest.raises(ValidationError):
            ValidationDesign(**fields)


def test_validation_design_rejects_empty_strings() -> None:
    """An empty derivation is the same defect wearing a value."""
    with pytest.raises(ValidationError):
        ValidationDesign(
            addressable_population="x",
            expected_yield="x",
            decision_threshold="x",
            threshold_derivation="",
        )


@pytest.mark.parametrize(
    ("blank_field", "blank_value"),
    [
        ("addressable_population", "   "),
        ("expected_yield", "  "),
        ("decision_threshold", " "),
        ("threshold_derivation", "\t"),
    ],
)
def test_validation_design_rejects_whitespace_only_strings(
    blank_field: str, blank_value: str
) -> None:
    """A whitespace-only value satisfies min_length=1 but states nothing.

    A manifest claiming ``evidence_status: validated`` must not be able to pass
    this gate by filling a field with spaces or a tab.
    """
    fields = {
        "addressable_population": "x",
        "expected_yield": "x",
        "decision_threshold": "x",
        "threshold_derivation": "x",
    }
    fields[blank_field] = blank_value

    with pytest.raises(ValidationError, match="must not be blank"):
        ValidationDesign(**fields)


VALIDATION_DESIGN = {
    "addressable_population": "Every row in the frozen cohort.",
    "expected_yield": "At least 95% source coverage.",
    "decision_threshold": "All reconciliations pass and coverage is at least 95%.",
    "threshold_derivation": "The frozen design identifies 95% as the minimum useful coverage.",
    "threshold_basis": "proportion",
    "threshold_value": 0.95,
}

VALIDATION_RESULT = {
    "design_path": "specs/example.md",
    "design_sha256": "a" * 64,
    "evaluated_on": "2026-09-13",
    "metric": "source coverage of the frozen cohort",
    "numerator": 97,
    "denominator": 100,
    "interval_low": 0.914,
    "interval_high": 0.991,
    "interval_method": "Wilson 95%",
    "threshold_met": True,
    "confirmatory": True,
}


@pytest.mark.parametrize("status", [EvidenceStatus.VALIDATED, EvidenceStatus.APPROVED])
def test_promoted_manifest_requires_validation_design(
    tmp_path: Path, status: EvidenceStatus
) -> None:
    raw = _manifest("a" * 64)
    raw["evidence_status"] = status.value
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))

    with pytest.raises(ValidationError, match="requires a validation_design block"):
        load_study_manifest(path)

    errors = validate_manifest_file(path, repository_root=tmp_path)
    assert any("requires a validation_design block" in error for error in errors)


@pytest.mark.parametrize("status", [EvidenceStatus.VALIDATED, EvidenceStatus.APPROVED])
def test_promoted_manifest_loads_with_validation_design(
    tmp_path: Path, status: EvidenceStatus
) -> None:
    raw = _manifest("a" * 64)
    raw["evidence_status"] = status.value
    raw["validation_design"] = VALIDATION_DESIGN
    raw["validation_result"] = VALIDATION_RESULT
    if status is EvidenceStatus.APPROVED:
        raw["frozen_artifacts"].append({"path": "reviews/approval.md", "sha256": "b" * 64})
        raw["claim_approval"] = {
            "review_path": "reviews/approval.md",
            "review_sha256": "b" * 64,
            "approved_on": "2026-09-23",
        }
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))

    manifest = load_study_manifest(path)

    assert manifest.evidence_status is status
    assert manifest.validation_design is not None
    assert manifest.validation_result is not None
    assert manifest.validation_result.point_estimate == pytest.approx(0.97)


def _promoted(status: EvidenceStatus) -> dict:
    raw = _manifest("a" * 64)
    raw["evidence_status"] = status.value
    raw["validation_design"] = dict(VALIDATION_DESIGN)
    raw["validation_result"] = dict(VALIDATION_RESULT)
    if status is EvidenceStatus.APPROVED:
        raw["frozen_artifacts"].append({"path": "reviews/approval.md", "sha256": "b" * 64})
        raw["claim_approval"] = {
            "review_path": "reviews/approval.md",
            "review_sha256": "b" * 64,
            "approved_on": "2026-09-23",
        }
    return raw


@pytest.mark.parametrize("status", [EvidenceStatus.VALIDATED, EvidenceStatus.APPROVED])
def test_promoted_manifest_requires_validation_result(
    tmp_path: Path, status: EvidenceStatus
) -> None:
    """A design alone says what would count; promotion needs what was found."""
    raw = _promoted(status)
    del raw["validation_result"]
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))

    with pytest.raises(ValidationError, match="requires a validation_result block"):
        load_study_manifest(path)


@pytest.mark.parametrize("status", [EvidenceStatus.VALIDATED, EvidenceStatus.APPROVED])
def test_promoted_manifest_requires_threshold_basis(tmp_path: Path, status: EvidenceStatus) -> None:
    raw = _promoted(status)
    del raw["validation_design"]["threshold_basis"]
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))

    with pytest.raises(ValidationError, match="requires validation_design.threshold_basis"):
        load_study_manifest(path)


def test_reproducible_manifest_may_omit_threshold_basis_and_result(tmp_path: Path) -> None:
    """Existing designs written before the result block keep loading below validated."""
    raw = _manifest("a" * 64)
    raw["validation_design"] = {
        key: value for key, value in VALIDATION_DESIGN.items() if key != "threshold_basis"
    }
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))

    manifest = load_study_manifest(path)

    assert manifest.validation_design is not None
    assert manifest.validation_design.threshold_basis is None
    assert manifest.validation_result is None


@pytest.mark.parametrize("status", [EvidenceStatus.VALIDATED, EvidenceStatus.APPROVED])
def test_post_hoc_result_cannot_promote(tmp_path: Path, status: EvidenceStatus) -> None:
    """A result from a design changed after the data were seen is reportable, not confirmatory."""
    raw = _promoted(status)
    raw["validation_result"]["confirmatory"] = False
    raw["validation_result"]["post_hoc_analyses"] = ["Enlarged the cut from 200 to 500 pairs."]
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))

    with pytest.raises(ValidationError, match="requires a confirmatory validation_result"):
        load_study_manifest(path)


@pytest.mark.parametrize("status", [EvidenceStatus.VALIDATED, EvidenceStatus.APPROVED])
def test_result_design_hash_must_match_the_pinned_design(
    tmp_path: Path, status: EvidenceStatus
) -> None:
    raw = _promoted(status)
    raw["validation_result"]["design_sha256"] = "b" * 64
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))

    with pytest.raises(ValidationError, match="does not match the frozen hash"):
        load_study_manifest(path)


@pytest.mark.parametrize("status", [EvidenceStatus.VALIDATED, EvidenceStatus.APPROVED])
def test_result_design_path_must_be_pinned(tmp_path: Path, status: EvidenceStatus) -> None:
    raw = _promoted(status)
    raw["validation_result"]["design_path"] = "specs/not-pinned.md"
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))

    with pytest.raises(ValidationError, match="is not listed in frozen_artifacts"):
        load_study_manifest(path)


@pytest.mark.parametrize("status", [EvidenceStatus.VALIDATED, EvidenceStatus.APPROVED])
def test_design_hash_of_a_different_frozen_artifact_is_rejected(
    tmp_path: Path, status: EvidenceStatus
) -> None:
    """A study pins several designs; the hash must belong to the one it names.

    Matching any frozen hash would let a study cite its own amendments log --
    the file that by definition records changes made after the design froze --
    as the evaluated design.
    """
    raw = _promoted(status)
    raw["frozen_artifacts"].append({"path": "specs/amendments.md", "sha256": "c" * 64})
    raw["validation_result"]["design_sha256"] = "c" * 64
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))

    with pytest.raises(ValidationError, match="does not match the frozen hash"):
        load_study_manifest(path)


def test_validated_records_a_missed_threshold_but_approved_rejects_it(tmp_path: Path) -> None:
    """validated means the preregistered test ran and its outcome is on the record."""
    raw = _promoted(EvidenceStatus.VALIDATED)
    raw["validation_result"].update(
        {
            "numerator": 4,
            "denominator": 10,
            "interval_low": 0.168,
            "interval_high": 0.687,
            "threshold_met": False,
        }
    )
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))
    manifest = load_study_manifest(path)
    assert manifest.validation_result is not None
    assert manifest.validation_result.threshold_met is False

    raw["evidence_status"] = EvidenceStatus.APPROVED.value
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))
    with pytest.raises(ValidationError, match="requires validation_result.threshold_met"):
        load_study_manifest(path)


def test_approved_status_requires_one_pinned_claim_review(tmp_path: Path) -> None:
    raw = _promoted(EvidenceStatus.APPROVED)
    del raw["claim_approval"]
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))

    with pytest.raises(ValidationError, match="requires a claim_approval block"):
        load_study_manifest(path)

    raw = _promoted(EvidenceStatus.APPROVED)
    raw["claim_approval"]["review_path"] = "reviews/unpinned.md"
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))
    with pytest.raises(ValidationError, match="is not listed in frozen_artifacts"):
        load_study_manifest(path)

    raw = _promoted(EvidenceStatus.APPROVED)
    raw["claim_approval"]["review_sha256"] = "c" * 64
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))
    with pytest.raises(ValidationError, match="does not match the frozen hash"):
        load_study_manifest(path)

    raw = _promoted(EvidenceStatus.APPROVED)
    raw["claim_approval"]["approved_on"] = "2026-09-12"
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))
    with pytest.raises(ValidationError, match="cannot predate the validation result"):
        load_study_manifest(path)


def test_count_threshold_requires_a_frozen_population() -> None:
    """A count floor over a shrinking population is unreachable for the wrong reasons."""
    fields = {key: value for key, value in VALIDATION_DESIGN.items() if key != "threshold_basis"}
    fields["threshold_value"] = 10  # a count basis needs a whole-number threshold
    with pytest.raises(ValidationError, match="requires frozen_population_artifact"):
        ValidationDesign(**fields, threshold_basis=ThresholdBasis.COUNT_ON_FROZEN_POPULATION)
    design = ValidationDesign(
        **fields,
        threshold_basis=ThresholdBasis.COUNT_ON_FROZEN_POPULATION,
        frozen_population_artifact="studies/example-study/eligible_pairs.csv",
    )
    assert design.frozen_population_artifact is not None


def test_frozen_population_artifact_must_be_pinned(tmp_path: Path) -> None:
    raw = _promoted(EvidenceStatus.VALIDATED)
    raw["validation_design"].update(
        {
            "threshold_basis": "count_on_frozen_population",
            "threshold_value": 10,
            "frozen_population_artifact": "studies/example-study/eligible_pairs.csv",
        }
    )
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))
    with pytest.raises(ValidationError, match="is not listed in frozen_artifacts"):
        load_study_manifest(path)

    raw["frozen_artifacts"].append(
        {"path": "studies/example-study/eligible_pairs.csv", "sha256": "c" * 64}
    )
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))
    assert load_study_manifest(path).validation_design is not None


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"numerator": 11}, "numerator cannot exceed denominator"),
        ({"interval_low": 0.99}, "interval_low cannot exceed interval_high"),
        ({"interval_low": 0.98, "interval_high": 0.99}, "lies outside the reported interval"),
    ],
)
def test_validation_result_interval_must_be_coherent(override: dict, message: str) -> None:
    fields = dict(VALIDATION_RESULT)
    fields.update(
        {"numerator": 9, "denominator": 10, "interval_low": 0.596, "interval_high": 0.982}
    )
    fields.update(override)
    with pytest.raises(ValidationError, match=message):
        ValidationResult(**fields)


@pytest.mark.parametrize("field", ["design_path", "metric", "interval_method"])
def test_validation_result_rejects_blank_strings(field: str) -> None:
    """min_length=1 admits "   "; ValidationDesign already rejects it."""
    fields = dict(VALIDATION_RESULT)
    fields[field] = "   "
    with pytest.raises(ValidationError, match="must not be blank"):
        ValidationResult(**fields)


def test_count_floor_cannot_be_filed_as_a_proportion() -> None:
    """decision_threshold is prose, so the basis is checked against a number.

    A count floor such as "10 distinct pairs" written under
    threshold_basis: proportion is the exact shape that sank ma-discovery-recall.
    """
    fields = dict(VALIDATION_DESIGN)
    fields.update(decision_threshold="At least 10 distinct pairs.", threshold_value=10)
    with pytest.raises(ValidationError, match="requires threshold_value in"):
        ValidationDesign(**fields)


def test_count_basis_requires_a_whole_number_threshold() -> None:
    fields = dict(VALIDATION_DESIGN)
    fields.update(
        threshold_basis="count_on_frozen_population",
        threshold_value=10.5,
        frozen_population_artifact="specs/example.md",
    )
    with pytest.raises(ValidationError, match="requires a whole-number"):
        ValidationDesign(**fields)


@pytest.mark.parametrize("status", [EvidenceStatus.VALIDATED, EvidenceStatus.APPROVED])
def test_promoted_manifest_requires_threshold_value(tmp_path: Path, status: EvidenceStatus) -> None:
    raw = _promoted(status)
    del raw["validation_design"]["threshold_value"]
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))

    with pytest.raises(ValidationError, match="requires validation_design.threshold_value"):
        load_study_manifest(path)


REPRODUCTION = {
    "live_sources": [
        {
            "name": "GSA contract-opportunity archive",
            "retrieval_manifest": "specs/example.md",
            "upstream_measure": "rows_scanned",
            "identity_grain": "notice_id",
        }
    ],
    "tolerances": [
        {
            "quantity": "rows_scanned",
            "absolute_band": 2,
            "derivation": "One revised notice per rebuild is expected; two is the observed ceiling.",
        }
    ],
}


def test_live_source_manifest_must_be_pinned(tmp_path: Path) -> None:
    """Naming a path that is not frozen is what left the motivating rebuild unclassifiable."""
    raw = _manifest("a" * 64)
    raw["reproduction"] = copy.deepcopy(REPRODUCTION)
    raw["reproduction"]["live_sources"][0]["retrieval_manifest"] = "data/not-pinned.json"
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))

    with pytest.raises(ValidationError, match="not listed in frozen_artifacts"):
        load_study_manifest(path)


def test_live_source_with_a_pinned_manifest_loads(tmp_path: Path) -> None:
    raw = _manifest("a" * 64)
    raw["reproduction"] = copy.deepcopy(REPRODUCTION)
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))

    manifest = load_study_manifest(path)

    assert manifest.reproduction is not None
    assert manifest.reproduction.live_sources[0].identity_grain == "notice_id"


@pytest.mark.parametrize(
    "field", ["name", "retrieval_manifest", "upstream_measure", "identity_grain"]
)
def test_live_source_rejects_blank_fields(field: str) -> None:
    fields = dict(REPRODUCTION["live_sources"][0])
    fields[field] = "   "
    with pytest.raises(ValidationError, match="must not be blank"):
        LiveSource(**fields)


@pytest.mark.parametrize("field", ["quantity", "derivation"])
def test_tolerance_rejects_blank_fields(field: str) -> None:
    fields = dict(REPRODUCTION["tolerances"][0])
    fields[field] = "\t"
    with pytest.raises(ValidationError, match="must not be blank"):
        ReproductionTolerance(**fields)


def test_tolerance_requires_a_derivation() -> None:
    """A band with no stated basis is not a contract, per R2."""
    with pytest.raises(ValidationError):
        ReproductionTolerance(quantity="positives", absolute_band=2)


def test_duplicate_tolerance_quantities_are_rejected(tmp_path: Path) -> None:
    """Two bands for one quantity makes the contract ambiguous."""
    raw = _manifest("a" * 64)
    raw["reproduction"] = copy.deepcopy(REPRODUCTION)
    raw["reproduction"]["tolerances"].append(dict(raw["reproduction"]["tolerances"][0]))
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))

    with pytest.raises(ValidationError, match="duplicate reproduction tolerance"):
        load_study_manifest(path)


def test_a_study_without_live_sources_is_unaffected(tmp_path: Path) -> None:
    """R4: nothing here changes a study that declares no live source."""
    raw = _manifest("a" * 64)
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))

    assert load_study_manifest(path).reproduction is None


def test_tolerance_on_an_unreported_quantity_is_rejected(tmp_path: Path) -> None:
    """A band nothing reports cannot be breached, so it constrains nothing."""
    raw = _manifest("a" * 64)
    raw["reproduction"] = copy.deepcopy(REPRODUCTION)
    raw["reproduction"]["tolerances"].append(
        {"quantity": "never_reported", "absolute_band": 1, "derivation": "d"}
    )
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))

    with pytest.raises(ValidationError, match="cannot be breached"):
        load_study_manifest(path)


def test_a_quantity_named_in_the_estimand_is_accepted(tmp_path: Path) -> None:
    """The study's own text is what makes a quantity findable to a reader."""
    raw = _manifest("a" * 64)
    raw["estimand"] = "Count observable examples, reported as surviving_pairs."
    raw["reproduction"] = copy.deepcopy(REPRODUCTION)
    raw["reproduction"]["tolerances"].append(
        {"quantity": "surviving_pairs", "absolute_band": 1, "derivation": "d"}
    )
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))

    assert load_study_manifest(path).reproduction is not None
