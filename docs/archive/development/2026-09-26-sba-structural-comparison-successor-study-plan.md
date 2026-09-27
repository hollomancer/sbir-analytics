# SBA Structural-Comparison Successor Study Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a successor study ID for the SBA annual-report structural comparison whose generated public page states the v0.18.0 result's real status under the citation rule from #792, without touching the released v0.18.0 study folder or its page.

**Architecture:** The renderer gains a `StudyProfile` registry keyed by study ID. The default profile reproduces the v0.18.0 sidecar and page byte for byte. A second profile points at a new study folder and page, with different status wording, claim prefix and suffix, and release heading. The count stage and the public reproduction command accept the study manifest to pin against, so a clean replay at HEAD can run with HEAD hashes. The successor manifest pins the same result artifacts as v0.18.0 and re-pins only the files that changed at HEAD.

**Tech Stack:** Python 3.12, `uv`, pydantic `StudyManifest`, pytest, Make, the repository CI guards (`validate_study_manifests.py`, `check_study_artifact_roundtrip.py`, `check_research_question_status.py`, `check_epistemic_tiers.py`).

**Spec:** GitHub issue #796 (https://github.com/hollomancer/sbir-analytics/issues/796) and `specs/sba-annual-report-approved-evidence-release/` (`requirements.md`, `design.md` "Gate reconciliation", `amendments.md`).

## Global Constraints

- Tier: `evidence`. The successor starts at `reproducible`. It may claim `validated` only after a clean replay at HEAD. It must not claim `approved` and must not carry `claim_approval`.
- `studies/sba-annual-report-structural-comparison/` must stay byte-identical to tag `v0.18.0`. CI (`validate_study_manifests.py` via `verify_current_release_subtree`) fails on any added, removed, or changed byte there.
- `docs/public/sba-structural-comparison.md` and the renderer's default output must stay byte-identical. `test_committed_public_artifacts_regenerate_byte_for_byte` and the registered round-trip pair enforce this.
- If the count-stage replay at HEAD differs from `studies/sba-annual-report-structural-comparison/results/count-comparison.csv` by any byte, **stop**. Spec Revision 3 then requires renewed independent review. Do not proceed to Task 6 or later.
- The successor page must not say: `approved`; that the published-sample blocker is resolved; that the result is new or differs from v0.18.0; that v0.18.0 was wrong; or anything beyond the manifest's bounded claims.
- Generated files (`release/public-result.json` and the public page) are never hand-edited. Regenerate both together with the renderer.
- Ordering rule created by the frozen-hash design: the sidecar embeds the SHA-256 of `scripts/data/render_sba_structural_comparison.py`, `scripts/data/reproduce_sba_structural_comparison.py`, `scripts/data/run_sba_structural_comparison.py`, `producer.py`, and `uv.lock`. Finish every code change before pinning those hashes (Task 5) and rendering (Task 6). Any later edit to those files requires re-pin and re-render, and the re-rendered page is new claim-facing bytes for review.
- The named successor ID used throughout this plan is `sba-annual-report-structural-comparison-release`, with public page `docs/public/sba-structural-comparison-release.md`. This is a proposal. If the owner prefers another ID, replace both strings everywhere in this plan before starting Task 3. The ID must match `^[a-z0-9]+(?:-[a-z0-9]+)*$` and equal the directory name.
- Line length 100. Ruff rules E, W, F, I, B, C4, UP. Plain language in prose; ASD-STE100 style in the study contract files.
- Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

---

### Task 0: Recover the local checkout

The local checkout is on `docs/human-readable-readme` (already merged as #794) with a stalled merge of local `main` and a conflict in `README.md`. Local `main` is 17 commits behind `origin/main`, which predates #792 and #793.

**Files:** none in the repository.

- [ ] **Step 1: Abort the stalled merge**

This discards only the in-progress merge state. The branch's commits and the 2026-09-16 stash are untouched. Confirm with the owner before running if they did not approve it when they approved this plan.

```bash
cd /Users/hollomancer/projects/sbir-analytics
git merge --abort
git status --short | wc -l   # expected: 0
```

- [ ] **Step 2: Update main and branch**

```bash
git checkout main
git pull --ff-only origin main
git log --oneline -1          # expected: 701ada72 refactor(evidence): separate approval from citation (#792) or newer
git checkout -b studies/sba-structural-comparison-successor
```

- [ ] **Step 3: Refresh the environment and confirm the baseline is green**

```bash
make install
uv run python -c "import sbir_etl; print(sbir_etl.__version__)"   # expected: 0.19.0
uv run pytest tests/unit/scripts/test_render_sba_structural_comparison.py tests/unit/quality/test_study_manifest.py -q
uv run python scripts/ci/validate_study_manifests.py
uv run python scripts/ci/check_study_artifact_roundtrip.py
```

Expected: all pass. If anything fails here, stop and report; the baseline must be green before any change.

---

### Task 1: Spec amendment Revision 4

**Files:**
- Modify: `specs/sba-annual-report-approved-evidence-release/amendments.md` (append after Revision 3, line 68)

**Interfaces:**
- Produces: the authorization that every later task cites. `design.md` lines 77–80 allow "a separate descriptive structural-comparison product" but forbid relabeling "the existing blocked outcome as achieved".

- [ ] **Step 1: Append Revision 4**

Append this text to the end of `amendments.md`:

```markdown

## Revision 4 — 2026-09-26 — successor study authorized for the citation rule

This revision authorizes one separate descriptive product under the
"Gate reconciliation" rule in `design.md`. The product is a successor study
ID, `sba-annual-report-structural-comparison-release`, whose generated public
page states the v0.18.0 result's status under the citation rule adopted in
#792: a study result may be cited from an immutable release only when the
study is `reproducible` or higher, with its actual evidence status attached.

The successor changes wording, not evidence. It pins the same 632-cell
comparison, the same 1,264 of 1,264 confirmatory result, the same estimand,
the same two permitted claims in substance, and the same eight limitations.
It re-pins only files that changed at HEAD after `v0.18.0`: `producer.py`
(a rename of `citable` to `approved`), `uv.lock`, and the three study
scripts that this revision parameterises. Nothing is re-analysed.

Rules for the successor:

1. It starts at `reproducible`. It may record `validated` only after a clean
   replay at HEAD reproduces `results/count-comparison.csv` byte for byte.
   Any differing byte is a substantive change and requires renewed
   independent review under Revision 3.
2. It must not record `approved` or a `claim_approval` block. Revision 12 of
   the study record states that the claim-facing bytes still require an
   evidence audit and a cold named-reader review. The successor does not
   inherit reviews that never happened.
3. Its page must repeat the permanent published-sample reproduction blocker.
   It must not present the result as new, as different from `v0.18.0`, or
   as a correction of the `v0.18.0` page, which was correct under the rule
   then in force.
4. Its page may state that the result may be cited as `validated` only after
   an evidence audit of the exact manifest, sidecar, and page bytes and a
   cold named-reader review of the exact page bytes are both recorded in the
   successor's `amendments.md`.
5. Until an annotated tag binds the successor in `studies/releases.yaml`, the
   page must say that its release is pending.

The released `v0.18.0` study folder and page are not modified. CI keeps
them byte-identical to the tag.
```

- [ ] **Step 2: Verify the evidence-tier paperwork guard still passes**

```bash
uv run python scripts/ci/check_epistemic_tiers.py
```

Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add specs/sba-annual-report-approved-evidence-release/amendments.md
git commit -m "spec(sba-structural): Revision 4 authorizes a successor study for the citation rule

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Parameterise the count stage by study manifest

The count producer verifies the SHA-256 of `producer.py` against the study manifest it is given (`producer.py:232-244`). At HEAD `producer.py` differs from the v0.18.0 pin, so the count stage cannot run at HEAD against the v0.18.0 manifest. It needs to accept the successor manifest.

**Files:**
- Modify: `scripts/data/run_sba_structural_comparison.py:114-120` and `:185-215`
- Test: `tests/unit/scripts/test_run_sba_structural_comparison_manifest.py` (create)

**Interfaces:**
- Produces: `build_production_inputs(repository_root: Path, source_root: Path, *, study_manifest_path: Path | None = None) -> ProductionInputs`. Default behaviour is unchanged.
- Produces: CLI flag `--study-manifest PATH` (default: `studies/sba-annual-report-structural-comparison/study.yaml` under the repository root).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/scripts/test_run_sba_structural_comparison_manifest.py`:

```python
"""The count stage pins its inputs against the manifest it is given."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.data import run_sba_structural_comparison as count_stage


ROOT = Path(__file__).resolve().parents[3]
OLD_STUDY = "studies/sba-annual-report-structural-comparison"


def _copy_repository_pins(destination: Path) -> None:
    """Copy only the repository files the count stage pins, not the raw sources."""
    for relative in (
        f"{OLD_STUDY}/study.yaml",
        f"{OLD_STUDY}/source-manifest.json",
        f"{OLD_STUDY}/validation-design-v1.md",
        f"{OLD_STUDY}/validation-population-v1.csv",
        "studies/sba-annual-report-tables/award-export-2026-09-17.meta.json",
        "studies/sba-annual-report-tables/data/awards_by_state_fy20.csv",
        "studies/sba-annual-report-tables/data/awards_by_state_fy21.csv",
        "studies/sba-annual-report-tables/data/awards_by_state_fy22.csv",
        count_stage.PRODUCER.as_posix(),
    ):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)


def test_build_production_inputs_defaults_to_the_released_manifest(tmp_path: Path) -> None:
    _copy_repository_pins(tmp_path)

    inputs = count_stage.build_production_inputs(tmp_path, tmp_path)

    assert inputs.implementation.reference == count_stage.PRODUCER.as_posix()


def test_build_production_inputs_pins_against_the_given_manifest(tmp_path: Path) -> None:
    _copy_repository_pins(tmp_path)
    successor = tmp_path / "studies/successor/study.yaml"
    successor.parent.mkdir(parents=True)
    text = (tmp_path / OLD_STUDY / "study.yaml").read_text(encoding="utf-8")
    successor.write_text(
        text.replace(
            "study_id: sba-annual-report-structural-comparison\n",
            "study_id: successor\n",
        ),
        encoding="utf-8",
    )

    inputs = count_stage.build_production_inputs(
        tmp_path, tmp_path, study_manifest_path=successor
    )

    assert inputs.implementation.reference == count_stage.PRODUCER.as_posix()


def test_build_production_inputs_rejects_a_missing_manifest(tmp_path: Path) -> None:
    _copy_repository_pins(tmp_path)

    with pytest.raises(FileNotFoundError):
        count_stage.build_production_inputs(
            tmp_path, tmp_path, study_manifest_path=tmp_path / "studies/none/study.yaml"
        )
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run pytest tests/unit/scripts/test_run_sba_structural_comparison_manifest.py -q
```

Expected: the second and third tests FAIL with `TypeError: build_production_inputs() got an unexpected keyword argument 'study_manifest_path'`.

- [ ] **Step 3: Add the parameter**

In `scripts/data/run_sba_structural_comparison.py`, change the function signature and first lines:

```python
def build_production_inputs(
    repository_root: Path,
    source_root: Path,
    *,
    study_manifest_path: Path | None = None,
) -> ProductionInputs:
    """Construct production inputs from the two checked-in manifests.

    ``study_manifest_path`` selects which study's frozen hashes the inputs are
    pinned against. It defaults to the released study manifest.
    """

    study_manifest_path = study_manifest_path or repository_root / STUDY_MANIFEST
    study_manifest = load_study_manifest(study_manifest_path)
```

Then in `_parse_args()` add, after the `--source-root` argument:

```python
    parser.add_argument(
        "--study-manifest",
        type=Path,
        help="Study manifest whose frozen hashes pin the inputs (default: released study).",
    )
```

And in `main()`:

```python
    inputs = build_production_inputs(
        repository_root,
        source_root,
        study_manifest_path=args.study_manifest.resolve() if args.study_manifest else None,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run pytest tests/unit/scripts/test_run_sba_structural_comparison_manifest.py -q
```

Expected: 3 passed. If `load_study_manifest` raises `OSError` rather than `FileNotFoundError` for a missing path, change the third test's `pytest.raises` to `OSError`; do not change the script.

- [ ] **Step 5: Commit**

```bash
git add scripts/data/run_sba_structural_comparison.py tests/unit/scripts/test_run_sba_structural_comparison_manifest.py
git commit -m "feat(sba-structural): let the count stage pin against a chosen study manifest

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Renderer study profiles

The round-trip guard calls `render_markdown(payload)` with only the payload, so the profile must be recoverable from `payload["content"]["study_id"]`. `build_payload` and `generate_public_artifacts` take an explicit `study_id`.

**Files:**
- Modify: `scripts/data/render_sba_structural_comparison.py:23-37` (constants), `:423-431` (`_bounded_claim`), `:503-529` (`_validate_manifest`), `:607-718` (`build_payload`), `:720-757` (`_validate_payload`), `:861-877` and `:1002` (`render_markdown`), `:1017-1052` (`generate_public_artifacts`, `_parse_args`, `main`)
- Test: `tests/unit/scripts/test_render_sba_structural_comparison.py`

**Interfaces:**
- Produces: `StudyProfile` frozen dataclass; `PROFILES: dict[str, StudyProfile]`; `SUCCESSOR_STUDY_ID = "sba-annual-report-structural-comparison-release"`; `_profile_for(study_id: str) -> StudyProfile` raising `PublicResultError` on unknown IDs.
- Produces: `build_payload(repository_root, *, study_id: str = STUDY_ID, comparison_path=None, study_manifest_path=None, source_manifest_path=None, run_diagnostics_path=None)`.
- Produces: `generate_public_artifacts(repository_root, *, study_id: str = STUDY_ID, sidecar_path=None, markdown_path=None)`.
- Produces: CLI flag `--study-id` with choices from `PROFILES`.
- Keeps: module constants `STUDY_ID`, `STUDY_DIRECTORY`, `COMPARISON_REFERENCE`, `STUDY_MANIFEST_REFERENCE`, `SOURCE_MANIFEST_REFERENCE`, `RUN_DIAGNOSTICS_REFERENCE`, `SIDECAR_REFERENCE`, `MARKDOWN_REFERENCE`, `RELEASE_STATUS`, `REPRODUCTION_COMMAND` (tests and `reproduce_sba_structural_comparison.py` import them). `STUDY_DIRECTORY` stays the v0.18.0 folder for every profile because the successor pins the same result artifacts.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/scripts/test_render_sba_structural_comparison.py`:

```python
def test_profiles_default_to_the_released_study() -> None:
    default = renderer.PROFILES[renderer.STUDY_ID]
    successor = renderer.PROFILES[renderer.SUCCESSOR_STUDY_ID]

    assert default.sidecar_reference == renderer.SIDECAR_REFERENCE
    assert default.markdown_reference == renderer.MARKDOWN_REFERENCE
    assert default.release_status == "Validated, not citable"
    assert default.reproduction_command == "make reproduce-sba-structural"
    assert successor.study_id == "sba-annual-report-structural-comparison-release"
    assert successor.sidecar_reference != default.sidecar_reference
    assert successor.markdown_reference != default.markdown_reference
    assert successor.release_status != default.release_status
    assert successor.reproduction_command != default.reproduction_command


def test_render_rejects_a_sidecar_whose_study_has_no_profile() -> None:
    payload = json.loads(SIDECAR.read_text(encoding="utf-8"))
    payload["content"]["study_id"] = "no-such-study"
    payload["content_sha256"] = renderer._canonical_sha256(payload["content"])

    with pytest.raises(renderer.PublicResultError, match="no renderer profile"):
        renderer.render_markdown(payload)


def test_render_rejects_a_release_status_borrowed_from_another_profile() -> None:
    payload = json.loads(SIDECAR.read_text(encoding="utf-8"))
    successor = renderer.PROFILES[renderer.SUCCESSOR_STUDY_ID]
    payload["content"]["release_status"] = successor.release_status
    payload["content_sha256"] = renderer._canonical_sha256(payload["content"])

    with pytest.raises(renderer.PublicResultError, match="wrong study or release status"):
        renderer.render_markdown(payload)


def test_build_payload_rejects_an_unknown_study_id(reviewed_release_root: Path) -> None:
    with pytest.raises(renderer.PublicResultError, match="no renderer profile"):
        renderer.build_payload(reviewed_release_root, study_id="no-such-study")


def test_bounded_claim_uses_the_profile_prefix_and_suffix() -> None:
    manifest = load_study_manifest(ROOT / renderer.STUDY_MANIFEST_REFERENCE)
    successor = renderer.PROFILES[renderer.SUCCESSOR_STUDY_ID]

    with pytest.raises(renderer.PublicResultError, match="does not match the .* release form"):
        renderer._bounded_claim(manifest, successor)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/unit/scripts/test_render_sba_structural_comparison.py -q -k "profile or no_profile or borrowed or unknown_study or prefix_and_suffix"
```

Expected: 5 FAIL with `AttributeError: module ... has no attribute 'PROFILES'` or a `TypeError` on the extra argument.

- [ ] **Step 3: Add the profile registry**

In `scripts/data/render_sba_structural_comparison.py`, add `from dataclasses import dataclass` to the imports (keep alphabetical order: after `from collections.abc import Mapping, Sequence`). Then replace lines 27–43 (from `STUDY_ID = ...` through `RENDER_COMMAND = ...`) with:

```python
STUDY_ID = "sba-annual-report-structural-comparison"
SUCCESSOR_STUDY_ID = "sba-annual-report-structural-comparison-release"
# Every profile renders the same frozen result artifacts from the released study folder.
STUDY_DIRECTORY = Path("studies") / STUDY_ID
COMPARISON_REFERENCE = (STUDY_DIRECTORY / "results/count-comparison.csv").as_posix()
STUDY_MANIFEST_REFERENCE = (STUDY_DIRECTORY / "study.yaml").as_posix()
SOURCE_MANIFEST_REFERENCE = (STUDY_DIRECTORY / "source-manifest.json").as_posix()
RUN_DIAGNOSTICS_REFERENCE = (
    STUDY_DIRECTORY / "validation/confirmatory/run-diagnostics.json"
).as_posix()
SIDECAR_REFERENCE = (STUDY_DIRECTORY / "release/public-result.json").as_posix()
MARKDOWN_REFERENCE = "docs/public/sba-structural-comparison.md"
RELEASE_STATUS = "Validated, not citable"
PREPARED_FOR = (
    "SBIR program managers and policy analysts in Treasury, OMB, JCT, "
    "and state economic-development offices"
)
REPRODUCTION_COMMAND = "make reproduce-sba-structural"
RENDER_COMMAND = "uv run python scripts/data/render_sba_structural_comparison.py"


@dataclass(frozen=True)
class StudyProfile:
    """The pieces of the public page that differ between the released study and a successor.

    The result artifacts, expected counts, and validation checks do not vary. A profile
    only changes where the manifest, sidecar, and page live and how the status is worded.
    """

    study_id: str
    manifest_reference: str
    sidecar_reference: str
    markdown_reference: str
    release_status: str
    claim_prefix: str
    claim_suffix: str
    status_lines: tuple[str, ...]
    release_heading: str
    reproduction_command: str


PROFILES: dict[str, StudyProfile] = {
    STUDY_ID: StudyProfile(
        study_id=STUDY_ID,
        manifest_reference=STUDY_MANIFEST_REFERENCE,
        sidecar_reference=SIDECAR_REFERENCE,
        markdown_reference=MARKDOWN_REFERENCE,
        release_status=RELEASE_STATUS,
        claim_prefix="Validated, not citable: ",
        claim_suffix=" This statement is not citable until",
        status_lines=(
            "This page reports a validated current-vintage structural comparison. The release",
            "gates are still closed. Do not quote this result as a released finding.",
        ),
        release_heading="## Release gates still open",
        reproduction_command=REPRODUCTION_COMMAND,
    ),
    SUCCESSOR_STUDY_ID: StudyProfile(
        study_id=SUCCESSOR_STUDY_ID,
        manifest_reference=f"studies/{SUCCESSOR_STUDY_ID}/study.yaml",
        sidecar_reference=f"studies/{SUCCESSOR_STUDY_ID}/release/public-result.json",
        markdown_reference="docs/public/sba-structural-comparison-release.md",
        release_status="Validated; release pending",
        claim_prefix="Validated: ",
        claim_suffix=" Cite this statement only from",
        status_lines=(
            "This page reports the same validated structural comparison that release v0.18.0",
            "froze. Nothing was re-analysed. Under the repository citation rule, a validated",
            "result may be cited from an immutable release with its evidence status attached.",
            "No release binds this study yet, so there is nothing to cite yet. The result is",
            "validated. It is not approved evidence.",
        ),
        release_heading="## Release pending",
        reproduction_command=f"{REPRODUCTION_COMMAND} SBA_STUDY_ID={SUCCESSOR_STUDY_ID}",
    ),
}


def _profile_for(study_id: object) -> StudyProfile:
    profile = PROFILES.get(study_id) if isinstance(study_id, str) else None
    if profile is None:
        raise PublicResultError(f"no renderer profile for study_id {study_id!r}")
    return profile
```

`PublicResultError` is defined at line 177, after these constants. Python resolves the name at call time, so the forward reference is fine.

- [ ] **Step 4: Thread the profile through claim parsing and manifest validation**

Replace the head of `_bounded_claim` (lines 423–431):

```python
def _bounded_claim(manifest: StudyManifest, profile: StudyProfile) -> str:
    if len(manifest.permitted_claims) != 2:
        raise PublicResultError("study manifest must contain two permitted result claims")
    source = manifest.permitted_claims[0]
    prefix = profile.claim_prefix
    suffix = profile.claim_suffix
    if not source.startswith(prefix) or suffix not in source:
        raise PublicResultError(
            f"study permitted claim does not match the {profile.study_id} release form"
        )
    claim = source.removeprefix(prefix).split(suffix, 1)[0]
```

The rest of the function is unchanged.

Replace the head and tail of `_validate_manifest` (lines 503–529):

```python
def _validate_manifest(manifest: StudyManifest, profile: StudyProfile) -> None:
    if manifest.study_id != profile.study_id:
        raise PublicResultError(f"unexpected study_id: {manifest.study_id!r}")
```

(the middle checks are unchanged) and the last two lines become:

```python
    _bounded_claim(manifest, profile)
    _summary_claim(manifest)
```

- [ ] **Step 5: Thread the profile through payload build and validation**

Replace the signature and first lines of `build_payload` (lines 607–624):

```python
def build_payload(
    repository_root: Path = REPOSITORY_ROOT,
    *,
    study_id: str = STUDY_ID,
    comparison_path: Path | None = None,
    study_manifest_path: Path | None = None,
    source_manifest_path: Path | None = None,
    run_diagnostics_path: Path | None = None,
) -> dict[str, Any]:
    """Build the public sidecar for one study profile from the declared study inputs."""

    profile = _profile_for(study_id)
    root = repository_root.resolve()
    comparison_path = comparison_path or root / COMPARISON_REFERENCE
    study_manifest_path = study_manifest_path or root / profile.manifest_reference
    source_manifest_path = source_manifest_path or root / SOURCE_MANIFEST_REFERENCE
    run_diagnostics_path = run_diagnostics_path or root / RUN_DIAGNOSTICS_REFERENCE
    manifest = load_study_manifest(study_manifest_path)
    _validate_manifest(manifest, profile)
```

In the `content` dict inside `build_payload`, change two values:

```python
        "release_status": profile.release_status,
        ...
        "bounded_claim": _bounded_claim(manifest, profile),
        ...
        "reproduction": {
            "setup_command": "make install-core",
            "one_command": profile.reproduction_command,
            "renderer_command": RENDER_COMMAND,
        },
```

In `_validate_payload`, replace the block at lines 753–758:

```python
    profile = _profile_for(content["study_id"])
    if (
        content["release_status"] != profile.release_status
        or content["prepared_for"] != PREPARED_FOR
    ):
        raise PublicResultError("public sidecar has the wrong study or release status")
```

- [ ] **Step 6: Thread the profile through the page**

In `render_markdown`, after `content = _validate_payload(payload)` add `profile = _profile_for(content["study_id"])`. Replace the two literal status lines (lines 875–876):

```python
        f"> **Status: {content['release_status']}.**",
        "",
        *profile.status_lines,
        "",
        "## Bounded claim",
```

Replace the literal heading at line 1002:

```python
            profile.release_heading,
```

- [ ] **Step 7: Thread the profile through artifact generation and the CLI**

```python
def generate_public_artifacts(
    repository_root: Path = REPOSITORY_ROOT,
    *,
    study_id: str = STUDY_ID,
    sidecar_path: Path | None = None,
    markdown_path: Path | None = None,
) -> tuple[Path, Path]:
    """Regenerate the sidecar and page together after all checks pass."""

    profile = _profile_for(study_id)
    root = repository_root.resolve()
    payload = build_payload(root, study_id=study_id)
    sidecar_path = sidecar_path or root / profile.sidecar_reference
    markdown_path = markdown_path or root / profile.markdown_reference
```

(the rest is unchanged), and:

```python
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--study-id", choices=sorted(PROFILES), default=STUDY_ID)
    parser.add_argument("--sidecar", type=Path)
    parser.add_argument("--markdown", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    sidecar_path, markdown_path = generate_public_artifacts(
        args.repository_root,
        study_id=args.study_id,
        sidecar_path=args.sidecar,
        markdown_path=args.markdown,
    )
```

- [ ] **Step 8: Run the whole renderer test file and the round-trip guard**

```bash
uv run pytest tests/unit/scripts/test_render_sba_structural_comparison.py -q
uv run python scripts/ci/check_study_artifact_roundtrip.py
uv run ruff check scripts/data/render_sba_structural_comparison.py tests/unit/scripts/test_render_sba_structural_comparison.py
uv run ruff format --check scripts/data/render_sba_structural_comparison.py
```

Expected: all tests pass, including `test_committed_public_artifacts_regenerate_byte_for_byte`, which proves the default output is unchanged. The round-trip guard prints `1 registered pair(s)`.

- [ ] **Step 9: Commit**

```bash
git add scripts/data/render_sba_structural_comparison.py tests/unit/scripts/test_render_sba_structural_comparison.py
git commit -m "feat(sba-structural): select the public page wording by study profile

The default profile reproduces the v0.18.0 sidecar and page byte for byte.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Parameterise the public reproduction command

`reproduce_sba_structural_comparison.py` verifies the count stage, the confirmatory seal, and the public artifacts. It must pin against the chosen study's manifest, otherwise the successor's advertised reproduction command fails in its own release checkout.

**Files:**
- Modify: `scripts/data/reproduce_sba_structural_comparison.py:28-34` (imports), `:123-135`, `:200-215`, `:227-248`
- Modify: `Makefile:152-155`
- Test: `tests/unit/scripts/test_reproduce_sba_structural_comparison.py`

**Interfaces:**
- Consumes: `PROFILES`, `STUDY_ID`, `_profile_for` from Task 3; `build_production_inputs(..., study_manifest_path=...)` from Task 2.
- Produces: `reproduce(repository_root, source_root, *, acquire: bool, study_id: str = STUDY_ID) -> ReproductionRecord`; CLI flag `--study-id`; Make variable `SBA_STUDY_ID` (default: the released study).

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/scripts/test_reproduce_sba_structural_comparison.py`:

```python
def test_reproduce_rejects_an_unknown_study_before_touching_sources(tmp_path: Path) -> None:
    from scripts.data.render_sba_structural_comparison import PublicResultError

    with pytest.raises(PublicResultError, match="no renderer profile"):
        reproduction.reproduce(tmp_path, tmp_path, acquire=False, study_id="no-such-study")
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run pytest tests/unit/scripts/test_reproduce_sba_structural_comparison.py -q
```

Expected: FAIL with `TypeError: reproduce() got an unexpected keyword argument 'study_id'`.

- [ ] **Step 3: Implement**

Change the renderer import block to:

```python
from scripts.data.render_sba_structural_comparison import (
    STUDY_ID,
    _profile_for,
    build_payload,
    render_markdown,
    serialize_payload,
)
```

and drop `MARKDOWN_REFERENCE` and `SIDECAR_REFERENCE` from that import. In the count-stage import keep `SOURCE_MANIFEST` and `build_production_inputs`; drop `STUDY_MANIFEST` if nothing else in the file uses it (check with `grep -n STUDY_MANIFEST`).

Change `reproduce`:

```python
def reproduce(
    repository_root: Path,
    source_root: Path,
    *,
    acquire: bool,
    study_id: str = STUDY_ID,
) -> ReproductionRecord:
    """Acquire sources when requested and verify every released count value."""

    profile = _profile_for(study_id)
    repository_root = repository_root.resolve()
    source_root = source_root.resolve()
    source_manifest = repository_root / SOURCE_MANIFEST
    study_manifest_path = repository_root / profile.manifest_reference
    if acquire:
        acquire_sources(source_manifest, source_root)

    inputs = build_production_inputs(
        repository_root, source_root, study_manifest_path=study_manifest_path
    )
```

Further down, replace the public-artifact block:

```python
    public_sidecar = repository_root / profile.sidecar_reference
    public_markdown = repository_root / profile.markdown_reference
    for label, path in (
        ("public result sidecar", public_sidecar),
        ("public result Markdown", public_markdown),
    ):
        if not path.is_file():
            raise ReproductionFailure(f"{label} is missing: {path}")
    payload = build_payload(repository_root, study_id=study_id)
    if serialize_payload(payload).encode("utf-8") != public_sidecar.read_bytes():
        raise ReproductionFailure("public result sidecar does not reproduce byte-for-byte")
    if render_markdown(payload).encode("utf-8") != public_markdown.read_bytes():
        raise ReproductionFailure("public result Markdown does not reproduce byte-for-byte")
    public_sidecar_sha256 = file_sha256(public_sidecar)
    public_markdown_sha256 = file_sha256(public_markdown)
    if public_sidecar_sha256 != _frozen_sha256(study_manifest_path, profile.sidecar_reference):
        raise ReproductionFailure("public result sidecar does not match its frozen digest")
    if public_markdown_sha256 != _frozen_sha256(
        study_manifest_path, profile.markdown_reference
    ):
        raise ReproductionFailure("public result Markdown does not match its frozen digest")
```

CLI:

```python
    parser.add_argument(
        "--study-id",
        default=STUDY_ID,
        help="Study profile to reproduce (default: the released study).",
    )
```

and in `main()` pass `study_id=args.study_id` to `reproduce(...)`.

Makefile target:

```make
SBA_STUDY_ID ?= sba-annual-report-structural-comparison

.PHONY: reproduce-sba-structural
reproduce-sba-structural: ## Reproduce the bounded SBA count comparison (SBA_STUDY_ID selects the study)
	@$(call info,Reproducing the SBA annual-report structural comparison for $(SBA_STUDY_ID))
	$(call run,PYTHONPATH="$(CURDIR):$(CURDIR)/packages/sbir-analytics" uv run --no-sync python scripts/data/reproduce_sba_structural_comparison.py --study-id $(SBA_STUDY_ID))
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/unit/scripts/test_reproduce_sba_structural_comparison.py tests/unit/scripts/test_render_sba_structural_comparison.py -q
uv run ruff check scripts/data/reproduce_sba_structural_comparison.py
make -n reproduce-sba-structural | grep -- '--study-id sba-annual-report-structural-comparison$'
```

Expected: all pass; the dry-run prints the default study ID.

- [ ] **Step 5: Commit**

```bash
git add scripts/data/reproduce_sba_structural_comparison.py tests/unit/scripts/test_reproduce_sba_structural_comparison.py Makefile
git commit -m "feat(sba-structural): reproduce a chosen study profile

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

All code that the successor manifest will pin is now final. Do not edit `render_sba_structural_comparison.py`, `reproduce_sba_structural_comparison.py`, `run_sba_structural_comparison.py`, `producer.py`, or `uv.lock` after this point without repeating Tasks 5 through 9.

---

### Task 5: Successor manifest at `reproducible` and the count-stage replay at HEAD

**Files:**
- Create: `studies/sba-annual-report-structural-comparison-release/study.yaml`
- Create: `studies/sba-annual-report-structural-comparison-release/amendments.md`

**Interfaces:**
- Produces: a manifest that `validate_study_manifests.py` accepts at HEAD and that the count stage can pin against.

- [ ] **Step 1: Copy the v0.18.0 manifest**

```bash
SID=sba-annual-report-structural-comparison-release
mkdir -p studies/$SID/release studies/$SID/reviews
cp studies/sba-annual-report-structural-comparison/study.yaml studies/$SID/study.yaml
```

- [ ] **Step 2: Edit the identity, status, gate, and claim fields**

In `studies/$SID/study.yaml`:

1. `study_id: sba-annual-report-structural-comparison-release`
2. `evidence_status: reproducible`
3. Leave `title`, `research_questions`, `estimand`, `implementation`, `identity_policy`, `limitations`, `validation_design`, and `validation_result` exactly as copied.
4. Replace the `materialization` block:

```yaml
materialization:
  allowed: false
  blockers:
    - >-
      No annotated release tag binds this study in studies/releases.yaml.
      Until one does, there is no immutable object to cite.
    - >-
      The published-sample reproduction blocker is permanent. The
      publication-era SBIR.gov export is unavailable, so no study in this
      repository can reproduce the counts the SBA tables were computed from.
      This study compares the printed counts with a current-vintage export.
```

5. Replace only the first entry of `permitted_claims` (keep the second entry byte-identical):

```yaml
permitted_claims:
  - >-
    Validated: for all 632 award-count cells printed in FY2020
    Table 18, FY2021 Table 18, and FY2022 Table 20, this study reports the
    differences between those published counts and counts computed from the
    pinned September 17, 2026 SBIR.gov export under EXPORT_ROW_V1,
    AWARD_YEAR_FIELD_V1, and the frozen program, phase, and jurisdiction rules.
    A separate blinded-role implementation reproduced 1,264 of 1,264 count
    operands. The recorded interval is [1.0, 1.0] using the method: exact
    complete-population point interval; no sampling. Cite this statement only from
    an immutable release that binds this study, with the evidence status
    validated attached. No such release exists yet.
```

6. Remove the two trailing `frozen_artifacts` entries for `studies/sba-annual-report-structural-comparison/release/public-result.json` and `docs/public/sba-structural-comparison.md`. The successor pins its own sidecar and page in Task 6.

- [ ] **Step 3: Re-pin the files that changed at HEAD**

```bash
SID=sba-annual-report-structural-comparison-release
NEW=studies/$SID/study.yaml
for p in \
  packages/sbir-analytics/sbir_analytics/assets/sba_annual_report_structural_comparison/producer.py \
  uv.lock \
  scripts/data/render_sba_structural_comparison.py \
  scripts/data/reproduce_sba_structural_comparison.py \
  scripts/data/run_sba_structural_comparison.py; do
  h=$(shasum -a 256 "$p" | cut -d' ' -f1)
  uv run python - "$NEW" "$p" "$h" <<'REPIN'
import pathlib, re, sys
manifest, path, sha = sys.argv[1:]
text = pathlib.Path(manifest).read_text(encoding="utf-8")
pattern = re.compile(rf"(  - path: {re.escape(path)}\n    sha256: )[0-9a-f]{{64}}")
new, count = pattern.subn(lambda m: m.group(1) + sha, text)
assert count == 1, (path, count)
pathlib.Path(manifest).write_text(new, encoding="utf-8")
REPIN
done
uv run python scripts/ci/validate_study_manifests.py
```

Expected: `validate_study_manifests.py` exits 0 and reports one more manifest than before. If it reports a hash mismatch for any path other than the five above, that path also changed since v0.18.0; add it to the loop, and record it in the amendments file in Step 6.

- [ ] **Step 4: Acquire the pinned sources and run the count stage at HEAD**

This downloads the 394,636,989-byte award export and verifies all four sources against the pinned hashes. All four URLs answered from this machine on 2026-09-26.

```bash
export PYTHONPATH="$PWD:$PWD/packages/sbir-analytics"
uv run --no-sync python - <<'ACQ'
from pathlib import Path
from scripts.data.acquire_sba_structural_sources import acquire_sources
acquire_sources(
    Path("studies/sba-annual-report-structural-comparison/source-manifest.json"),
    Path("."),
)
ACQ
SID=sba-annual-report-structural-comparison-release
uv run --no-sync python scripts/data/run_sba_structural_comparison.py \
  --study-manifest studies/$SID/study.yaml \
  --output "$TMPDIR/count-comparison-head.csv"
cmp "$TMPDIR/count-comparison-head.csv" \
    studies/sba-annual-report-structural-comparison/results/count-comparison.csv \
  && echo "REPLAY CLEAN" || echo "REPLAY DIFFERS"
```

Expected: `Wrote 632 frozen count cells ... Dropped 1 retained rows with blank State.` then `REPLAY CLEAN`.

**If it prints `REPLAY DIFFERS`, stop.** Commit the manifest at `reproducible`, write the amendments entry in Step 6 with the differing byte offsets from `cmp -l | head`, and report. Do not do Tasks 6 through 10.

- [ ] **Step 5: Record `validated`**

Only after `REPLAY CLEAN`:

```bash
sed -i '' 's/^evidence_status: reproducible$/evidence_status: validated/' studies/$SID/study.yaml
uv run python scripts/ci/validate_study_manifests.py
```

Expected: exit 0.

- [ ] **Step 6: Start the successor's amendment record**

Create `studies/$SID/amendments.md`:

```markdown
# SBA Structural Comparison Release Study — Freeze and Amendment Record

This study is the successor product authorized by Revision 4 of
`specs/sba-annual-report-approved-evidence-release/amendments.md`. It carries
the `v0.18.0` result of `studies/sba-annual-report-structural-comparison`
under the citation rule from #792. Nothing is re-analysed.

## Revision 0 — 2026-09-26 — manifest created and replay at HEAD

**Status:** `validated`. Not approved evidence. Release pending.

The manifest pins the same result artifacts as `v0.18.0` by path and hash:
`results/count-comparison.csv`
`e86ab66905f65adaa7fdb721ced6bcbc7b3991a288ba37156f1efe9b4bed7381`, the
confirmatory validation values, the sealed components, and the reviews. It
re-pins five files at their HEAD hashes because they changed after `v0.18.0`:
`producer.py` (rename of `citable` to `approved`, no count logic change),
`uv.lock`, and the three study scripts that now take a study parameter.

The count stage ran at HEAD against this manifest with the four pinned
sources. It reproduced `results/count-comparison.csv` byte for byte. On that
basis the manifest records `validated`, restating the `v0.18.0` result of
1,264 of 1,264 operands with interval `[1.0, 1.0]`.

The manifest does not record `approved` and carries no `claim_approval`.
```

- [ ] **Step 7: Commit**

```bash
git add studies/$SID/study.yaml studies/$SID/amendments.md
git commit -m "studies(sba-structural-release): successor manifest pinned at HEAD, replay clean

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Render the successor sidecar and page, then pin them

**Files:**
- Create (generated): `studies/sba-annual-report-structural-comparison-release/release/public-result.json`
- Create (generated): `docs/public/sba-structural-comparison-release.md`
- Modify: `studies/sba-annual-report-structural-comparison-release/study.yaml` (append two `frozen_artifacts` entries)

**Interfaces:**
- Consumes: `generate_public_artifacts(root, study_id=SUCCESSOR_STUDY_ID)` from Task 3.

- [ ] **Step 1: Render**

```bash
SID=sba-annual-report-structural-comparison-release
PYTHONPATH="$PWD:$PWD/packages/sbir-analytics" uv run --no-sync python \
  scripts/data/render_sba_structural_comparison.py --study-id $SID
```

Expected: `Wrote .../studies/$SID/release/public-result.json and .../docs/public/sba-structural-comparison-release.md.`

- [ ] **Step 2: Read the page and check the forbidden statements**

```bash
grep -nE 'approved|not citable|Do not quote|new result|was wrong|Release gates still open' docs/public/sba-structural-comparison-release.md
```

Expected: the only `approved` hit is the status line "It is not approved evidence." No other hits. Read the whole page once as the declared reader would.

- [ ] **Step 3: Pin the generated pair in the manifest**

Append to `frozen_artifacts` in `studies/$SID/study.yaml`:

```bash
for p in studies/$SID/release/public-result.json docs/public/sba-structural-comparison-release.md; do
  printf '  - path: %s\n    sha256: %s\n' "$p" "$(shasum -a 256 "$p" | cut -d' ' -f1)"
done
```

Insert those four lines as the last two entries of `frozen_artifacts` (before `implementation:`). Then confirm the render is stable:

```bash
PYTHONPATH="$PWD:$PWD/packages/sbir-analytics" uv run --no-sync python \
  scripts/data/render_sba_structural_comparison.py --study-id $SID
git status --short docs/public studies/$SID
uv run python scripts/ci/validate_study_manifests.py
```

Expected: the second render changes no bytes (the manifest is not an input to the sidecar); the validator exits 0.

- [ ] **Step 4: Commit**

```bash
git add studies/$SID docs/public/sba-structural-comparison-release.md
git commit -m "studies(sba-structural-release): generate and pin the public sidecar and page

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Round-trip registration and successor tests

**Files:**
- Modify: `scripts/ci/check_study_artifact_roundtrip.py:64-70`
- Modify: `tests/unit/scripts/test_render_sba_structural_comparison.py` (`test_registry_names_the_public_result_pair`, plus new tests)

- [ ] **Step 1: Write the failing tests**

Replace `test_registry_names_the_public_result_pair` with:

```python
def test_registry_names_both_public_result_pairs() -> None:
    matching = [
        pair
        for pair in roundtrip.REGISTERED_PAIRS
        if pair.renderer_path == "scripts/data/render_sba_structural_comparison.py"
    ]
    successor = renderer.PROFILES[renderer.SUCCESSOR_STUDY_ID]

    assert matching == [
        roundtrip.RoundTripPair(
            markdown=renderer.MARKDOWN_REFERENCE,
            sidecar=renderer.SIDECAR_REFERENCE,
            renderer="scripts/data/render_sba_structural_comparison.py:render_markdown",
        ),
        roundtrip.RoundTripPair(
            markdown=successor.markdown_reference,
            sidecar=successor.sidecar_reference,
            renderer="scripts/data/render_sba_structural_comparison.py:render_markdown",
        ),
    ]
```

Append:

```python
SUCCESSOR = renderer.PROFILES[renderer.SUCCESSOR_STUDY_ID]
SUCCESSOR_SIDECAR = ROOT / SUCCESSOR.sidecar_reference
SUCCESSOR_MARKDOWN = ROOT / SUCCESSOR.markdown_reference


def test_successor_artifacts_regenerate_byte_for_byte_at_head(
    reviewed_release_root: Path,
) -> None:
    payload = renderer.build_payload(ROOT, study_id=renderer.SUCCESSOR_STUDY_ID)
    released = renderer.build_payload(reviewed_release_root)

    assert renderer.serialize_payload(payload) == SUCCESSOR_SIDECAR.read_text(encoding="utf-8")
    assert renderer.render_markdown(payload) == SUCCESSOR_MARKDOWN.read_text(encoding="utf-8")
    assert payload["content"]["release_status"] == "Validated; release pending"
    assert payload["content"]["study_id"] == renderer.SUCCESSOR_STUDY_ID
    # Same result, same validation, same non-claims as v0.18.0.
    assert payload["content"]["comparison"] == released["content"]["comparison"]
    assert payload["content"]["validation"] == released["content"]["validation"]
    assert payload["content"]["non_claims"] == released["content"]["non_claims"]
    assert payload["content"]["result_summary_claim"] == released["content"]["result_summary_claim"]
    assert payload["content"]["bounded_claim"] == released["content"]["bounded_claim"]


def test_successor_page_states_the_citation_rule_and_the_permanent_blocker() -> None:
    markdown = SUCCESSOR_MARKDOWN.read_text(encoding="utf-8")

    assert "> **Status: Validated; release pending.**" in markdown
    assert "may be cited as a validated result from that immutable release" in markdown
    assert "## Release pending" in markdown
    assert "published-sample reproduction blocker is permanent" in markdown
    assert "make reproduce-sba-structural SBA_STUDY_ID=" in markdown
    assert "Do not quote this result as a released finding" not in markdown
    assert "not citable" not in markdown
    assert "claim_approval" not in markdown
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/unit/scripts/test_render_sba_structural_comparison.py -q -k "registry or successor"
```

Expected: `test_registry_names_both_public_result_pairs` FAILS (one pair registered). The two successor tests pass already if Task 6 rendered correctly; if they fail, fix the page through the profile in Task 3, then repeat Tasks 5 Step 3 onward, because the renderer hash changed.

- [ ] **Step 3: Register the pair**

In `scripts/ci/check_study_artifact_roundtrip.py`, extend `REGISTERED_PAIRS`:

```python
REGISTERED_PAIRS: tuple[RoundTripPair, ...] = (
    RoundTripPair(
        markdown="docs/public/sba-structural-comparison.md",
        sidecar="studies/sba-annual-report-structural-comparison/release/public-result.json",
        renderer="scripts/data/render_sba_structural_comparison.py:render_markdown",
    ),
    RoundTripPair(
        markdown="docs/public/sba-structural-comparison-release.md",
        sidecar=(
            "studies/sba-annual-report-structural-comparison-release/release/public-result.json"
        ),
        renderer="scripts/data/render_sba_structural_comparison.py:render_markdown",
    ),
)
```

- [ ] **Step 4: Run the tests and the guard**

```bash
uv run pytest tests/unit/scripts/test_render_sba_structural_comparison.py tests/unit/scripts/test_study_artifact_roundtrip.py -q
uv run python scripts/ci/check_study_artifact_roundtrip.py
```

Expected: all pass; the guard prints `2 registered pair(s)`.

- [ ] **Step 5: Commit**

```bash
git add scripts/ci/check_study_artifact_roundtrip.py tests/unit/scripts/test_render_sba_structural_comparison.py
git commit -m "ci(sba-structural-release): register the successor round-trip pair

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: One-line links

The research-question guard requires the `### D1` section to link `studies/<study_id>/` for every study that lists `D1`, so the research-questions link is mandatory, not optional.

**Files:**
- Modify: `STATUS.md:16` (add one table row after it)
- Modify: `docs/public/reproducibility.md:53` (add one sentence)
- Modify: `docs/research-questions.md:872` (add one link)
- Modify: `CHANGELOG.md` under `## [Unreleased]` (one line)

- [ ] **Step 1: STATUS.md**

After the existing SBA row in the "Validated, not approved" table add:

```markdown
| [SBA annual-report structural comparison, release page](docs/public/sba-structural-comparison-release.md) | The same 1,264/1,264 result, restated under the citation rule; release pending | One final pinned review must approve the exact manifest claim boundary |
```

- [ ] **Step 2: docs/public/reproducibility.md**

After the last paragraph add:

```markdown
The [release page](sba-structural-comparison-release.md) restates the same
result under the citation rule. Reproduce it with
`make reproduce-sba-structural SBA_STUDY_ID=sba-annual-report-structural-comparison-release`.
```

- [ ] **Step 3: docs/research-questions.md**

Change the `Studies:` list in D1 so its last two entries read:

```markdown
  [prospective structural comparison](../studies/sba-annual-report-structural-comparison/study.yaml),
  [release page study](../studies/sba-annual-report-structural-comparison-release/study.yaml)*
```

- [ ] **Step 4: CHANGELOG.md**

Under `## [Unreleased]`, in the `### Added` section (create it after `### Breaking` if absent):

```markdown
- Successor study `sba-annual-report-structural-comparison-release` whose generated public page states the v0.18.0 result's status under the citation rule (#796).
```

- [ ] **Step 5: Run the guards**

```bash
uv run python scripts/ci/check_research_question_status.py
make lint-boundaries
```

Expected: exit 0 for both.

- [ ] **Step 6: Commit**

```bash
git add STATUS.md docs/public/reproducibility.md docs/research-questions.md CHANGELOG.md
git commit -m "docs: link the SBA structural-comparison release page

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Evidence audit and cold named-reader review of the exact bytes

Both reviews run as the repository agents defined in `.claude/agents/`. They are read-only. Their verdicts are written into the successor's `reviews/` folder, pinned in the manifest, and recorded in the successor's `amendments.md`. Neither authorizes a tag, `approved`, or a `Start-here` edit.

**Files:**
- Create: `studies/sba-annual-report-structural-comparison-release/reviews/successor-evidence-audit.md`
- Create: `studies/sba-annual-report-structural-comparison-release/reviews/named-reader-review-1.md`
- Modify: `studies/sba-annual-report-structural-comparison-release/study.yaml` (pin the two review files)
- Modify: `studies/sba-annual-report-structural-comparison-release/amendments.md` (Revision 1)

- [ ] **Step 1: Record the exact hashes under review**

```bash
SID=sba-annual-report-structural-comparison-release
git rev-parse HEAD
shasum -a 256 studies/$SID/study.yaml studies/$SID/release/public-result.json docs/public/sba-structural-comparison-release.md
uv run python -c "import json; print(json.load(open('studies/$SID/release/public-result.json'))['content_sha256'])"
```

- [ ] **Step 2: Run the evidence-auditor agent**

Dispatch the `evidence-auditor` agent with this prompt, filling in the hashes from Step 1:

> Audit the successor study `studies/sba-annual-report-structural-comparison-release/` at commit `<HEAD>` against the evidence-tier contract in `docs/steering/epistemic-tiers.md` and Revision 4 of `specs/sba-annual-report-approved-evidence-release/amendments.md`. The exact bytes under audit are `study.yaml` (`<sha>`), `release/public-result.json` (`<sha>`, content digest `<digest>`), and `docs/public/sba-structural-comparison-release.md` (`<sha>`). Confirm: (1) the manifest pins the same result artifacts as v0.18.0 by path and hash and re-pins only files changed at HEAD; (2) `validated` is supported by the recorded clean replay in `amendments.md` Revision 0; (3) no `approved` status, `claim_approval`, or claim beyond the manifest's bounded claims appears in the manifest, sidecar, or page; (4) the page repeats the permanent published-sample blocker and says its release is pending. Return `GO` or `NO-GO` with findings. You do not authorize a tag or approval.

- [ ] **Step 3: Write the audit record**

Create `studies/$SID/reviews/successor-evidence-audit.md` in the format of `studies/sba-annual-report-structural-comparison/reviews/revision-11-evidence-audit.md`: reviewer role, date, reviewed commit, verdict, the three exact hashes and content digest, then the agent's findings verbatim. Include the sentence: "This verdict does not authorize merge, tag, publication, materialization, citation, or `approved` promotion."

If the verdict is `NO-GO`, fix the cause. A fix that changes the renderer or the manifest's claim text changes the page bytes: repeat Task 5 Step 3 onward, then rerun this task from Step 1.

- [ ] **Step 4: Run the named-reader-reviewer agent**

Dispatch the `named-reader-reviewer` agent with this prompt:

> Review the exact bytes of `docs/public/sba-structural-comparison-release.md` at commit `<HEAD>` (`<sha>`). The declared reader is the page's "Prepared for" header. The page is a new outside-reader entry point for research question D1. Report the one sentence that reader would quote, whether it is licensed by the manifest's permitted claims in `studies/sba-annual-report-structural-comparison-release/study.yaml`, and whether the page could be read as saying the result is new, that v0.18.0 was wrong, that the published-sample blocker is resolved, or that the result is approved or already citable. Return `BRIEF` or a remediation list. You do not authorize citation or a Start-here edit.

- [ ] **Step 5: Write the reader review record**

Create `studies/$SID/reviews/named-reader-review-1.md` in the format of `studies/sba-annual-report-structural-comparison/reviews/named-reader-review-6.md`: reviewer role, date, reviewed commit, verdict, declared reader, quotable sentence, findings verbatim. Same non-authorization sentence as Step 3.

If remediation is required, apply it through the profile in Task 3 or the manifest claim text, then repeat Task 5 Step 3 onward and both reviews.

- [ ] **Step 6: Pin the review records and record Revision 1**

```bash
for p in studies/$SID/reviews/successor-evidence-audit.md studies/$SID/reviews/named-reader-review-1.md; do
  printf '  - path: %s\n    sha256: %s\n' "$p" "$(shasum -a 256 "$p" | cut -d' ' -f1)"
done
```

Append those entries to `frozen_artifacts` in `studies/$SID/study.yaml`. Then append to `studies/$SID/amendments.md`:

```markdown

## Revision 1 — <date> — exact-byte reviews recorded

The evidence audit of `study.yaml`, `release/public-result.json`, and
`docs/public/sba-structural-comparison-release.md` at commit `<HEAD>`
returned `<GO>`; see `reviews/successor-evidence-audit.md`. The cold
named-reader review of the exact page bytes returned `<BRIEF>`; see
`reviews/named-reader-review-1.md`.

With both reviews recorded, the page's statement that the result may be
cited as `validated` from an immutable release is licensed under Revision 4
rule 4. No release binds this study yet. Neither review authorizes a tag,
`approved`, a `claim_approval` block, or a Start-here edit.
```

Confirm the sidecar and page did not change (review files are not renderer inputs):

```bash
PYTHONPATH="$PWD:$PWD/packages/sbir-analytics" uv run --no-sync python \
  scripts/data/render_sba_structural_comparison.py --study-id $SID
git status --short docs/public studies/$SID/release   # expected: empty
uv run python scripts/ci/validate_study_manifests.py
```

- [ ] **Step 7: Commit**

```bash
git add studies/$SID
git commit -m "studies(sba-structural-release): record the evidence audit and named-reader review

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: End-to-end replay, full checks, and the pull request

- [ ] **Step 1: Run the successor's advertised reproduction command**

```bash
make reproduce-sba-structural SBA_STUDY_ID=sba-annual-report-structural-comparison-release
```

Expected: `Verified 632 comparison cells (e86ab669...). Verified 1264 confirmatory values (...) and 8 sealed components. Verified public sidecar (...) and Markdown (...).` and exit 0. This proves the successor reproduces end to end at HEAD with HEAD hashes.

- [ ] **Step 2: Confirm the released study is untouched**

```bash
git diff --stat v0.18.0 HEAD -- studies/sba-annual-report-structural-comparison docs/public/sba-structural-comparison.md
```

Expected: no output.

- [ ] **Step 3: Full local CI analog**

```bash
make ci-local
```

Expected: exit 0. Fix only what the run reports; if a fix touches a pinned file, repeat Task 5 Step 3 onward.

- [ ] **Step 4: Open the pull request**

```bash
git push -u origin studies/sba-structural-comparison-successor
gh pr create --title "studies: successor SBA structural-comparison study under the citation rule" --body "$(cat <<'BODY'
Closes #796.

## What

- Spec Revision 4 authorizes a successor descriptive product (design.md "Gate reconciliation").
- New study `studies/sba-annual-report-structural-comparison-release/` pins the same v0.18.0 result artifacts by path and hash. It re-pins `producer.py`, `uv.lock`, and the three study scripts at HEAD.
- The renderer selects wording by study profile; the default output is byte-identical to v0.18.0 (existing byte-for-byte test and round-trip pair still pass).
- The count stage and reproduce command take a study parameter so a replay at HEAD can pin against HEAD hashes. `make reproduce-sba-structural` is unchanged by default; `SBA_STUDY_ID=` selects the successor.
- Generated `docs/public/sba-structural-comparison-release.md` says: validated, same result as v0.18.0, may be cited from an immutable release with its status attached, no release yet, not approved, published-sample blocker permanent.
- Evidence audit and cold named-reader review of the exact bytes are recorded in the successor's `amendments.md`.

## Not in this PR

- No tag and no `studies/releases.yaml` binding. That is a separate change; next version is 0.20.0 because #792 was breaking.
- No `approved` status and no `claim_approval`.
- `studies/sba-annual-report-structural-comparison/` and `docs/public/sba-structural-comparison.md` are byte-identical to v0.18.0.

## Verification

- Count-stage replay at HEAD reproduced `results/count-comparison.csv` byte for byte (amendments.md Revision 0).
- `make reproduce-sba-structural SBA_STUDY_ID=sba-annual-report-structural-comparison-release` exits 0.
- `make ci-local` exits 0.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
BODY
)"
```

- [ ] **Step 5: Report**

State plainly: which tasks completed, the replay verdict, both review verdicts, and that the tag and release binding remain to be done in a separate change.

---

## Self-review against issue #796

| Issue item | Task |
|---|---|
| 1 Spec amendment first | Task 1 |
| 2 Clean replay at HEAD; stop on any byte difference | Task 5 Step 4 (count stage), Task 10 Step 1 (end to end) |
| 3 New study folder, same result pins, HEAD re-pins, same `validation_result` | Task 5 |
| 4 Parameterise the renderer, do not copy it; default byte-identical | Task 3 |
| 5 New sidecar and page, generated only | Task 6 |
| 6 `REGISTERED_PAIRS` entry plus renderer-parameter test | Task 7 (and Task 3 tests) |
| 7 One-line links only | Task 8 |
| 8 Evidence audit and named-reader review before "may be cited" | Task 9 |
| 9 Tag and binding later, page says release pending | Out of scope; profile wording in Task 3 |
| Must-not-claim list | Global Constraints; Task 6 Step 2 grep; Task 7 page test |
| Do-not-touch list | Task 10 Step 2 |
| Network blocker | Not present locally; Task 5 Step 4 downloads |

Deviations from the issue's literal list, and why:

- Task 2 and Task 4 parameterise the count stage and reproduce command. The issue lists only the renderer. Without them the replay at HEAD cannot run, because the count producer verifies the `producer.py` hash against the manifest it is given and the v0.18.0 pin no longer matches, and the successor's advertised reproduction command would fail in its own release checkout.
- Task 8 edits `docs/research-questions.md` D1 with one link. The issue allows a link there, and `check_research_question_status.py` requires it.
- Task 8 adds one CHANGELOG line, per the repository release policy.

Known fragility: the successor manifest pins `uv.lock` at HEAD. Any dependency bump breaks `validate_study_manifests.py` and the successor byte-for-byte test until the manifest is re-pinned and the page re-rendered, which is new claim-facing bytes. The v0.18.0 study had the same property before its tag. The cure is the separate tag-and-bind change in issue step 9, done promptly after merge.

---

## Outcome (recorded 2026-09-27)

The plan was executed on 2026-09-26 as PR #801. Two rulings made during
execution were reversed by the owner in commit 06cd333a:

- The page now says "Successor release pending" literally, with the qualifier
  "no release is scheduled". The plan's substance-over-letter reading of
  Revision 4 rule 5 was dropped.
- The two review records Task 9 created were removed. Spec Revision 4 rule 4
  was rewritten: a wording-only successor relies on the clean replay and the
  round-trip guards and does not carry its own evidence-audit or named-reader
  gate. The single pinned claim-boundary review remains the `approved` gate.
  The reviews still ran during execution; the cold named-reader review found
  a reproduce instruction that could not work, and that finding shaped the
  page's wording.

Other deviations from this plan as written: `StudyProfile` has thirteen
fields, not ten (`renderer_command`, `reproduction_lines`, `release_limits`
were added); release limits come from the profile, not from
`materialization.blockers`; `Makefile` is pinned in the successor manifest; the
round-trip loader registers renderers in `sys.modules`. Eight HEAD files are
pinned until the successor is tag-bound (issue step 9, version 0.20.0).
