# Named-reader review 1

**Date:** 2026-09-21
**Reviewer:** `sba_named_reader_review`, project named-reader-reviewer role
**Snapshot:** public result `a2223cb2...`; Markdown `45316942...`
**Verdict:** `MISLABELED`; named-reader completion gated

The reviewer started from the root README and followed only the public packet.
The reviewer correctly identified the status as `Validated, not citable`, the
September 17, 2026 export vintage, the FY2020-FY2022 report tables, the export-
row and award-year rules, and the difference between fidelity and source
agreement.

The sentence the reviewer would quote was: "The comparison contains 632 count
cells: 276 are exact and 356 are unresolved." That sentence and the aggregate
`+333` difference were not present in `permitted_claims`, so the public result
was not licensed as written.

The review also found these reader-facing defects:

1. The packet had no declared `Prepared for`, `Audience`, or `Answers for`
   header.
2. The generated result was not linked from the front door.
3. `CITATION.cff` declared a release date, version, preferred citation, and tag
   URL before that release or tag existed.
4. "Independent" could imply unaffiliated third-party replication. The run
   established separation between blinded roles and implementations inside the
   repository.
5. The filename and status phrase implied a citable release before the citable
   gate opened.
6. The generated page omitted the `make install` prerequisite.
7. The page did not explain why its content digest differed from the whole-file
   digest.

This review did not authorize citation, merge, publication, materialization, or
a tag. The packet requires a new cold review after remediation.
