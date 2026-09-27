# Named-reader review 1 — successor public page

**Reviewer:** `pr796_successor_named_reader`, project named-reader-reviewer role  
**Date:** 2026-09-26  
**Reviewed commit:** `7bc22b9dcd46da5a116746ff66c047aac90dbd46`  
**Reviewed page bytes:** `09b5b1f0617067028cfba228f7f0aa2ddebe0d6ed5e33fe2c7cd3bc9c756de7d`  
**Verdict:** `BRIEF`; no remediation

This verdict does not authorize merge, tag, publication, materialization, citation, or `approved` promotion.

A first pass by the same role on the earlier page bytes `d6470ea378c64500d5713f3b93ca77d8fcd7f5d12837bbd51afdde1973e610dc` returned `OVERCLAIMS` on the reproduce lead-in and recommended badge and heading changes. The renderer profile was corrected and the page re-rendered; this record is the cold review of the corrected bytes.

## Reviewer's report (verbatim)

```
## Named-Reader Review (re-review): `docs/public/sba-structural-comparison-release.md` @ `7bc22b9d`

### Hash confirmation

All three confirmed against the bytes at `7bc22b9dcd46da5a116746ff66c047aac90dbd46`; working tree clean apart from untracked `docs/superpowers/`.

| Artifact | Expected | Read |
| --- | --- | --- |
| `docs/public/sba-structural-comparison-release.md` | `09b5b1f0617067028cfba228f7f0aa2ddebe0d6ed5e33fe2c7cd3bc9c756de7d` | matches |
| `studies/.../release/public-result.json` (whole file) | `46aed9913753ad3059dbf0fb6b77f3241721af9c57ba5b7f00e63cafeed83003` | matches |
| sidecar `content` digest | `7ccf34ee0ab5e96d4f533c1711552b1e0425665f6eacb57e84f1b08798aaa473` | matches — recomputed independently over the `content` object as canonical JSON (sorted keys, compact separators); equals the stored `content_sha256` and the page's line 125 |
| `studies/.../study.yaml` | `ff48975e20bee5473dd6f77859734df997c836bc43505a8d71ce5c2795a0cd4d` | matches |

Manifest diff verified, not taken on trust: the only changes in `study.yaml` are three self-referential `frozen_artifacts` hashes (renderer, sidecar, page). `permitted_claims`, `limitations`, `estimand`, `evidence_status`, `materialization.blockers`, and every `validation_*` field are byte-identical to `74cd92a1`. Page diff is confined to the badge, the Reproduce lead-in, the heading, the renderer self-hash, and the sidecar content digest. No number moved: `+333`, `869`, `632`, `276`, `356`, `57`, `219`, `208`, `148`, `20,502`, `20,835`, `1,264 of 1,264`, `[1.0, 1.0]` all unchanged, and `count-comparison.csv` remains `e86ab669…`.

### Verdict: BRIEF

All three remediations landed, and landed in the right place. The renderer diff adds one `StudyProfile` field, `reproduction_lines`, and applies it to **both** profiles — the predecessor keeps its original sentence verbatim, so the successor fix did not silently change the released page. The hardcoded string at the old line 1047 is gone, replaced by `*profile.reproduction_lines`. No wording now sits outside the profile mechanism.

### Declared Reader

- Header: `**Prepared for:** SBIR program managers and policy analysts in Treasury, OMB, JCT, and state economic-development offices` (line 3, unchanged)
- Inventory slot: **Start here**, both halves. `docs/research-questions.md` lines 114–121 and 122–126 each carry D1 as "Validated, not approved."
- Question IDs: **D1** (award totals)

### Quotable Sentence

- They will quote: **"Recomputed minus published counts sum to +333, while absolute cell differences sum to 869."** (line 26, unchanged)
- Licensed: **YES** — verbatim in `permitted_claims[1]`, with its fence in the same sentence block ("These summaries are not an omitted-award estimate, a source-correctness verdict, or a causal explanation").
- The badge is now the second-most quotable string and has materially improved. **"Status: Validated; cite from release v0.18.0, not this page."** A reader who lifts nothing but the badge into a slide now carries the licensed rank *and* the citation instruction in the same clipping. That is the single best change in this revision: the restriction no longer depends on the reader continuing past the blockquote.

### Over-Read

**1. "Validated; cite from release v0.18.0, not this page"**
- They will hear: *"Checked and correct, and I footnote v0.18.0."* The second half is now correct and self-contained.
- Blocks the "counts are right / SBA is wrong" hearing: **YES** — lines 21–22 and 62–63 still scope `Validated` to capture and transformation fidelity, and the bounded claim names what was validated (1,264 extracted operands).
- The "release pending → imminent" hearing I flagged last round is **gone**. The badge no longer promises a schedule, and `## Release status and limits` no longer frames a permanent blocker as a to-do item. The heading now accurately describes what sits under it: one citation restriction and one permanent limit.

**2. "may be cited as a validated result from that immutable release"** (lines 8–10, unchanged)
- Blocks the "this page is citable" hearing: **YES**, and now on three surfaces rather than one-and-a-half — the badge (line 5), the preamble's "from that immutable release" (line 9), and the closing bullet's "never from this page or a moving branch" (line 128). The first screen and the last screen now agree without the reader having to travel between them.
- Factual premise re-verified: `count-comparison.csv` is byte-identical at `v0.18.0` and HEAD, so a reader quoting this page and footnoting v0.18.0 footnotes the same bytes.

**3. "+333" and "869"**
- Blocks the "annual reports undercount by 333 awards" hearing: **YES**, unchanged and still the strongest part of the page — in-sentence disclaimer, signed-vs-absolute explanation, "every nonzero difference remains `unresolved`", "one export row, not necessarily one unique award", and the current-vintage caveat.

### The four hazard readings

- **Result is new?** No — "the same validated structural comparison that release v0.18.0 froze. Nothing was re-analyzed."
- **v0.18.0 was wrong?** No — nothing reads as a correction.
- **Published-sample blocker resolved?** No — "is permanent" (line 129), and the heading no longer works against it.
- **Result approved?** No — "Its substantive claims are not approved evidence" (line 11).
- **This page or the moving branch is the citable object?** No, and this is now answered in the badge itself rather than 120 lines down.

### Decision

- **What they can do:** Everything from the prior review, plus — and this is what changed — **verify independently**. The Reproduce section now tells the truth: "No release tag contains this study yet. From a v0.18.0 checkout, the default `make reproduce-sba-structural` reproduces the identical frozen result. The successor selector below works only from a checkout of the moving branch that contains this study."

  I checked each of the three assertions rather than accepting them:
  - *No release tag contains this study* — true; I scanned every tag, zero hits for `sba-annual-report-structural-comparison-release`.
  - *Default command at v0.18.0 reproduces the identical frozen result* — true; the v0.18.0 recipe invokes `reproduce_sba_structural_comparison.py` with no selector, defaulting to the predecessor study, whose `count-comparison.csv` is byte-identical.
  - *Selector works only from the branch* — true, and this instruction closes the silent-failure path I flagged last round. At v0.18.0 the recipe does not reference `$(SBA_STUDY_ID)`, so the override was previously dropped without warning; a reader following the new text will not pass it there.

  Reproduction does fetch the manifest-declared external sources (the 394 MB 2026-09-17 export and three SBA PDFs). `acquire_sba_structural_sources.py` hard-fails on byte-count or SHA-256 mismatch rather than proceeding, so if SBIR.gov ever serves different bytes the reader gets a loud `SourceAcquisitionError`, not quietly different numbers. External availability is a real dependency, but it is disclosed by the Sources and vintage table and it cannot degrade silently. Not a defect.

- **What they cannot:** Unchanged. Treat +333 as omitted awards, a dollar figure, a source-correctness verdict, or an economic-return input. Cite this page or the branch. Treat the result as approved evidence.

### Required Remediation

**None.** The named reader can be handed this page without a maintainer in the room.

One non-blocking observation for whoever next touches the profile, recorded so it is not rediscovered: the copy-paste code block still shows only the successor selector form, while the v0.18.0 path appears as inline prose backticks. A reader who copies the block and runs it at v0.18.0 still hits the dropped-selector behaviour. The three lines immediately above the block say it works only from a branch checkout, on the same screen and directly adjacent, so the fence is adequate and I am not asking for a change. If the successor ever gets its own tag, `reproduction_lines` is the field to revisit.

### Scope statement

`BRIEF` means the named reader can read this page unattended without being misled. It does **not** authorize citation, does **not** authorize cutting a release tag, and does **not** authorize a Start-here edit. Citation and any evidence-status change remain `evidence-auditor`; the inventory edit remains a human decision. `STATUS.md` still correctly reads "Approved evidence — None," and the page should keep saying so. I edited no file and ran only read-only commands.
```
