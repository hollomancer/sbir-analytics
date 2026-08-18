"""D4 money/paper-trail scorer for the STTR spinout-linkage RQ1 cascade.

Scores `kernel.D4MoneyTrail` for one award. Per `design.md`'s D4 row and its
"D4 has two directions" discipline note, this dimension carries **two
independent signals in two independent directions**, and getting the
direction backwards silently produces the wrong evidence (the same class of
bug O-12 caught for D3's PatentsView `government_interest` field):

1. **`ri_subaward_share`** -- a **subcontract** marker. For a given STTR
   award (the SBC holds the *prime* award), do USASpending subaward records
   show the **RI as a subawardee under that specific prime award**? This
   needs subawards *for a known prime award id*, filtered for the RI's name
   among the subawardees -- not a name search for the SBC across all prime
   awards (that is the opposite direction `scripts/data/nano_ws5a_subawards.py`
   already uses for a different question: whether a dark SBIR firm itself
   subcontracted to someone else's prime).
2. **`form_d_officer_ri_affiliated`** -- a **spinout** marker. A Form D
   officer/director name (`data/form_d_details.jsonl`) matched to an
   RI-affiliated name, via the same `kernel.resolve_identity` /
   `identity_similarity` person-matching machinery D2 uses.

**Which name is "RI-affiliated" for direction 2?** Originally this module
matched Form D officers/directors against the award's "RI POC Name" only,
reasoning that the PI's employer election (RI employee vs. SBC employee) is
exactly the unresolved fact this classifier exists to proxy for, so matching
the PI would be circular. That reasoning did not hold up against the data:
checked against the real award population, "RI POC Name" and "PI Name" are
the same person only 2.77% of the time -- RI POC is overwhelmingly a
different, apparently administrative contact, not the PI. D2 (scholarly
authorship) and D4 (SEC officer filings) are independently-scored dimensions
per design.md's own rule precisely *because* they check the same underlying
fact -- is this person tied to the RI? -- through different data sources; a
PI name that also turns up as a Form D officer/director is independent
corroboration from a second, distinct source, exactly the pattern the
Order-2 cascade rule in design.md is built to reward, not circular
reasoning. This module therefore checks Form D officer/director names
against **both** the award's "RI POC Name" and its "PI Name", treating a
match against either as a positive `form_d_officer_ri_affiliated` -- RI-POC
matching stays (a real, if rare, additional check on its own), PI-name
matching is added alongside it rather than replacing it.

**Grant vs. contract instrument.** Neither `kernel.D1Spine` nor
`d1_spine.build_d1_spine_frame` carries the raw SBIR.gov "Contract" field (the
award's actual PIID/FAIN), so `ri_subaward_share` is not a well-formed concept
without reading it independently -- this module adds a small, D4-scoped
loader (`load_d4_raw_fields`) rather than extending the shared D1 substrate.
`classify_instrument_type` is a deterministic regex classifier over that
field's *format* (never guessed from `agency`), empirically validated against
the full 5,841-award STTR Phase II population: 96.6% classified confidently
(CONTRACT 3,975; GRANT 1,666), the remainder `UNKNOWN` (55 unrecognized
formats + 145 blank `Contract` values) -- reported honestly as `UNKNOWN`,
never guessed into either bucket.

**Live-API verification (done before writing the client below).** Manually
probed `api.usaspending.gov` against real STTR prime award ids:
`/api/v2/subawards/` with `award_id=<generated award hash>` returns subaward
records **for that one prime award** (confirmed both by the API's own
contract doc -- `award_id`: "a 'generated' natural award id ... or a database
surrogate award id" -- and by a real example: DOE grant `DE-AR0001314`
(Envergex LLC / University of North Dakota) returns two subawards, one to
"UNIVERSITY OF NORTH DAKOTA" -- the D1 spine's own RI name for that award,
normalizing identically under `CompanyNameProfile.MATCHING_V1`). This is the
correct endpoint/direction; `/api/v2/awards/<id>/`'s aggregate
`total_subaward_amount` (what `scripts/ot_consortium/probe_subaward_coverage.py`
uses) is not enough here because D4 needs the *recipient name* of each
subaward, not just a coverage percentage.

The documented `award_ids` filter's double-quoted "exact match" form
(`'"AWARD-ID"'`) reproducibly returned HTTP 500/503 against known-good award
ids in manual testing; the unquoted form works and is verified exact here by
re-checking the dash-stripped `Award ID` in the response against the query
before accepting a `generated_internal_id` -- so an unrelated fuzzy hit is
never silently treated as the prime award. SBIR.gov's `Contract` field also
is not byte-identical to USASpending's stored `Award ID`: it carries dashes
USASpending strips, and NIH grant numbers carry a leading type-code digit and
trailing support-year suffix (`"2R42MD014075-02"`) that USASpending's FAIN
does not (`"R42MD014075"`). `normalize_award_id_for_search` handles both,
confirmed against six real awards across DoD, NASA, DOE, and NIH.

Epistemic tier: exploratory (`specs/sttr-spinout-linkage/tasks.md`, task
1.3's D4 slice). No dimension score from this module is citable.
"""

from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

import pandas as pd
import requests
from loguru import logger

from sbir_etl.identity import CompanyNameProfile, normalize_company_name
from sbir_etl.utils.coercion import _blank

from .d1_spine import filter_sttr_phase_ii, first_col, load_award_data, resolve_award_data_path
from .kernel import (
    D4MoneyTrail,
    DimensionStatus,
    IdentityKind,
    ResolvedIdentity,
    SignalAbsentReason,
    resolve_identity,
)


EPISTEMIC_TIER = "exploratory"

USASPENDING_API = "https://api.usaspending.gov/api/v2"

_OFFICER_DIRECTOR_TITLE_RE = re.compile(r"director|officer", re.IGNORECASE)


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "sbir_etl").exists():
            return candidate
    raise RuntimeError("Not inside the sbir-analytics checkout")


_REPO_ROOT = _find_repo_root(Path(__file__).resolve())
DEFAULT_FORM_D_PATH = _REPO_ROOT / "data" / "form_d_details.jsonl"


# ---------------------------------------------------------------------------
# Instrument-type detection (grant vs. contract), from the raw `Contract`
# field's *format* -- see module docstring for the empirical validation.
# ---------------------------------------------------------------------------


class InstrumentType(StrEnum):
    """Whether an STTR award's funding instrument is a grant or a contract.

    `UNKNOWN` is a real, reported outcome (unrecognized `Contract` field
    format, or the field is blank) -- never silently folded into GRANT or
    CONTRACT.
    """

    GRANT = "grant"
    CONTRACT = "contract"
    UNKNOWN = "unknown"


# Each pattern is anchored to the *shape* of a real, observed instrument
# identifier format, not to the awarding agency -- validated against the
# full STTR Phase II population (see module docstring for the counts).
_GRANT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\d[A-Z]\d{2}[A-Z]{2}\d+(-\d+)?(A\d)?$"),  # NIH: 4R42AR083779-02
    re.compile(r"^D-?E-[A-Z0-9-]+$"),  # DOE: DE-AR0001984, DE-SC0024799
    re.compile(r"^\d{7}$"),  # NSF: 2507534
    re.compile(r"^\d{4}-\d{5}$"),  # USDA/NIFA: 2024-04679
)
_CONTRACT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^[A-Z0-9]{5,8}-?\d{2}-?[A-Z0-9]-?[A-Z0-9]{2,7}$"),  # PIID: agency-FY-type-serial
    re.compile(r"^[A-Z0-9]{6,12}C[A-Z0-9]{0,6}$"),  # compact NASA/DoD, e.g. NNX17CJ01C
    re.compile(r"^NAS\d-\d{5}$"),  # legacy NASA: NAS3-03076
)

# USASpending's `award_type_codes` filter rejects mixing groups ("must only
# contain types from one group"); these are the two single-group code sets
# relevant to STTR primes.
USASPENDING_GRANT_TYPE_CODES: tuple[str, ...] = ("02", "03", "04", "05", "F001", "F002")
USASPENDING_CONTRACT_TYPE_CODES: tuple[str, ...] = ("A", "B", "C", "D")


def classify_instrument_type(contract_number: object) -> InstrumentType:
    """Classify one award's funding instrument from its raw `Contract` field.

    Deterministic format matching only -- no agency-based guessing. See the
    module docstring for the empirical validation over the full population.
    """

    if _blank(contract_number):
        return InstrumentType.UNKNOWN
    value = str(contract_number).strip().upper()
    for pattern in _GRANT_PATTERNS:
        if pattern.match(value):
            return InstrumentType.GRANT
    for pattern in _CONTRACT_PATTERNS:
        if pattern.match(value):
            return InstrumentType.CONTRACT
    return InstrumentType.UNKNOWN


_NIH_GRANT_RE = re.compile(r"^\d([A-Z]\d{2}[A-Z]{2}\d+)(-.*)?$")


def normalize_award_id_for_search(contract_number: str, *, instrument: InstrumentType) -> str:
    """Map SBIR.gov's `Contract` field to USASpending's stored `Award ID` form.

    Confirmed by manual live-API testing against six real awards (module
    docstring): USASpending strips dashes from PIIDs/FAINs, and NIH grant
    numbers additionally drop the leading type-code digit and trailing
    support-year suffix (`"2R42MD014075-02"` -> `"R42MD014075"`).
    """

    value = contract_number.strip().upper()
    if instrument is InstrumentType.GRANT:
        match = _NIH_GRANT_RE.match(value)
        if match:
            return match.group(1)
    return re.sub(r"[\s-]", "", value)


# ---------------------------------------------------------------------------
# D4-local raw-field loader: `Contract` (instrument id) and `RI POC Name`
# (the RI-affiliated name Form D officers/directors are matched against).
# Neither is on the shared D1 spine (`d1_spine.build_d1_spine_frame`); reuses
# `d1_spine`'s `first_col` / `filter_sttr_phase_ii` / `load_award_data` /
# `resolve_award_data_path` rather than a second CSV-reading implementation.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class D4RawFields:
    """The two D4-specific raw fields for one award, keyed by `award_id`."""

    contract_number: object
    ri_poc_name: object


def load_d4_raw_fields(award_data_path: Path | None = None) -> dict[object, D4RawFields]:
    """Load `{award_id: D4RawFields}` for the STTR Phase II population.

    Same population and column-resolution pattern as
    `d1_spine.build_d1_spine_frame` (this is deliberately not folded into that
    function -- see module docstring on why these fields are D4-local).
    """

    path = award_data_path or resolve_award_data_path()
    awards_raw = load_award_data(path)
    sttr_p2 = filter_sttr_phase_ii(awards_raw)

    award_id_col = first_col(
        sttr_p2, ("award_id", "Agency Tracking Number", "agency_tracking_number")
    )
    contract_col = first_col(sttr_p2, ("contract_number", "Contract", "contract"))
    poc_col = first_col(sttr_p2, ("ri_poc_name", "RI POC Name", "ri_poc"))
    if award_id_col is None:
        raise KeyError(f"Award frame lacks an award-id column: {list(sttr_p2.columns)}")

    contract_series = (
        sttr_p2[contract_col] if contract_col else pd.Series(pd.NA, index=sttr_p2.index)
    )
    poc_series = sttr_p2[poc_col] if poc_col else pd.Series(pd.NA, index=sttr_p2.index)
    return {
        award_id: D4RawFields(contract_number=contract, ri_poc_name=poc)
        for award_id, contract, poc in zip(
            sttr_p2[award_id_col], contract_series, poc_series, strict=True
        )
    }


# ---------------------------------------------------------------------------
# Form D officer/director index (direction 2: spinout marker)
# ---------------------------------------------------------------------------


def load_form_d_officer_index(
    path: Path | None = None,
    *,
    min_confidence_tier: str | None = "high",
) -> dict[str, tuple[str, ...]]:
    """Load `data/form_d_details.jsonl` into `{FORM_D_JOIN_V1 firm key: officer/director names}`.

    Same file, same `match_confidence.tier == "high"` filter, and same
    `CompanyNameProfile.FORM_D_JOIN_V1` name key as
    `notebooks/explorations/b1_sttr_partner_type_commercialization.ipynb`'s
    `join-channels` cell (Form D carries no UEI, so name-key is the only join
    key). A missing file returns an empty index (channel not searched) rather
    than raising -- never fabricates officer names. Officer/director names
    come from each `offerings[].related_persons[]` entry whose `title`
    contains "director" or "officer" (case-insensitive); other roles (e.g.
    plain "Promoter") are excluded.
    """

    if path is None:
        path = DEFAULT_FORM_D_PATH
    index: dict[str, set[str]] = defaultdict(set)
    if not path.exists():
        logger.warning("Form D details file not found at {} -- officer names not searched", path)
        return {}

    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            tier = (record.get("match_confidence") or {}).get("tier")
            if min_confidence_tier is not None and tier != min_confidence_tier:
                continue
            key = normalize_company_name(
                record.get("company_name"), profile=CompanyNameProfile.FORM_D_JOIN_V1
            )
            if not key:
                continue
            for offering in record.get("offerings") or []:
                for person in offering.get("related_persons") or []:
                    name = person.get("name")
                    title = str(person.get("title") or "")
                    if name and _OFFICER_DIRECTOR_TITLE_RE.search(title):
                        index[key].add(name)

    return {key: tuple(sorted(names)) for key, names in index.items()}


def score_form_d_officer_ri_affiliated(
    *,
    company_name: object,
    ri_poc_name: object,
    pi_name: object,
    form_d_index: dict[str, tuple[str, ...]] | None,
) -> tuple[DimensionStatus, bool, SignalAbsentReason | None]:
    """Score direction 2: a Form D officer/director matched to the RI POC name
    or the PI name.

    Two independent name signals -- the award's RI POC name and its PI name --
    are each checked against the same Form D officer/director index; a match
    against **either** is sufficient positive spinout evidence (module
    docstring's "Which name is 'RI-affiliated'" section), so the returned
    boolean does not distinguish which of the two fired. Follows the same
    multi-candidate-name pattern `d2_person_scorer.score_d2_person_trail` uses
    for PI + Form-D founder names: blank names are dropped, each remaining
    name is resolved once and deduplicated by its normalized identity.

    Exact normalized-name match only (via `kernel.resolve_identity` /
    `IdentityKind.PERSON`, `generic_token_guard`-gated) -- no fuzzy cutoff.
    O-3 froze the fuzzy-match *method* for the cascade's own D2 person
    comparison but left the numeric cutoff explicitly deferred; inventing an
    unfrozen threshold for a different comparison here would silently
    un-defer it, so this direction stays precision-over-recall (same
    discipline as D5's lexicon), a stated limitation, not an oversight.
    """

    candidate_names = [name for name in (ri_poc_name, pi_name) if not _blank(name)]
    if not candidate_names:
        return DimensionStatus.NOT_MEASURABLE, False, SignalAbsentReason.SOURCE_FIELD_UNAVAILABLE

    candidates: list[ResolvedIdentity] = []
    seen_normalized: set[str] = set()
    for raw_name in candidate_names:
        identity = resolve_identity(raw_name, kind=IdentityKind.PERSON)
        if identity is None or not identity.guard_passed:
            continue
        if identity.normalized in seen_normalized:
            continue
        seen_normalized.add(identity.normalized)
        candidates.append(identity)
    if not candidates:
        return (
            DimensionStatus.NOT_MEASURABLE,
            False,
            SignalAbsentReason.NAME_GENERIC_TOKEN_GUARD_FAILED,
        )
    if not form_d_index:
        return DimensionStatus.NOT_EVALUATED, False, SignalAbsentReason.SOURCE_NOT_QUERIED

    key = normalize_company_name(company_name, profile=CompanyNameProfile.FORM_D_JOIN_V1)
    officer_names = form_d_index.get(key, ())
    if not officer_names:
        # A real search: either no high-confidence Form D match for this
        # company, or a match with no officer/director-titled person.
        return DimensionStatus.MEASURED, False, None

    for officer_name in officer_names:
        officer_identity = resolve_identity(officer_name, kind=IdentityKind.PERSON)
        if officer_identity is None or not officer_identity.guard_passed:
            continue
        matched_candidate = next(
            (c for c in candidates if c.normalized == officer_identity.normalized), None
        )
        if matched_candidate is not None:
            logger.debug(
                "D4 Form D officer match: {!r} matched officer {!r} (company {!r})",
                matched_candidate.raw,
                officer_identity.raw,
                company_name,
            )
            return DimensionStatus.MEASURED, True, None
    return DimensionStatus.MEASURED, False, None


# ---------------------------------------------------------------------------
# USASpending subaward lookup (direction 1: subcontract marker)
# ---------------------------------------------------------------------------


class SubawardClient(Protocol):
    """Structural type for the USASpending calls this scorer needs.

    Satisfied by `UsaspendingSubawardClient` without importing it here, so
    unit tests can inject a bare fake -- no live network call in the test
    suite.
    """

    def find_prime_award_id(
        self, award_id_query: str, *, instrument: InstrumentType
    ) -> str | None: ...

    def fetch_subawards(self, prime_award_id: str) -> list[dict[str, object]]: ...


class UsaspendingSubawardClient:
    """Live `api.usaspending.gov` client for the two confirmed-correct calls.

    See the module docstring's "Live-API verification" section for the
    verification trail behind both calls and the `award_ids` quoting caveat.
    """

    def __init__(
        self, session: requests.Session | None = None, *, base_url: str = USASPENDING_API
    ) -> None:
        self._session = session or requests.Session()
        self._session.headers.setdefault("Content-Type", "application/json")
        self._base_url = base_url

    def _post(self, path: str, body: dict[str, object], retries: int = 4) -> dict[str, object]:
        url = f"{self._base_url}{path}"
        response = None
        for attempt in range(retries):
            response = self._session.post(url, json=body, timeout=60)
            if response.status_code == 200:
                result: dict[str, object] = response.json()
                return result
            if response.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2**attempt)
                continue
            response.raise_for_status()
        assert response is not None  # retries >= 1 guarantees a response was set
        response.raise_for_status()
        raise RuntimeError(f"unreachable: {path} did not return 200 or raise")

    def find_prime_award_id(self, award_id_query: str, *, instrument: InstrumentType) -> str | None:
        codes = (
            USASPENDING_GRANT_TYPE_CODES
            if instrument is InstrumentType.GRANT
            else USASPENDING_CONTRACT_TYPE_CODES
        )
        body = {
            "filters": {"award_ids": [award_id_query], "award_type_codes": list(codes)},
            "fields": ["Award ID", "generated_internal_id"],
            "page": 1,
            "limit": 10,
        }
        data = self._post("/search/spending_by_award/", body)
        for result in data.get("results", []):  # type: ignore[union-attr]
            award_id = str(result.get("Award ID") or "")
            if re.sub(r"[\s-]", "", award_id.upper()) != award_id_query:
                continue  # unrelated fuzzy hit -- never silently accepted
            generated = result.get("generated_internal_id")
            if generated:
                return str(generated)
        return None

    def fetch_subawards(self, prime_award_id: str) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        page = 1
        while page <= 5:  # STTR primes are modest-sized; bounds worst-case pagination
            body = {
                "award_id": prime_award_id,
                "page": page,
                "limit": 100,
                "sort": "amount",
                "order": "desc",
            }
            data = self._post("/subawards/", body)
            batch = data.get("results", [])
            results.extend(batch)  # type: ignore[arg-type]
            page_metadata = data.get("page_metadata", {})
            if len(batch) < 100 or not page_metadata.get("hasNext"):  # type: ignore[union-attr]
                break
            page += 1
            time.sleep(0.2)
        return results


def score_ri_subaward_share(
    *,
    contract_number: object,
    ri_name: object,
    client: SubawardClient | None,
) -> tuple[DimensionStatus, float | None, SignalAbsentReason | None]:
    """Score direction 1: RI subaward share under the SBC's own STTR prime award.

    `NOT_APPLICABLE` / `NON_GRANT_INSTRUMENT` for a confirmed contract
    instrument -- an RI subaward share is not a well-formed concept there,
    and this status must never be read as a negative `ri_subaward_share=0.0`
    (design.md's D4 "Typed absence encodes" column). `UNKNOWN` instrument
    format is a distinct `NOT_MEASURABLE` case -- we genuinely cannot tell,
    which is not the same claim as "confirmed non-grant."
    """

    instrument = classify_instrument_type(contract_number)
    if instrument is InstrumentType.CONTRACT:
        return DimensionStatus.NOT_APPLICABLE, None, SignalAbsentReason.NON_GRANT_INSTRUMENT
    if instrument is InstrumentType.UNKNOWN:
        return DimensionStatus.NOT_MEASURABLE, None, SignalAbsentReason.SOURCE_FIELD_UNAVAILABLE

    ri_identity = resolve_identity(ri_name, kind=IdentityKind.ORGANIZATION)
    if ri_identity is None or not ri_identity.guard_passed:
        return (
            DimensionStatus.NOT_MEASURABLE,
            None,
            SignalAbsentReason.NAME_GENERIC_TOKEN_GUARD_FAILED,
        )
    if client is None:
        return DimensionStatus.NOT_EVALUATED, None, SignalAbsentReason.SOURCE_NOT_QUERIED

    query = normalize_award_id_for_search(str(contract_number), instrument=instrument)
    try:
        prime_award_id = client.find_prime_award_id(query, instrument=instrument)
    except Exception as exc:  # noqa: BLE001 -- live network boundary, any failure mode possible
        logger.warning("D4 subaward prime-award lookup failed for {!r}: {}", query, exc)
        return DimensionStatus.EVALUATION_FAILED, None, None
    if prime_award_id is None:
        # Confirmed grant instrument, but the prime award could not be
        # located on USASpending under this normalized id -- a real
        # coverage gap, not a searched-and-negative subaward share.
        return DimensionStatus.NOT_MEASURABLE, None, SignalAbsentReason.SOURCE_FIELD_UNAVAILABLE

    try:
        subawards = client.fetch_subawards(prime_award_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("D4 subaward fetch failed for {!r}: {}", prime_award_id, exc)
        return DimensionStatus.EVALUATION_FAILED, None, None

    total_amount = sum(float(s.get("amount") or 0.0) for s in subawards)
    matched_amount = 0.0
    for subaward in subawards:
        recipient_identity = resolve_identity(
            subaward.get("recipient_name"), kind=IdentityKind.ORGANIZATION
        )
        if recipient_identity is None or not recipient_identity.guard_passed:
            continue
        if recipient_identity.normalized == ri_identity.normalized:
            matched_amount += float(subaward.get("amount") or 0.0)

    if total_amount > 0:
        share = matched_amount / total_amount
    else:
        share = 1.0 if matched_amount > 0 else 0.0
    return DimensionStatus.MEASURED, share, None


# ---------------------------------------------------------------------------
# Combined D4 scoring
# ---------------------------------------------------------------------------


def score_d4_money_trail(
    *,
    ri_name: object,
    company_name: object,
    contract_number: object,
    ri_poc_name: object,
    pi_name: object,
    subaward_client: SubawardClient | None = None,
    form_d_index: dict[str, tuple[str, ...]] | None = None,
) -> D4MoneyTrail:
    """Score both D4 directions independently into one `D4MoneyTrail`.

    `kernel.D4MoneyTrail` carries `subaward_status` and `form_d_status` as two
    independent fields precisely so one direction's typed absence (e.g. a
    contract-instrument award's `NOT_APPLICABLE` subaward share) can never
    suppress the other direction's real result (e.g. a measured Form D
    officer match) -- exactly the class of directional bug this module's
    docstring opens with. `kernel.classify_linkage` already reads each
    direction's own status field independently, so this scorer does not
    combine them into a shared status; it just passes each direction's own
    scored status, value, and reason straight through.
    """

    subaward_status, share, subaward_reason = score_ri_subaward_share(
        contract_number=contract_number,
        ri_name=ri_name,
        client=subaward_client,
    )
    form_d_status, officer_match, form_d_reason = score_form_d_officer_ri_affiliated(
        company_name=company_name,
        ri_poc_name=ri_poc_name,
        pi_name=pi_name,
        form_d_index=form_d_index,
    )

    return D4MoneyTrail(
        subaward_status=subaward_status,
        form_d_status=form_d_status,
        ri_subaward_share=share,
        form_d_officer_ri_affiliated=officer_match,
        subaward_reason=subaward_reason,
        form_d_reason=form_d_reason,
    )
