"""D1 award-spine loader for the STTR spinout-linkage RQ1 cascade.

Loads the STTR Phase II award population design.md's D1 row anchors on
(`program = STTR`, SBIR.gov award data) and computes each award's `D1Spine`
(`kernel.D1Spine`) from RI/PI presence. Every D2-D5 dimension scorer and the
cascade-assembly step (task 1.3+) starts from this population; this module
does not itself score D1-D5's later dimensions.

Filtering reuses the exact `first_col` / STTR / Phase II filter pattern
already used twice in this repo for the same population --
`notebooks/explorations/b1_sttr_partner_type_commercialization.ipynb` and
`notebooks/explorations/sttr_rq1_data_availability.ipynb` -- extracted here so
a third, differently-written copy of the same filter never exists. The two
notebooks are not rewritten to import this module in this PR (out of scope
per the task brief); a follow-on housekeeping change can do that.

No Neo4j, no CANDIDATE-assertion emission, no Parquet write. Per design.md,
"Parquet is authoritative; Neo4j is a disposable investigative projection" --
this loader only needs to hand a population to the D2-D5 scorers that follow,
so it returns a `pandas.DataFrame`, matching what both precedent notebooks
already produce.

Epistemic tier: exploratory (`specs/sttr-spinout-linkage/tasks.md` header):
no tests or abstractions beyond what a single probe needs.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from sbir_etl.utils.coercion import _blank

from .freeze_guard import verify_design_frozen
from .kernel import D1Spine


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "sbir_etl").exists():
            return candidate
    raise RuntimeError("Not inside the sbir-analytics checkout")


_REPO_ROOT = _find_repo_root(Path(__file__).resolve())

# Same candidate order as both precedent notebooks: prefer the enriched
# parquet, fall back to the raw SBIR.gov CSV.
DEFAULT_AWARD_CANDIDATES: tuple[Path, ...] = (
    _REPO_ROOT / "data" / "processed" / "enriched_sbir_awards.parquet",
    _REPO_ROOT / "data" / "raw" / "sbir" / "award_data.csv",
)


def first_col(frame: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    """Return the first column in `frame` matching any of `names`, case-insensitively.

    The exact helper both precedent notebooks define locally
    (`b1_sttr_partner_type_commercialization.ipynb`,
    `sttr_rq1_data_availability.ipynb`); extracted here so a third
    implementation is never written.
    """

    lookup = {column.lower(): column for column in frame.columns}
    for name in names:
        if name.lower() in lookup:
            return lookup[name.lower()]
    return None


def is_sttr(value: object) -> bool:
    """`program` column predicate, identical to both precedent notebooks."""

    text = str(value or "").strip().upper()
    return text == "STTR"


def is_phase_ii(value: object) -> bool:
    """`phase` column predicate, identical to both precedent notebooks."""

    text = str(value or "").strip().upper().replace("PHASE ", "")
    return text in {"II", "2"}


def resolve_award_data_path(candidates: tuple[Path, ...] = DEFAULT_AWARD_CANDIDATES) -> Path:
    """First existing candidate path, or the last (canonical) one if none exist."""

    return next((path for path in candidates if path.exists()), candidates[-1])


def load_award_data(path: Path) -> pd.DataFrame:
    """Read the SBIR award population from parquet or CSV, matching both notebooks."""

    if not path.exists():
        raise FileNotFoundError(f"No award data at {path}")
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, dtype=str, low_memory=False)


def filter_sttr_phase_ii(frame: pd.DataFrame) -> pd.DataFrame:
    """Filter to `program = STTR`, `phase = Phase II` rows.

    Same predicate both precedent notebooks apply. Raises `KeyError` if the
    award frame lacks recognizable program/phase columns rather than
    silently returning an empty population -- this is a shared substrate for
    downstream scorers, not an interactive probe, so a missing column must
    fail loud here.
    """

    program_col = first_col(frame, ("program", "Program"))
    phase_col = first_col(frame, ("phase", "Phase"))
    if program_col is None or phase_col is None:
        raise KeyError(f"Award frame lacks program/phase columns: {list(frame.columns)}")
    return frame.loc[frame[program_col].map(is_sttr) & frame[phase_col].map(is_phase_ii)].copy()


@dataclass(frozen=True)
class D1SpineRecord:
    """One STTR Phase II award: the D1-row fields plus its computed `D1Spine`."""

    award_id: object
    agency: object
    award_year: object
    award_date: object
    uei: object
    company_name: object
    ri_name: object
    pi_name: object
    abstract: object
    spine: D1Spine


def build_d1_spine_frame(sttr_p2: pd.DataFrame) -> pd.DataFrame:
    """Select/rename the D1 fields and attach `ri_present`/`pi_present`/`d1_spine`.

    `sttr_p2` must already be filtered to STTR Phase II rows
    (`filter_sttr_phase_ii`). Presence uses `sbir_etl.utils.coercion._blank`
    -- the same blank/NaN/whitespace check `kernel.py` already imports for
    its own presence logic, not a new definition of "present."
    """

    award_id_col = first_col(
        sttr_p2, ("award_id", "Agency Tracking Number", "agency_tracking_number")
    )
    agency_col = first_col(sttr_p2, ("agency", "Agency"))
    year_col = first_col(sttr_p2, ("award_year", "Award Year"))
    date_col = first_col(sttr_p2, ("award_date", "Proposal Award Date"))
    uei_col = first_col(sttr_p2, ("uei", "UEI", "company_uei"))
    company_col = first_col(sttr_p2, ("company_name", "Company", "company"))
    ri_col = first_col(sttr_p2, ("ri_name", "RI Name", "research_institution"))
    pi_col = first_col(sttr_p2, ("pi_name", "PI Name", "principal_investigator"))
    abstract_col = first_col(sttr_p2, ("abstract", "Abstract"))

    def _column(col: str | None) -> pd.Series:
        return sttr_p2[col] if col else pd.Series(pd.NA, index=sttr_p2.index)

    spine = pd.DataFrame(
        {
            "award_id": _column(award_id_col),
            "agency": _column(agency_col),
            "award_year": _column(year_col),
            "award_date": _column(date_col),
            "uei": _column(uei_col),
            "company_name": _column(company_col),
            "ri_name": _column(ri_col),
            "pi_name": _column(pi_col),
            "abstract": _column(abstract_col),
        }
    )
    spine["ri_present"] = ~spine["ri_name"].map(_blank)
    spine["pi_present"] = ~spine["pi_name"].map(_blank)
    spine["d1_spine"] = [
        D1Spine(ri_present=bool(ri), pi_present=bool(pi))
        for ri, pi in zip(spine["ri_present"], spine["pi_present"], strict=True)
    ]
    return spine


def load_d1_spine(
    award_data_path: Path | None = None,
    *,
    verify_freeze: bool = True,
) -> pd.DataFrame:
    """Load the D1 award spine for the STTR Phase II population.

    Calls `verify_design_frozen` first (skip with `verify_freeze=False` only
    if the caller already verified once in the same process) -- design.md's
    D1 row and the Order-0 cascade rule this spine feeds are both part of the
    Revision 1 freeze.
    """

    if verify_freeze:
        verify_design_frozen()
    path = award_data_path or resolve_award_data_path()
    awards_raw = load_award_data(path)
    sttr_p2 = filter_sttr_phase_ii(awards_raw)
    return build_d1_spine_frame(sttr_p2)


def iter_d1_spine_records(frame: pd.DataFrame) -> Iterator[D1SpineRecord]:
    """Yield one `D1SpineRecord` per row of a `load_d1_spine` frame."""

    for row in frame.itertuples(index=False):
        yield D1SpineRecord(
            award_id=row.award_id,
            agency=row.agency,
            award_year=row.award_year,
            award_date=row.award_date,
            uei=row.uei,
            company_name=row.company_name,
            ri_name=row.ri_name,
            pi_name=row.pi_name,
            abstract=row.abstract,
            spine=row.d1_spine,
        )
