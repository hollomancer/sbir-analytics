# Procurement Data Sources Evaluation — Design

## Overview

This is an **investigation spec**, not an implementation spec. The "design" is the
methodology for evaluating each source consistently and producing adoption decisions
that feed follow-on implementation work.

Output artifacts (all produced by the investigation):

1. `matrix.md` — one-row-per-source comparison table.
2. `evaluations/<source_name>.md` — per-source deep-dive for `adopt` /
   `evaluate_further` candidates.
3. `decisions.md` — final adoption decisions and follow-on spec plan.
4. `fixtures/` references — sample API payloads for future implementation.

## Evaluation Methodology

### Step 1 — Inventory

Transcribe every source from `github.com/makegov/awesome-procurement-data` into the
matrix with uniform metadata. Capture: name, category (per the upstream list), URL,
auth required (yes/no/api-key/oauth), rate limits (documented or tested), and a
one-sentence description.

### Step 2 — Relevance filter

Classify each source's potential utility to **our pipeline specifically**, not
procurement data in general:

| Label | Meaning |
|---|---|
| `imputation-critical` | Directly unlocks a method in `specs/data-imputation/design.md` §4 |
| `enrichment-upgrade` | Improves an existing `sbir_etl/enrichers/*` integration |
| `new-enrichment` | Enables a net-new enrichment not currently in the pipeline |
| `tooling` | Client library or helper that reduces our implementation burden |
| `orthogonal` | Valid procurement data but unrelated to SBIR analytics needs |

Sources labeled `orthogonal` are documented but not deep-evaluated.

### Step 3 — Deep evaluation (adopt-candidates only)

For each source that passes the relevance filter, produce an evaluation doc
containing:

- **Data model:** What fields does it expose? Which of ours do they fill?
- **Access model:** Auth, rate limits, pagination, incremental/delta support.
- **Freshness:** How often does the source update? What's the publication lag?
- **Coverage test:** Run the source against a sample of recent SBIR awards
  (FY23–FY24 DoD Phase II is a reasonable default) and report match rate.
- **Legal / ToS:** Redistribution terms, attribution requirements, any known
  caveats.
- **Effort estimate:** T-shirt size to integrate given our existing extractor
  scaffolding.
- **Dependency graph:** What other work does it block or unblock?

### Step 4 — Cross-reference against imputation methods

For every `imputation-critical` source, explicitly map to the specific
`specs/data-imputation/design.md` §4 method(s) it touches, with a proposed diff
(as inline markdown, not a patch) for how the imputation method's description
would change.

### Step 5 — Decision record

For each source, record one of:

- **Adopt (v1)** — Include in the next implementation cycle.
- **Adopt (v2)** — Valuable but not blocking; schedule after v1 imputation ships.
- **Evaluate further** — Needs prototyping or credential acquisition before decision.
- **Defer** — Low value, low urgency.
- **Reject** — Not useful, document why to prevent re-litigation.

Each adopt decision names the follow-on spec that will carry the implementation
(either reuse an existing spec slot or create a new one under `specs/`).

## Initial hypotheses (pre-investigation)

The investigation should confirm or refute these, not assume them:

| Hypothesis | Expected source | Confidence |
|---|---|---|
| SAM.gov Entity Extracts materially improves UEI backfill recall | Bulk download extracts | High |
| SAM.gov Opportunities API replaces Phase 4.3's agency-page scraping for solicitation ceilings and periods of performance | Opportunities API | High |
| FSCPSC's NAICS prediction beats our homegrown abstract-NN method | FSCPSC API | Medium — needs coverage test |
| PSC Selection Tool provides the NAICS↔PSC crosswalk we need for topic-derived NAICS | PSC tool API | Medium |
| DIIG CSIS Lookup Tables provide useful reference NAICS hierarchy | GitHub repo | Medium |
| David Gill's AcquisitionInnovation R utilities are reference-only, not adoptable | R stack | High — reject expected |
| Sec. 889, FAR, CALC, Pulse of GovCon are orthogonal | N/A | High — orthogonal expected |

## Sample source list (from upstream, to be validated)

Non-authoritative snapshot of what the upstream list contained at investigation
start; the investigation will re-fetch to confirm:

**Official:** SAM.gov Entity Extracts, SAM.gov Opportunities API, CALC API, FPDS API,
USASpending, SBIR API, FAR, Acquisition Gateway Document Library API.

**Utilities / client libs:** FPDS Python tool, PSC Selection Tool, FSCPSC,
pysam, SamDotNet, procurement-tools, Pulse of GovCon Part9, Sec. 889 Compliance Tool.

**Data science / analytics:** AcquisitionInnovation (R), DIIG CSIS Lookup Tables,
USASpending Bot (Slack), SAM.gov Webscraper (Google Sheets).

## Exit criteria

Investigation is complete when:

1. Every source has a matrix row with a recommendation label.
2. Every `adopt` or `evaluate_further` source has a deep-evaluation doc.
3. `decisions.md` names a concrete follow-on spec for every adopted source.
4. The two high-priority hypotheses (Entity Extracts, Opportunities API) have
   coverage-test results — not just argued merit.
5. Proposed edits to `specs/data-imputation/` are ready to land in a separate PR.

## What this spec does **not** produce

- Working extractors or enrichers.
- Production config changes.
- Adoption decisions for sources outside the awesome-procurement-data list.

Those are follow-on work, scoped in their own specs.
