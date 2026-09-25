# M&A snippet extractor fixtures

Frozen, synthetic press-style snippets for the exploratory extractor eval.
No live web results and no real PII. Labels are hand-written for the
committed text, not measured recall on Form-D-missing firms.

Used by `sbir_etl.enrichers.ma_discovery.extractor_eval` and
`tests/unit/enrichers/ma_discovery/`.

| Category | What it probes |
|---|---|
| `slam_dunk` | Both names, a completed-deal verb, and usually a date |
| `negative` | Same-industry news with no deal |
| `rumor` | Talks / potential / exploring — must not confirm |
| `suffix_mismatch` | Legal suffix on the query names, stripped in the snippet |
| `case_mismatch` | Letter-case only |
| `missing_date` / `missing_value` | Completed deal with one field absent |

`expected_confirmed` is required. Date and value are optional gold fields.
