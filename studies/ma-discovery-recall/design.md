# M&A discovery recall — frozen method

This is the method note for `studies/ma-discovery-recall`. It does not
authorize citation. It does not authorize a `reproducible` or `validated`
rank until the blockers in `study.yaml` are cleared.

## Estimand

Among Form-D-missing rows in a pinned `sbir_ma_events.jsonl` cut that name an
acquirer, count distinct `(company, acquirer)` pairs that a web-search snippet
extractor confirms at **medium or high** confidence and that C3 would insert or
promote, as of the run's as-of date.

Non-detection is not proof that no acquisition occurred. The count is not an
SBIR exit rate, not a foreign-acquirer finding, and not a replacement for the
Form D / EFTS detector.

The estimate is wrong if any of the following hold:

- the search index or snippet cut is not the declared input;
- an LLM call is live on the rerun path (responses must be frozen, or the
  confirmer must be the keyword extractor);
- pair identity uses any normalizer other than `CompanyNameProfile.RECIPIENT_V1`;
- C3 overwrites a Form D acquirer;
- fixture `mock` hits are mixed into a measured run.

## Population and grain

- **Population:** rows in `data/sbir_ma_events.jsonl` with a non-empty
  `acquirer` and no `form_d_detail`.
- **Grain:** `(company_name, acquirer)` after `RECIPIENT_V1` normalization.
- **As-of:** the timestamp recorded in the run summary.

## Method

1. Generate the four query templates in `queries.generate_queries`.
2. Search with a declared backend. For a rerun, the backend is `snippets`
   over a frozen JSONL of `{query, snippet, link}`. Live Tavily/Brave is a
   one-time capture, not the reproducible path.
3. Confirm snippets with a declared extractor. Keyword is deterministic and
   cannot emit medium/high (no date). LLM confirmation is allowed on the
   measured path only when every model response is stored as an artifact.
4. Assign confidence from the design table: date+value+≥2 sources → high;
   date present → medium; otherwise low.
5. Join onto existing events with C3 (`apply_c3`): ±30-day date window;
   company-only match when the existing `event_date` is missing; never lower
   confidence; never overwrite a Form D acquirer.

## Validation design (required for `validated`)

Preregistered before the measured run:

1. **Recall floor.** The run must insert or promote ≥ 10 distinct medium/high
   pairs in the Form-D-missing population that the Form D / EFTS detector did
   not already carry at medium/high with `discovery_confirmed`.
2. **Precision cap.** Draw a stratified sample of 20 medium-confidence *new or
   promoted* rows (or all of them if fewer than 20). A human labels each
   `true` / `false` / `ambiguous` against the stored snippet and URL.
   False-positive rate = `false / (true + false)`. Pass if that rate is ≤ 0.25.
   Ambiguous rows are excluded from the denominator and reported.
3. **Cost cap.** Search + LLM cost ≤ $0.10 per candidate pair, and the run
   stays inside `--max-candidates 200` and `--max-cost-usd 5`.

A run that fails any of the three does not promote. The labels are the
validation artifact; they are not an extractor.

## Rerun

Re-running requires the frozen snippet cut (and frozen LLM responses if used),
the pinned events file, and `apply_c3` / `assign_confidence` /
`process_batch` at the implementation references in `study.yaml`.
