"""Configuration loading utilities.

Epistemic tier: primitives. All configuration access goes through this
package's loader and schemas; behavior that changes loaded values is a
versioned change, never an edit in place.
"""

EPISTEMIC_TIER = "primitives"
