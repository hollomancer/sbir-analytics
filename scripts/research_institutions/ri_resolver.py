"""Resolve SBIR.gov ``RI Name`` strings to IPEDS institutions or NSF FFRDCs.

Epistemic tier: exploratory. Non-citable.

Rules, in order, all on the same key (``ORGANIZATION_KEY_V1`` with a leading
``THE`` removed):

1. ``blank``: empty or a placeholder token such as ``N/A``.
2. ``exact_name``: the key equals one reference institution's name key.
3. ``ipeds_main_campus``: the key equals an IPEDS name with its trailing
   ``-Main Campus`` removed.
4. ``alias``: the key equals one IPEDS ``IALIAS`` entry that passes the
   specificity guard.
5. ``ambiguous``: a rule matched more than one reference institution.
6. ``unresolved``: nothing matched. The surface name stays a surface name.

No fuzzy scoring. Campus, laboratory, foundation, and department grain is not
decided here: a string that names a unit inside an institution stays unresolved
unless the reference list carries that unit as its own row.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from sbir_etl.identity.company_names import CompanyNameProfile, normalize_company_name


EPISTEMIC_TIER = "exploratory"

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_LISTS = REPO_ROOT / "data" / "reference" / "sttr_partner_type_seed_lists"
IPEDS_PATH = SEED_LISTS / "ipeds_institutions" / "HD2024.csv"
FFRDC_PATH = SEED_LISTS / "ffrdc_master" / "ffrdc_master.csv"

# Placeholder strings in ``RI Name`` are typed missingness, not an institution.
RI_PLACEHOLDER_TOKENS = frozenset({"n/a", "na", "none", "null", "nan", "-"})

RULE_BLANK = "blank"
RULE_EXACT = "exact_name"
RULE_MAIN_CAMPUS = "ipeds_main_campus"
RULE_ALIAS = "alias"
RULE_AMBIGUOUS = "ambiguous"
RULE_UNRESOLVED = "unresolved"
RULES = (RULE_BLANK, RULE_EXACT, RULE_MAIN_CAMPUS, RULE_ALIAS, RULE_AMBIGUOUS, RULE_UNRESOLVED)

_ALIAS_SEPARATORS = re.compile(r"\s*\|\s*|\s*,\s*|\s{2,}")
_MAIN_CAMPUS = re.compile(r"\s*-\s*main campus\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class ReferenceInstitution:
    """One row of a reference list: a stable id, its name, and declared aliases."""

    reference_id: str
    name: str
    source: str
    state: str | None = None
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class RIResolution:
    """The outcome of resolving one surface name."""

    surface_name: str
    key: str
    rule: str
    reference_id: str | None
    reference_name: str | None
    source: str | None
    candidate_count: int


def ri_key(value: object) -> str:
    """Return the comparison key shared by surface names and reference names."""

    key = normalize_company_name(value, profile=CompanyNameProfile.ORGANIZATION_KEY_V1)
    return key.removeprefix("THE ").strip()


def is_placeholder(value: object) -> bool:
    """Return True for blank, null-like, or placeholder research-institution text."""

    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    text = " ".join(str(value).split()).casefold()
    return text == "" or text in RI_PLACEHOLDER_TOKENS


def split_aliases(text: object) -> tuple[str, ...]:
    """Split an IPEDS ``IALIAS`` cell on its mixed separators."""

    if text is None:
        return ()
    parts = (part.strip() for part in _ALIAS_SEPARATORS.split(str(text)))
    return tuple(part for part in parts if part)


def alias_is_specific(alias: str) -> bool:
    """Reject aliases that are one generic word.

    Multi-token aliases pass. A single token passes only as an all-capital
    acronym of three to six letters (``MIT``, ``UCSF``). ``Tech``, ``Pacific``,
    and ``Arkansas`` do not pass: each names many institutions or none.
    """

    tokens = ri_key(alias).split()
    if not tokens:
        return False
    if len(tokens) >= 2:
        return True
    raw = alias.strip()
    return raw.isalpha() and raw.isupper() and 3 <= len(raw) <= 6


def load_ipeds(path: Path = IPEDS_PATH) -> tuple[ReferenceInstitution, ...]:
    """Load IPEDS HD rows as reference institutions keyed by ``UNITID``."""

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return tuple(
            ReferenceInstitution(
                reference_id=f"ipeds:{row['UNITID'].strip()}",
                name=row["INSTNM"].strip(),
                source="ipeds",
                state=row.get("STABBR", "").strip() or None,
                aliases=split_aliases(row.get("IALIAS", "")),
            )
            for row in csv.DictReader(handle)
        )


def load_ffrdc(path: Path = FFRDC_PATH) -> tuple[ReferenceInstitution, ...]:
    """Load the NSF FFRDC master list keyed by a slug of the FFRDC name."""

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    institutions = []
    for row in rows:
        name = " ".join(row["ffrdc_name"].split())
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        institutions.append(
            ReferenceInstitution(
                reference_id=f"ffrdc:{slug}",
                name=name,
                source="ffrdc",
                state=(row.get("loc_state") or "").strip() or None,
            )
        )
    return tuple(institutions)


class RIResolver:
    """Exact and alias resolution over a fixed set of reference institutions."""

    def __init__(self, institutions: Iterable[ReferenceInstitution]) -> None:
        self._by_id: dict[str, ReferenceInstitution] = {}
        self._exact: dict[str, set[str]] = {}
        self._derived: dict[str, dict[str, str]] = {}
        for institution in institutions:
            if institution.reference_id in self._by_id:
                raise ValueError(f"duplicate reference id: {institution.reference_id}")
            self._by_id[institution.reference_id] = institution
            name_key = ri_key(institution.name)
            if name_key:
                self._exact.setdefault(name_key, set()).add(institution.reference_id)
            if institution.source == "ipeds":
                stripped = _MAIN_CAMPUS.sub("", institution.name)
                if stripped != institution.name and (campus_key := ri_key(stripped)):
                    self._add_derived(campus_key, institution.reference_id, RULE_MAIN_CAMPUS)
            for alias in institution.aliases:
                if not alias_is_specific(alias):
                    continue
                alias_key = ri_key(alias)
                if alias_key and alias_key != name_key:
                    self._add_derived(alias_key, institution.reference_id, RULE_ALIAS)
        # An exact institution name always wins over another institution's alias.
        for key in list(self._derived):
            if key in self._exact:
                del self._derived[key]

    def _add_derived(self, key: str, reference_id: str, rule: str) -> None:
        candidates = self._derived.setdefault(key, {})
        # The derived campus rule is more specific than a declared alias.
        if candidates.get(reference_id) != RULE_MAIN_CAMPUS:
            candidates[reference_id] = rule

    def __len__(self) -> int:
        return len(self._by_id)

    def institution(self, reference_id: str) -> ReferenceInstitution:
        return self._by_id[reference_id]

    def resolve(self, value: object) -> RIResolution:
        surface = "" if value is None else " ".join(str(value).split())
        if is_placeholder(value):
            return RIResolution(surface, "", RULE_BLANK, None, None, None, 0)
        key = ri_key(surface)
        if not key:
            return RIResolution(surface, key, RULE_BLANK, None, None, None, 0)

        exact_ids = self._exact.get(key)
        if exact_ids:
            return self._outcome(surface, key, RULE_EXACT, sorted(exact_ids))
        derived = self._derived.get(key)
        if derived:
            ids = sorted(derived)
            rule = derived[ids[0]] if len(ids) == 1 else RULE_AMBIGUOUS
            return self._outcome(surface, key, rule, ids)
        return RIResolution(surface, key, RULE_UNRESOLVED, None, None, None, 0)

    def _outcome(self, surface: str, key: str, rule: str, ids: list[str]) -> RIResolution:
        if len(ids) != 1:
            return RIResolution(surface, key, RULE_AMBIGUOUS, None, None, None, len(ids))
        institution = self._by_id[ids[0]]
        return RIResolution(
            surface, key, rule, institution.reference_id, institution.name, institution.source, 1
        )


def build_default_resolver() -> RIResolver:
    """Build the resolver from the repository's pinned IPEDS and FFRDC seed lists."""

    return RIResolver((*load_ipeds(), *load_ffrdc()))


def resolution_frame(
    names: Iterable[object],
    resolver: RIResolver,
    weights: Mapping[object, int] | None = None,
) -> pd.DataFrame:
    """Resolve each distinct surface name once and return one row per name.

    ``weights`` maps a surface name to the number of awards that carry it, so the
    match rate can be reported both per distinct string and per award.
    """

    rows = []
    for name in dict.fromkeys(names):
        outcome = resolver.resolve(name)
        rows.append(
            {
                "surface_name": outcome.surface_name,
                "key": outcome.key,
                "rule": outcome.rule,
                "reference_id": outcome.reference_id,
                "reference_name": outcome.reference_name,
                "source": outcome.source,
                "candidate_count": outcome.candidate_count,
                "awards": int(weights.get(name, 1)) if weights is not None else 1,
            }
        )
    columns = [
        "surface_name",
        "key",
        "rule",
        "reference_id",
        "reference_name",
        "source",
        "candidate_count",
        "awards",
    ]
    return pd.DataFrame(rows, columns=columns)


def match_rate_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Summarize resolution outcomes by rule, per distinct string and per award."""

    if frame.empty:
        return pd.DataFrame(
            columns=["rule", "distinct_strings", "distinct_share", "awards", "award_share"]
        )
    grouped = (
        frame.groupby("rule")
        .agg(distinct_strings=("surface_name", "size"), awards=("awards", "sum"))
        .reindex(RULES, fill_value=0)
        .reset_index()
    )
    grouped["distinct_share"] = grouped["distinct_strings"] / len(frame)
    grouped["award_share"] = grouped["awards"] / frame["awards"].sum()
    return grouped.loc[:, ["rule", "distinct_strings", "distinct_share", "awards", "award_share"]]


__all__ = [
    "EPISTEMIC_TIER",
    "FFRDC_PATH",
    "IPEDS_PATH",
    "RI_PLACEHOLDER_TOKENS",
    "RULES",
    "RIResolution",
    "RIResolver",
    "ReferenceInstitution",
    "alias_is_specific",
    "build_default_resolver",
    "is_placeholder",
    "load_ffrdc",
    "load_ipeds",
    "match_rate_table",
    "resolution_frame",
    "ri_key",
    "split_aliases",
]
