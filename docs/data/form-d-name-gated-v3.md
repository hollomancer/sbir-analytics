# Form D tier rule `name-gated-v3`

**Tier:** `pipelines`. The rule is deterministic and makes no inference beyond the stated
signals. A tier is a match-strength label. It is not identity validation.

**Reason.** The Form D matcher audit (branch `research/form-d-matcher-audit`, commit
`0ae85ff6`) found these defects in the Form D name match and tier rule:

- The index matcher used `token_set_ratio`. That score is 100 when the tokens of one name are a
  subset of the tokens of the other name ("space kinetic" against "space").
- The index matcher kept the first candidate at or above 85, not the best candidate.
- `form_d_index.jsonl` did not record the match type or the score. The detail fetch then set
  every name score below 0.85 to 0.85.
- A missing filing state counted as neutral. A name-only record with no parsed offering got the
  medium tier.
- The PI-to-officer person score also used `token_set_ratio`.
- An exact ZIP alone gave the high tier, also for a fuzzy name. In the audit review, 5 of 50
  such matches were likely different firms.

## Name match

- Normalize both names with `sbir_etl.identity` profile `RECIPIENT_V1`.
- An exact match is equal normalized names.
- For a fuzzy match, score every candidate in the block with `token_sort_ratio`. This score does
  not reward a subset.
- Keep the best candidate at or above 0.85. If two candidates have the same score, keep the
  candidate that sorts first.
- Write `name_match_type` (`exact` or `fuzzy`) and `name_score` to each index record.
- The detail fetch uses these stored values. It does not rescore the name, and it does not set
  a minimum score.

## Person signal

A PI name and a related-person name agree when both conditions are true:

1. The family names (last tokens) are equal.
2. The given names (first tokens) are equal, or one given name is an initial of the other.

Titles, generational suffixes, and punctuation are removed first. Accents are folded ("García"
becomes "garcia"). In-word hyphens and apostrophes are dropped, so "Smith-Lee" stays one token
and does not agree with "Lee". A nickname ("Bob" against
"Robert") does not agree. This rule accepts some false negatives so that a different person
with the same family name does not match. `person_score` is 1.0 when one pair agrees, else 0.0.

## Tier rule

A missing state, ZIP, or person signal is no evidence. It never raises a tier.

| Name match | high | medium | low |
|---|---|---|---|
| exact | exact ZIP, or person and state | person, or state | all other cases |
| fuzzy | exact ZIP and person | exact ZIP, or person and state | all other cases |

A state agreement is not independent of a ZIP agreement, so it cannot be the second signal for
a fuzzy ZIP match.

## Adoption

- `name-gated-v3` is added to `FORM_D_TIER_RULE_VERSIONS`.
- The default `FORM_D_TIER_RULE_VERSION` stays `corroborated-person-v2` in this change.
  Consumers reject a record whose rule is not the default. If the default changes before
  `form_d_details.jsonl` is rebuilt, every consumer stops, including the Dagster asset
  `agency_private_capital_form_d_matched_comparison`.
- `rescore_form_d_details.py` refuses `name-gated-v3` as a target. The stored records do not
  have the name match type or the raw PI names, so an offline migration would have to guess.
- It also refuses to relabel a v3 record to an older rule. v3 stores a 0/1 person score, and the
  older rules expect a fuzzy score.
- To adopt v3: rerun `fetch_form_d_index.py`, then `fetch_form_d_details.py --rule-version
  name-gated-v3`. Then change the default in a separate change.

## Not verified

- `token_sort_ratio` at 0.85 rejects the token-subset pairs. It still accepts 6 of the 9 shared
  near-collision pairs in `tests/unit/identity/test_company_names.py` (for example "adelphi
  technology" against "adept technology"). The tier rule, not the name score, holds these at
  low.
- The 0.85 threshold on `token_sort_ratio` is carried over from the old rule. It was not
  calibrated.
- The audit's blind review was done by the analysis agent and was not adjudicated.
