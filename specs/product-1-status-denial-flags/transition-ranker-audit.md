# Transition Ranker — Precision@K Hand-Audit

> **Status:** Sample drawn; awaiting human review. Validates the fusion transition ranker
> ([transition-ranker-fusion.md](./transition-ranker-fusion.md), held-out AUC 0.809) at the metric
> that actually governs a lead tool — **precision@K on reviewed leads** — not AUC. Analogous to the
> 191-flag [validation-plan.md](./validation-plan.md).

## Why this, not AUC
AUC summarizes the *whole* ranking; a lead tool only ever shows the **top few**. A 0.75-AUC model with
a clean top can beat 0.85-AUC with a muddy top on precision@K. The operational bar is the
`phase-3-solicitation-alerts` **≥85% precision** on flagged leads — measurable only by hand-audit.

## The sample
`scripts/phase3_benchmark/pc_audit_sample3.py` (seed 20260716) → 40 random firms, ranked by the
**deployable AWARD-LEVEL model (AUC 0.844)**, **out-of-fold** (each firm scored by a fold's model that
did **not** train on it — no optimism). For each firm the ranker scores the full 273-notice pool; the
**top-3** are surfaced → **120 review rows** in `data/derived/phase3_transition_leads_audit.csv` (gitignored).

**Each row is a concrete transition claim: a specific Phase I/II SBIR AWARD → the funding EVENT** — the
award the model matched (contract#/topic cited by the notice, `id_cited` 21/120, else max abstract sim
99/120). Columns: `firm_name, rank, model_score, award_link` | **SBIR side:** `sbir_phase, sbir_award_year,
sbir_award_title, sbir_contract, sbir_topic, sbir_abstract_snippet` | `gap_years` (per-award transition
lag) | **event side:** `notice_year, notice_text_snippet` | reviewer fields. The reviewer verifies the
*linkage* (does the event continue *that award's* work), judging **technical continuity, not the gap**.
Pre-audit vs code labels: **precision@1 55%, recall@3 65%**.

**Finding (surfaced by the award linkage):** the firm-level ranker sometimes attaches a transition to a
weak originating award — but the diagnostic must be **technical continuity, not elapsed time.** True lag
from the *originating* award (ID-cited subset, n=40, most reliable) is **median ~6y, p75 11y, 50% >6y**,
long tail into 15–20y (the earlier "18y" was gap-to-earliest-award — an artifact of firm SBIR longevity,
not transition lag). So a 2005 award → 2020 notice is in the *tail*, uncommon but real (emerging/deep tech
matures over 10–20 yrs) — not implausible. Only *tech-mismatch* cases (e.g., XML-security award →
airborne-relay notice) are suspect, not long-gap ones. **Reviewers judge whether the event continues the
award's WORK, ignoring the gap.**

→ **Design refinement: match at the AWARD level** (specific abstract → notice), yielding a per-award gap as
a *continuous/soft* feature with **no tight upper bound** (long lags are valid). Improves accuracy and makes
every prediction an inherently verifiable award→event claim.

## Reviewer instructions
For each surfaced notice, judge **from the text** whether it is genuinely **this firm's SBIR Phase III
transition** (its work continued into that funding agreement). Set `transition_confirmed`:
- `Y` — genuine transition for this firm;
- `N` — not this firm's (a text-confusable other-firm notice) or not a real transition;
- `unclear` — insufficient info.
Record `reviewer` + `notes`. Judge independently first; `notice_owner_is_this_firm` is a hidden answer
key (code-label attribution) for computing human-vs-label agreement — **don't read it before judging**.
The audit can catch *both* false positives (top pick is a different firm's notice) and **label-missed
wins** (a notice genuinely the firm's transition that the SR3 coding didn't attribute → `owner=0` but `Y`).

## Metrics (computed after review)
- **precision@1** = confirmed `Y` among rank-1 rows, Wilson 95% CI, vs the ≥85% target.
- **precision@3 / recall@3** = firm has ≥1 confirmed `Y` in its top-3.
- **MRR**; **human-vs-code-label agreement** (does the ranker surface transitions the coding missed?).
- Pre-audit (vs code labels only): precision@1 **52%**, recall@3 **60%** — the human review is the truth.

## Operating-point analysis (Task A, `pc_operating_point.py`, vs code labels)
Out-of-fold scored EVERY firm×notice pair at realistic imbalance (**0.8% base rate**, 198 true / 25,344).
As a **global auto-flagger** it hits the base-rate wall: AP 0.155; precision tops ~0.31 (score≥0.70);
**precision ≥0.85 only at score=1.00, recall 0.04**. Two reasons this is a pessimistic LOWER bound, not
the deployment number:
1. **Measured vs the CODE labels, which undercount** (the project's premise). Confirmed label-missed wins
   (e.g. INTELLISENSE, BENTHOS marked `Y` but `owner=OTHER`) count here as false positives → true
   precision is higher; only the human audit reveals it.
2. **Global threshold ≠ how we deploy.** The tool ranks **per firm** and shows **top-K**; there the
   ranking floats the true one up (precision@1 55% vs code, not 0.8%). Per-firm top-K exploits the
   ranking within a firm; a global threshold pools all firms and drowns in the base rate.
**Conclusion:** deploy as a **per-firm lead ranker** (analyst reviews each firm's top-K — viable), **not a
universe-wide auto-flag** (base-rate wall). precision@K (this audit), not global precision, is the metric.

## Scope / honest limits
- The candidate pool is the **273 recovered Phase III notices** (all real Phase III), so this measures
  **attribution precision** ("is this the *right firm's* transition") — a necessary condition — **not**
  discrimination of Phase III from a firm's *routine* contracts. A fuller deployment audit would add
  non-Phase-III candidates; blocked on rich text for routine contracts (the linkage wall).
- Conditional on the **recoverable segment** (firms with a posted notice + rich text); not the full
  transition population (sole-source-without-J&A firms absent).
