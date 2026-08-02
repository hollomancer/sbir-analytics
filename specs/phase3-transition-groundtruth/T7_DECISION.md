# T7 — Decision Memo: Can the fusion ranker order the procurement packet?

**Decision: NO — deadline-primary. Use fusion as a top-3 surfacing aid, not the sole
orderer and not a gate.** Evidence below, in plain language first.

---

## Plain-language summary (read this first)

We built a tool (the **ranker**) that guesses which small companies are likely to win a
follow-on government contract, and uses those guesses to **order** the monthly packet —
best bets on top. The question this memo answers: can we trust it to do that ordering?

**The problem we had to fix first.** Until now, the only answer key we could grade the
ranker against was **built by the same pipeline that feeds it** — grading its own
homework. If the system had a blind spot, the answer key had the same blind spot, so a
good score could be good for the wrong reason. That self-graded score is the **proxy**.

**What we did.** We collected **293 real transitions from outside sources** — agency
press releases, DARPA success stories, and actual signed contracts in the federal
spending database. Nobody in our pipeline touched those, so they're an **independent**
answer key we can trust. We balanced them across agencies (Navy went from 85% of the
set down to ~50%) so the score wouldn't just reflect one branch.

**What we found.** Graded against the real answers, the ranker gets the right company as
its **#1 pick 47% of the time** (`p@1 = 0.467`) and somewhere in its **top 3, 56% of the
time** (`p@3 = 0.556`). Blind guessing would be ~10%. So it has real skill — but it's
coin-flip territory, not lock-it-in territory. Its self-graded proxy had claimed **68%**
(`0.681`); the honest number is **21 points lower**. The proxy was flattering itself —
exactly the suspicion that started this work.

**Why it's mediocre — and it's not what we feared.** We worried the test was
Navy-skewed. It wasn't. The real dividing line is **how much text a contract record
contains.** The ranker works by comparing words; when a contract's entire official
description is "SBIR PHASE III AWARD." there are no words to compare and it's flying
blind. Rich-text contracts (sensing/optics) score **0.60**; near-empty ones
(logistics) score **0.21**. The ceiling here is **missing data in government records,
not the algorithm.**

**What we decided.** Trust it to *suggest*, not to *decide*. Order the packet by the
simple, reliable, human-obvious rule — **which opportunities close soonest**
("deadline-primary") — and let the ranker flag a few likely candidates in the top 3 for
a human to check. It is not accurate enough to fully sort the list, and nowhere near safe
enough to silently *drop* companies (a "gate"), where one wrong drop hides a real
opportunity.

This is a good outcome: the packet now has an evidence-backed answer to "can we trust the
model to reorder our leads?" — *suggest, don't decide* — instead of the model's opinion
of itself.

---

## The numbers (full detail in `T6_RESULTS.md`)

| test | p@1 | p@3 | MRR |
|---|---|---|---|
| **Independent, balanced (headline)** | **0.467** [0.33, 0.62] | 0.556 | 0.588 |
| self-graded proxy (what it claimed) | 0.681 | — | — |
| blind guessing | ~0.100 | — | — |

- **By text richness:** sensing 0.60 · medical 0.50 · **logistics 0.21**; thin-desc 0.29.
- **Hardest case** (pick the true contract out of the firm's *own* portfolio): p@1 0.33,
  p@3 0.83 — it finds a top-3 band but can't nail the exact one.
- n = 45 scored (of 293 collected; most lack a usable contract identifier or text —
  see coverage/drop log in `T6_RESULTS.md`).

## What would make it more trustworthy (priority order)

1. **Enrich the candidate text** — pull J&A justifications, solicitation notices, SBIR
   topic text, PSC/NAICS expansions so near-empty contract records have real words to
   match. Directly attacks the measured cause (logistics 0.21). *Highest leverage.*
2. **Add non-text features** — firm award lineage, agency/topic continuity, timing gap,
   NAICS ancestry — signals that survive empty descriptions.
3. **Collect verified negatives** — companies that looked promising and did *not*
   transition. The missing ingredient to ever justify a *gate* (dropping leads).
4. **Bake-off on the new answer key** — compare embeddings vs word-matching and
   re-calibrate on real labels (held-out fold), now that an independent set exists.
5. **Trust it only where earned** — deploy the model in the rich-text conditions it's
   proven (≈0.60) and defer to deadline elsewhere.
6. **More labels** — 45 cases → wide CI (0.33–0.62); more independent cases sharpen it.

None of the top items is "tune the model." The leverage is in the **data**.

## Documented limitations (not hand-waved)

- **Notice-grained validation gap.** The packet ranks *notices*; our ground truth is
  *contracts*, and there's no PIID→notice mapping (Phase III sole-source awards often
  have no competing solicitation). A notice-grained independent test is future work.
  (The retired "Path B" scored proxy labels on a 91%-Navy slice — not a real validation.)
- **No forward validation.** All of this ranks a *retrospective* set where the true
  transition is present by construction. It does not validate use on *open* solicitations
  where nothing has transitioned yet — a separate effort.
- **Minor cleanups:** 2 SimVentions rows carry bare IDV order numbers (not unique keys);
  Anduril/EpiSci OT→SBIR lineage still to confirm.
