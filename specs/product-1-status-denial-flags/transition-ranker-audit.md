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
`scripts/phase3_benchmark/pc_audit_sample.py` (seed 20260716) → 40 random firms, **out-of-fold** scored
(each firm ranked by a fold's model that did **not** train on it — no optimism). For each firm, the
ranker scores the full 273-notice Phase III pool; the **top-3** are surfaced → **120 review rows** in
`data/derived/phase3_transition_leads_audit.csv` (gitignored). Columns: `firm_uei, firm_name, rank,
model_score, firm_abstract_snippet, notice_type, notice_year, notice_text_snippet` + reviewer fields.

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

## Scope / honest limits
- The candidate pool is the **273 recovered Phase III notices** (all real Phase III), so this measures
  **attribution precision** ("is this the *right firm's* transition") — a necessary condition — **not**
  discrimination of Phase III from a firm's *routine* contracts. A fuller deployment audit would add
  non-Phase-III candidates; blocked on rich text for routine contracts (the linkage wall).
- Conditional on the **recoverable segment** (firms with a posted notice + rich text); not the full
  transition population (sole-source-without-J&A firms absent).
