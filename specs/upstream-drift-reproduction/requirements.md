# Reproduction against drifting upstreams — Requirements

**Target epistemic tier:** `primitives`

The deliverable is a `StudyManifest` contract change and its enforcement,
serving studies at `reproducible` and above.

**Research question anchor:** none directly. This is repository machinery: it
changes what a study must record so that `reproducible` remains a checkable
claim when an input is a live source.

**Status:** active. Requirements are settled; no schema change is implemented
here. Design decisions that must be made before implementation are listed under
Open questions, and the registry entry in `specs/status.md` says the same.

## The problem, from a real case

`transition-scoring` claims its fusion corpus is "regenerable from committed
scripts and pinned manifests." On 2026-09-13 the corpus was rebuilt from those
committed scripts to test that claim:

| Quantity | Frozen (2026-08-01) | Rebuild (2026-09-13) |
|---|---:|---:|
| corpus rows | 828 | 822 |
| positives | 138 | 137 |
| firms | 101 | 100 |

One positive short, and the six missing rows are that positive plus its
negatives. By any ordinary reading this is a successful reproduction. The
repository cannot say so, and that is the defect.

## What is actually missing

The upstream is the public `falextracts` GSA archive, which is updated
continuously. Bit-exact reproduction against it is not achievable and never
will be. That is not the problem.

The problem is that the evidence needed to *classify* the difference was
discarded. `recover_award_grain.py` writes a retrieval manifest that already
records everything required:

```json
{"fiscal_year": 2018,
 "url": "https://falextracts.s3.amazonaws.com/.../FY2018_archived_opportunities.csv",
 "fetched_at": "2026-09-13T22:05:14Z",
 "rows_scanned": 428147, "sbir_notices": 184, "rows_kept": 17}
```

`rows_scanned` measures the upstream itself, independent of any filtering this
repository does. With the original pull's manifest, the 828-to-822 difference
resolves in one comparison:

| `rows_scanned` | `rows_kept` | Meaning |
|---|---|---|
| same | same | exact reproduction |
| moved | moved | upstream drift — a finding, not a defect |
| same | moved | the pipeline changed — a regression |
| moved | same | drift that did not reach the kept set |

`specs/phase3-notice-corpus-fusion/corpus.manifest.json` records its `sources`
as `["/tmp/gsa_award_grain", "data/derived/phase3_firm_seed.parquet"]` — the
first a path on a temp filesystem, now gone. `studies/transition-scoring/study.yaml`
pins that manifest as a frozen artifact, so the study's provenance chain
terminates in a dead path rather than in the retrieval manifest that recorded
`rows_scanned`. The repository measured the drift and then threw the measurement
away, and the 2026-09-13 rebuild is undiagnosable as a result.

This will recur for every study whose inputs include USAspending bulk archives,
SEC EDGAR full-text search, SAM.gov, the GSA archive, or any other live public
source. It is not specific to `transition-scoring`.

## Requirements

### R1 — A live-upstream study pins a retrieval manifest, not a path

A study that claims `reproducible` or above, and whose inputs include a source
outside this repository, must list the retrieval manifest for that source in
`frozen_artifacts`. A study at `exploratory` is encouraged to and not required
to; the obligation attaches with the claim, not with the data source. This is
the same scope the retrofit clause below states, written once rather than twice. The manifest must
record, per retrieved object: the URL, the fetch timestamp, and at least one
upstream-size measure taken before this repository's own filtering
(`rows_scanned` or equivalent).

The GSA producers already emit these: `recover_award_grain.py`,
`pull_gsa_archive.py`, and `extract_phase3_selflabeled.py` all write `url`,
`fetched_at`, `rows_scanned`, and `rows_kept`. For those, the change is that the
study pins one instead of naming a directory, and the cost is near zero.

This is **not** true of every live source the problem statement names. The
USAspending bulk-archive extractor, EDGAR full-text search, and SAM.gov do not
today emit a manifest in this shape. R1 therefore implies producer work for
those sources, and that work is part of implementing this spec rather than a
precondition already satisfied. Design must enumerate which producers need it
before R1 binds a study that uses them.

### R2 — A study declares what reproduction means for it

`reproducible` currently reads as bit-exact, which is unachievable against a
live source and is therefore quietly ignored rather than enforced. A study with
a live upstream must state its reproduction tolerance: which derived quantities
are checked, the agreement band for each, and why that band is the right one.

The derivation requirement mirrors `threshold_derivation` in
`ValidationDesign`: a number with no stated basis is not a contract. A band
wide enough to admit any rebuild is a defect, and the derivation is what makes
that visible.

### R3 — The check distinguishes drift from regression

A rebuild comparison must report which of the four cells above it landed in,
and must state the grain at which each measure was taken. The 2x2 is a triage
aid, not a proof: `rows_scanned` and `rows_kept` can both hold steady while the
*identity* of the kept rows changes, and an upstream can revise a record in
place without changing any count. Equal counts are evidence of agreement, not a
demonstration of it.

The binding rules are therefore narrower than the table alone suggests:

- Constant upstream measure with changed kept rows **fails**, regardless of
  tolerance. That is this repository's behaviour changing, not the world's.
- Moved upstream measure with kept rows inside the R2 band **passes and is
  recorded as drift**, provided the comparison also reports a row-identity
  check at the declared grain, not only counts.
- Any cell in which the identity check disagrees while counts agree **fails**,
  and is the case the counts alone would have hidden.

Design must fix the grain per source kind: a notice id for the GSA archive, an
accession for EDGAR, an award key for USAspending. A count-only comparison is
not sufficient at any tier this spec serves.

Collapsing drift and regression into one numeric comparison is what makes
today's 137-versus-138 uninterpretable.

### R4 — Nothing here weakens an existing contract

`frozen_artifacts` keeps meaning exact bytes. In-repo artifacts are unaffected.
A study with no live upstream declares no tolerance and is checked exactly as
it is today. Tolerance applies only to quantities derived from a declared live
source.

## Done when

`primitives` requires comprehensive tests, so completion is defined by
observable checks rather than by the prose above being agreed. This spec is
complete when all of the following hold:

1. `StudyManifest` accepts a live-source declaration carrying a pinned retrieval
   manifest and a reproduction tolerance, and rejects each of: a declaration
   naming a manifest absent from `frozen_artifacts`; a tolerance with no
   derivation; a tolerance band stated for a quantity the study does not report.
2. A study at `reproducible` or above with a declared live source and no pinned
   retrieval manifest fails `validate_study_manifests.py`.
3. The comparison reports a classification for each of the four cells, and tests
   exercise all four plus the counts-agree-identity-disagrees case named in R3.
4. Tolerance boundary tests exist on both sides of a declared band, including
   equality at the boundary.
5. `transition-scoring` carries a declaration whose rebuild comparison returns a
   determinate verdict for the 2026-09-13 rebuild — currently the motivating
   case and currently unanswerable.

Item 5 is the acceptance test that matters: if the mechanism cannot classify the
rebuild that motivated it, it has not solved the problem.

## Explicitly out of scope

- **Caching upstream snapshots to force bit-exactness.** For the GSA archive
  alone this is roughly 10 GB per rebuild, and it converts a live-data problem
  into a storage problem without making the claim any truer: the study still
  measured a moment in time. If a snapshot is kept for other reasons, R1 still
  applies to it.
- **Promoting any study.** This spec changes what a study must record, not any
  study's rank.
- **Retrofitting every existing study at once.** R1 through R3 bind a study when
  it next claims `reproducible` or above.

## Open questions for design

1. **Where does tolerance live in `StudyManifest`?** `frozen_artifacts` means
   exact bytes and `extra="forbid"` rules out ad hoc fields, so this needs a new
   typed block. The same gap blocked recording a scoring-config digest in
   `transition-scoring`, which had to go into `limitations` prose instead. One
   block may serve both.
2. **Is the tolerance checked in CI or at audit time?** CI cannot re-pull a
   10 GB archive on every push. A plausible split is that CI validates the
   declaration is present and coherent, and the rebuild comparison runs when a
   rebuild is actually performed.
3. **What is the right upstream-size measure when a source has no row count?**
   EDGAR full-text search returns hit counts; SAM.gov paginates. The measure
   has to be defined per source kind, not assumed to be rows.
4. **Does a tolerance breach retire a study, or reopen it?** A study whose
   rebuild falls outside its declared band has a real problem, but
   `retired` may be too strong when the cause is upstream.

## Provenance

The rebuild that motivated this spec: `recover_award_grain.py --years
2016..2025` followed by `build_notice_corpus.py --award-grain`, run 2026-09-13,
producing 822 rows / 137 positives / 100 firms against a frozen 828 / 138 / 101.
The fiscal-year range had to be recovered from `findings.md` prose because
`corpus.manifest.json` does not record it — which is itself an instance of R1.
