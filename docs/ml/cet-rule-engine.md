# CET Rule Engine

The CET classifier (`sbir_ml.ml.models.cet_classifier.CETClassifier`) produces a
0–100 score per CET area from a calibrated TF-IDF → logistic-regression pipeline.
A **rule engine** (`sbir_ml.ml.models.rule_engine.RuleEngine`) then post-processes
those scores using editable YAML rules, so analysts can tune classifications
without retraining.

## How rules compose with the ML classifier

After ML scoring, `RuleEngine.apply_all_rules(scores, text, agency, branch)`
**overwrites** the score dict, applying three passes in order:

1. **Negative-keyword penalty** — each matched negative keyword multiplies that
   CET's score by `0.7` (30% cut, compounding). Negative keywords come from the
   taxonomy (`CETArea.negative_keywords` in `taxonomy.yaml`), **not** from
   `classification.yaml`.
2. **Context rules** — keyword-combination boosts (additive, clamped to 100).
3. **Agency/branch priors** — additive boosts by funding agency/branch (clamped to 100).

## Tuning `config/cet/classification.yaml`

The rule-engine inputs live in two blocks of `config/cet/classification.yaml`
(the rest of the file is ML hyperparameters):

```yaml
priors:
  enabled: true
  agencies:
    National Science Foundation:
      _all_cets: 5            # boost every CET for NSF-funded awards
      artificial_intelligence: 8
  branches:
    "Air Force":
      hypersonics: 10

context_rules:
  enabled: true
  artificial_intelligence:
    - keywords: ["neural", "network"]   # ALL must appear (AND)
      boost: 15
```

- **Boost/penalize an agency or branch** → edit `priors.agencies` / `priors.branches`
  (use the special key `_all_cets` to boost every area).
- **Disambiguate keyword collisions** → add `{keywords, boost}` entries under
  `context_rules.<cet_id>` (all listed keywords must appear).
- **Toggle a whole rule class** → `priors.enabled` / `context_rules.enabled`.
- **Adjust negative-keyword penalties** → edit per-CET `negative_keywords` in the
  taxonomy YAML, not here.

CET IDs used as keys must match the taxonomy.

## Patent keywords

`config/cet/patent_keywords.yaml` (`cet_keywords: {<cet_id>: [phrase, ...]}`) feeds
the separate **patent feature extractor**, not the rule engine. Edit it to improve
patent-side CET recall; keys must match taxonomy IDs.

## Related

- [CET classifier](cet-classifier.md)
- [CET integration](cet-integration.md)
- [CET award training data](cet-award-training-data.md)
