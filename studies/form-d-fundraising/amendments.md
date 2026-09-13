# Form D Fundraising Study — Freeze and Amendment Log

This file records the lifecycle change to the previously frozen design. Git history preserves the
original bytes and the manifest preserves its former digest.

## Revision 0 — Historical person-or-ZIP design

- **Date:** 2026-04-23.
- **Rule:** The unversioned historical behavior is now named `person-or-zip-v1`.
- **Frozen design SHA-256:**
  `5459e2eea7b689b8f5e5e4ea0803b991328e488c32703eb7a730409bc2e99f2b`.
- **Result status:** The study later reported program, matched-firm, agency, and PIF cross-link
  numbers from local gitignored inputs. It was reproducible but never validated or citable.

## Revision 1 — Corroborated-person rule and retirement

- **Authority and date:** 2026-09-12 lifecycle repair requested before PR #717 may merge.
- **Reason:** Realistic distinct-person pairs can exceed the fuzzy person threshold. No threshold
  cleanly separates true matches from collisions, so a person hit alone may no longer reach high.
- **Rule impact:** `corroborated-person-v2` keeps exact ZIP as sufficient for high and requires a
  person hit to have exact-ZIP or state corroboration. Person alone is medium. The scorer preserves
  the named v1 behavior for historical interpretation and persists the selected rule on every new
  confidence object.
- **Migration impact:** A deterministic offline rescorer can reassign stored tiers atomically from
  existing signal values. It cannot establish that two aggregate signals came from the same filing
  or issuer.
- **Aggregation finding:** The historical producer pooled confidence inputs across every filing on
  a company record, potentially across CIKs. The historical PIF audit also discarded a CIK link
  when the same company pair first matched on a person and treated several aggregate profiles as
  risk-free. Revision 1 retains both link types and treats its output as a review queue only.
- **Visible results at amendment:** The retired findings page contained the complete v1 numerical
  tables. PR #717 also reported local, unpinned counts of 193 high-to-medium record changes overall
  and 11 among business-combination records. Those counts cannot be reproduced from this checkout
  because the input corpus is absent; they are not adopted as Revision 1 results.
- **Evidence impact:** The study moves from `reproducible` to `retired`; its materialization gate is
  closed. All v1 numbers are withdrawn from current findings, demo guidance, research-question
  status, and downstream cohort descriptions. No v2 result exists.
- **Revision 1 design SHA-256:**
  `fd15408ec51295b28ea314020ffeaccaa7c900e2e290bd874c8dbffe60079440`.
- **Freeze status:** Revision 1 is frozen as a no-result rebuild protocol. A future result requires
  every gate in `design.md`, a new amendment, and new artifact hashes.
