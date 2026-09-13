"""Default constraints sent with a frozen study bundle.

Study-specific replacement files override this text. The Edison adapter must
not embed SBIR rules of its own; it ships whatever the bundle contains.
"""

EPISTEMIC_TIER = "exploratory"

DEFAULT_CONSTRAINTS = """\
# External analysis constraints

These rules apply to this run. They travel with the frozen bundle; they are
not the study contract, and they do not make the result citable.

- Treat supplied identifiers as authoritative.
- Do not perform new entity resolution unless explicitly requested.
- Do not reinterpret supplied Phase III classifications.
- Do not modify source data.
- Distinguish descriptive association from causal inference.
- Document transformations and exclusions.
- Report missing-data assumptions.
- Treat all conclusions as exploratory.
- Do not claim that provider output is validated or citable.
"""
