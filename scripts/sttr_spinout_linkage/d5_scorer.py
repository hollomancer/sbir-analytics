"""D5 text-trail scorer for the STTR spinout-linkage RQ1 cascade.

Scores `kernel.D5TextTrail` for one award from a frozen, hand-curated v1
phrase lexicon (`data/reference/sttr_spinout_linkage/d5_phrase_lexicon_v1.json`)
searched over the award abstract -- the only text source the D1 spine
(`d1_spine.load_d1_spine`) actually supplies. design.md's D5 row also names
"firm text" as a source; no firm-text field exists on the D1 spine this
scorer consumes, so searching one is not invented here (see the lexicon
file's `scope_note`).

Per O-4 (`specs/sttr-spinout-linkage/open-questions.md#o-4`): a small,
frozen, hand-curated lexicon ships in v1; this module performs deterministic
case-insensitive regex/substring matching only -- no fuzzy matching, no ML
text classifier.

What this module does NOT do: it does not assemble the cascade
(`kernel.classify_linkage` takes the `D5TextTrail` this module returns as one
of five caller-supplied inputs), and it does not write Parquet, Neo4j, or any
`CANDIDATE` assertion -- scoring only.

Epistemic tier: exploratory (`specs/sttr-spinout-linkage/tasks.md` header):
no tests or abstractions beyond what a single probe needs, and no citable
numbers from any hit-rate this module produces.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from sbir_etl.utils.coercion import _blank

from .kernel import DimensionStatus, D5TextTrail, SignalAbsentReason


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "sbir_etl").exists():
            return candidate
    raise RuntimeError("Not inside the sbir-analytics checkout")


_REPO_ROOT = _find_repo_root(Path(__file__).resolve())

DEFAULT_LEXICON_PATH = (
    _REPO_ROOT / "data" / "reference" / "sttr_spinout_linkage" / "d5_phrase_lexicon_v1.json"
)


@dataclass(frozen=True)
class D5Lexicon:
    """A loaded, compiled D5 phrase lexicon."""

    version: str
    frozen: str
    pattern_ids: tuple[str, ...]
    compiled: tuple[re.Pattern[str], ...]


def load_lexicon(path: Path = DEFAULT_LEXICON_PATH) -> D5Lexicon:
    """Load and compile the D5 phrase lexicon from its frozen JSON file.

    Raises `FileNotFoundError` if the lexicon file is missing rather than
    silently scoring against an empty pattern set -- an empty lexicon would
    make every award look like a measured negative instead of surfacing the
    real problem (the frozen artifact is gone or misconfigured).
    """

    if not path.exists():
        raise FileNotFoundError(f"D5 phrase lexicon not found at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    patterns = data["patterns"]
    return D5Lexicon(
        version=data["version"],
        frozen=data["frozen"],
        pattern_ids=tuple(p["id"] for p in patterns),
        compiled=tuple(re.compile(p["pattern"], re.IGNORECASE) for p in patterns),
    )


@lru_cache(maxsize=1)
def _default_lexicon() -> D5Lexicon:
    return load_lexicon()


def score_d5_text_trail(
    abstract: object,
    *,
    lexicon: D5Lexicon | None = None,
) -> D5TextTrail:
    """Score one award's D5 text trail from its abstract.

    - Blank/missing abstract -> `NOT_MEASURABLE` /
      `SOURCE_FIELD_UNAVAILABLE` (design.md's D5 "Typed absence encodes"
      column: "no firm text available" -- the abstract is the only text
      field actually present on the D1 spine, so its absence is this case).
    - Non-blank abstract -> `MEASURED`, with `spinout_phrase` set to whether
      any lexicon pattern matched (case-insensitive). A `MEASURED` row with
      `spinout_phrase=False` is a real, searched negative -- the lexicon ran
      and found nothing -- never conflated with the `NOT_MEASURABLE` case.
    """

    if _blank(abstract):
        return D5TextTrail(
            status=DimensionStatus.NOT_MEASURABLE,
            reason=SignalAbsentReason.SOURCE_FIELD_UNAVAILABLE,
        )

    active_lexicon = lexicon or _default_lexicon()
    text = str(abstract)
    matched = any(pattern.search(text) for pattern in active_lexicon.compiled)
    return D5TextTrail(status=DimensionStatus.MEASURED, spinout_phrase=matched)
