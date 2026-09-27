# SBA Annual-Report Structural Comparison Release — Freeze and Amendment Log

**Status:** Active evidence-approval work. The validated result is frozen. One
final pinned claim-approval review remains open.

The current input candidate is identified by raw-byte SHA-256
`aed146eab56f370c9f3fe7f562475e3eedfc61cca2eba112c830fac6f73bf38a` and byte
count `394636989`. Recording that identity does not authorize a validation run
or public claim.

Before the first evaluated validation run, the study record was required to
name:

1. approver and approval time;
2. Git-history anchor;
3. raw-byte SHA-256 values for the design, eligible population, source
   metadata, definitions, and extraction instructions;
4. every comparison result, pilot, or extraction visible at approval;
5. the independent reviewer or untouched-population boundary; and
6. the exact permitted claim and non-claims.

The canonical freeze and amendment history is now
`studies/sba-annual-report-structural-comparison/amendments.md`. It records the
formal pre-run freeze, five packet revisions, four invalid or nonconfirmatory
runs, the confirmatory Run 5 result, and the post-result evidence audit.

## Revision 1 — 2026-09-21 — validated result recorded

The design, 1,264-unit population, exact source identities, count-only producer,
632-cell sidecar, permitted claim, and non-claims were frozen before the first
evaluated extraction. Run 5 reproduced 1,264 of 1,264 count operands with the
exact complete-population point interval `[1.0, 1.0]`. The post-result evidence
audit authorized `validated` only.

The public renderer, explanatory sidecar, clean replay, and mutation checks now
pass. The final cold named-reader review returned `BRIEF`; it did not authorize
citation or release. The citable materialization state, immutable tag and
citation metadata, and owner merge approval remain open. Any change to the
estimand, population, source identity, transformation rules, threshold, claim,
or non-claim still requires a numbered study amendment.

## Revision 2 — 2026-09-22 — owner-review disclosure remediation

The claim-facing result now reports signed difference `+333` beside absolute
cell difference 869, the 208/148 direction counts, 57 zero-versus-zero cells,
and 219 exact cells among the 575-cell nonzero union. It also discloses one
excluded blank-`State` export row and 60 zero-filled groups. These are
mechanical summaries and diagnostics of the unchanged frozen result.

The study amendment records the Run 3 ordering limitation and a forward-only
pre-reconciliation invalidity rule. The prospective v1 design and all run
artifacts remain unchanged. The exact-byte evidence audit returned `GO` and the
fresh cold named-reader review returned `BRIEF` with no remediation. Neither
review authorized merge, tag, publication, materialization, citation, or
`citable` promotion.

## Revision 3 — 2026-09-23 — approval terminology and gate consolidation

The highest evidence status is renamed from `citable` to `approved`. Citation
of immutable artifacts, operational materialization, and repository-owner merge
authority are independent workflows, not additional scientific evidence.

The remaining evidence gate is one final pinned review approving the exact
manifest claim boundary. Existing evidence audits and reader-comprehension
reviews remain supporting records; they are not repeated merely because
editorial or governance bytes change. Substantive changes to a claim, method,
input, or limitation still require renewed independent review and a new
immutable version.

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
(a rename of `citable` to `approved`), `uv.lock`, the three study scripts
that this revision parameterizes, and the `Makefile` wrapper that forwards
the selected study ID. Nothing is re-analyzed.

Rules for the successor:

1. It starts at `reproducible`. It may record `validated` only after a clean
   replay at HEAD reproduces `results/count-comparison.csv` byte for byte.
   Any differing byte is a substantive change and requires renewed
   independent review under Revision 3.
2. It must not record `approved` or a `claim_approval` block. Approval still
   requires the one final pinned review of the exact claim boundary described
   by Revision 3 and task 13; a wording-only successor does not satisfy or
   bypass that gate.
3. Its page must repeat the permanent published-sample reproduction blocker.
   It must not present the result as new, as different from `v0.18.0`, or
   as a correction of the `v0.18.0` page, which was correct under the rule
   then in force.
4. Its page may state that the unchanged result may be cited as `validated`
   from immutable release `v0.18.0` after the clean replay in rule 1 and the
   registered predecessor and successor round trips pass. That statement does
   not make the successor page or a moving branch citable. Consistent with
   Revision 3 and #792, editorial and governance changes do not repeat an
   evidence audit or cold named-reader review; the eventual `approved` gate
   remains the single pinned claim-boundary review.
5. Until an annotated tag binds the successor in `studies/releases.yaml`, the
   page must say that its release is pending.
6. Release and citation status must remain separate from operational
   materialization. A closed materialization gate must name an actual
   operational blocker, not a missing tag, citation rule, or evidence limit.

The released `v0.18.0` study folder and page are not modified. CI keeps
them byte-identical to the tag.
