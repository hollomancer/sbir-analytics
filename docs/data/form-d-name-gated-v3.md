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
  a minimum score. It refuses an index that has no recorded `name_score`, under any rule.

## Person signal

A PI name and a related-person name agree when all of these conditions are true:

1. The family names are equal. When one name is written "Family, Given", all tokens before the
   comma are the family name, and the other name must end with the same tokens ("Lee Wong, John"
   agrees with "John Lee Wong" and does not agree with "Lee Chen, John" or "John Wong").
2. The given names (first tokens) are equal, or one given name is an initial of the other.
3. If both names have a middle name, the middle names are equal or initial-compatible. A middle
   name on one side only does not block agreement.
4. If both names have a generational suffix (Jr., Sr., II, III, IV, V), the suffixes are equal.
   A suffix on one side only does not block agreement.

Before the comparison:
- Titles ("Dr."), credentials ("P.E.", "Ph. D.", "M.S.", "RN", "CPA"), job titles ("CEO",
  "President", "Founder"), parenthesized text ("(Retired)"), and punctuation are removed. A
  credential or job title is never the family name.
- Short forms that are also surnames ("Ma", "Do", "Ba") are removed only when they are dotted
  ("M.A.") or follow a comma. "Wei Ma" keeps "Ma" as the family name.
- Accents are folded ("García" becomes "garcia"), and ø, æ, ł, and ß are transliterated. A name
  that still holds a non-ASCII letter is not read, and it does not agree with any name.
- In-word hyphens and apostrophes are dropped, so "Smith-Lee" stays one token and does not agree
  with "Lee".
- A name that joins two people with "&" or "and" is not read. A missing name is not read. A name
  that is not read is no evidence and does not agree with any name.

A nickname ("Bob" against "Robert") does not agree. This rule accepts some false negatives so
that a different person with the same family name does not match. `person_score` is 1.0 when
one pair agrees, else 0.0.

## Tier rule

A missing state, ZIP, or person signal is no evidence. It never raises a tier.

| Name match | high | medium | low |
|---|---|---|---|
| exact | exact ZIP, or person and state | person, or state | all other cases |
| fuzzy | exact ZIP and person | exact ZIP, or person and state | all other cases |

A state agreement is not independent of a ZIP agreement, so it cannot be the second signal for
a fuzzy ZIP match.

## Adoption

- `name-gated-v3` is in `FORM_D_TIER_RULE_VERSIONS`.
- On 2026-11-21 the owner adopted `name-gated-v3` as the default `FORM_D_TIER_RULE_VERSION`.
  `corroborated-person-v2` and `person-or-zip-v1` stay in `FORM_D_TIER_RULE_VERSIONS`, so old
  materializations stay interpretable. They are historical rules.
- Consumers reject a record whose rule is not the default. A `form_d_details.jsonl` built under
  `corroborated-person-v2` stops every consumer, including the Dagster asset
  `agency_private_capital_form_d_matched_comparison`. The error names the rebuild commands.
- Merge the default change only after the server rebuild under `name-gated-v3` is complete and its
  output hashes are recorded.
- To rebuild: run `fetch_form_d_index.py`, then `fetch_form_d_details.py --rule-version
  name-gated-v3`. Then rebuild every file derived from `form_d_details.jsonl` and rematerialize
  the dependent assets.
- `rescore_form_d_details.py` refuses `name-gated-v3` as a target. The stored records do not
  have the name match type or the raw PI names, so an offline migration would have to guess. The
  script has no default target rule. It only reproduces a named historical rule.
- It also refuses to relabel a v3 record to an older rule. v3 stores a 0/1 person score, and the
  older rules expect a fuzzy score.
- `fetch_form_d_details.py` now scores under v3 by default. It refuses an index without
  `name_match_type`, so an index built before v3 must be rebuilt.

## Not verified

- `token_sort_ratio` at 0.85 rejects the token-subset pairs. It still accepts 6 of the 9 shared
  near-collision pairs in `tests/unit/identity/test_company_names.py` (for example "adelphi
  technology" against "adept technology"). The tier rule, not the name score, holds these at
  low.
- The 0.85 threshold on `token_sort_ratio` is carried over from the old rule. It was not
  calibrated.
- The audit's blind review was done by the analysis agent and was not adjudicated.
