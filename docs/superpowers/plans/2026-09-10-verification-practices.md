# Verification Practices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the three verification practices that would have caught seven of the ten defects found in the M&A pipeline between 2026-09-08 and 2026-09-10.

**Architecture:** Three independent pull requests. PR 1 adds a `validation_design` block to the study-manifest schema and a testing convention to `CLAUDE.md`. PR 2 adds artifact-boundary invariant tests. PR 3 runs an adversarial audit against the six functions that can produce a false positive which reads as evidence, starting with the canonical identity primitive.

**Tech Stack:** Python 3.11–3.12, pydantic v2 (`BaseModel`, `Field`, `ConfigDict(extra="forbid")`), pytest, ruff, mypy, uv.

**Spec:** `docs/superpowers/specs/2026-09-10-verification-practices-design.md`

## Global Constraints

- Line length 100. Ruff rules E, W, F, I, B, C4, UP. Target Python 3.11–3.12.
- Use `StrEnum`, not `str, Enum`. Use `datetime.UTC`, not `timezone.utc`.
- Company-name normalization goes through `sbir_etl.identity`; do not fork it.
- Run `make lint-boundaries` before every commit; it must pass.
- Tests live in `tests/unit/...` mirroring the source path.
- Install once with `make install` (`uv sync --extra stack-dev`); bare `uv run pytest` fails on a fresh checkout.
- Each PR branches from `main` and is independent of the other two.
- Nothing in this plan changes `docs/steering/epistemic-tiers.md`. scope-guard's finding on #704 was that the four-item evidence contract is the wrong home for both halves of that issue.

---

## File Structure

**PR 1**
- Modify `sbir_etl/quality/study_manifest.py` — add the `ValidationDesign` model and an optional field on `StudyManifest`.
- Modify `scripts/ci/validate_study_manifests.py` — require the block when `evidence_status` is `validated` or `citable`.
- Modify `tests/unit/quality/test_study_manifest.py` — model-level tests.
- Create `tests/unit/scripts/ci/test_validate_study_manifests.py` — validator-level tests.
- Modify `studies/README.md` — document the block.
- Modify `CLAUDE.md` — the class-A/B testing convention.

**PR 2**
- Create `tests/unit/capital_events/test_artifact_boundaries.py` — one test per artifact a separate stage reads.

**PR 3**
- Modify `tests/unit/identity/test_company_names.py` — adversarial cases for the identity primitive.
- Further files as findings dictate; audit `identity/company_names.py` first and split the PR if findings exceed roughly four files.

---

## PR 1 — Validation design block and testing convention

### Task 1: `ValidationDesign` model

**Files:**
- Modify: `sbir_etl/quality/study_manifest.py`
- Test: `tests/unit/quality/test_study_manifest.py`

**Interfaces:**
- Consumes: `BaseModel`, `Field`, `ConfigDict` from pydantic; `EvidenceStatus` already defined at `study_manifest.py:12`.
- Produces: `ValidationDesign` pydantic model; `StudyManifest.validation_design: ValidationDesign | None`.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/quality/test_study_manifest.py`:

```python
def test_validation_design_requires_all_four_fields() -> None:
    """A threshold with no derivation is the defect this block exists to stop.

    studies/ma-discovery-recall/design.md:53-55 set a recall floor of 10 as a
    bare count, then applied it unchanged to cuts whose eligible pools were
    342, 503 and 307.
    """
    from pydantic import ValidationError as PydanticValidationError

    from sbir_etl.quality.study_manifest import ValidationDesign

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
        with pytest.raises(PydanticValidationError):
            ValidationDesign(**fields)


def test_validation_design_rejects_empty_strings() -> None:
    """An empty derivation is the same defect wearing a value."""
    from pydantic import ValidationError as PydanticValidationError

    from sbir_etl.quality.study_manifest import ValidationDesign

    with pytest.raises(PydanticValidationError):
        ValidationDesign(
            addressable_population="x",
            expected_yield="x",
            decision_threshold="x",
            threshold_derivation="",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/quality/test_study_manifest.py -k validation_design -v`
Expected: FAIL with `ImportError: cannot import name 'ValidationDesign'`

- [ ] **Step 3: Write minimal implementation**

In `sbir_etl/quality/study_manifest.py`, add after the `MaterializationGate` class (around line 60):

```python
class ValidationDesign(BaseModel):
    """What the study must show, written before the data is seen.

    The evidence-tier contract checks that a number is pinned, not that the
    study could have detected the effect. ``studies/ma-discovery-recall``
    failed three times against a recall floor of 10 that was stated as a bare
    count and never normalised to a shrinking eligible pool; at the observed
    rate that floor passes about 30% of the time even when the method performs
    exactly as measured.

    Required only when a manifest targets ``validated`` or ``citable``. A
    census or an enumeration has no pass/fail threshold and does not need one.
    """

    model_config = ConfigDict(extra="forbid")

    addressable_population: str = Field(min_length=1)
    expected_yield: str = Field(min_length=1)
    decision_threshold: str = Field(min_length=1)
    threshold_derivation: str = Field(min_length=1)
```

Then add to `StudyManifest` after `limitations` (line 87):

```python
    validation_design: ValidationDesign | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/quality/test_study_manifest.py -k validation_design -v`
Expected: PASS, 2 tests

- [ ] **Step 5: Verify the whole suite and lint**

Run: `uv run pytest tests/unit/quality/ -q && uv run ruff check sbir_etl/quality/study_manifest.py && uv run mypy sbir_etl/quality/study_manifest.py`
Expected: all pass. `extra="forbid"` on `StudyManifest` means existing manifests without the field still load, because the field is optional, not forbidden.

- [ ] **Step 6: Commit**

```bash
git add sbir_etl/quality/study_manifest.py tests/unit/quality/test_study_manifest.py
git commit -m "feat(studies): add a validation_design block to the manifest schema"
```

---

### Task 2: Require the block for validated and citable studies

**Files:**
- Modify: `scripts/ci/validate_study_manifests.py`
- Create: `tests/unit/scripts/ci/test_validate_study_manifests.py`

**Interfaces:**
- Consumes: `StudyManifest` and `ValidationDesign` from Task 1; `validate_manifest_references(manifest, *, manifest_path, repository_root) -> list[str]` at `validate_study_manifests.py:47`.
- Produces: an additional error string in that function's return list.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/scripts/ci/test_validate_study_manifests.py`:

```python
"""Tests for the study-manifest CI validator."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
_spec = importlib.util.spec_from_file_location(
    "validate_study_manifests", REPO_ROOT / "scripts" / "ci" / "validate_study_manifests.py"
)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

from sbir_etl.quality.study_manifest import (  # noqa: E402
    EvidenceStatus,
    StudyManifest,
    ValidationDesign,
)


def _manifest(status: EvidenceStatus, *, design: ValidationDesign | None) -> StudyManifest:
    return StudyManifest(
        schema_version=1,
        study_id="example-study",
        title="Example",
        evidence_status=status,
        research_questions=["F2"],
        estimand="An example estimand.",
        frozen_artifacts=[{"path": "studies/example/design.md", "sha256": "0" * 64}],
        implementation=[{"path": "sbir_etl/quality/study_manifest.py", "symbol": "StudyManifest"}],
        identity_policy={"strategy": "RECIPIENT_V1", "version": "recipient-v1"},
        materialization={"allowed": False},
        permitted_claims=["Nothing numeric."],
        limitations=["Exploratory."],
        validation_design=design,
    )


DESIGN = ValidationDesign(
    addressable_population="1,514 pairs",
    expected_yield="~2.3%",
    decision_threshold="10 pairs",
    threshold_derivation="CI lower bound clears 1.5% at k>=10",
)


@pytest.mark.parametrize("status", [EvidenceStatus.VALIDATED, EvidenceStatus.CITABLE])
def test_validated_and_citable_require_a_validation_design(status: EvidenceStatus) -> None:
    """A study claiming its design passed must say what the design was."""
    errors = _mod.validation_design_errors(_manifest(status, design=None))
    assert any("validation_design" in e for e in errors)


@pytest.mark.parametrize("status", [EvidenceStatus.VALIDATED, EvidenceStatus.CITABLE])
def test_validated_and_citable_pass_when_present(status: EvidenceStatus) -> None:
    assert _mod.validation_design_errors(_manifest(status, design=DESIGN)) == []


@pytest.mark.parametrize(
    "status",
    [EvidenceStatus.EXPLORATORY, EvidenceStatus.REPRODUCIBLE, EvidenceStatus.RETIRED],
)
def test_lower_statuses_do_not_require_it(status: EvidenceStatus) -> None:
    """A census has no pass/fail threshold and must not be forced to invent one."""
    assert _mod.validation_design_errors(_manifest(status, design=None)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/scripts/ci/test_validate_study_manifests.py -v`
Expected: FAIL with `AttributeError: module 'validate_study_manifests' has no attribute 'validation_design_errors'`

- [ ] **Step 3: Write minimal implementation**

In `scripts/ci/validate_study_manifests.py`, add before `validate_manifest_references` (line 47):

```python
_REQUIRES_VALIDATION_DESIGN = frozenset(
    {EvidenceStatus.VALIDATED, EvidenceStatus.CITABLE}
)


def validation_design_errors(manifest: StudyManifest) -> list[str]:
    """A study whose validation design passed must state what that design was.

    Required only above ``reproducible``. A census or enumeration has no
    pass/fail threshold, and forcing one would produce a paragraph reading
    "n/a" rather than a check.
    """
    if manifest.evidence_status not in _REQUIRES_VALIDATION_DESIGN:
        return []
    if manifest.validation_design is None:
        return [
            f"evidence_status '{manifest.evidence_status}' requires a "
            "validation_design block: addressable_population, expected_yield, "
            "decision_threshold, threshold_derivation"
        ]
    return []
```

Add the import at the top of the file, alongside the existing
`from sbir_etl.quality.study_manifest import StudyManifest, load_study_manifest`:

```python
from sbir_etl.quality.study_manifest import (
    EvidenceStatus,
    StudyManifest,
    load_study_manifest,
)
```

Then call it inside `validate_manifest_references`, immediately before its
`return errors` at line 95:

```python
    errors.extend(validation_design_errors(manifest))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/scripts/ci/test_validate_study_manifests.py -v`
Expected: PASS, 7 tests

- [ ] **Step 5: Verify no existing manifest breaks**

Run: `uv run python scripts/ci/validate_study_manifests.py`
Expected on `main`: `Validated 3 study manifest(s).` A fourth,
`studies/ma-discovery-recall`, exists only on the #705 branch; if that has
merged you will see 4. Every one is `exploratory` or `reproducible`, so none is
required to carry the block and none should newly fail.

- [ ] **Step 6: Mutation check**

Temporarily change `_REQUIRES_VALIDATION_DESIGN` to `frozenset()`, then run
`uv run pytest tests/unit/scripts/ci/test_validate_study_manifests.py -q`.
Expected: 2 failures. Restore the constant. A test that passes with the gate
removed is testing nothing — this exact failure happened on PR #705, where a
coverage test asserted `main() == 1` and passed with the gate disabled because
a missed recall floor also exits 1.

- [ ] **Step 7: Commit**

```bash
git add scripts/ci/validate_study_manifests.py tests/unit/scripts/ci/test_validate_study_manifests.py
git commit -m "feat(ci): require a validation design above reproducible"
```

---

### Task 3: Document the block and the testing convention

**Files:**
- Modify: `studies/README.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: the schema from Task 1 and the check from Task 2.
- Produces: no code.

- [ ] **Step 1: Add the block to `studies/README.md`**

Under the description of the `validated` status, add:

```markdown
A manifest at `validated` or `citable` must carry a `validation_design` block:

```yaml
validation_design:
  addressable_population: >-
    How many units the estimand can reach, and how that was counted.
  expected_yield: >-
    What the study expects to find, from what prior.
  decision_threshold: >-
    The number the result must clear.
  threshold_derivation: >-
    Why that number, and the power to clear it at the expected yield.
```

Write it before capture. Its purpose is to make a study state, in advance,
whether it could detect the effect it is looking for.
`studies/ma-discovery-recall` failed three times against a recall floor of 10
that was never normalised to a shrinking eligible pool; at the observed
detection rate that floor passes about 30% of the time even when the method
works as measured.
```

- [ ] **Step 2: Add the testing convention to `CLAUDE.md`**

In the `## Testing` section, after the existing `make` targets block, add:

```markdown
### Adversarial cases for matchers and classifiers

Two kinds of function need tests that try to break them, because a false
positive from either reads as evidence rather than as a crash:

- **Role assignment from free text** — decides who did what to whom.
  `classify_direction`, `ucc/matcher.is_debtor_side_match`,
  `sec_edgar._classify_mention`.
- **Cross-population entity matching** — decides whether two names are the same
  firm. `identity/company_names`, `press_wire._match_company`,
  `form_d_scoring`, `company_fuzzy_matcher`, `ucc/matcher.classify_match`.

For every rule or branch that can return a positive result, write at least one
input where that rule must **not** fire. `tests/unit/scripts/test_refine_ma_direction.py`
is the worked example: its `ACQUIRER_SIDE_OR_NOISE` table lists phrasings where
the subject company is the buyer, the seller, or merely mentioned.

This is not a general testing rule. A field normaliser such as
`_normalize_state` cannot produce a false positive that reads as evidence, and
does not need it.

Happy-path coverage is not a substitute and can hide the defect:
`tests/unit/enrichers/test_press_wire.py` holds 28 tests for a matcher with
0/18 precision, because every test asserts that matching works and none tries
`BAL` against `"global"`.
```

- [ ] **Step 3: Verify docs guards pass**

Run: `make docs-check && make lint-boundaries`
Expected: both pass.

- [ ] **Step 4: Commit**

```bash
git add studies/README.md CLAUDE.md
git commit -m "docs: document the validation design block and adversarial cases"
```

---

## PR 2 — Artifact-boundary invariants

### Task 4: Invariant tests for the M&A artifacts

**Files:**
- Create: `tests/unit/capital_events/test_artifact_boundaries.py`

**Interfaces:**
- Consumes: `build_ma_events(cohort, source_path)` from `sbir_etl/capital_events/sources/ma_events.py`, which yields dicts with keys `company_name`, `event_date`, `event_type`, `event_subtype`, `amount_usd`, `counterparty`, `source_id`, `metadata`.
- Produces: no code.

**Background the implementer needs:** `sbir_etl/capital_events/sources/ma_events.py:34` filters on `confidence in {"high", "medium"}`. Three other consumers do not: `packages/sbir-analytics/sbir_analytics/assets/agency_private_capital/asset.py`, the same package's `phase2_outcomes.py`, and `scripts/archive/data/run_agency_private_capital_phase1.py` all key off row presence and never read `confidence`. That is why a row demoted to `low` still counted as an exit, and why 281 refuted rows had to be routed out of the artifact rather than demoted within it.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/capital_events/test_artifact_boundaries.py`:

```python
"""Invariants that consumers of the M&A artifacts rely on.

Each test states the assumption in terms of what a consumer can observe, not
in terms of what the producer intends. Three consumers key off row presence and
never read `confidence`, so "the tier is low" is not an assumption any of them
can act on.
"""

from __future__ import annotations

import json
from pathlib import Path

from sbir_etl.capital_events.sources.ma_events import build_ma_events

COHORT = [{"company_name": "ACME INC"}]


def _row(name: str, confidence: str, **extra: object) -> dict:
    row = {
        "company_name": name,
        "event_date": "2023-06-15",
        "acquirer": "GLOBEX CORP",
        "confidence": confidence,
        "signals": {"efts_subsidiary": True},
        "signal_count": 1,
    }
    row.update(extra)
    return row


def test_every_emitted_row_names_a_counterparty_or_says_why_not(tmp_path: Path) -> None:
    """A consumer reading `counterparty` cannot tell null-because-unknown from
    null-because-the-firm-was-the-buyer.

    407 events once reached this artifact at high confidence with a null
    acquirer, because a Form D business-combination flag graded high on its own
    and Form D names no counterparty.
    """
    src = tmp_path / "ma.jsonl"
    src.write_text(json.dumps(_row("ACME INC", "high", acquirer=None)) + "\n")

    events = list(build_ma_events(COHORT, src))
    for event in events:
        assert event["counterparty"], (
            "an emitted M&A event must name a counterparty; a row that cannot "
            "belongs in data/sbir_ma_non_exit.jsonl"
        )


def test_signal_count_matches_the_signals_it_reports(tmp_path: Path) -> None:
    """Legacy rows carry a count inflated by a removed source.

    The deleted press stage incremented `signal_count` once per press hit, and
    all 18 of its hits were false positives, so 18 rows on disk carry a count
    one above their own `signals`.
    """
    src = tmp_path / "ma.jsonl"
    row = _row("ACME INC", "high")
    row["signal_count"] = 99
    src.write_text(json.dumps(row) + "\n")

    events = list(build_ma_events(COHORT, src))
    meta = json.loads(events[0]["metadata"])
    assert meta["signal_count"] == 1


def test_absent_source_file_yields_nothing_rather_than_raising(tmp_path: Path) -> None:
    """A clean rebuild with no artifact must not look like a rebuild with zero
    M&A events.

    `build_ma_events` returns silently when its input is missing, which is why
    deleting the only producer of `enriched_sbir_ma_events.jsonl` would have
    dropped every MA_EVENT without an error.
    """
    events = list(build_ma_events(COHORT, tmp_path / "absent.jsonl"))
    assert events == []
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/unit/capital_events/test_artifact_boundaries.py -v`
Expected: `test_every_emitted_row_names_a_counterparty_or_says_why_not` FAILS — the builder emits a row with `counterparty: None`. The other two PASS.

- [ ] **Step 3: Decide the counterparty invariant with the user**

Do not implement a fix in this task. The failing test states a real invariant
the artifact does not currently hold. Two ways to make it hold, and the choice
is not the implementer's:

1. Filter null-counterparty rows out of `build_ma_events` into
   `data/sbir_ma_non_exit.jsonl`, consistent with how acquirer-side and refuted
   rows are handled.
2. Accept null counterparties and change the test to assert only that
   `event_subtype` records the tier, leaving consumers to interpret.

Report the failure and the two options; do not choose.

- [ ] **Step 4: Commit the passing tests only**

```bash
git add tests/unit/capital_events/test_artifact_boundaries.py
git commit -m "test(capital-events): assert the invariants consumers rely on"
```

If the counterparty test is still failing, mark it `@pytest.mark.xfail(reason="invariant not yet held; see PR discussion")` rather than deleting it, so the gap stays visible.

---

## PR 3 — Class-A/B adversarial audit

### Task 5: Audit the identity primitive

**Files:**
- Modify: `tests/unit/identity/test_company_names.py`

**Interfaces:**
- Consumes: `company_name_similarity(left, right, ...)` and `normalize_company_name(value, *, profile)` from `sbir_etl/identity/company_names.py`; `CompanyNameProfile` from `sbir_etl.identity`.
- Produces: no code unless a defect is found.

**Background the implementer needs:** this file is `primitives` tier, whose contract in `docs/steering/epistemic-tiers.md` is "one implementation per concept, versioned behavior, comprehensive tests". It has 62 tests and one negative assertion. `tests/unit/enrichers/test_press_wire.py` had the same shape — 28 tests, no negative cases — and the matcher it covers has 0/18 precision. Every consumer in the repository routes identity through this module, so a false positive here has the widest blast radius of anything in the audit.

- [ ] **Step 1: Write the adversarial table**

Add to `tests/unit/identity/test_company_names.py`:

```python
# --- Adversarial audit -------------------------------------------------------
#
# Pairs that must NOT be treated as the same firm. Drawn from real false
# positives found in the Form D join on 2026-09-08, plus the short-name
# collisions that make `press_wire._match_company` 0/18.

MUST_NOT_MATCH = [
    ("3D Control Systems, Inc.", "3D SYSTEMS CORP", "real Form D false positive"),
    ("ADELPHI TECHNOLOGY", "ADEPT TECHNOLOGY", "real Form D false positive"),
    ("Nanomimetics", "NANOMETRICS", "real Form D false positive"),
    ("Pronghorn Technologies", "PROCORE TECHNOLOGIES", "real Form D false positive"),
    ("ADT Pharmaceuticals", "ADT Inc.", "real Form D false positive"),
    ("COMPASS SYSTEMS", "Compass, Inc.", "real Form D false positive"),
    ("Linked, Inc.", "LINKEDIN CORP", "real Form D false positive"),
    ("BAL", "BALL CORP", "real Form D false positive"),
    ("SiliconCore Technology, Inc.", "SILICON STORAGE TECHNOLOGY INC", "shared tokens"),
]


@pytest.mark.parametrize("left,right,reason", MUST_NOT_MATCH)
def test_distinct_firms_do_not_score_as_the_same_firm(
    left: str, right: str, reason: str
) -> None:
    """Every pair here was a real attribution error or is one waiting to happen.

    This asserts a documented ceiling, not a target. If a pair scores above it,
    the number in this assertion is the thing to change deliberately, with the
    consumer thresholds re-checked.
    """
    score = company_name_similarity(left, right)
    assert score < 0.95, f"{left!r} vs {right!r} scored {score}: {reason}"
```

- [ ] **Step 2: Run it and record what happens**

Run: `uv run pytest tests/unit/identity/test_company_names.py -k distinct_firms -v`
Expected: unknown. This is the audit. Record which pairs score above 0.95 and their scores.

- [ ] **Step 3: Interpret before changing anything**

A failure here is not automatically a defect in `company_name_similarity`. The
function returns a similarity score; it is the *consumer's* threshold that
turns a score into a match. If pairs score high:

1. Check what thresholds consumers apply — grep for `company_name_similarity`
   across `sbir_etl` and `packages`.
2. If every consumer already thresholds below the observed scores, the finding
   is that the assertion above is set at the wrong level; adjust it to the
   real ceiling and say so in the docstring.
3. If a consumer accepts at or above the observed scores, that consumer has a
   defect. Open an issue naming the consumer; do not change the primitive.

Do not lower the primitive's discrimination to make a test pass. Report and stop.

- [ ] **Step 4: Commit the audit**

```bash
git add tests/unit/identity/test_company_names.py
git commit -m "test(identity): adversarial pairs for the company-name primitive"
```

- [ ] **Step 5: Report before continuing**

Report to the user: which pairs failed, at what scores, what consumer
thresholds exist, and whether the finding is in the primitive or a consumer.
Do not proceed to the remaining five files until that is answered — if the
primitive turns out to be sound, the rest of the audit is cheaper than
expected; if not, the remaining files may need re-scoping.

---

### Task 6: Audit the remaining five files

**Files:**
- Modify: `tests/unit/enrichers/test_press_wire.py`
- Modify or create tests for `sbir_etl/enrichers/sec_edgar/form_d_scoring.py`, `sbir_etl/enrichers/company_fuzzy_matcher.py`, `sbir_etl/ucc/matcher.py`, `sbir_etl/enrichers/sec_edgar/enricher.py`

**Interfaces:**
- Consumes: whatever Task 5 established about consumer thresholds.
- Produces: no code unless defects are found.

- [ ] **Step 1: For each file, write the negative table first**

For each of the five, list every rule or branch that can return a positive
result, then write one input per rule where it must not fire. Follow the shape
of `MUST_NOT_MATCH` in Task 5 and `ACQUIRER_SIDE_OR_NOISE` in
`tests/unit/scripts/test_refine_ma_direction.py`.

`press_wire._match_company` has a known answer already: it does unanchored
substring matching, so `BAL` matches inside `"global"` and `APP` inside
`"approximately"`. Its table should assert that a short watchlist name does not
match inside a longer ordinary word. That test will fail; the fix is tracked as
#708 and `fix/press-wire-feeds` is held behind it.

- [ ] **Step 2: Run each table and record failures**

Run: `uv run pytest tests/unit/enrichers/ tests/unit/ucc/ -q`
Expected: unknown. Record every failure with the input that produced it.

- [ ] **Step 3: Split the PR if findings are large**

If the findings exceed roughly four files' worth of changes, stop and split:
land the tables that pass plus the fixes that are unambiguous, and open issues
for the rest. A PR that changes five matchers at once cannot be reviewed
carefully, and these are functions whose false positives reach published
numbers.

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: adversarial cases for the remaining class-A/B functions"
```

---

## Out of scope, recorded so it is not silently dropped

**Ground-truth calibration.** The one defect none of these three PRs reaches is
the Form D direction inversion — that Item 10 marks the acquirer, not the
target. The test category that reaches it asserts that a signal fires on cases
where the answer is already known. The repository has no ground truth that can
serve it: `labels.jsonl`, `confirmatory-labels.jsonl` and
`form_d_join_adjudication.jsonl` all label the detector's own output and
inherit its selection, and `confirmatory-run-manifest.json` selects
Form-D-*missing* rows, so testing the Form D flag against it is circular.

Building an acquisition list assembled independently of any signal is a
prerequisite for that category of test. It is real work, it is not a test to
write, and it deserves its own issue.
