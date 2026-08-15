"""Exploratory kernel for STTR spinout/subcontract classification.

Four building blocks the RQ1 cascade and the partner-type classifier will
consume (`specs/sttr-spinout-linkage/design.md`): identity resolution, a
generic-token guard, a typed absence-reason enum, and the pure cascade rule
over already-scored dimension evidence.

**What this module does NOT do.** It does not score any dimension (D1-D5) --
that requires the source adapters (OpenAlex/PubMed authorship, USPTO
assignment data, USASpending subawards, Form D, the D5 phrase lexicon) that
task 1.3 builds. `classify_linkage` here is the frozen *cascade rule
structure* (Order 0-4) applied to caller-supplied `DimensionAssessment`-style
evidence -- pure, deterministic, no I/O. The `SPINOUT_T2` similarity cutoff
(O-3) is left as a required parameter with no default: Revision 1 froze the
comparison *method* only (`company_name_similarity` under
`CompanyNameMetric.JARO_WINKLER`, gated by `generic_token_guard`); the numeric
cutoff is deferred to a post-task-1.4 amendment
(`specs/sttr-spinout-linkage/open-questions.md#o-3`).

Org-name matching goes through `sbir_etl.identity.normalize_company_name` /
`company_name_similarity` -- no forked normalizer. Person-name normalization
has no existing repository primitive (confirmed during Phase 0, O-0) and is
net-new here, scoped to what the D2 person trail needs: case/whitespace
normalization, given/family splitting, and generic-token stripping built on
the same `generic_token_guard` used for organization names.

Every emitted assertion this kernel supports is a `CANDIDATE` assertion only
(`docs/architecture/neo4j-epistemic-assertions-plan.md`, ADR-005): no
`SPUN_OUT_OF` edge type, no `ACCEPTED`/`REJECTED` claim status. This module
does not touch Neo4j or any graph writer; it returns plain Python values.

Epistemic tier: exploratory. This is new, spec-local code per the O-0
resolution ("(a) build the four kernel functions as new exploratory-tier code
in this spec"), grounded in `sbir_etl.identity` primitives but not itself a
primitives-tier promotion. Promote to a shared primitive only if a second
consumer appears outside this spec.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from sbir_etl.identity import (
    SUFFIX_TOKENS,
    CompanyNameMetric,
    CompanyNameProfile,
    company_name_similarity,
    normalize_company_name,
)
from sbir_etl.utils.coercion import _blank


EPISTEMIC_TIER = "exploratory"


# ---------------------------------------------------------------------------
# generic_token_guard
# ---------------------------------------------------------------------------

# Organization-name guard vocabulary: sbir_etl.identity.SUFFIX_TOKENS covers
# legal-entity suffixes only (Inc, LLC, ...); it does not cover generic
# institutional-noun tokens ("Institute", "Center" alone) that design.md's
# discipline notes and this task's brief both call out by name. Built from
# SUFFIX_TOKENS, extended -- not a forked normalizer, a guard-only addition.
ORG_GENERIC_TOKENS: frozenset[str] = SUFFIX_TOKENS | frozenset(
    {
        "institute",
        "institutes",
        "center",
        "centre",
        "foundation",
        "university",
        "college",
        "laboratory",
        "laboratories",
        "group",
        "association",
        "society",
    }
)

# Person-name analog of sbir_etl.identity.SUFFIX_TOKENS: titles, generational
# suffixes, and post-nominals that, alone or in combination, do not identify a
# specific person. Net-new -- no existing repository list covers person names.
GENERIC_PERSON_TOKENS: frozenset[str] = frozenset(
    {
        "dr",
        "mr",
        "mrs",
        "ms",
        "mx",
        "prof",
        "professor",
        "phd",
        "md",
        "jr",
        "sr",
        "ii",
        "iii",
        "iv",
    }
)


def generic_token_guard(tokens: Iterable[str], *, generic_tokens: frozenset[str]) -> bool:
    """Return ``True`` (guard passes) iff at least one non-generic token remains.

    A name dominated by generic tokens -- "The", "Inc", "Institute", "Center"
    alone for an organization, or a bare title/suffix like "Dr." or "Jr." for
    a person -- must never be allowed to produce an accepted match. Mandatory
    on D2 person-name matching and on all organization-name matching
    (`design.md`'s "Evidence dimensions" discipline notes).

    Callers select the generic-token vocabulary for their name kind:
    organization names reuse `sbir_etl.identity.SUFFIX_TOKENS`; person names
    use `GENERIC_PERSON_TOKENS`.
    """

    return any(token and token.lower() not in generic_tokens for token in tokens)


# ---------------------------------------------------------------------------
# resolve_identity
# ---------------------------------------------------------------------------


class IdentityKind(StrEnum):
    """Which normalization path `resolve_identity` applies."""

    ORGANIZATION = "organization"
    PERSON = "person"


@dataclass(frozen=True)
class ResolvedIdentity:
    """A name resolved to a normalized, guard-checked identity.

    `given_name` / `family_name` are populated only for `IdentityKind.PERSON`
    (best-effort split, last token treated as family name, or the explicit
    "Family, Given" order when a comma is present in the raw input).
    """

    kind: IdentityKind
    raw: str
    normalized: str
    tokens: tuple[str, ...]
    guard_passed: bool
    given_name: str | None = None
    family_name: str | None = None


def _normalize_person_name(value: str) -> tuple[str, tuple[str, ...]]:
    """Net-new person-name normalization: no existing primitive covers this.

    Case-folds, strips diacritics and punctuation other than hyphens/
    apostrophes within a name, and reorders an explicit "Family, Given" input
    to given-then-family order so a trailing-token family-name assumption
    holds consistently downstream.
    """

    text = unicodedata.normalize("NFKD", str(value).strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    if "," in text:
        family_part, _, given_part = text.partition(",")
        text = f"{given_part.strip()} {family_part.strip()}"
    text = re.sub(r"[^a-z\s'-]", " ", text)
    tokens = tuple(token for token in text.split() if token)
    return " ".join(tokens), tokens


def _split_person_name(tokens: tuple[str, ...]) -> tuple[str | None, str | None]:
    """Best-effort given/family split: last token is the family name."""

    if not tokens:
        return None, None
    if len(tokens) == 1:
        return None, tokens[0]
    return " ".join(tokens[:-1]), tokens[-1]


def resolve_identity(
    name: str | None,
    *,
    kind: IdentityKind,
    organization_profile: CompanyNameProfile = CompanyNameProfile.MATCHING_V1,
) -> ResolvedIdentity | None:
    """Resolve a raw org or person name to a normalized, guard-checked identity.

    Returns ``None`` for a blank/null input (the caller encodes that absence
    with `SignalAbsentReason`, this function never invents a placeholder
    identity). Organization resolution is a thin wrapper over
    `sbir_etl.identity.normalize_company_name`; no matching logic is
    reimplemented here.
    """

    if _blank(name):
        return None
    raw = str(name)
    if kind is IdentityKind.ORGANIZATION:
        normalized = normalize_company_name(raw, profile=organization_profile)
        tokens = tuple(normalized.split())
        guard_passed = generic_token_guard(tokens, generic_tokens=ORG_GENERIC_TOKENS)
        return ResolvedIdentity(
            kind=kind,
            raw=raw,
            normalized=normalized,
            tokens=tokens,
            guard_passed=guard_passed,
        )

    normalized, tokens = _normalize_person_name(raw)
    guard_passed = generic_token_guard(tokens, generic_tokens=GENERIC_PERSON_TOKENS)
    given_name, family_name = _split_person_name(tokens)
    return ResolvedIdentity(
        kind=kind,
        raw=raw,
        normalized=normalized,
        tokens=tokens,
        guard_passed=guard_passed,
        given_name=given_name,
        family_name=family_name,
    )


def identity_similarity(left: ResolvedIdentity | None, right: ResolvedIdentity | None) -> float:
    """Jaro-Winkler similarity over two already-`resolve_identity`-normalized names.

    Reuses `sbir_etl.identity.company_name_similarity` for the similarity
    computation itself (no forked string-similarity implementation) on names
    that have already been normalized by `resolve_identity` -- organization
    names via `sbir_etl.identity`'s own profile, person names via the
    net-new person-name normalizer above. This is the O-3-frozen method
    (`CompanyNameMetric.JARO_WINKLER`); the numeric acceptance cutoff is
    applied by the caller (`classify_linkage`), not here.
    """

    if left is None or right is None:
        return 0.0
    return company_name_similarity(
        left.normalized,
        right.normalized,
        metric=CompanyNameMetric.JARO_WINKLER,
    )


# ---------------------------------------------------------------------------
# signal_absent_reason
# ---------------------------------------------------------------------------


class DimensionStatus(StrEnum):
    """Per-dimension epistemic state, mirroring ADR-005's `DimensionStatus`.

    `MEASURED` requires a bounded, finite score -- zero is a measured
    no-signal, not an absence. Every other status means the dimension was
    not, or could not be, measured. Missing or null data never stands in for
    one of these states (`design.md`, "Evidence dimensions").
    """

    MEASURED = "measured"
    NOT_MEASURABLE = "not_measurable"
    NOT_APPLICABLE = "not_applicable"
    NOT_EVALUATED = "not_evaluated"
    EVALUATION_FAILED = "evaluation_failed"


class SignalAbsentReason(StrEnum):
    """Typed reason a dimension carries no signal, distinct from a genuine negative.

    Modeled on `sbir_etl.identity.RecoveryStatus`'s typed-absence pattern.
    Attached to a `NOT_MEASURABLE` / `NOT_APPLICABLE` / `NOT_EVALUATED`
    dimension status; never a substitute for a `MEASURED` zero. Each member
    below is named directly from a "Typed absence encodes" case in
    `design.md`'s D1-D5 evidence-dimension table.
    """

    # D1: RI or PI missing on the award spine -- blocks scoring downstream.
    SPINE_INCOMPLETE = "spine_incomplete"
    # D2 (person names) and organization-name matching: the name is
    # dominated by generic tokens and `generic_token_guard` rejects it --
    # distinct from "searched, found nothing."
    NAME_GENERIC_TOKEN_GUARD_FAILED = "name_generic_token_guard_failed"
    # D2/D3/D4/D5: the source that would supply this dimension's evidence has
    # not been queried yet (pipeline not yet run), as opposed to queried and
    # empty.
    SOURCE_NOT_QUERIED = "source_not_queried"
    # D3: license absence is `NOT_MEASURABLE`, never negative SUBCONTRACT
    # evidence -- recorded RI-to-SBC licenses are structurally sparse
    # (O-12), not a queryable "no license" fact.
    LICENSE_RECORDS_SPARSE = "license_records_sparse"
    # D4: the award's funding instrument is not grant-based, so an RI
    # subaward share is not an applicable concept for this row.
    NON_GRANT_INSTRUMENT = "non_grant_instrument"
    # D4/D5: the underlying field (Form D officer/director, firm text for
    # phrase matching) is absent on the source record itself.
    SOURCE_FIELD_UNAVAILABLE = "source_field_unavailable"


# ---------------------------------------------------------------------------
# classify_linkage
# ---------------------------------------------------------------------------


class LinkageLabel(StrEnum):
    """The four RQ1 classification outcomes (`design.md`, "Classification cascade")."""

    SPINOUT_T1 = "spinout_t1"
    SPINOUT_T2 = "spinout_t2"
    SUBCONTRACT = "subcontract"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True)
class D1Spine:
    """D1: the award join spine. No `DimensionStatus` of its own -- Order 0
    of the cascade reads presence directly."""

    ri_present: bool
    pi_present: bool


@dataclass(frozen=True)
class D2PersonTrail:
    """D2: person trail (PI and Form-D-derived founders), already scored.

    `person_similarity` is the raw `identity_similarity` score between the
    best-candidate person name and an RI-affiliated authorship name; the
    O-3 cutoff that turns it into a `SPINOUT_T2` fuzzy positive is applied
    inside `classify_linkage`, not here.
    """

    status: DimensionStatus
    exact_person_ri_affiliation: bool = False
    person_similarity: float | None = None
    person_guard_passed: bool = False
    reason: SignalAbsentReason | None = None


@dataclass(frozen=True)
class D3IpTrail:
    """D3: IP trail. `any_ip_link` is derived by `classify_linkage`, not
    supplied here, so the two sub-signals stay the single source of truth."""

    status: DimensionStatus
    patent_assigned_to_ri_with_sbc_inventor: bool = False
    recorded_license_ri_to_sbc: bool = False
    reason: SignalAbsentReason | None = None


@dataclass(frozen=True)
class D4MoneyTrail:
    """D4: money / paper trail. Two independent directions -- `ri_subaward_share`
    is a subcontract marker, `form_d_officer_ri_affiliated` is a spinout marker."""

    status: DimensionStatus
    ri_subaward_share: float | None = None
    form_d_officer_ri_affiliated: bool = False
    reason: SignalAbsentReason | None = None


@dataclass(frozen=True)
class D5TextTrail:
    """D5: deterministic phrase-lexicon trail over award/firm text."""

    status: DimensionStatus
    spinout_phrase: bool = False
    reason: SignalAbsentReason | None = None


@dataclass(frozen=True)
class LinkageDecision:
    """The cascade's output: a label plus which Order fired and why."""

    label: LinkageLabel
    cascade_order: int
    rationale: str


def classify_linkage(
    *,
    d1: D1Spine,
    d2: D2PersonTrail,
    d3: D3IpTrail,
    d4: D4MoneyTrail,
    d5: D5TextTrail,
    similarity_cutoff: float,
) -> LinkageDecision:
    """Apply the frozen Order 0-4 cascade rule to already-scored dimensions.

    This is the cascade **rule structure** only -- Order 0 through 4 exactly
    as frozen in `design.md`'s "Classification cascade (RQ1)" table. It does
    not score D1-D5 (that is task 1.3, over the source adapters D2-D5
    depend on); every input here is caller-supplied, already-computed
    evidence. Pure and deterministic: no I/O, no randomness, no clock reads.

    ``similarity_cutoff`` has **no default**. O-3 froze the fuzzy-match
    *method* (`company_name_similarity` under `CompanyNameMetric.JARO_WINKLER`,
    gated by `generic_token_guard`) but explicitly deferred the numeric
    cutoff to a post-task-1.4 amendment; hardcoding a value here would
    silently un-defer it.

    Discipline enforced (`design.md`):
    - **Absence never advances a label.** Order 3 requires `MEASURED` status
      on D2, D3, D5 and a positive D4 subaward share; any `NOT_MEASURABLE` /
      `NOT_APPLICABLE` / `NOT_EVALUATED` / `EVALUATION_FAILED` dimension
      falls through to Order 4 `INDETERMINATE`.
    - **License absence cannot create a SUBCONTRACT.** D3's status must be
      `MEASURED` at Order 3; a `NOT_MEASURABLE` D3 (license sparsity, O-12)
      never satisfies that clause on its own.
    """

    # Order 0: the join spine itself is incomplete.
    if not (d1.ri_present and d1.pi_present):
        return LinkageDecision(
            LinkageLabel.INDETERMINATE,
            cascade_order=0,
            rationale="D1 spine incomplete: RI or PI absent",
        )

    fuzzy_person = (
        d2.person_similarity is not None
        and d2.person_similarity >= similarity_cutoff
        and d2.person_guard_passed
    )
    any_person_link = d2.exact_person_ri_affiliation or fuzzy_person
    any_ip_link = d3.patent_assigned_to_ri_with_sbc_inventor or d3.recorded_license_ri_to_sbc

    # Order 1: one exact person or IP link with affiliation evidence.
    if d2.status is DimensionStatus.MEASURED and d2.exact_person_ri_affiliation:
        return LinkageDecision(
            LinkageLabel.SPINOUT_T1,
            cascade_order=1,
            rationale="exact D2 person-RI affiliation",
        )
    if d3.status is DimensionStatus.MEASURED and any_ip_link:
        return LinkageDecision(
            LinkageLabel.SPINOUT_T1,
            cascade_order=1,
            rationale="exact D3 IP link (patent assignment or recorded license)",
        )

    # Order 2: a fuzzy positive corroborated by a second, distinct dimension.
    d2_fuzzy_positive = d2.status is DimensionStatus.MEASURED and fuzzy_person
    d5_positive = d5.status is DimensionStatus.MEASURED and d5.spinout_phrase
    if d2_fuzzy_positive or d5_positive:
        primary = "D2" if d2_fuzzy_positive else "D5"
        corroborated = (
            (primary != "D3" and d3.status is DimensionStatus.MEASURED and any_ip_link)
            or (d4.status is DimensionStatus.MEASURED and d4.form_d_officer_ri_affiliated)
            or (primary != "D5" and d5.status is DimensionStatus.MEASURED and d5.spinout_phrase)
        )
        if corroborated:
            return LinkageDecision(
                LinkageLabel.SPINOUT_T2,
                cascade_order=2,
                rationale=f"fuzzy positive ({primary}) with independent corroboration",
            )

    # Order 3: spinout-bearing dimensions measured and negative, subaward positive.
    if (
        d4.status is DimensionStatus.MEASURED
        and d4.ri_subaward_share is not None
        and d4.ri_subaward_share > 0
        and d2.status is DimensionStatus.MEASURED
        and not any_person_link
        and d3.status is DimensionStatus.MEASURED
        and not any_ip_link
        and d5.status is DimensionStatus.MEASURED
        and not d5.spinout_phrase
    ):
        return LinkageDecision(
            LinkageLabel.SUBCONTRACT,
            cascade_order=3,
            rationale="measured-negative D2/D3/D5 with positive D4 subaward share",
        )

    # Order 4: typed absence dominates.
    return LinkageDecision(
        LinkageLabel.INDETERMINATE,
        cascade_order=4,
        rationale="no exact or corroborated fuzzy evidence; typed absence dominates",
    )
