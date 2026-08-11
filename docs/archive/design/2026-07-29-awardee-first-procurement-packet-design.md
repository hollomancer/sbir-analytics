# Awardee-First Procurement Transition Packet — Design

**Date:** 2026-07-29
**Status:** Implemented; retained as the design record
**Implementation history:** PR #466 and follow-up PRs

## Problem

The monthly procurement-transition packet (for SBA Procurement Center Representatives)
today renders **one section per matched pair** and leads with methodology. Two issues:

1. **Not awardee-first.** A PCR thinks in terms of "which awardees do I own, and what
   can each of them win next?" The current packet scatters an awardee across the report
   and only shows its single best match, so the rep cannot see the full set of open
   procurements a given awardee is relevant to.
2. **No bottom line.** The report opens with a "how to read" glossary instead of the
   answer (how many leads, which is most urgent, what to hold).

## Goal

Reshape the packet so each **awardee** is the unit. For every transitioning awardee,
list **every** open procurement it is relevant to — direct-award-possible first, then
competitive, soonest deadline first — under a BLUF header.

## Scope

**In scope (rendering only):**
- New pure helper `group_candidates_by_awardee` in
  `sbir_etl/reporting/procurement_transition/core.py`.
- Rework the markdown section builder to iterate awardee groups. HTML is derived from
  the markdown via `MarkdownIt`, so it follows automatically.
- BLUF header block.
- Regenerated `examples/army_science_technology_report.md` golden file.
- Unit tests for the grouping helper.

**Out of scope (unchanged):**
- `pairing.py`, `assets.py`, `similarity.py`, scoring weights/thresholds. The scored
  candidate frame is already award×opportunity many-to-many with a per-row score and
  HIGH flag; weaker matches already exist as non-HIGH rows and are simply hidden today.
- `phase_iii_candidates.parquet` schema (the pair-grained audit ledger stays as-is).
- Any new solicitation source or threshold relaxation.

## Design

### Data flow

```
scored candidates (award × opportunity rows, each with score + is_high)
        │
        ▼
group_candidates_by_awardee(scored_df, awards_df)  ── pure, testable
        │   → list[AwardeeGroup]
        ▼
render_markdown_packet(groups, month)  ── section per awardee
        │
        ▼
MarkdownIt → sanitized HTML   (existing path, unchanged)
```

### `AwardeeGroup` shape

A plain dataclass (or dict) per awardee — keyed by *firm* identity (UEI, else
normalized company name), so a firm holding several cohort awards is one
section and a procurement it reaches through more than one of them is listed
once:

- `award_id` (the representative award), `award_ids` (all of the firm's cohort
  awards), `company`, `award_title`, `phase`, `amount`, `abstract`
- `award_why_listed` (reuses existing `_award_why_listed`)
- `directed`: list of procurement matches, tier = direct-award-possible
- `competitive`: list of procurement matches, tier = competitive follow-on
- `watchlist`: below-threshold matches (kept, not dropped)
- each procurement match carries: title, notice type, response deadline,
  evidence facts (reuses existing `_public_field_facts`), source url

### Ordering rules

**Awardees:**
1. Awardees with ≥1 directed (direct-award-possible) match first.
2. Then by soonest procurement response deadline (min over the awardee's matches).
3. Then by award amount descending.

**Procurements within an awardee:**
1. Directed before competitive.
2. Soonest response deadline first.
3. Below-threshold matches demoted to a per-awardee "weaker — needs more evidence"
   sub-list (not removed).

### BLUF header

```
## Bottom line
- N awardees with M relevant open procurements (X could support a direct award).
- Most urgent: <awardee> — <procurement>, responses due <date>.
- Hold: <count> awardees have only weaker matches or none.

For any lead, confirm the new work "derives from, extends, or completes" the awardee's
prior SBIR/STTR work before anything moves. A match here is a starting point, not a decision.
```

The statutory test appears **once**, in the BLUF, and is not repeated per section.

### Edge cases

- **Awardee with zero matched procurements:** still listed, with
  "No open procurements matched this month." The rep sees the whole transitioning cohort.
- **Awardee with only watchlist matches:** listed under a "Hold — weaker evidence" grouping.
- **Empty packet (no awardees):** existing empty-state behavior preserved.

## Addendum — Potential transition paths table (2026-07-29)

Follow-on to the awardee-first reshape, same PR. Adds a headline
`## Potential transition paths` table placed after the Bottom line and before the
detailed awardee sections. One row per awardee→procurement path, illustrating the
transition: **awardee · what they built (plain) · possible next procurement (with
path type) · why it connects · respond-by**.

- **Plain "what they built":** deterministic leading-sentence trim (`_plain_abstract`)
  by default; an optional `abstract_simplifier: Callable[[str], str | None]`
  constructor hook upgrades the table cell to genuine plain language when wired to a
  model. Deterministic-by-default is preserved — no key, no behavior change. The
  detailed awardee section still shows the full real abstract as evidence; only the
  table cell is simplified.
- **Why it connects:** compacted reuse of `_public_field_facts` (shared NAICS/PSC,
  overlapping terms, lineage phrases).
- **Multi-path awardees:** company + built cells shown once, blank on following rows.
- **Zero-path awardees:** one row marked "— no matched procurement · ends <date>",
  folding in the award-pipeline's end-date value.

Rendering-only; no scoring/pairing/schema change. The standalone award-pipeline
table is retained.

## Addendum — collapse the body to tables + compact path blocks (2026-07-29)

Same PR. The verbose per-awardee sections (heavy six-subsection cards) are
replaced. The packet is now: **Bottom line → Potential transition paths (table)
→ Award pipeline (table) → Path details → Methodology.**

- **Path details** (`_path_details_section` / `_path_detail`) emits one compact
  block per path (`### <company> → <procurement> — <kind>, respond by <date>`)
  with four lines: **Asks for**, **Why it connects**, **Analyst note** (if any),
  **Validate**, plus **Sources**. `<kind>` is `direct-award` / `competitive` /
  `needs more evidence`. The optional AI comparison summary still renders here,
  gated by the score-ranked budget.
- The transition-paths table now includes watchlist rows tagged
  `(needs more evidence)`; only awardees with no match at all show
  "— no matched procurement · ends <date>".
- The full award abstract is dropped from the body; its leading sentence lives
  in the table's "what they built" cell and the full record is one click away via
  **Sources**. Cuts the synthetic example from ~291 to ~103 lines.

Rendering-only; no scoring/pairing/schema change.

## Addendum — evidence-specific Validate + Built-on context (2026-07-29)

Same PR. Two refinements to the path blocks:

- **`**Built on:**`** — each block now opens with the awardee's plain-language
  funded scope (`_plain_award_summary`), so the block carries its own technology
  context instead of relying on the table above.
- **Evidence-specific `**Validate:**`** — replaces the constant boilerplate
  (which was tautologically always true) with `_validate_line(row, signal)`,
  derived from the actual public fields: whether the notice names the awardee's
  UEI, the finest shared org level (office > organization > agency), and any
  lineage phrase present. Directed and competitive paths get different guidance;
  the always-true "a screening rank does not establish lineage" disclaimer is
  dropped from every row (it remains once in Methodology). Shared UEI/org logic
  is factored into `_notice_names_awardee` / `_matching_organization` and reused
  by `_public_field_facts` to avoid drift.

Deterministic; no scoring/pairing/schema change.

## Addendum — exclude notices that already name the awardee (2026-07-29)

Same PR. Domain correction: a SAM.gov *solicitation* does not name a specific
firm's UEI — only **award notices** and **sole-source justifications (J&A)** do,
and in both the agency has already decided. Such a pairing is therefore not a
forward transition path a representative would route.

- `group_candidates_by_awardee` now filters out any pairing where
  `_notice_names_awardee(row)` is true (the single chokepoint feeding both the
  table and Path details). The master audit ledger keeps every row — the
  exclusion is presentation-only.
- The "names the awardee's UEI → strong signal" branch is removed from
  `_validate_line` (unreachable once such rows are excluded). The remaining
  strength signal is the shared org level (office > organization > agency) plus
  lineage language.
- Fixture: the earlier contrived UEI-on-a-solicitation demo is reverted; the
  notices now carry `agency = "DEPARTMENT OF THE ARMY"`, so the example
  realistically exercises the **agency-level** match branch alongside the
  "extends" lineage branch.

## Testing

Unit tests (`tests/unit/reporting/test_procurement_transition.py` additions):
1. Directed-before-competitive ordering within an awardee.
2. Soonest-deadline ordering of procurements.
3. Awardee ordering (directed-first, then deadline, then amount).
4. Below-threshold match demoted to watchlist, not dropped.
5. Zero-match awardee still emitted.

Plus regenerate `examples/army_science_technology_report.md` and assert the renderer
reproduces it (golden test) so future drift is caught.

## Rejected alternatives

- **Inline grouping in the string builder** — loses unit testability of the ordering rules.
- **Push grouping into the parquet asset** — that frame is the pair-grained audit ledger;
  reshaping it would break the audit CSVs. Keep grouping in the presentation layer.
- **Relax thresholds / add sources** — a different concern (match coverage), not this
  reshape. Deferred.

## Consolidation

This work was built on PR #464, which already contained the work from PR #450. A
single PR against `main` therefore carried all three bodies of work. PRs #450 and
#464 were superseded by the consolidated PR.
