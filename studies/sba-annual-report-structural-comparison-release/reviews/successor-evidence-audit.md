# Evidence audit — successor study, Revision 1

**Reviewer:** `pr796_successor_evidence_audit`, project evidence-auditor role  
**Date:** 2026-09-26  
**Reviewed commit:** `7bc22b9dcd46da5a116746ff66c047aac90dbd46`  
**Verdict:** `BLOCK` on sequencing only (Revision 4 Rule 4); every contract check `PASS`. The block clears when this record and the named-reader record are pinned and Revision 1 is entered, provided that commit is governance-only.

This verdict does not authorize merge, tag, publication, materialization, citation, or `approved` promotion.

## Exact bytes audited

- Manifest: `ff48975e20bee5473dd6f77859734df997c836bc43505a8d71ce5c2795a0cd4d`
- JSON: `46aed9913753ad3059dbf0fb6b77f3241721af9c57ba5b7f00e63cafeed83003`
- Markdown: `09b5b1f0617067028cfba228f7f0aa2ddebe0d6ed5e33fe2c7cd3bc9c756de7d`
- Canonical content: `7ccf34ee0ab5e96d4f533c1711552b1e0425665f6eacb57e84f1b08798aaa473`
- Renderer: `df6f65410e761b9f60b092abc599965b80a3ab68b5460f0c59fff729581ef142`

## Auditor's report (verbatim)

```
## Evidence Audit: `studies/sba-annual-report-structural-comparison-release/` at `7bc22b9d` (re-audit after named-reader remediation)

### Verdict: BLOCK — sequencing only, unchanged in kind from my audit of `74cd92a1`

Every substantive check passes on the new bytes, and the delta is an improvement. The block is the same Revision 4 Rule 4 gap: the page's citation sentence is present while `reviews/` is empty and `amendments.md` still contains only Revision 0. That gap closes with the next commit. Below I answer, with evidence, exactly what will and will not satisfy Rule 4 once those records exist.

### Bytes under audit — confirmed

HEAD is `7bc22b9dcd46da5a116746ff66c047aac90dbd46`; tree clean apart from untracked `docs/superpowers/`. All four SHA-256 values match on disk:

- `study.yaml` → `ff48975e20bee5473dd6f77859734df997c836bc43505a8d71ce5c2795a0cd4d`
- `release/public-result.json` → `46aed9913753ad3059dbf0fb6b77f3241721af9c57ba5b7f00e63cafeed83003`; content digest recomputes to `7ccf34ee0ab5e96d4f533c1711552b1e0425665f6eacb57e84f1b08798aaa473`
- `docs/public/sba-structural-comparison-release.md` → `09b5b1f0617067028cfba228f7f0aa2ddebe0d6ed5e33fe2c7cd3bc9c756de7d`
- `scripts/data/render_sba_structural_comparison.py` → `df6f65410e761b9f60b092abc599965b80a3ab68b5460f0c59fff729581ef142`

### Intended Claim
- **Status:** `validated`. Not approved. No release binds the successor.
- **Estimand:** unchanged — signed and absolute differences across the 632 published cells versus the pinned 2026-09-17 export under EXPORT_ROW_V1, AWARD_YEAR_FIELD_V1 and the frozen jurisdiction profile.
- **Permitted claim:** unchanged, both bounded claims byte-identical to what I audited.

### Delta verification — matches the description exactly

`git diff 74cd92a1 7bc22b9d` touches five files: the page, the renderer, the sidecar, the manifest, and the renderer's test. The manifest diff is confined to three re-pinned hashes (renderer, sidecar, page) at lines 129–141. `permitted_claims`, `limitations`, `estimand`, `validation_design`, `validation_result`, `identity_policy`, `materialization.blockers` and every result-artifact pin are untouched. `evidence_status: validated`; `claim_approval` absent.

The renderer change is a pure profile extension: a new `reproduction_lines` field, with the released profile receiving the original single line so its output is unchanged, and `render_markdown` substituting `*profile.reproduction_lines` for the hardcoded string.

### Contract
- **Frozen spec: PASS.** All 61 `frozen_artifacts` entries resolve and match at HEAD (0 missing, 0 mismatched).
- **SHA enforcement: PASS.** Unchanged two-level chain. The hardening note from my prior audit still stands and is still inherited from v0.18.0, not a regression: the four `external_source: true` entries in `study.yaml` mirror `source-manifest.json` and are not the enforcement point.
- **Blocking asset checks: PASS.** `materialization.allowed: false` with both blockers unchanged; the `approved`-gated `_verify_manifest` still cannot pass at `validated`.
- **Declared estimand: PASS.** Unchanged, with all eight limitations carried.

### Replay — transfers, not repeated

I did not re-run the replay, and it is sound not to. The replay depends on `producer.py`, `run_sba_structural_comparison.py`, `uv.lock`, `source-manifest.json`, the four raw sources, the captured tables, and the validation design and population. None of those changed between `74cd92a1` and `7bc22b9d` — the five-file diff excludes every one of them, and the `results/count-comparison.csv` pin is still `e86ab66905f65adaa7fdb721ced6bcbc7b3991a288ba37156f1efe9b4bed7381`. My verified byte-identical replay at `74cd92a1` therefore carries over unchanged. `studies/sba-annual-report-structural-comparison/` and `docs/public/sba-structural-comparison.md` remain byte-identical to the v0.18.0 tag (empty diff).

### Reproduction checks — PASS
- `check_study_artifact_roundtrip.py`: both registered pairs reproduce, including the successor page from its sidecar. The released page still reproduces, confirming the renderer refactor did not perturb the v0.18.0 profile.
- `pytest tests/unit/scripts/test_render_sba_structural_comparison.py`: 18 passed.
- `check_epistemic_tiers.py`, `validate_study_manifests.py` (13 manifests), `check_research_question_status.py`: all pass.

### The named-reader remediation — correct, and a real fix

**The OVERCLAIMS finding was valid and is now fixed.** The old lead-in read "From the repository root in a tagged release checkout, run: `make reproduce-sba-structural SBA_STUDY_ID=sba-annual-report-structural-comparison-release`". That instruction could not work. I verified why: `studies/releases.yaml` binds only the released study to v0.18.0, and `git show v0.18.0:Makefile` has no `SBA_STUDY_ID` variable at all — its target is a bare `reproduce_sba_structural_comparison.py` with no `--study-id`. So in a tagged release checkout the documented command silently reproduces something other than what the page implies, and the successor manifest does not even exist there.

Each clause of the replacement is accurate:
- "No release tag contains this study yet" — correct per `releases.yaml`.
- "From a v0.18.0 checkout, the default `make reproduce-sba-structural` reproduces the identical frozen result" — correct; the tag's target runs the released study, producing the same `e86ab669…` CSV.
- "The successor selector below works only from a checkout of the moving branch that contains this study" — correct; `SBA_STUDY_ID ?= sba-annual-report-structural-comparison` exists only at HEAD (Makefile line 152).

**The badge change is a strengthening.** "Validated; release pending" → "Validated; cite from release v0.18.0, not this page" tells the reader where to cite from rather than only that something is outstanding. For a page whose single largest misuse risk is being quoted directly, this is the better wording.

### Observation on Revision 4 Rule 5 — a decision point, not a block

Rule 5 states: "Until an annotated tag binds the successor in `studies/releases.yaml`, the page must say that its release is pending." The word "pending" no longer appears anywhere on the page — it left both the badge and the heading (`## Release pending` → `## Release status and limits`).

I judge Rule 5 satisfied on substance, and the purpose better served than before. The page says "This successor study is not bound to a release yet", "No release tag contains this study yet", and "No annotated release tag binds this study in studies/releases.yaml. Until one does, cite the result only from release v0.18.0, never from this page or a moving branch." A reader cannot conclude the study is released.

Flagging it so the acceptance is deliberate rather than accidental: the two reviews pull in different directions here, Rule 5 is worded as a positive requirement, and a future reviewer or CI grep for "pending" would now find nothing. If you want zero ambiguity at no cost to the named reader's improvement, the cheapest fix is a heading of `## Release status and limits (release pending)`, which preserves the new badge. I do not recommend reverting the badge.

### Rule 4 once the records exist — your direct question

**Yes, Rule 4 is satisfied as written once both records exist, subject to two conditions I can state precisely.**

**Condition 1 — the named-reader review must be of `09b5b1f0…`, the current page bytes.** Rule 4 requires "a cold named-reader review of the exact page bytes". The review that returned OVERCLAIMS examined the superseded page `d6470ea3…` and returned an adverse verdict. Pinning that review as `reviews/named-reader-review-1.md` would not satisfy Rule 4: wrong bytes, and an unresolved adverse verdict. The remediation was claim-facing — it corrected a false reproduction instruction — and Revision 3 requires renewed independent review for substantive changes, with Revision 12 of the released study treating page bytes as claim-facing. A cold named-reader review of `09b5b1f0…` returning a non-adverse verdict is required. If your plan is already that, this condition is met; I flag it because the file name suggests the earlier review.

**Condition 2 — the review commit must be governance-only.** Pinning the two review files will change `study.yaml` from `ff48975e…` to a new hash, so strictly the audit recorded in `reviews/successor-evidence-audit.md` will describe a manifest that no longer exists byte-for-byte. This bootstrap is unavoidable and it is benign here, for a reason I verified in code rather than assumed:

`_artifact_records` (line 677) iterates the curated `ARTIFACT_LABELS` map, **not** `frozen_hashes`. Adding two `reviews/*` entries to `frozen_artifacts` therefore adds no row to the page table or the sidecar. **The page and sidecar bytes I audited stay valid after the review commit; only `study.yaml` moves.** And the only manifest delta is two added review pins — no claim, estimand, input, method, limitation, blocker or result pin changes. Revision 3 covers this directly: "Existing evidence audits and reader-comprehension reviews remain supporting records; they are not repeated merely because editorial or governance bytes change." So the review commit does not re-trigger Rule 4.

That holds only if the commit is confined to: (a) the two review files, (b) their two `frozen_artifacts` pins, (c) the `amendments.md` entry. If it touches the page, the sidecar, any claim, or any other pin, Rule 4 re-triggers and neither this audit nor the named-reader review covers the resulting bytes.

**Nothing else stands in the way.** Every other Rule in Revision 4 is met at these bytes: Rule 1 (validated only after a clean byte-for-byte replay at HEAD — verified), Rule 2 (no `approved`, no `claim_approval` — verified by grep and manifest read), Rule 3 (permanent blocker repeated; result presented as the same v0.18.0 result, not new, different, or a correction), Rule 5 (satisfied on substance, see the observation above).

### Claim and Provenance
- **PASS** — all manifest paths and implementation entry points resolve; the renderer re-pin matches the code that produced these bytes, confirmed by the roundtrip check.
- **PASS** — v0.18.0 result artifacts re-pinned by identical path and hash; the tag's tree untouched.
- **PASS** — the reproduce-section correction removes a false instruction rather than softening a claim.
- **BLOCK** — the page's citation authorization still precedes the two records Rule 4 requires. `reviews/` is empty and `amendments.md` is unchanged from `74cd92a1` (Revision 0 only).
- **Observation** — the new page and sidecar bytes are not yet recorded in any numbered amendment. Revision 0 is not falsified by them (it quotes the result hash, which is unchanged, and still correctly says five files were re-pinned), but the v0.18.0 practice in Revision 12 was to record a presentation-only re-freeze as its own numbered revision listing the re-frozen bytes. Recommend the next commit add a numbered revision naming `df6f6541…`, `46aed991…`, `09b5b1f0…` and the named-reader remediation, so the Rule 4 record is self-contained.
- **Observation** — if the amendments entry quotes the manifest hash, quote `ff48975e…` as the audited manifest and state that the only later delta is the two review pins. Otherwise the quoted hash goes stale the moment the pins land.
- **Observation, carried forward** — `amendments.md` is still not in `frozen_artifacts`. Rule 4 makes it the register of authorization, so pinning it would be appropriate; it matches v0.18.0 practice not to, so this is not a regression.
- **Observation, carried forward** — the permitted-claim lead is still "Validated:" rather than "Validated, not citable:". The restriction survives in the same paragraph and in the blockers, and the new badge now compensates on the page. Lower concern than in my prior audit.

### Required Remediation
1. Obtain a cold named-reader review of page bytes `09b5b1f0617067028cfba228f7f0aa2ddebe0d6ed5e33fe2c7cd3bc9c756de7d` with a non-adverse verdict. Do not pin the earlier OVERCLAIMS review of `d6470ea3…` in its place.
2. Record both that review and this audit in `studies/sba-annual-report-structural-comparison-release/amendments.md`, naming the manifest, sidecar and page SHA-256 values audited.
3. Keep the review commit governance-only: the two review files, their two pins, and the amendments entry. Nothing else.
4. Optional, to remove all ambiguity against Rule 5: add "release pending" to the release heading while keeping the new badge.

### Prohibited Claim Until Resolved
- "Under the repository citation rule, that result may be cited as a validated result from that immutable release, with its evidence status attached" — correct in substance and consistent with `STATUS.md`, `docs/steering/epistemic-tiers.md` and Revision 3, but not yet authorized to appear on this page until both Rule 4 records exist.
- Any statement that the successor study, this page, or the branch is citable. Cite only from v0.18.0.
- "Approved evidence", "repository-approved", or any wording implying a claim-approval review exists.
- Any presentation of the successor as a new, corrected, or superseding result relative to v0.18.0.

### Scope of this verdict

This verdict does not authorize a tag, an `approved` status, a `claim_approval` block, or a Start-here edit. It authorizes none of them even after the Rule 4 records are in place; clearing Rule 4 permits the page's citation sentence and nothing more. I edited no file, ran no live materialization, and downloaded nothing. The only bytes I wrote in this session were scratch files outside the repository tree, during the earlier audit.
```
