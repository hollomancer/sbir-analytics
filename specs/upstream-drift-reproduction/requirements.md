# Reproduction against drifting upstreams — Requirements

**Target epistemic tier:** `primitives`

The deliverable is a `StudyManifest` contract change and its enforcement,
serving studies at `reproducible` and above.

**Research question anchor:** none directly. This is repository machinery: it
changes what a study must record so that `reproducible` remains a checkable
claim when an input is a live source.

**Status:** proposed. No schema change is implemented in this spec.

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

`studies/transition-scoring/study.yaml` recorded its source as the string
`"/tmp/gsa_award_grain"` — a path, on a temp filesystem, now gone. So the
repository measured the drift and then threw the measurement away, and the
2026-09-13 rebuild is undiagnosable as a result.

This will recur for every study whose inputs include USAspending bulk archives,
SEC EDGAR full-text search, SAM.gov, the GSA archive, or any other live public
source. It is not specific to `transition-scoring`.

## Requirements

### R1 — A live-upstream study pins a retrieval manifest, not a path

A study whose inputs include a source outside this repository must list the
retrieval manifest for that source in `frozen_artifacts`. The manifest must
record, per retrieved object: the URL, the fetch timestamp, and at least one
upstream-size measure taken before this repository's own filtering
(`rows_scanned` or equivalent).

The producers already emit these. The change is that the study pins one instead
of naming a directory.

Cost is near zero: the manifests are small JSON files and are already written.

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

A rebuild comparison must report which of the four cells above it landed in.
Upstream drift within the declared tolerance is recorded and passes. A change
in kept rows at constant upstream size fails regardless of tolerance, because
that is this repository's behaviour changing, not the world's.

Collapsing both into one numeric comparison is what makes today's 137-versus-138
uninterpretable.

### R4 — Nothing here weakens an existing contract

`frozen_artifacts` keeps meaning exact bytes. In-repo artifacts are unaffected.
A study with no live upstream declares no tolerance and is checked exactly as
it is today. Tolerance applies only to quantities derived from a declared live
source.

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
