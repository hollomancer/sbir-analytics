# NASA TechPort: source and linkage protocol

Status: **puller fixture-tested; transition labels and empirical AUC not validated.**

TechPort is a public project portfolio, not a Phase III contract register.
Projects with no SBIR phase are unlabeled NASA projects, not inferred Phase III
transitions. A firm's presence on a project can also be lead, recipient, or
supporting participation; those roles must remain distinct.

## Required handling

- Preserve organization ID, name, type, and lead/support role together with
  phase, program, dates, TRL, and outcomes.
- Resolve a name only when it maps uniquely to one UEI. Ambiguous normalized
  names remain unresolved and are counted in the manifest.
- Preserve total search hits before applying a limit. A bounded pull is never
  marked complete for the full search.
- Treat any historical NASA AUC as a portfolio-topicality proxy until targets
  are linked to known Phase III records or independently adjudicated lineage.

The earlier 0.879 and 0.828 values are retained only as provisional history in
`provisional-results.json`; the corrected puller does not reproduce them.
