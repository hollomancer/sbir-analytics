# Release 0.20.0 and Successor Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut release v0.20.0 and bind the successor study `sba-annual-report-structural-comparison-release` to it in `studies/releases.yaml`, so its page is citable from an immutable release and its manifest stops pinning HEAD files.

**Architecture:** Three sequential deliveries. (1) A release-preparation PR: version bump to 0.20.0, CHANGELOG section, the successor re-frozen with binding-proof wording and a checksum inventory. (2) The annotated tag `v0.20.0` on the merged commit, which the release workflow publishes. (3) A binding PR that adds the `studies/releases.yaml` entry, which CI validates by extracting the tag tree. The order is forced: the binding validator resolves the tag, the tag must contain the inventory, and the inventory must hash the version-bumped `uv.lock`.

**Tech Stack:** `uv`, `gh`, git annotated tags, `scripts/ci/check_versioning.py`, `scripts/ci/validate_study_manifests.py` with `scripts/ci/released_studies.py`, `.github/workflows/release.yml`.

**Spec:** Issue #796 step 9; `docs/steering/versioning.md` (release checklist); `specs/sba-annual-report-approved-evidence-release/amendments.md` Revision 4 (rules 4 to 6); `studies/releases.yaml` schema as enforced by `scripts/ci/released_studies.py`.

## Global Constraints

- Version 0.20.0. Minor, because the unreleased section carries two breaking changes (#792 status rename, #800 code removal) and this repo is below 1.0.0. Every version source must match: root and two package `pyproject.toml`, `uv.lock` (three local packages), `sbir_etl/__init__.py`, `config/base.yaml` `pipeline.version`, and `CITATION.cff`.
- `studies/sba-annual-report-structural-comparison/` and `docs/public/sba-structural-comparison.md` stay byte-identical to v0.18.0. CI enforces it.
- After binding, `studies/sba-annual-report-structural-comparison-release/` becomes byte-frozen forever (`verify_current_release_subtree`). Every byte in that folder, including `README.md` and `amendments.md`, must be worded so it stays true after the tag exists. Task 3 does this.
- Generated files (`release/public-result.json`, the public page) are never hand-edited. Regenerate both with `scripts/data/render_sba_structural_comparison.py --study-id sba-annual-report-structural-comparison-release`.
- The successor manifest pins `uv.lock` and the renderer, both of which change in this plan. Order inside the release PR: bump versions and run `uv lock` (Task 1) → edit the renderer profile (Task 3) → re-pin `uv.lock` and the renderer → render → re-pin sidecar and page → write the amendment → re-pin `amendments.md` last → build the inventory last of all (Task 4). Any later edit to a pinned file restarts from the re-pin.
- Binding fields (`released_studies.py`): `tag`, `source_revision` (full 40-hex commit SHA the tag points to), `tree_oid` (full 40-hex tree of that commit), `checksum_manifest` (a path inside the tag tree), optional `checksum_errata`. The tag must be annotated.
- Inventory line format: `<sha256>  <repository-relative path>` (two spaces). No duplicates, no `..`, every path present in the tag tree.
- Merges on this repo are squash merges. The squash commit's tree is what gets tagged, so Task 6 re-verifies the inventory and pins against `main` before tagging. v0.18.0 needed a checksum erratum because this step was skipped.
- Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` (or the runtime's own attribution line if it names one).

## Decisions for the owner before Task 3

1. **Binding-proof wording (recommended: yes).** Rule 5 says the page must say its release is pending until a tag binds it. After binding the folder is frozen, so a dated status would become false forever, which is the v0.18.0 defect again. The plan amends rule 5 (Revision 5) so the page states the condition: "If no annotated tag binds this study in `studies/releases.yaml`, its release is pending; cite from v0.18.0." That sentence is true before and after binding and still contains the literal words. If you prefer to keep the current dated wording and accept a permanently stale sentence, skip Task 3 steps 2 to 4 and re-pin only `uv.lock`.
2. **Release scope.** v0.20.0 also releases #792 and #800. That is what the unreleased section already says; no change needed unless you want them separated.

---

### Task 0: Preconditions

**Files:** none.

- [ ] **Step 1: Clean main, fresh branch**

```bash
cd /Users/hollomancer/projects/sbir-analytics
git checkout main && git pull --ff-only origin main && git status --short | wc -l   # expected 0
git log --oneline -1   # expected 0674d1ac or newer
git checkout -b release/v0.20.0
```

- [ ] **Step 2: Baseline**

```bash
uv run python scripts/ci/validate_study_manifests.py
uv run python scripts/ci/check_study_artifact_roundtrip.py
uv run python scripts/ci/check_versioning.py
ls data/raw/sbir/award-export/2026-09-17/award_data.csv   # cached source; needed for the end-to-end replay in Task 3
```

Expected: all pass; the export is present.

---

### Task 1: Version bump to 0.20.0

**Files:**
- Modify: `pyproject.toml:3`, `packages/sbir-analytics/pyproject.toml:3`, `packages/sbir-ml/pyproject.toml:3`, `sbir_etl/__init__.py:9`, `config/base.yaml:7`, `CITATION.cff:18-23`, `uv.lock` (via `uv lock`)

- [ ] **Step 1: Edit the static sources**

```bash
sed -i '' 's/^version = "0.19.0"$/version = "0.20.0"/' pyproject.toml packages/sbir-analytics/pyproject.toml packages/sbir-ml/pyproject.toml
sed -i '' 's/^__version__ = "0.19.0"$/__version__ = "0.20.0"/' sbir_etl/__init__.py
sed -i '' 's/^  version: "0.19.0"$/  version: "0.20.0"/' config/base.yaml
sed -i '' -e 's/^version: 0.19.0$/version: 0.20.0/' -e 's|releases/tag/v0.19.0|releases/tag/v0.20.0|' -e 's/The immutable v0.19.0 release tag/The immutable v0.20.0 release tag/' CITATION.cff
grep -n 'date-released' CITATION.cff   # if present, set it to the tag date in Task 6, not now
```

- [ ] **Step 2: Lock and check**

```bash
uv lock
grep -c 'version = "0.20.0"' uv.lock          # expected 3 (sbir-etl, sbir-analytics, sbir-ml)
uv run python scripts/ci/check_versioning.py --tag v0.20.0
```

Expected: checker exit 0.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml packages/sbir-analytics/pyproject.toml packages/sbir-ml/pyproject.toml sbir_etl/__init__.py config/base.yaml CITATION.cff uv.lock
git commit -m "chore(release): bump version metadata to 0.20.0

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: CHANGELOG section

**Files:**
- Modify: `CHANGELOG.md:11-40`

- [ ] **Step 1: Promote the unreleased section**

Replace the line `## [Unreleased]` with:

```markdown
## [Unreleased]

## [0.20.0] — 2026-09-27
```

Use the actual tag date if Task 6 slips. Keep the `### Breaking`, `### Added`, `### Changed` blocks under 0.20.0 unchanged. Under `### Added` append one bullet:

```markdown
- Release checksum inventory for the successor study at
  `studies/sba-annual-report-structural-comparison-release/release/checksums.sha256`,
  so a later `studies/releases.yaml` binding can verify the tagged tree.
```

- [ ] **Step 2: Verify the workflow can read it**

The release workflow fails if the version's section is missing or empty. Check:

```bash
awk '/^## \[0\.20\.0\]/{f=1;next} /^## \[/{f=0} f' CHANGELOG.md | grep -c '^- '   # expected > 0
```

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): add the 0.20.0 section

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Re-freeze the successor with binding-proof wording

**Files:**
- Modify: `scripts/data/render_sba_structural_comparison.py` (successor profile only: `status_lines`, `release_limits[0]`, `reproduction_lines`)
- Modify: `tests/unit/scripts/test_render_sba_structural_comparison.py` (three literals)
- Modify: `studies/sba-annual-report-structural-comparison-release/README.md` (Status section)
- Modify: `specs/sba-annual-report-approved-evidence-release/amendments.md` (append Revision 5)
- Modify: `studies/sba-annual-report-structural-comparison-release/amendments.md` (append Revision 3)
- Modify: `studies/sba-annual-report-structural-comparison-release/study.yaml` (re-pin `uv.lock`, renderer, sidecar, page, `amendments.md`)
- Regenerate: `studies/sba-annual-report-structural-comparison-release/release/public-result.json`, `docs/public/sba-structural-comparison-release.md`

- [ ] **Step 1: Spec Revision 5**

Append to `specs/sba-annual-report-approved-evidence-release/amendments.md`:

```markdown

## Revision 5 — 2026-09-27 — rule 5 stated as a condition

Rule 5 of Revision 4 asks the successor page to say that its release is
pending until an annotated tag binds the study. After the binding, CI freezes
the study folder byte for byte, so a dated status sentence would become false
and could never be corrected. That is the defect issue #796 was opened for.

Rule 5 now reads: the page must state the condition, not the date. It must
say that if no annotated tag binds this study in `studies/releases.yaml`,
the release is pending and the reader must cite the unchanged result from
release `v0.18.0`. It must name `studies/releases.yaml` as the authority.
The sentence must contain the words "release is pending". The same rule
applies to every prose file inside the successor folder.

This revision authorizes one presentation re-freeze before the 0.20.0 tag
and no other change. It does not authorize `approved` or a `claim_approval`
block.
```

- [ ] **Step 2: Successor profile wording**

In `scripts/data/render_sba_structural_comparison.py`, `PROFILES[SUCCESSOR_STUDY_ID]`, replace:

`status_lines` with:

```python
        status_lines=(
            "This page reports the same validated structural comparison that release v0.18.0",
            "froze. Nothing was re-analyzed. Under the repository citation rule, that result",
            "may be cited as a validated result from an immutable release, with its evidence",
            "status attached. `studies/releases.yaml` says whether an annotated tag binds this",
            "study. If none does, its release is pending: cite the unchanged result only from",
            "release v0.18.0, never from this page or a moving branch. The result is not",
            "approved evidence.",
        ),
```

the first entry of `release_limits` with:

```python
            "Release binding: this page was frozen before any tag bound this study. "
            "`studies/releases.yaml` is the authority. If no annotated tag binds this study "
            "there, its release is pending; cite the unchanged result only from release "
            "v0.18.0, never from this page or a moving branch.",
```

and `reproduction_lines` with:

```python
        reproduction_lines=(
            "A v0.18.0 checkout can reproduce the identical predecessor result, but it",
            "cannot select this successor. Run the selector below from a checkout that",
            "contains this study and its selector-aware Makefile: the release whose tag binds",
            "this study in `studies/releases.yaml`, or the moving branch:",
        ),
```

Leave the second `release_limits` entry (the permanent published-sample blocker), `release_status`, `release_heading`, `claim_prefix`, `claim_suffix`, `renderer_command`, and `reproduction_command` unchanged. Leave the default profile untouched.

- [ ] **Step 3: Test literals**

In `tests/unit/scripts/test_render_sba_structural_comparison.py`, in `test_successor_page_states_the_citation_rule_and_the_permanent_blocker`, replace the two assertions on the old wording with:

```python
    assert "If none does, its release is pending" in markdown
    assert "Release binding: this page was frozen before any tag bound this study" in markdown
    assert "`studies/releases.yaml` is the authority" in markdown
```

and delete `assert "No release tag contains this study yet." in markdown` and any assertion on `"Successor release pending"` or `"Release pending: no annotated release tag binds this study"`. Keep every other assertion.

- [ ] **Step 4: README Status section**

Replace the `## Status` paragraph in `studies/sba-annual-report-structural-comparison-release/README.md` with:

```markdown
## Status

**Validated. Not approved evidence.** `studies/releases.yaml` says whether an
annotated tag binds this study. If none does, its release is pending. Cite the
unchanged result only from release v0.18.0, never from the page or a moving
branch. After a tag binds this study, cite from that release.
```

and in `## Reproduce` replace "Use a checkout that contains this folder and the selector-aware `Makefile`." with "Use a checkout that contains this folder and the selector-aware `Makefile`: the release whose tag binds this study, or the moving branch."

- [ ] **Step 5: Re-pin inputs, render, re-pin outputs**

```bash
SID=sba-annual-report-structural-comparison-release
NEW=studies/$SID/study.yaml
repin() { h=$(shasum -a 256 "$1" | cut -d' ' -f1); uv run python - "$NEW" "$1" "$h" <<'REPIN'
import pathlib, re, sys
manifest, path, sha = sys.argv[1:]
text = pathlib.Path(manifest).read_text(encoding="utf-8")
pattern = re.compile(rf"(  - path: {re.escape(path)}\n    sha256: )[0-9a-f]{{64}}")
new, count = pattern.subn(lambda m: m.group(1) + sha, text)
assert count == 1, (path, count)
pathlib.Path(manifest).write_text(new, encoding="utf-8")
REPIN
}
repin uv.lock
repin scripts/data/render_sba_structural_comparison.py
PYTHONPATH="$PWD:$PWD/packages/sbir-analytics" uv run --no-sync python scripts/data/render_sba_structural_comparison.py --study-id $SID
repin studies/$SID/release/public-result.json
repin docs/public/sba-structural-comparison-release.md
PYTHONPATH="$PWD:$PWD/packages/sbir-analytics" uv run --no-sync python scripts/data/render_sba_structural_comparison.py --study-id $SID
git status --short docs/public studies/$SID/release   # expected: the two regenerated files only, unchanged by the second render
grep -nE 'Successor release pending|No release tag contains this study yet|no release is scheduled' docs/public/sba-structural-comparison-release.md || echo "old wording gone"
grep -c 'release is pending' docs/public/sba-structural-comparison-release.md   # expected 2
```

- [ ] **Step 6: Study amendment Revision 3, then self-pin**

Append to `studies/$SID/amendments.md`, filling the hashes from `shasum -a 256` of the four files:

```markdown

## Revision 3 — 2026-09-27 — release re-freeze before the 0.20.0 tag

Spec Revision 5 authorizes this re-freeze. The page, this README, and the
release limits now state the binding condition instead of a dated status, so
they stay true after `studies/releases.yaml` binds this study and CI freezes
this folder. The version bump to 0.20.0 changed `uv.lock`, which this manifest
pins, so `uv.lock` was re-pinned in the same revision.

Re-frozen bytes:

- `uv.lock`: `<sha>`
- `scripts/data/render_sba_structural_comparison.py`: `<sha>`
- `release/public-result.json`: `<sha>` (content digest `<digest>`)
- `docs/public/sba-structural-comparison-release.md`: `<sha>`

Nothing in the result, estimand, permitted claims, limitations, or validation
record changed. This revision does not authorize `approved`, a
`claim_approval` block, or operational materialization. The tag and the
`studies/releases.yaml` binding are separate steps after this revision.
```

Then, with the text final:

```bash
repin studies/$SID/amendments.md
uv run python scripts/ci/validate_study_manifests.py
uv run python scripts/ci/check_study_artifact_roundtrip.py
uv run pytest tests/unit/scripts/test_render_sba_structural_comparison.py tests/unit/scripts/test_reproduce_sba_structural_comparison.py tests/unit/scripts/test_study_artifact_roundtrip.py -q
uv run ruff check scripts/data/render_sba_structural_comparison.py tests/unit/scripts/test_render_sba_structural_comparison.py
uv run python scripts/ci/check_epistemic_tiers.py
make reproduce-sba-structural SBA_STUDY_ID=$SID     # end to end, uses the cached sources
git diff --stat v0.18.0 HEAD -- studies/sba-annual-report-structural-comparison docs/public/sba-structural-comparison.md   # expected empty
```

Expected: all pass; reproduce prints the four verified hashes and exits 0.

- [ ] **Step 7: Commit**

```bash
git add scripts/data/render_sba_structural_comparison.py tests/unit/scripts/test_render_sba_structural_comparison.py studies/$SID docs/public/sba-structural-comparison-release.md specs/sba-annual-report-approved-evidence-release/amendments.md
git commit -m "studies(sba-structural-release): re-freeze with binding-proof wording for 0.20.0

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Successor release checksum inventory

**Files:**
- Create: `studies/sba-annual-report-structural-comparison-release/release/checksums.sha256`

The inventory mirrors v0.18.0's: every file in the study folder, the public page, the pinned code and lock, and the reader-path documents. It is not pinned in `study.yaml` (v0.18.0's is not either) and it cannot list itself.

- [ ] **Step 1: Generate**

```bash
SID=sba-annual-report-structural-comparison-release
OUT=studies/$SID/release/checksums.sha256
{
  git ls-files "studies/$SID" | grep -v "release/checksums.sha256"
  printf '%s\n' docs/public/sba-structural-comparison-release.md docs/public/sba-structural-comparison.md docs/public/reproducibility.md docs/public/what-this-is.md docs/public/evidence-status.md docs/public/repository-map.md docs/research-questions.md README.md STATUS.md Makefile uv.lock sbir_etl/identity/geography.py packages/sbir-analytics/sbir_analytics/assets/sba_annual_report_structural_comparison/producer.py scripts/data/acquire_sba_structural_sources.py scripts/data/run_sba_structural_comparison.py scripts/data/render_sba_structural_comparison.py scripts/data/reproduce_sba_structural_comparison.py
} | sort -u | while read -r p; do printf '%s  %s\n' "$(shasum -a 256 "$p" | cut -d' ' -f1)" "$p"; done > "$OUT"
wc -l "$OUT"; awk -F'  ' '{print $2}' "$OUT" | sort | uniq -d   # expected: no duplicates
shasum -a 256 -c "$OUT" | grep -v ': OK$' || echo "inventory verifies"
```

- [ ] **Step 2: Commit and run the CI analog**

```bash
git add "$OUT"
git commit -m "studies(sba-structural-release): add the release checksum inventory

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
make ci-local
git checkout -- .secrets.baseline 2>/dev/null; git status --short | wc -l   # expected 0
```

Expected: `make ci-local` exit 0.

---

### Task 5: Release-preparation PR

- [ ] **Step 1: Push and open**

```bash
git push -u origin release/v0.20.0
gh pr create --base main --title "chore: prepare release v0.20.0" --body "$(cat <<'BODY'
Prepares v0.20.0 (minor: two breaking changes in the unreleased section, #792 and #800).

- Version metadata bumped in every source; `uv lock` run; `check_versioning.py --tag v0.20.0` passes.
- CHANGELOG 0.20.0 section.
- Successor study re-frozen with binding-proof wording (spec Revision 5, study Revision 3): the page states the binding condition, not a dated status, so it stays true after `studies/releases.yaml` binds it and CI freezes the folder. `uv.lock` re-pinned.
- Successor release checksum inventory added; the later binding PR points `checksum_manifest` at it.

After merge: verify the squash-merged tree (inventory and pins) on `main`, then tag `v0.20.0` there. The `studies/releases.yaml` binding follows in its own PR, because its validator resolves the tag.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
BODY
)"
```

- [ ] **Step 2: Hold anything that touches an inventoried file.** Until the binding PR (Task 7) has merged, do not merge: the Monday 09:00 dependabot pip/uv group PR (`uv.lock` is pinned and inventoried; merging it after the tag and before the binding makes the study unbindable without a new tag), and PR #802 (`README.md` is inventoried; merging it before the tag makes the tag tree fail `verify_release_checksums`). Merge, tag, and bind in one sitting.

- [ ] **Step 3: Wait for CI, then squash-merge**

```bash
gh pr checks --watch
gh pr merge --squash --delete-branch
```

---

### Task 6: Verify the merged tree, then tag

The squash commit's tree is what the tag freezes. Verify it before tagging.

- [ ] **Step 1: Verify on main**

```bash
git checkout main && git pull --ff-only origin main && git log --oneline -1
uv run python scripts/ci/check_versioning.py --tag v0.20.0
uv run python scripts/ci/validate_study_manifests.py
uv run python scripts/ci/check_study_artifact_roundtrip.py
shasum -a 256 -c studies/sba-annual-report-structural-comparison-release/release/checksums.sha256 | grep -v ': OK$' || echo "inventory verifies on main"
```

If the inventory or any pin fails here, open a one-commit fix PR that regenerates the inventory (Task 4 step 1) and re-pins whatever moved, merge it, and repeat this step. Do not tag a tree that fails and do not plan on a checksum erratum.

- [ ] **Step 2: Tag and push**

```bash
git tag -a v0.20.0 -m "Release v0.20.0"
git push origin v0.20.0
gh run list --workflow=release.yml --limit 1
gh release view v0.20.0 --json name,publishedAt
```

Expected: the Release workflow runs on the tag and publishes `SBIR Analytics v0.20.0`. If `CITATION.cff` has a `date-released` field, set it to this date in the binding PR.

---

### Task 7: Binding PR

**Files:**
- Modify: `studies/releases.yaml` (one entry)
- Modify: `STATUS.md:17` (one cell)
- Modify: `CHANGELOG.md` (one line under the new `## [Unreleased]`)

- [ ] **Step 1: Branch and compute the identity**

```bash
git checkout main && git pull --ff-only origin main && git fetch --tags origin
git checkout -b studies/bind-successor-v0.20.0
SRC=$(git rev-parse 'v0.20.0^{commit}'); TREE=$(git rev-parse 'v0.20.0^{tree}'); echo "$SRC $TREE"
git cat-file -t v0.20.0   # expected: tag
```

- [ ] **Step 2: Add the entry**

Append under `releases:` in `studies/releases.yaml`, with the two values from Step 1:

```yaml
  sba-annual-report-structural-comparison-release:
    tag: v0.20.0
    source_revision: <SRC>
    tree_oid: <TREE>
    checksum_manifest: studies/sba-annual-report-structural-comparison-release/release/checksums.sha256
```

No `checksum_errata`. If the validator reports a checksum mismatch, the tree was not verified in Task 6; do not add an erratum, fix the cause.

- [ ] **Step 3: Validate**

```bash
uv run python scripts/ci/validate_study_manifests.py     # extracts the v0.20.0 tree; expected 13 manifests valid, successor validated inside the tag tree
uv run pytest tests/unit/scripts/test_released_studies.py tests/unit/scripts/test_render_sba_structural_comparison.py -q
```

The renderer test `test_successor_artifacts_regenerate_byte_for_byte_at_head` builds the successor payload at `ROOT` (HEAD), and `build_payload` re-hashes `uv.lock` and the renderer at HEAD. After binding, `study.yaml` can never be re-pinned, so the next `uv lock` or renderer edit breaks that test permanently. Move it in this PR, unconditionally: add a module-scoped fixture `successor_release_root` that yields `released_study_root(ROOT, load_released_studies(ROOT)["sba-annual-report-structural-comparison-release"])`, and build the successor payload from that root instead of `ROOT` (compare its serialized sidecar and rendered page with the files under that root). Keep the v0.18.0 comparison via `reviewed_release_root`. Run the renderer test file and `test_released_studies.py`.

- [ ] **Step 4: Links and changelog**

`STATUS.md` release-page row, middle cell: `The same 1,264/1,264 result, restated under the citation rule; bound to release v0.20.0`. Under `## [Unreleased]` in `CHANGELOG.md`, `### Changed`:

```markdown
- Bound `sba-annual-report-structural-comparison-release` to tag v0.20.0 in
  `studies/releases.yaml`; its page may now be cited from that release with
  status `validated`.
```

- [ ] **Step 5: Commit, PR, merge**

```bash
git add studies/releases.yaml STATUS.md CHANGELOG.md
git commit -m "studies: bind the successor study to release v0.20.0

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push -u origin studies/bind-successor-v0.20.0
gh pr create --base main --title "studies: bind the successor SBA structural-comparison study to v0.20.0" --body "Adds the studies/releases.yaml entry for sba-annual-report-structural-comparison-release (tag v0.20.0). CI now validates the study inside the tag tree and freezes its folder. Closes the follow-up from #796 / #801.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
gh pr checks --watch && gh pr merge --squash --delete-branch
```

---

### Task 8: Wrap-up

- [ ] Run `make lint-boundaries` on `main` after the binding merge.
- [ ] Move this plan to `docs/archive/development/` with an outcome section, keeping every link as a code span so the docs link checker accepts it.
- [ ] Update the project memory note for issue 796: bound, HEAD coupling ended.

## Self-review

| Requirement | Task |
|---|---|
| Issue #796 step 9: tag and binding | Tasks 6, 7 |
| versioning.md checklist steps 1 to 7 | Tasks 1, 2, 5, 6 |
| Binding needs inventory in the tag tree | Task 4 before Task 6 |
| Successor pins uv.lock, renderer | Task 3 step 5 |
| Folder frozen after binding must stay true | Decision 1, Task 3 |
| Squash-merge tree hazard (v0.18.0 erratum) | Task 6 step 1 |
| Rule 5 literal words | Task 3 wording contains "release is pending" |

Known limits: the release PR touches pinned files, so any review-driven edit to the renderer or `uv.lock` after Task 3 restarts from Task 3 step 5. Keep review comments on those files to the minimum.

---

## Outcome (recorded 2026-09-27)

Executed the same day. Release PR #804 squash-merged as cfaf44af; the merged
tree was verified (versioning, 13 manifests, two round trips, inventory all OK)
before the annotated tag `v0.20.0` was pushed; the release workflow published
`SBIR Analytics v0.20.0`. Binding PR #805 squash-merged as 0a5210d4; the
validator validates the successor inside the tag tree and freezes its folder.

Deviations from the plan as written: `CITATION.cff` `date-released` was set to
the tag date in the release PR, not the binding PR, because the tag is
immutable; the CHANGELOG link footer needed the `[0.20.0]` definition and a
new `[Unreleased]` compare base; the study amendment's superseding clause was
generalized to cover Revisions 0 to 2 before the folder froze; the successor
renderer test moved to a released-tree fixture unconditionally. Two sequencing
hazards were held until the binding merged: the Monday dependabot pip/uv PR
(`uv.lock` pinned and inventoried) and PR #802 (`README.md` inventoried).
Parked: the page badge names v0.18.0 as the citation source, which stays true;
the folder README also names v0.20.0.
