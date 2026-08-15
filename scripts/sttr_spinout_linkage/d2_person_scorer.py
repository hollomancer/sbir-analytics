"""D2 person-trail scorer for the STTR spinout-linkage RQ1 cascade (task 1.3).

Scores `kernel.D2PersonTrail` for one award: PI plus Form-D-derived founder
names, matched against OpenAlex / PubMed / ORCID authorship affiliations for
the award's RI. Composes `kernel.resolve_identity` / `identity_similarity` /
`generic_token_guard` and the existing `Sync{OpenAlex,PubMed,ORCID}Client`
``.lookup(name)`` facades (`sbir_etl/enrichers/sync_wrappers.py`) -- no
forked identity or API-calling logic, and no second rate-limit/retry layer
(the clients' own `RateLimiter`/`BaseAsyncAPIClient` retry already covers
that).

**Scope (O-1, resolved).** D2 covers the PI plus founders, where "founders"
means officer/director names already surfaced by a *high-confidence* Form-D
company match in `data/form_d_details.jsonl` -- no new founder-discovery
pipeline. `founder_names_for_company` implements this join, reusing the exact
`CompanyNameProfile.FORM_D_JOIN_V1` name-key pattern already used in
`notebooks/explorations/b1_sttr_partner_type_commercialization.ipynb`'s
`join-channels` cell (Form D carries no UEI, so the join is name-key only,
same as that cell). An award whose firm has no Form-D match falls back to
PI-only D2 matching, per O-1.

**±5-year window (O-2, resolved) -- known limitation.** Design.md's D2 row
requires RI-affiliated authorship within ±5 years of the award date to
count. `OpenAlexRecord` / `PubMedRecord` / `ORCIDRecord` -- the dataclasses
`SyncOpenAlexClient.lookup` / `SyncPubMedClient.lookup` /
`SyncORCIDClient.lookup` return -- carry an `affiliations: list[str]`
snapshot with no per-affiliation dates (OpenAlex's raw API *does* carry a
``years`` list per affiliation, and ORCID's raw employment summaries carry
start/end dates, but extracting them means reading the raw profile dict
below the `.lookup()` facade the task brief specifies, which starts to
duplicate the clients' own parsing). This scorer therefore accepts
`award_year` / `window_years` so the window is declared and threaded through
the call, but does **not** mechanically filter affiliation matches by year
in v1 -- `exact_person_ri_affiliation` and `person_similarity` are affiliation
-list-membership checks, not date-windowed ones. This is a real, flagged gap
(specs/sttr-spinout-linkage/design.md's D2 row), not silently assumed away;
follow-on work can extend the client parsing or add a dedicated
years-aware lookup to close it.

Epistemic tier: exploratory (`specs/sttr-spinout-linkage/tasks.md`, task
1.3's D2 slice). No dimension score from this module is citable.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from loguru import logger

from sbir_etl.exceptions import APIError
from sbir_etl.identity import CompanyNameProfile, normalize_company_name
from sbir_etl.utils.coercion import _blank

from .kernel import (
    D2PersonTrail,
    DimensionStatus,
    IdentityKind,
    ResolvedIdentity,
    SignalAbsentReason,
    identity_similarity,
    resolve_identity,
)


EPISTEMIC_TIER = "exploratory"

DEFAULT_WINDOW_YEARS = 5

_OFFICER_DIRECTOR_TITLE_RE = re.compile(r"director|officer", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Form-D founder-name join (O-1: officer/director names only, no new
# discovery pipeline)
# ---------------------------------------------------------------------------


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "sbir_etl").exists():
            return candidate
    raise RuntimeError("Not inside the sbir-analytics checkout")


_REPO_ROOT = _find_repo_root(Path(__file__).resolve())
DEFAULT_FORM_D_PATH = _REPO_ROOT / "data" / "form_d_details.jsonl"


def load_form_d_founder_index(
    path: Path | None = None,
    *,
    min_confidence_tier: str | None = "high",
) -> dict[str, list[str]]:
    """Load `data/form_d_details.jsonl` into `{FORM_D_JOIN_V1 firm key: officer/director names}`.

    Same file, same `keep=lambda rec: match_confidence.tier == "high"` filter, and same
    `CompanyNameProfile.FORM_D_JOIN_V1` name key as
    `notebooks/explorations/b1_sttr_partner_type_commercialization.ipynb`'s `join-channels`
    cell's `load_jsonl_names` -- Form D carries no UEI, so name-key is the only join key,
    matching that precedent exactly. `min_confidence_tier=None` disables the tier filter.

    A missing file returns an empty index (channel not searched), matching that same
    notebook's missingness discipline -- never raises, never fabricates founder names.
    Officer/director names come from each `offerings[].related_persons[]` entry whose
    `title` contains "director" or "officer" (case-insensitive); other roles (e.g. plain
    "Promoter") are excluded.
    """

    if path is None:
        path = DEFAULT_FORM_D_PATH
    index: dict[str, set[str]] = defaultdict(set)
    if not path.exists():
        logger.warning("Form D details file not found at {} -- founder names not searched", path)
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

    return {key: sorted(names) for key, names in index.items()}


def founder_names_for_company(
    company_name: object, form_d_index: dict[str, list[str]]
) -> list[str]:
    """Look up Form-D-derived officer/director names for one award's company name.

    Returns `[]` (not an error) when the company has no Form-D match, no name at all, or
    `form_d_index` is empty (file absent) -- D2 falls back to PI-only matching per O-1.
    """

    if _blank(company_name):
        return []
    key = normalize_company_name(company_name, profile=CompanyNameProfile.FORM_D_JOIN_V1)
    return form_d_index.get(key, [])


# ---------------------------------------------------------------------------
# D2 person-trail scoring
# ---------------------------------------------------------------------------


class PersonLookupClient(Protocol):
    """Structural type for the three `Sync*Client.lookup(name)` facades this scorer calls.

    Satisfied by `SyncOpenAlexClient`, `SyncPubMedClient`, `SyncORCIDClient`
    (`sbir_etl/enrichers/sync_wrappers.py`) without importing them here, so unit tests can
    inject a bare fake implementing only `.lookup`.
    """

    def lookup(self, name: str) -> object | None: ...


def _record_author_name(record: object) -> str | None:
    """Extract the API record's own author-name string, whichever dataclass it is.

    `OpenAlexRecord.display_name`, `PubMedRecord.author_name`, or
    `ORCIDRecord.given_name`/`family_name` -- the three `lookup()` return types named in
    the task brief. Duck-typed via `getattr` so this module does not import the enricher
    dataclasses (no new coupling beyond the `.lookup()` call itself).
    """

    display_name = getattr(record, "display_name", None)
    if display_name:
        return str(display_name)
    author_name = getattr(record, "author_name", None)
    if author_name:
        return str(author_name)
    family_name = getattr(record, "family_name", None)
    if family_name:
        given_name = getattr(record, "given_name", None) or ""
        return f"{given_name} {family_name}".strip()
    return None


@dataclass(frozen=True)
class _SourceHit:
    """One candidate-name x source-client query outcome, already RI-scoped.

    `ri_affiliation_hit=False` means the record's affiliations did not contain the award's
    RI at all -- this hit contributes nothing to either the exact or fuzzy path. Both
    `exact_identity` and `similarity` are only meaningful when `ri_affiliation_hit=True`,
    matching `D2PersonTrail.person_similarity`'s kernel-level contract ("the raw
    `identity_similarity` score between the best-candidate person name and an
    RI-affiliated authorship name" -- the fuzziness is about the *name* match, not
    the affiliation, which is exact per O-3).
    """

    ri_affiliation_hit: bool
    exact_identity: bool
    similarity: float | None
    author_guard_passed: bool


def _score_one_source(
    candidate: ResolvedIdentity,
    ri_identity: ResolvedIdentity,
    client: PersonLookupClient,
) -> _SourceHit | None:
    """Query one source for one candidate name; `None` means no usable record came back."""

    try:
        record = client.lookup(candidate.raw)
    except APIError as exc:
        logger.warning("D2 lookup failed for {!r}: {}", candidate.raw, exc)
        return None
    if record is None:
        return None

    author_name = _record_author_name(record)
    author_identity = resolve_identity(author_name, kind=IdentityKind.PERSON)
    if author_identity is None:
        return None

    affiliations: Iterable[str] = getattr(record, "affiliations", None) or []
    ri_affiliation_hit = any(
        resolved is not None
        and resolved.guard_passed
        and resolved.normalized == ri_identity.normalized
        for resolved in (
            resolve_identity(affiliation, kind=IdentityKind.ORGANIZATION)
            for affiliation in affiliations
        )
    )
    if not ri_affiliation_hit:
        return _SourceHit(
            ri_affiliation_hit=False,
            exact_identity=False,
            similarity=None,
            author_guard_passed=author_identity.guard_passed,
        )

    exact_identity = (
        author_identity.guard_passed and author_identity.normalized == candidate.normalized
    )
    similarity = identity_similarity(candidate, author_identity)
    return _SourceHit(
        ri_affiliation_hit=True,
        exact_identity=exact_identity,
        similarity=similarity,
        author_guard_passed=author_identity.guard_passed,
    )


def score_d2_person_trail(
    *,
    pi_name: object,
    founder_names: Sequence[str] = (),
    ri_name: object,
    award_year: int | None = None,
    window_years: int = DEFAULT_WINDOW_YEARS,
    openalex: PersonLookupClient | None = None,
    pubmed: PersonLookupClient | None = None,
    orcid: PersonLookupClient | None = None,
) -> D2PersonTrail:
    """Score D2 for one award: PI + Form-D founders against OpenAlex/PubMed/ORCID.

    `award_year` / `window_years` are accepted and threaded through (module docstring's
    "±5-year window -- known limitation": not mechanically enforced in v1, since
    `.lookup()`'s `affiliations: list[str]` carries no per-affiliation dates).

    A `None` source client means that source was not queried this call (the caller's
    batch-rate-limit/skip decision) -- if **all three** are `None`, the whole trail is
    `NOT_EVALUATED`/`SOURCE_NOT_QUERIED`, never presented as a negative. At least one
    configured source with no hits is a real `MEASURED` negative.
    """

    del award_year, window_years  # declared, not enforced -- see module docstring

    candidate_names = [name for name in (pi_name, *founder_names) if not _blank(name)]
    if not candidate_names:
        return D2PersonTrail(
            status=DimensionStatus.NOT_MEASURABLE,
            reason=SignalAbsentReason.SOURCE_FIELD_UNAVAILABLE,
        )

    ri_identity = resolve_identity(ri_name, kind=IdentityKind.ORGANIZATION)
    if ri_identity is None or not ri_identity.guard_passed:
        return D2PersonTrail(
            status=DimensionStatus.NOT_MEASURABLE,
            reason=SignalAbsentReason.SOURCE_FIELD_UNAVAILABLE,
        )

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
        return D2PersonTrail(
            status=DimensionStatus.NOT_MEASURABLE,
            reason=SignalAbsentReason.NAME_GENERIC_TOKEN_GUARD_FAILED,
        )

    sources: dict[str, PersonLookupClient | None] = {
        "openalex": openalex,
        "pubmed": pubmed,
        "orcid": orcid,
    }
    configured = {name: client for name, client in sources.items() if client is not None}
    if not configured:
        return D2PersonTrail(
            status=DimensionStatus.NOT_EVALUATED,
            reason=SignalAbsentReason.SOURCE_NOT_QUERIED,
        )

    any_exact = False
    best_similarity: float | None = None
    best_guard_passed = False
    for candidate in candidates:
        for client in configured.values():
            hit = _score_one_source(candidate, ri_identity, client)
            if hit is None or not hit.ri_affiliation_hit:
                continue
            if hit.exact_identity:
                any_exact = True
            elif hit.similarity is not None and (
                best_similarity is None or hit.similarity > best_similarity
            ):
                best_similarity = hit.similarity
                best_guard_passed = hit.author_guard_passed

    return D2PersonTrail(
        status=DimensionStatus.MEASURED,
        exact_person_ri_affiliation=any_exact,
        person_similarity=best_similarity,
        person_guard_passed=best_guard_passed,
    )
