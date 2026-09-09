# M&A discovery recall — held-out 1501 protocol

Epistemic tier: exploratory until the gates below pass and evidence-auditor
does not BLOCK a rank flip. This note is the measured protocol for pairs
**1501–2500**. It does not rewrite [design.md](design.md) or
[confirmatory-design.md](confirmatory-design.md).

The 200-pair envelope in design.md remains a failed preregistered validation
(recall 9<10). The 501–1500 confirmatory freeze is an exploratory record;
evidence-auditor BLOCKED promoting it because freeze-before-run was not
shown. Do not evaluate a rewritten gate on either freeze.

Hash this file and [held-out-1501.yaml](held-out-1501.yaml) into
`study.yaml` **before** any Brave or LLM call on pairs 1501+.

Intended study rank if the gates pass and evidence-auditor does not BLOCK:
`validated`. Materialization stays closed. Inventory F2/A4 is not edited.
`citable` is out of scope.

## Estimand (strict)

Among Form-D-missing rows in the pinned `data/sbir_ma_events.jsonl` cut that
name an acquirer **and whose existing event is not already**
`confidence in {medium, high}`, count distinct `(company, acquirer)` pairs
after `CompanyNameProfile.RECIPIENT_V1` that a web-search snippet extractor
confirms at medium or high confidence and that C3 inserts or promotes, as of
the run as-of date.

Non-detection is not proof of no acquisition. The count is not an SBIR exit
rate, not a foreign-acquirer finding, and not a section-level answer to
inventory F2 or A4.

The estimate is wrong if any of the following hold:

- the snippet cut or LLM freeze is not the declared input;
- an LLM call is live on the rerun path;
- pair identity uses any normalizer other than `RECIPIENT_V1`;
- C3 overwrites a Form D acquirer;
- fixture `mock` hits are mixed into the measured run;
- this cut overlaps pairs 1–1500 (pilot or confirmatory).

## Cut

- Order: `query_rows_from_events` on the pinned events file (file order).
- Skip the first **1,500** unique pairs (pilot 1–500 and confirmatory 501–1500).
- Keep the next **1,000** unique pairs (pairs 1501–2500).
- One query template:
  `"<RECIPIENT_V1 company>" acquired by "<RECIPIENT_V1 acquirer>" press release`.
  Not the four templates in `generate_queries`.
- Finish all 1,000 even if the recall floor is met early. Do not enlarge
  this cut after seeing the outcome.

Events pin: `data/sbir_ma_events.jsonl` sha256
`6ffc8481a240b2ee9bd9fdef806395d3f62e9d1f3ba12a68490d28fb53a1cf49`
(n=4306). Output directory:
`data/processed/ma_discovery_heldout_1501` (gitignored).

## Stop rule

For each pair, send search hits to the extractor until a **dated** confirm
(medium or high) or hits are exhausted. Skip hits with no snippet and no URL.
If every confirming hit is undated, keep one low-confidence confirm (first
undated confirm). This differs from the pilot’s first-confirm-wins rule.

## Gates

All three; no extra conjuncts.

1. **Recall.** ≥10 distinct **strict** medium/high C3 insert-or-promote pairs
   (existing event not already medium/high).
2. **Precision.** Label all medium rows if fewer than 20. Human
   `true` / `false` / `ambiguous` against the stored snippet and URL.
   FP = `false / (true + false)` ≤ 0.25. Ambiguous excluded from the
   denominator and reported.
3. **Cost.** Search + LLM ≤ $0.10 per candidate pair at list Brave Search
   ($5/1k) and OpenRouter/xAI grok-4.6 ($2/1M input, $6/1M output). Monthly
   vendor credits are not subtracted. No $5 absolute cap. No
   `--max-candidates 200`.

A run that fails any of the three does not promote. Do not restate the
envelope after a miss.

## Capture

Live Brave or `--capture-llm` must use
`--protocol studies/ma-discovery-recall/held-out-1501.yaml`. The CLI refuses
that call unless this note and the YAML are in `HEAD` and pinned in
`study.yaml` `frozen_artifacts`, the flags match the YAML, and
`--fail-on-gate` is on (implied by `--protocol`).

## Rerun

- Search backend: `snippets` over the frozen JSONL.
- Confirmer: freeze-only LLM extractor. No API key. Missing freeze row is
  unconfirmed and must not call the network.
- SHA mismatch on events, snippets, or LLM JSONL vs the held-out run
  manifest: non-zero exit.
- Kill-gates are written in the same process as the summary. Failed recall
  or completed-precision gate: non-zero exit. Incomplete labels keep
  `accepted: false` and are not a recall failure.

## Capture-code provenance

**Correction, 2026-09-08.** An earlier version of this section, frozen at
sha256 `ca17ba0dcd031c6987dcebd0b887f256d56a5cda959a6a0d856f917a5df088fb`,
said that no Brave call and no LLM call had touched pairs 1501+ when commits
`5fdccb7c` and `e64be572` changed the capture path. That was false. A capture
ran from 09-07 11:58 to 09-08 02:15 and covered 948 of the 1,000 cut pairs.
It preceded those commits and both rewrites of this section (`1fc7d936`,
`bb7c2ac3`). The superseded hash is recorded here so the error stays visible.

Freeze-before-run holds for this note **as hashed at `0023e204`**, which
preceded the capture. It does **not** hold for this note as now frozen. The
estimand, cut, stop rule, and the three gates are byte-identical across every
version; what changed after data existed is the validity precondition, which
decides whether a recall miss counts as a miss. Rewriting that rule with
948/1,000 pairs on disk is the same structural defect that blocked this study
on 2026-09-02. This cut does not promote on any reading.

The change counts network faults. It does not score them as evidence.
Before it, a failed search recorded an empty hit. An LLM timeout recorded an
unconfirmed verdict and wrote no freeze row. Both look identical to a true
negative, in the summary and in the replay. Either one lowers recall with no
trace. `sample_run_summary.json` now reports `search_failure_n`,
`llm_timeout_n`, and `kill_gate.fully_measured`.

### Validity precondition

A fault cannot manufacture a confirmed **hit**: pairs are processed
independently, and a timeout drops one hit without aborting the pair.

That is not the same as monotonicity of the gated quantity, and an earlier
version of this note wrongly asserted it was. `strict_medium_high_n` is
**not** monotone in the discovered set. `apply_c3` matches on the company key
alone and credits a promotion to the existing row's pair key, so a fault can
raise strict recall. A counterexample was executed against the real
`apply_c3` on 2026-09-08: two events on one company key gave
`strict_medium_high_n` 0 with both discoveries present and 1 with one search
faulted. Exposure in this cut is bounded: 3 company keys carry more than one
acquirer, covering 6 pairs.

Treat the rules below as a bounded operating convention, not a proof.

This is not a fourth gate. It cannot promote a run and it cannot excuse a
fully measured miss.

Apply these rules:

- Accept a recall pass that carries faults. True recall is at least the
  observed count. Report the fault counts with the result.
- Treat a recall miss that carries faults as not measured. It is not a miss.
- Retry the faulted pairs only. Do not re-query clean pairs.
- Treat a fully measured recall miss as a miss. Do not retry it.
- Do not enlarge the cut after a retry.
- Do not move to pairs 2501+ after a retry.

A faulted search writes a row marked `fault`. `load_recorded_queries` does
not freeze that query, so a retry re-queries the faulted pairs only. A
genuine zero-hit row does freeze: Brave answered.

A row marked `unverified_empty` also does not freeze its query. That marker
covers empty rows captured before fault marking existed, where a genuine zero
hit and a swallowed fault cannot be told apart. It was added in `f34266c5`
and applied to 476 rows of this cut **after** those rows existed, which is
why this cut cannot promote: retry eligibility must be pre-specified, and
here it was not. Any future protocol must declare both markers before
capture.

The retry rule is a one-sided ratchet — a pass carrying faults is accepted, a
miss triggers a retry that can only add. That is safe only while retry
eligibility is observation-independent. Do not add a further retry class
after a capture.

Faults do not affect gate 2. A fault removes a candidate row. It does not
create a confirmed row. Label the medium rows that exist.

Faults lower measured cost per pair, so a gate 3 pass under faults is not
conservative. Compute gate 3 from the run after the retry.

## Out of scope

Inventory Status edits (`docs/research-questions.md`). `capital_events` /
Neo4j writes. Citable claims. Foreign-acquirer findings. Exit rates.
Changing C3’s ±30-day window (strict count is the filter). Restating gates
after seeing pairs 1–1500.
