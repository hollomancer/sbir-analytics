"""Deterministic monthly procurement-center packet generation."""

from __future__ import annotations

import hashlib
import html
import json
import logging
import math
import re
import shutil
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import pandas as pd
from markdown_it import MarkdownIt

from sbir_etl.reporting.procurement_transition.ai import MAX_SUMMARY_CHARS
from sbir_etl.reporting.procurement_transition.cet_vocabulary import cet_agreement_fact
from sbir_etl.utils.procurement_text import (
    document_token_frequencies,
    extract_connection_sentences,
    find_lineage_phrases,
    rank_phrases_by_rarity,
    shared_technical_phrases,
    tokenize_technical_text,
)


logger = logging.getLogger(__name__)

_AWARD_KEY_VERSION = "sbir-source-v2"

_ANNOTATION_FIELDS = (
    ("interest_alignment", "Mission-interest alignment"),
    ("technology_ecosystem", "Technology ecosystem"),
    ("potential_transition_lane", "Potential acquisition transition lane"),
    ("alignment_rationale", "Alignment rationale"),
)


def _pick(df: pd.DataFrame, *names: str) -> pd.Series:
    for name in names:
        if name in df.columns:
            return df[name]
    return pd.Series([None] * len(df), index=df.index)


def _coalesce(df: pd.DataFrame, *names: str) -> pd.Series:
    result = pd.Series([None] * len(df), index=df.index, dtype="object")
    for name in names:
        if name in df.columns:
            result = result.combine_first(df[name])
    return result


# Stable source fields used to identify one award. Mutable report content such
# as title, abstract, amount, and recorded end date deliberately stays out of
# this key; changes to those fields belong in ``row_hash``.
_AWARD_KEY_FIELDS = (
    ("Agency Tracking Number", "agency_tracking_number"),
    ("Contract", "contract_number"),
    ("Agency", "agency"),
    ("Branch", "branch", "sub_agency"),
    ("Phase", "phase"),
    ("Program", "program"),
    ("Proposal Award Date", "award_date"),
    ("Solicitation Number", "solicitation_number"),
)


def _row_value(row: pd.Series, *names: str) -> str | None:
    for name in names:
        if (value := _display(row.get(name))) is not None:
            return value
    return None


def _identity_component(value: Any) -> str:
    return re.sub(r"\s+", " ", _display(value) or "").strip().upper()


def _award_key_field_value(row: pd.Series, names: tuple[str, ...]) -> str | None:
    value = _row_value(row, *names)
    if names[0] != "Proposal Award Date" or value is None:
        return value
    text = value.strip()
    match = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:\D|$)", text)
    parts: tuple[str, str, str] | None
    if match is None:
        match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})(?:\D|$)", text)
        parts = (match.group(3), match.group(1), match.group(2)) if match else None
    else:
        parts = (match.group(1), match.group(2), match.group(3))
    if parts is None:
        return value
    try:
        year, month, day = (int(part) for part in parts)
        return date(year, month, day).isoformat()
    except ValueError:
        return value


def _natural_award_id(row: pd.Series) -> str | None:
    # Preserve the report's existing public lineage identifier for readable
    # output and legacy candidate files. It is never used as award grain: the
    # separate ``award_key`` owns joins, deduplication, and candidate identity.
    return _row_value(
        row,
        "Agency Tracking Number",
        "agency_tracking_number",
        "Contract",
        "contract_number",
        "award_id",
    )


def _stable_award_id(row: pd.Series) -> str:
    natural = _natural_award_id(row)
    if natural is not None:
        return natural
    return "sbir-" + _award_grain_key(row)[:20]


def _award_grain_key(row: pd.Series) -> str:
    """Identity of one *award*, not one firm/topic.

    ``award_id`` stays the natural identifier for readable lineage. It is not
    award-grain on its own, so joins, deduplication, and snapshot comparison use
    this separate stable source compound.
    """

    if existing := _row_value(row, "award_key"):
        if _row_value(row, "award_key_version") != _AWARD_KEY_VERSION:
            raise ValueError(
                "pre-migration award_key cannot be reused; regenerate identity from raw awards"
            )
        return existing

    recipient = (
        _row_value(row, "UEI", "uei", "recipient_uei")
        or _row_value(row, "Duns", "duns", "recipient_duns")
        or _row_value(row, "Company", "company", "recipient_name")
    )
    components = (
        "sbir",
        recipient,
        *(_award_key_field_value(row, names) for names in _AWARD_KEY_FIELDS),
    )
    material = "|".join(_identity_component(value) for value in components)
    return hashlib.sha256(material.encode()).hexdigest()[:24]


def normalize_awards(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize the public SBIR.gov CSV while preserving every phase label."""

    if raw.empty:
        return pd.DataFrame(
            columns=[
                "award_id",
                "award_key",
                "award_key_version",
                "agency_tracking_number",
                "contract_number",
                "company",
                "title",
                "agency",
                "branch",
                "phase",
                "program",
                "award_date",
                "recorded_end_date",
                "uei",
                "amount",
                "abstract",
                "row_hash",
                "source_edition_count",
                "source_edition_variants",
                "public_id_award_count",
                "naics_code",
                "psc_code",
                "office",
                "cet",
                "source_url",
                "solicitation_number",
                "topic_code",
            ]
        )
    out = pd.DataFrame(index=raw.index)
    out["award_id"] = raw.apply(_stable_award_id, axis=1)
    out["award_key"] = raw.apply(_award_grain_key, axis=1)
    out["award_key_version"] = _AWARD_KEY_VERSION
    out["agency_tracking_number"] = _pick(raw, "Agency Tracking Number", "agency_tracking_number")
    out["contract_number"] = _pick(raw, "Contract", "contract_number")
    out["company"] = _pick(raw, "Company", "company", "recipient_name")
    out["title"] = _pick(raw, "Award Title", "title")
    out["agency"] = _pick(raw, "Agency", "agency")
    out["branch"] = _pick(raw, "Branch", "branch", "sub_agency")
    out["phase"] = _pick(raw, "Phase", "phase")
    out["program"] = _pick(raw, "Program", "program")
    out["award_date"] = pd.to_datetime(
        _pick(raw, "Proposal Award Date", "award_date"), errors="coerce"
    ).dt.date
    out["recorded_end_date"] = pd.to_datetime(
        _pick(raw, "Contract End Date", "period_of_performance_end", "recorded_end_date"),
        errors="coerce",
    ).dt.date
    out["uei"] = _pick(raw, "UEI", "uei", "recipient_uei")
    out["amount"] = pd.to_numeric(
        _pick(raw, "Award Amount", "amount").astype(str).str.replace(r"[$,]", "", regex=True),
        errors="coerce",
    )
    out["abstract"] = _pick(raw, "Abstract", "abstract")
    out["naics_code"] = _pick(raw, "NAICS", "naics_code")
    out["psc_code"] = _pick(raw, "PSC", "psc_code", "product_or_service_code")
    out["office"] = _pick(raw, "Office", "office", "awarding_office_name")
    out["cet"] = _pick(raw, "CET", "cet")
    out["source_url"] = _pick(raw, "source_url", "SBIR URL")
    out["solicitation_number"] = _pick(raw, "Solicitation Number", "solicitation_number")
    out["topic_code"] = _pick(raw, "Topic Code", "topic_code")
    material = out.astype("string").fillna("").agg("|".join, axis=1)
    out["row_hash"] = material.map(lambda value: hashlib.sha256(value.encode()).hexdigest())

    # SBIR.gov sometimes publishes several editions of the same stable award
    # (typically revised amount/end-date records). Treat them as revisions, not
    # distinct awards, and retain the most current-looking public edition.
    edition_counts = out.groupby("award_key")["award_key"].transform("size")
    edition_variants = out.groupby("award_key")["row_hash"].transform("nunique")
    out["source_edition_count"] = edition_counts
    out["source_edition_variants"] = edition_variants
    duplicate_editions = edition_counts.gt(1)
    if duplicate_editions.any():
        logger.warning(
            "Collapsing %d SBIR source rows across %d stable award keys",
            int(duplicate_editions.sum()),
            int(out.loc[duplicate_editions, "award_key"].nunique()),
        )
        out = (
            out.assign(
                _end_sort=pd.to_datetime(out["recorded_end_date"], errors="coerce"),
                _amount_sort=pd.to_numeric(out["amount"], errors="coerce"),
            )
            .sort_values(
                ["award_key", "_end_sort", "_amount_sort", "row_hash"],
                kind="stable",
                na_position="first",
            )
            .drop_duplicates("award_key", keep="last")
            .drop(columns=["_end_sort", "_amount_sort"])
        )
    out["public_id_award_count"] = out.groupby("award_id")["award_key"].transform("nunique")
    return out.reset_index(drop=True)


def _month_bounds(report_month: str) -> tuple[date, date]:
    start = pd.Timestamp(f"{report_month}-01").date()
    end = (pd.Timestamp(start) + pd.offsets.MonthEnd(1)).date()
    return start, end


def build_award_cohorts(
    current: pd.DataFrame,
    previous: pd.DataFrame | None,
    *,
    report_month: str,
    approaching_days: int = 180,
) -> pd.DataFrame:
    def _prepare(frame: pd.DataFrame | None, *, label: str) -> pd.DataFrame:
        if frame is None or frame.empty:
            return pd.DataFrame() if frame is None else frame.copy()
        if "row_hash" not in frame.columns:
            return normalize_awards(frame)
        versions = frame.get("award_key_version", pd.Series(pd.NA, index=frame.index))
        if not versions.eq(_AWARD_KEY_VERSION).all():
            raise ValueError(
                f"{label} uses a pre-migration award key; regenerate it from raw awards"
            )
        return frame.copy()

    current = _prepare(current, label="current award snapshot")
    prior = _prepare(previous, label="previous award snapshot")
    start, end = _month_bounds(report_month)
    horizon = (pd.Timestamp(end) + pd.Timedelta(days=approaching_days)).date()

    def _between(value: Any, lower: date, upper: date, *, include_lower: bool = True) -> bool:
        if value is None or bool(pd.isna(value)):
            return False
        parsed = value if isinstance(value, date) else pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return False
        comparable = parsed.date() if isinstance(parsed, datetime) else parsed
        return lower <= comparable <= upper if include_lower else lower < comparable <= upper

    # Diff on the compound award-grain key, never on the bare tracking number:
    # the public snapshot reuses tracking numbers across tens of thousands of
    # distinct awards, and collapsing them marks unchanged rows as changed. The
    # value is a *set* of hashes so residual duplicates still compare correctly.
    def _keys(frame: pd.DataFrame) -> pd.Series:
        if "award_key" in frame.columns:
            return frame["award_key"].astype(str)
        return frame.get("award_id", pd.Series(dtype="object")).astype(str)

    prior_hashes: dict[str, set[str]] = {}
    if not prior.empty:
        for key, row_hash in zip(_keys(prior), prior.get("row_hash", []), strict=False):
            prior_hashes.setdefault(key, set()).add(str(row_hash))
    current_keys = _keys(current)
    current["newly_observed"] = ~current_keys.isin(prior_hashes)
    current["changed_since_prior_report"] = [
        key in prior_hashes and str(row_hash) not in prior_hashes[key]
        for key, row_hash in zip(current_keys, current["row_hash"], strict=True)
    ]
    current["awarded_in_period"] = current["award_date"].map(
        lambda value: _between(value, start, end)
    )
    current["recent_recorded_end"] = current["recorded_end_date"].map(
        lambda value: _between(value, start, end)
    )
    current["approaching_recorded_end"] = current["recorded_end_date"].map(
        lambda value: _between(value, end, horizon, include_lower=False)
    )
    flags = [
        "newly_observed",
        "changed_since_prior_report",
        "awarded_in_period",
        "recent_recorded_end",
        "approaching_recorded_end",
    ]
    return current.loc[current[flags].any(axis=1)].reset_index(drop=True)


def _slug(value: Any) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (_display(value) or "unassigned").lower()).strip("-")
    return slug or "unassigned"


def _money(value: Any) -> str:
    number = _number(value)
    return "N/A" if number is None else f"${number:,.0f}"


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(number) else number


def _display(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple, dict)):
        try:
            if bool(pd.isna(value)):
                return None
        except (TypeError, ValueError):
            pass
    text = str(value).strip()
    return text if text and text.lower() not in {"nan", "nat", "none", "<na>"} else None


def _as_bool(value: Any) -> bool:
    text = _display(value)
    return bool(text and text.lower() in {"true", "1", "yes", "y"})


def _first_value(*values: Any) -> Any:
    for value in values:
        if _display(value) is not None:
            return value
    return None


def _markdown_text(value: Any, *, default: str = "Unavailable", limit: int = 700) -> str:
    """Render one untrusted public-data value as inert, compact Markdown text."""

    text = _display(value)
    if text is None:
        return default
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        shortened = text[: limit - 1].rsplit(" ", 1)[0].rstrip()
        text = f"{shortened or text[: limit - 1]}\N{HORIZONTAL ELLIPSIS}"
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\`*_\[\]{}#|])", r"\\\1", text)


def _same_text(left: Any, right: Any) -> bool:
    left_text = _display(left)
    right_text = _display(right)
    if left_text is None or right_text is None:
        return False
    left_normalized = re.sub(r"\W+", " ", left_text.lower()).strip()
    right_normalized = re.sub(r"\W+", " ", right_text.lower()).strip()
    return left_normalized == right_normalized


def _safe_url(value: Any) -> str | None:
    raw = _display(value)
    if raw is None:
        return None
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return quote(raw, safe=":/?#@!$&'*,;=%+-._~")


def _date_label(value: Any) -> str | None:
    text = _display(value)
    if text is None:
        return None
    parsed = pd.to_datetime(text, errors="coerce", utc=True)
    if pd.isna(parsed):
        return text
    return f"{parsed.strftime('%B')} {parsed.day}, {parsed.year}"


_EVIDENCE_PLACEHOLDERS = frozenset(
    {
        "0",
        "NA",
        "NONE",
        "NULL",
        "UNKNOWN",
        "UNAVAILABLE",
        "NOTAVAILABLE",
        "NOTAPPLICABLE",
    }
)


def _evidence_text(value: Any) -> str | None:
    text = _display(value)
    if text is None:
        return None
    canonical = re.sub(r"[\s._/-]+", "", text.upper())
    return None if canonical in _EVIDENCE_PLACEHOLDERS else text


def _normalized_identifier(value: Any) -> str | None:
    text = _evidence_text(value)
    if text is None:
        return None
    normalized = re.sub(r"[^A-Z0-9]+", "", text.upper())
    if len(normalized) != 12 or set(normalized) == {"0"}:
        return None
    return normalized


def _normalized_code(value: Any, *, code_type: str) -> str | None:
    text = _evidence_text(value)
    if text is None:
        return None
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]
    normalized = re.sub(r"[\s-]+", "", text.upper())
    pattern = r"\d{2,6}" if code_type == "naics" else r"[A-Z0-9]{4}"
    if not re.fullmatch(pattern, normalized) or set(normalized) == {"0"}:
        return None
    return normalized


def _human_list(values: list[str]) -> str:
    if len(values) < 2:
        return values[0] if values else ""
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])}, and {values[-1]}"


def _matching_organization(row: pd.Series) -> tuple[str, str] | None:
    """Finest org level (office > organization > agency) shared by award and notice."""

    for award_field, opportunity_fields, label in (
        ("award_office", ("opportunity_office", "target_office"), "office"),
        ("award_branch", ("opportunity_sub_tier", "target_sub_agency"), "organization"),
        ("award_agency", ("opportunity_agency", "target_agency"), "agency"),
    ):
        award_value = _evidence_text(row.get(award_field))
        opportunity_value = _evidence_text(
            _first_value(*(row.get(name) for name in opportunity_fields))
        )
        if award_value and opportunity_value and _same_text(award_value, opportunity_value):
            return label, award_value
    return None


def _matching_organization_fact(row: pd.Series) -> str | None:
    match = _matching_organization(row)
    if match is None:
        return None
    label, value = match
    return f"The award and notice list the same {label} ({value})."


def _cited_award_identifier(row: pd.Series) -> str | None:
    """The awardee's SBIR award/contract number, iff the notice text cites it.

    A J&A or directed notice citing the prior award's own number is the
    strongest forward lineage evidence a reader can verify. Identifiers under
    6 normalized characters are ignored (false-hit prone).
    """

    notice_text = _display(
        _first_value(row.get("opportunity_description"), row.get("target_description"))
    )
    if notice_text is None:
        return None
    haystack = re.sub(r"[^A-Z0-9]+", "", notice_text.upper())
    for value in (
        row.get("award_contract_number"),
        row.get("prior_contract_number"),
        row.get("award_agency_tracking_number"),
        row.get("prior_agency_tracking_number"),
        row.get("award_id"),
        row.get("prior_award_id"),
    ):
        award_id = _display(value)
        if award_id is None:
            continue
        needle = re.sub(r"[^A-Z0-9]+", "", award_id.upper())
        if len(needle) >= 6 and needle in haystack:
            return award_id
    return None


def _notice_names_awardee(row: pd.Series) -> bool:
    """True iff the notice carries the awardee's own UEI (a strong lineage signal)."""

    award_uei = _normalized_identifier(
        _first_value(row.get("award_uei"), row.get("uei"), row.get("recipient_uei"))
    )
    opportunity_uei = _normalized_identifier(
        _first_value(
            row.get("opportunity_awardee_uei"),
            row.get("awardee_uei"),
            row.get("ueiSAM"),
            row.get("target_recipient_uei"),
        )
    )
    return bool(award_uei and award_uei == opportunity_uei)


def _lineage_labels(phrases: Iterable[str]) -> list[str]:
    return [
        "Phase III" if phrase == "phase iii" else "Phase 3" if phrase == "phase 3" else phrase
        for phrase in phrases
    ]


def _validate_line(row: pd.Series, signal: str) -> str:
    """Path-specific validation step derived from the actual public evidence."""

    opportunity_description = _display(
        _first_value(row.get("opportunity_description"), row.get("target_description"))
    )
    lineage = _lineage_labels(find_lineage_phrases(opportunity_description))
    lineage_clause = (
        f" The notice text says {_human_list([f'“{label}”' for label in lineage])} — read the "
        "statement of work to confirm it extends this awardee's effort, not a generic capability."
        if lineage
        else ""
    )

    if signal != "directed":
        return (
            "Assess technical fit, acquisition strategy, and competition requirements — this is "
            "an open competition, not a directed award." + lineage_clause
        )

    parts = [
        "Confirm the work derives from, extends, or completes this awardee's prior "
        "SBIR/STTR-funded effort and covers the stated need."
    ]
    if lineage_clause:
        parts.append(lineage_clause.strip())
    if cited := _cited_award_identifier(row):
        parts.append(
            f"The notice cites the awardee's SBIR award number ({cited}) — the strongest "
            "forward lineage signal; verify the citation refers to this award and effort."
        )
        return " ".join(parts)
    match = _matching_organization(row)
    level = match[0] if match else None
    if level == "office":
        parts.append(
            "It shares the prior award's buying office, a strong continuity signal — confirm "
            "the effort continues that work."
        )
    elif level in ("organization", "agency"):
        parts.append(
            f"It matches only at the {level} level — confirm the buying office actually funded "
            "the prior effort."
        )
    else:
        parts.append(
            "The public fields show no same-firm or same-office link — confirm the buying "
            "office funded the prior effort before treating this as directed."
        )
    return " ".join(parts)


def _public_field_facts(
    row: pd.Series,
    *,
    award_abstract: str | None,
    opportunity_description: str | None,
    token_doc_freq: dict[str, int] | None = None,
) -> list[str]:
    """Describe deterministic, reader-verifiable links in the merged public fields.

    ``token_doc_freq`` (document frequencies over the run's corpus) re-ranks the
    shared phrases rarest-first so distinctive jargon leads the evidence.
    """

    facts: list[str] = []
    if cited := _cited_award_identifier(row):
        facts.append(f"The notice cites the awardee's SBIR award number ({cited}).")

    if _notice_names_awardee(row):
        award_uei = _normalized_identifier(
            _first_value(row.get("award_uei"), row.get("uei"), row.get("recipient_uei"))
        )
        facts.append(f"The notice names the SBIR/STTR awardee (UEI {award_uei}).")

    if organization_fact := _matching_organization_fact(row):
        facts.append(organization_fact)

    lineage_phrases = find_lineage_phrases(opportunity_description)
    if lineage_phrases:
        quoted = [f"“{label}”" for label in _lineage_labels(lineage_phrases)]
        facts.append(f"The notice text contains {_human_list(quoted)}.")

    award_text = " ".join(
        text
        for text in (
            _display(_first_value(row.get("award_title"), row.get("prior_title"))),
            award_abstract,
        )
        if text
    )
    phrases = shared_technical_phrases(award_text, opportunity_description)
    if phrases:
        if token_doc_freq:
            phrases = rank_phrases_by_rarity(phrases, token_doc_freq)
        quoted = [f"“{phrase}”" for phrase in phrases]
        facts.append(f"Both describe {_human_list(quoted)}.")
    else:
        shared_terms = sorted(
            tokenize_technical_text(award_text) & tokenize_technical_text(opportunity_description)
        )[:8]
        if shared_terms:
            facts.append(f"Both texts mention {_human_list(shared_terms)}.")

    if cet_fact := cet_agreement_fact(row.get("cet"), opportunity_description):
        facts.append(cet_fact)

    for award_field, opportunity_fields, code_type, label in (
        (
            "award_naics_code",
            ("opportunity_naics_code", "target_naics_code"),
            "naics",
            "NAICS code",
        ),
        (
            "award_psc_code",
            ("opportunity_psc_code", "target_psc_code"),
            "psc",
            "product/service code (PSC)",
        ),
    ):
        award_code = _normalized_code(row.get(award_field), code_type=code_type)
        opportunity_code = _normalized_code(
            _first_value(*(row.get(name) for name in opportunity_fields)),
            code_type=code_type,
        )
        if award_code and award_code == opportunity_code:
            facts.append(f"Both records list {label} {award_code}.")
    return facts


def _award_why_listed(row: pd.Series) -> str:
    reasons: list[str] = []
    if _as_bool(row.get("awarded_in_period")):
        reasons.append("Newly awarded this month")
    elif _as_bool(row.get("newly_observed")):
        reasons.append("Newly observed in the current source")
    if _as_bool(row.get("changed_since_prior_report")):
        reasons.append("Record changed since last report")

    end_date = _display(row.get("recorded_end_date"))
    if _as_bool(row.get("recent_recorded_end")):
        reason = "Recorded end date is this month"
        reasons.append(f"{reason} ({end_date})" if end_date else reason)
    elif _as_bool(row.get("approaching_recorded_end")):
        reason = "Recorded end date is within 6 months"
        reasons.append(f"{reason} ({end_date})" if end_date else reason)
    return "; ".join(reasons) or "Included by the monthly award screen"


def _sort_awards_for_packet(awards: pd.DataFrame) -> pd.DataFrame:
    if awards.empty:
        return awards
    recent_end = awards.get("recent_recorded_end", pd.Series(False, index=awards.index)).map(
        _as_bool
    )
    approaching_end = awards.get(
        "approaching_recorded_end", pd.Series(False, index=awards.index)
    ).map(_as_bool)
    return (
        awards.assign(
            _time_sensitive=recent_end | approaching_end,
            _recorded_end_sort=pd.to_datetime(
                awards.get("recorded_end_date", pd.Series(index=awards.index, dtype="object")),
                errors="coerce",
            ),
            _award_id_sort=awards.get("award_id", pd.Series("", index=awards.index))
            .fillna("")
            .astype(str),
        )
        .sort_values(
            ["_time_sensitive", "_recorded_end_sort", "_award_id_sort"],
            ascending=[False, True, True],
            na_position="last",
            kind="stable",
        )
        .drop(columns=["_time_sensitive", "_recorded_end_sort", "_award_id_sort"])
    )


def _plain_abstract(value: Any, *, limit: int = 200) -> str | None:
    """Deterministically shorten an award abstract to its leading sentence.

    This is the always-available fallback; an optional ``abstract_simplifier``
    hook may replace it with genuine plain language when a model is wired in.
    """

    text = _display(value)
    if text is None:
        return None
    collapsed = re.sub(r"\s+", " ", text).strip()
    first_sentence = re.split(r"(?<=[.!?])\s+", collapsed)[0]
    return _markdown_text(first_sentence, default="", limit=limit) or None


def _response_deadline_ts(row: pd.Series) -> pd.Timestamp | None:
    text = _display(
        _first_value(row.get("opportunity_response_deadline"), row.get("target_response_deadline"))
    )
    if text is None:
        return None
    parsed = pd.to_datetime(text, errors="coerce", utc=True)
    return None if pd.isna(parsed) else parsed


_NO_DEADLINE_SORT_KEY = (1 << 63) - 1


def _deadline_sort_key(row: pd.Series) -> int:
    parsed = _response_deadline_ts(row)
    return int(parsed.value) if parsed is not None else _NO_DEADLINE_SORT_KEY


def _awardee_key(award: pd.Series) -> str:
    """Identity of the *firm*, not the award row: UEI, else normalized company name."""

    if uei := _normalized_identifier(_first_value(award.get("uei"), award.get("award_uei"))):
        return f"uei:{uei}"
    if company := _display(award.get("company")):
        return "company:" + re.sub(r"\W+", " ", company.lower()).strip()
    return f"award:{award.get('award_id')}"


def _award_identity(row: pd.Series, *, candidate: bool = False) -> str:
    names = (
        ("_report_award_key", "prior_award_key", "award_key", "prior_award_id")
        if candidate
        else ("award_key", "award_id")
    )
    value = _first_value(*(row.get(name) for name in names))
    return _display(value) or ""


def _ambiguous_public_award_ids(awards: pd.DataFrame) -> set[str]:
    if "award_id" not in awards:
        return set()
    public_ids = awards["award_id"].map(_display)
    source_counts = pd.to_numeric(
        awards.get("public_id_award_count", pd.Series(1, index=awards.index)),
        errors="coerce",
    ).fillna(1)
    ambiguous = public_ids.duplicated(keep=False) | source_counts.gt(1)
    return {value for value in public_ids.loc[ambiguous] if value is not None}


def _award_for_entry(group: dict[str, Any], entry: pd.Series) -> pd.Series:
    """Resolve the award actually associated with a candidate path."""

    identity = _award_identity(entry, candidate=True)
    matches = [award for award in group["awards"] if _award_identity(award) == identity]
    if len(matches) == 1:
        return matches[0]

    # Legacy direct callers may provide only a public id. The report join has
    # already rejected ambiguity, so a unique match remains safe here.
    prior_id = _display(entry.get("prior_award_id"))
    legacy_matches = [
        award
        for award in group["awards"]
        if prior_id is not None and _display(award.get("award_id")) == prior_id
    ]
    if len(legacy_matches) == 1:
        return legacy_matches[0]
    raise ValueError("candidate path does not resolve to one award-grain record")


def _procurement_key(row: pd.Series) -> str | None:
    return _display(_first_value(row.get("target_id"), row.get("opportunity_title")))


def _attach_fusion_scores(rows: pd.DataFrame) -> pd.DataFrame:
    """Attach ``fusion_score`` and ``fusion_ranked`` from the frozen award-grain ranker.

    Scores the whole run at once (run-fitted TF-IDF), so only within-run ordering
    is meaningful. If the coefficients or a dependency are unavailable the packet
    still renders: every score falls back to zero and ``fusion_ranked`` is False,
    which leaves ordering to the soonest-deadline key. Because ``fusion_score`` is
    the primary sort key, that fallback silently reverts the packet to deadline
    order — so it is logged, and ``fusion_ranked`` lets the report header tell a
    ranked packet from an unranked one.
    """

    def _unranked(frame: pd.DataFrame, reason: str) -> pd.DataFrame:
        logger.warning(
            "Fusion ranking unavailable (%s); packet falls back to deadline order", reason
        )
        frame = frame.copy()
        frame["fusion_score"] = 0.0
        frame["fusion_ranked"] = False
        return frame

    try:
        from sbir_ml.transition.detection.fusion_scoring import score_pairs_with_fusion
    except Exception as exc:  # sbir-ml optional at render time
        return _unranked(rows, f"sbir-ml unavailable: {exc}")

    award_texts: list[str] = []
    target_texts: list[str] = []
    naics: list[Any] = []
    notice_types: list[Any] = []
    firm_names: list[Any] = []
    for _, row in rows.iterrows():
        award_texts.append(
            " ".join(
                part
                for part in (
                    _display(_first_value(row.get("award_title"), row.get("prior_title"))),
                    _display(_first_value(row.get("award_abstract"), row.get("prior_abstract"))),
                )
                if part
            )
        )
        target_texts.append(
            _display(
                _first_value(row.get("opportunity_description"), row.get("target_description"))
            )
            or ""
        )
        naics.append(_first_value(row.get("opportunity_naics_code"), row.get("target_naics_code")))
        notice_types.append(
            _first_value(row.get("opportunity_notice_type"), row.get("target_notice_type"))
        )
        firm_names.append(
            _first_value(row.get("company"), row.get("award_company"), row.get("recipient_name"))
        )

    try:
        scores = score_pairs_with_fusion(
            award_texts, target_texts, naics, notice_types, firm_names=firm_names
        )
    except Exception as exc:
        return _unranked(rows, f"scoring failed: {exc}")

    rows = rows.copy()
    rows["fusion_score"] = scores
    rows["fusion_ranked"] = True
    return rows


def group_candidates_by_awardee(rows: pd.DataFrame, awards: pd.DataFrame) -> list[dict[str, Any]]:
    """Group scored candidate pairs under each awardee, ordered for the packet.

    Awardees are consolidated by firm identity (UEI, else normalized company
    name), so a firm holding several awards in the cohort is one section, and a
    procurement it is relevant to through more than one award appears once.
    Directed (possible direct-award) matches precede competitive ones. Within
    each of those lists — and within ``watchlist`` — procurements are ordered by
    **descending fusion score**, the ranker's validated per-firm-lead use, with
    soonest response deadline as the tie-break. Ranking by score deliberately
    demotes deadline: a procurement closing sooner can sit below a
    stronger-matching one that closes later, so the packet is a
    strongest-match-first queue, not a calendar. When the ranker is unavailable
    every score is zero and the order falls back to deadline (see
    :func:`_attach_fusion_scores`). Below-threshold matches are kept in a
    per-awardee ``watchlist`` rather than dropped. Awardees with no matched
    procurement are still emitted so the representative sees the whole cohort.

    Notices that already name the awardee's UEI (award notices, sole-source
    justifications) are excluded: the agency has already decided, so these are not
    forward transition paths for a representative to route. They remain in the
    master audit ledger — the exclusion is presentation-only.
    """

    if not rows.empty:
        rows = rows.loc[~rows.apply(_notice_names_awardee, axis=1)].reset_index(drop=True)
        rows = _attach_fusion_scores(rows)

    signals = rows.get("signal_class", pd.Series(index=rows.index, dtype="object"))
    confidence = rows.get("confidence_bucket", pd.Series(index=rows.index, dtype="object"))
    candidate_award_keys = _coalesce(rows, "_report_award_key", "prior_award_key", "award_key").map(
        _display
    )
    candidate_public_ids = rows.get(
        "prior_award_id", pd.Series(None, index=rows.index, dtype="object")
    ).map(_display)
    ambiguous_public_ids = _ambiguous_public_award_ids(awards)
    available_award_keys = {
        _award_identity(award) for _, award in awards.iterrows() if _award_identity(award)
    }
    available_public_ids = {
        value for value in awards.get("award_id", pd.Series(dtype="object")).map(_display) if value
    }
    resolved = candidate_award_keys.isin(available_award_keys) | (
        candidate_award_keys.isna()
        & candidate_public_ids.isin(available_public_ids)
        & ~candidate_public_ids.isin(ambiguous_public_ids)
    )
    if not resolved.all():
        raise ValueError("candidate rows do not resolve to unique award-grain records")

    def _entries(mask: pd.Series, seen: set[str]) -> list[pd.Series]:
        subset = rows.loc[mask]
        # Rank a firm's procurements by the frozen fusion ranker (its validated
        # per-firm-lead use), most promising first; soonest deadline breaks ties.
        ordered = sorted(
            (row for _, row in subset.iterrows()),
            key=lambda row: (
                -float(row.get("fusion_score") or 0.0),
                _deadline_sort_key(row),
                str(_first_value(row.get("opportunity_title"), row.get("target_id")) or ""),
            ),
        )
        unique: list[pd.Series] = []
        for row in ordered:
            key = _procurement_key(row)
            if key is not None:
                if key in seen:
                    continue
                seen.add(key)
            unique.append(row)
        return unique

    ordered_awards = _sort_awards_for_packet(awards) if not awards.empty else awards
    by_awardee: dict[str, list[pd.Series]] = {}
    for _, award in ordered_awards.iterrows():
        by_awardee.setdefault(_awardee_key(award), []).append(award)

    groups: list[dict[str, Any]] = []
    for awardee_awards in by_awardee.values():
        # The first award is the packet-order representative (_sort_awards_for_packet
        # already puts the most time-sensitive award of the firm first).
        primary = awardee_awards[0]
        ids = [str(award.get("award_id")) for award in awardee_awards]
        keys = [_award_identity(award) for award in awardee_awards]
        same = (
            candidate_award_keys.isin(keys)
            | (
                candidate_award_keys.isna()
                & candidate_public_ids.isin(ids)
                & ~candidate_public_ids.isin(ambiguous_public_ids)
            )
            if not rows.empty
            else pd.Series(False, index=rows.index, dtype=bool)
        )
        high = same & (confidence == "HIGH")
        seen: set[str] = set()
        directed = _entries(high & (signals == "directed"), seen)
        competitive = _entries(high & (signals == "followon"), seen)
        watchlist = _entries(same & (confidence == "WATCHLIST"), seen)
        deadline_keys = [
            _deadline_sort_key(entry) for entry in (*directed, *competitive, *watchlist)
        ]
        groups.append(
            {
                "award_id": str(primary.get("award_id")),
                "award_ids": ids,
                "award_keys": keys,
                "award": primary,
                "awards": awardee_awards,
                "directed": directed,
                "competitive": competitive,
                "watchlist": watchlist,
                "has_directed": bool(directed),
                "earliest_deadline": min(deadline_keys) if deadline_keys else _NO_DEADLINE_SORT_KEY,
            }
        )

    def _amount_value(group: dict[str, Any]) -> float:
        number = _number(group["award"].get("amount"))
        return number if number is not None else -1.0

    groups.sort(
        key=lambda group: (
            not group["has_directed"],
            group["earliest_deadline"],
            -_amount_value(group),
        )
    )
    return groups


_FORMULA_LEADS = ("=", "+", "-", "@", "\t", "\r")


def _spreadsheet_safe(value: Any) -> Any:
    """Neutralize a leading formula trigger in a presentation CSV cell.

    SBIR.gov and SAM.gov text is external input; a cell opening with ``=``,
    ``+``, ``-`` or ``@`` is evaluated as a formula when the CSV is opened in a
    spreadsheet, and quoting does not prevent it. Raw, unprefixed values remain
    available in ``evidence.ndjson``.
    """

    if not isinstance(value, str) or not value.startswith(_FORMULA_LEADS):
        return value
    return "'" + value


def _spreadsheet_safe_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    return frame.map(_spreadsheet_safe)


def _json_safe(value: Any) -> Any:
    """Coerce a record value into standards-compliant JSON.

    ``json.dumps(default=str)`` still emits the non-standard ``NaN`` token for
    float nulls, which strict parsers reject — normalize every pandas null to
    ``None`` and stringify what remains.
    """

    if value is None:
        return None
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, (bool, int)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def _packet_html(markdown: str, *, title: str) -> str:
    body = (
        MarkdownIt("commonmark", {"html": False, "breaks": True, "linkify": False})
        .enable("table")
        .render(markdown)
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ color: #1f2937; font: 16px/1.55 system-ui, sans-serif;
      margin: 2rem auto; max-width: 72rem; padding: 0 1.25rem; }}
    h1, h2, h3, h4 {{ color: #111827; line-height: 1.25; }}
    blockquote {{ border-left: 4px solid #9ca3af; color: #374151;
      margin-left: 0; padding-left: 1rem; }}
    table {{ border-collapse: collapse; display: block; overflow-x: auto; width: 100%; }}
    th, td {{ border: 1px solid #d1d5db; padding: 0.5rem; text-align: left; }}
    th {{ background: #f3f4f6; }}
    a {{ color: #075985; }}
  </style>
</head>
<body>
<main>
{body}</main>
</body>
</html>
"""


class MonthlyReportBuilder:
    """Join normalized public evidence and write auditable center packets."""

    def __init__(
        self,
        *,
        report_month: str,
        output_root: Path | str,
        summarizer: Callable[[dict[str, Any]], str | None] | None = None,
        max_summaries: int = 10,
        abstract_simplifier: Callable[[str], str | None] | None = None,
    ) -> None:
        _month_bounds(report_month)
        if max_summaries < 0:
            raise ValueError("max_summaries must be non-negative")
        self.report_month = report_month
        self.output_dir = Path(output_root) / report_month
        self.summarizer = summarizer
        self.max_summaries = max_summaries
        self.abstract_simplifier = abstract_simplifier
        self._summary_attempts = 0
        self._summary_targets: set[str] = set()
        self._token_doc_freq: dict[str, int] = {}

    def _master(
        self,
        awards: pd.DataFrame,
        candidates: pd.DataFrame,
        opportunities: pd.DataFrame,
    ) -> pd.DataFrame:
        master = candidates.copy()
        if master.empty:
            for column in ("signal_class", "confidence_bucket", "center_name", "center_code"):
                master[column] = pd.Series(dtype="object")
            return master
        if "prior_award_id" in master and "award_id" in awards:
            award_fields = awards.rename(
                columns={
                    "title": "award_title",
                    "abstract": "award_abstract",
                    "agency": "award_agency",
                    "branch": "award_branch",
                    "office": "award_office",
                    "uei": "award_uei",
                    "naics_code": "award_naics_code",
                    "psc_code": "award_psc_code",
                    "source_url": "award_source_url",
                    "agency_tracking_number": "award_agency_tracking_number",
                    "contract_number": "award_contract_number",
                }
            )
            prior_keys = master.get(
                "prior_award_key", pd.Series([None] * len(master), index=master.index)
            ).map(_display)
            keyed = prior_keys.notna()
            master = master.assign(_candidate_order=range(len(master)))
            joined: list[pd.DataFrame] = []
            if keyed.any():
                if "award_key" not in award_fields:
                    raise ValueError("award-keyed candidates require award_key on every award")
                joined.append(
                    master.loc[keyed].merge(
                        award_fields,
                        left_on="prior_award_key",
                        right_on="award_key",
                        how="left",
                        validate="many_to_one",
                    )
                )
            if (~keyed).any():
                # Backward compatibility for hand-authored candidate rows. A
                # reused public id is ambiguous and must fail rather than fan out.
                legacy = master.loc[~keyed]
                candidate_ids = set(legacy["prior_award_id"].map(_display).dropna())
                ambiguous_ids = sorted(_ambiguous_public_award_ids(award_fields) & candidate_ids)
                if ambiguous_ids:
                    preview = ", ".join(ambiguous_ids[:5])
                    raise ValueError(
                        "legacy prior_award_id is ambiguous; regenerate candidates with "
                        f"prior_award_key (examples: {preview})"
                    )
                joined.append(
                    legacy.merge(
                        award_fields,
                        left_on="prior_award_id",
                        right_on="award_id",
                        how="left",
                        validate="many_to_one",
                    )
                )
            master = (
                pd.concat(joined, ignore_index=True, sort=False)
                .sort_values("_candidate_order", kind="stable")
                .drop(columns="_candidate_order")
                .reset_index(drop=True)
            )
            missing_awards = master["award_id"].map(_display).isna()
            if missing_awards.any():
                missing = _coalesce(master.loc[missing_awards], "prior_award_key", "prior_award_id")
                preview = ", ".join(str(value) for value in missing.head(5))
                raise ValueError(f"candidate rows reference missing awards: {preview}")
            master["_report_award_key"] = _coalesce(
                master, "award_key", "prior_award_key", "award_id", "prior_award_id"
            )
        if "target_id" in master and "notice_id" in opportunities:
            opportunity_fields = opportunities.rename(
                columns={
                    "title": "opportunity_title",
                    "description": "opportunity_description",
                    "awardee_uei": "opportunity_awardee_uei",
                    "agency": "opportunity_agency",
                    "sub_tier": "opportunity_sub_tier",
                    "office": "opportunity_office",
                    "office_code": "opportunity_office_code",
                    "full_parent_path_code": "opportunity_parent_path_code",
                    "naics_code": "opportunity_naics_code",
                    "psc_code": "opportunity_psc_code",
                    "response_deadline": "opportunity_response_deadline",
                    "source_url": "opportunity_source_url",
                    "ui_url": "opportunity_ui_url",
                    "description_url": "opportunity_description_url",
                }
            )
            master = master.merge(
                opportunity_fields,
                left_on="target_id",
                right_on="notice_id",
                how="left",
            )
        confidence = master.get("is_high_confidence", pd.Series(False, index=master.index))
        master["confidence_bucket"] = confidence.map(
            lambda value: "HIGH" if _as_bool(value) else "WATCHLIST"
        )
        office = _coalesce(master, "opportunity_office", "target_office", "award_office")
        subtier = _coalesce(master, "opportunity_sub_tier", "target_sub_agency")
        agency = _coalesce(master, "opportunity_agency", "target_agency", "award_agency")
        master["center_name"] = (
            office.fillna(subtier).fillna(agency).map(lambda value: _display(value) or "Unassigned")
        )
        center_code = _coalesce(
            master,
            "opportunity_office_code",
            "opportunity_parent_path_code",
            "target_office",
        )
        master["center_code"] = center_code.map(_display).fillna(master["center_name"].map(_slug))
        master["report_month"] = self.report_month
        return master

    def _select_summary_targets(self, master: pd.DataFrame) -> set[str]:
        """Pick which HIGH candidates spend the bounded AI-summary budget.

        Render order is deadline-driven, so summary allocation is chosen up front
        by candidate score to keep the limited budget on the strongest leads.
        """

        if self.summarizer is None or master.empty or self.max_summaries <= 0:
            return set()
        high = master.loc[master.get("confidence_bucket") == "HIGH"]
        if high.empty:
            return set()

        def _has_text(row: pd.Series) -> bool:
            award_abstract = _display(
                _first_value(row.get("award_abstract"), row.get("prior_abstract"))
            )
            description = _display(
                _first_value(row.get("opportunity_description"), row.get("target_description"))
            )
            return bool(award_abstract and description)

        eligible = high.loc[high.apply(_has_text, axis=1)]
        if eligible.empty:
            return set()
        ranked = eligible.assign(
            _summary_sort_score=pd.to_numeric(
                eligible.get("candidate_score", pd.Series(index=eligible.index, dtype="float64")),
                errors="coerce",
            ).fillna(-1.0)
        ).sort_values("_summary_sort_score", ascending=False, kind="stable")
        return {
            str(_display(value))
            for value in ranked.get("candidate_id", pd.Series(dtype="object")).head(
                self.max_summaries
            )
            if _display(value) is not None
        }

    def _path_detail(self, award: pd.Series, entry: pd.Series, kind: str) -> list[str]:
        """One compact narrative block per awardee→procurement path.

        ``kind`` is the plain path label ("direct-award", "competitive", or
        "needs more evidence"). Keeps the solicitation ask, the connection, the
        validate-this action, and source links; drops the heavy per-lead card.
        """

        company = _markdown_text(award.get("company"), default="An awardee", limit=120)
        procurement = _markdown_text(
            _first_value(entry.get("opportunity_title"), entry.get("target_id")),
            default="Untitled opportunity",
            limit=160,
        )
        deadline = _markdown_text(
            _date_label(
                _first_value(
                    entry.get("opportunity_response_deadline"),
                    entry.get("target_response_deadline"),
                )
            ),
            default="date not published",
            limit=80,
        )
        award_abstract = _display(
            _first_value(entry.get("award_abstract"), entry.get("prior_abstract"))
        )
        opportunity_description = _display(
            _first_value(entry.get("opportunity_description"), entry.get("target_description"))
        )
        if _same_text(opportunity_description, entry.get("opportunity_title")):
            opportunity_description = None

        signal = _display(entry.get("signal_class")) or "unknown"
        summary = None
        if (
            self.summarizer
            and _display(entry.get("confidence_bucket")) == "HIGH"
            and award_abstract
            and opportunity_description
            and str(_display(entry.get("candidate_id"))) in self._summary_targets
            and self._summary_attempts < self.max_summaries
        ):
            self._summary_attempts += 1
            summary = self.summarizer(entry.to_dict())

        lines = [
            f"### {company} → {procurement} — {kind}, respond by {deadline}",
            "",
            f"**Built on:** {self._plain_award_summary(award)}",
        ]
        if opportunity_description:
            lines.append(f"**Asks for:** {_markdown_text(opportunity_description, limit=360)}")
        else:
            lines.append(
                "**Asks for:** Detailed solicitation text was not retrieved. Open the SAM.gov "
                "source record and review the statement of need before routing."
            )
        facts = _public_field_facts(
            entry,
            award_abstract=award_abstract,
            opportunity_description=opportunity_description,
            token_doc_freq=self._token_doc_freq,
        )
        if facts:
            lines.append(f"**Why it connects:** {_markdown_text(' '.join(facts), limit=500)}")
        else:
            lines.append(
                "**Why it connects:** No shared public fields — compare the source records."
            )
        if connection := extract_connection_sentences(award_abstract, opportunity_description):
            award_sentence, opportunity_sentence = connection
            # Quote the solicitation side only when it narrows a longer description;
            # a single-sentence ask is already shown verbatim above.
            if _same_text(opportunity_sentence, opportunity_description):
                lines.append(
                    f"**Connection:** Beyond its summary, the award describes "
                    f"“{_markdown_text(award_sentence, limit=240)}” — directly matching the "
                    "ask above."
                )
            else:
                lines.append(
                    f"**Connection:** The award describes "
                    f"“{_markdown_text(award_sentence, limit=240)}” — the solicitation "
                    f"specifically asks for “{_markdown_text(opportunity_sentence, limit=240)}”"
                )
        if rationale := _display(entry.get("alignment_rationale")):
            lines.append(f"**Analyst note:** {_markdown_text(rationale, limit=360)}")
        if summary:
            # Render at the validator's own limit — truncating a validated summary
            # could cut a sentence's citation off and present it as uncited.
            lines.append(
                f"**Evidence-bounded comparison:** "
                f"{_markdown_text(summary, limit=MAX_SUMMARY_CHARS)}"
            )
        lines.append(f"**Validate:** {_markdown_text(_validate_line(entry, signal), limit=500)}")
        award_url = _safe_url(
            _first_value(entry.get("award_source_url"), entry.get("prior_source_url"))
        )
        opportunity_url = _safe_url(
            _first_value(
                entry.get("opportunity_source_url"),
                entry.get("opportunity_ui_url"),
                entry.get("target_source_url"),
                entry.get("opportunity_description_url"),
            )
        )
        source_links = []
        if award_url:
            source_links.append(f"[SBIR/STTR award record]({award_url})")
        if opportunity_url:
            source_links.append(f"[SAM.gov solicitation]({opportunity_url})")
        source_text = " · ".join(source_links) if source_links else "Not supplied in this input"
        lines += [f"**Sources:** {source_text}", ""]
        return lines

    def _path_details_section(self, groups: list[dict[str, Any]]) -> list[str]:
        """Compact narrative for each path, replacing the heavy per-lead cards."""

        lines = [
            "## Path details",
            "",
            "One block per path — the solicitation ask, why it connects, what to validate, "
            "and the source records. Ordered to match the transition-paths table above.",
            "",
        ]
        emitted = False
        for group in groups:
            for entry in group["directed"]:
                lines += self._path_detail(_award_for_entry(group, entry), entry, "direct-award")
                emitted = True
            for entry in group["competitive"]:
                lines += self._path_detail(_award_for_entry(group, entry), entry, "competitive")
                emitted = True
            for entry in group["watchlist"]:
                lines += self._path_detail(
                    _award_for_entry(group, entry), entry, "needs more evidence"
                )
                emitted = True
        if not emitted:
            lines += ["No paths to detail this month.", ""]
        return lines

    def _plain_award_summary(self, award: pd.Series) -> str:
        """Plain-language 'what they built': AI upgrade if wired, else first sentence."""

        text = _display(_first_value(award.get("abstract"), award.get("award_abstract")))
        if text is None:
            return "Not supplied"
        if self.abstract_simplifier is not None:
            try:
                simplified = self.abstract_simplifier(text)
            except Exception:  # optional hook must never break the deterministic packet
                simplified = None
            plain = _markdown_text(simplified, default="", limit=200) if simplified else None
            if plain:
                return plain
        return _plain_abstract(text) or "Not supplied"

    def _why_it_connects(self, row: pd.Series) -> str:
        """Compact, deterministic reason the awardee and procurement connect."""

        award_abstract = _display(
            _first_value(row.get("award_abstract"), row.get("prior_abstract"))
        )
        opportunity_description = _display(
            _first_value(row.get("opportunity_description"), row.get("target_description"))
        )
        facts = _public_field_facts(
            row,
            award_abstract=award_abstract,
            opportunity_description=opportunity_description,
            token_doc_freq=self._token_doc_freq,
        )
        if not facts:
            return "No shared public fields — compare the source records."
        return _markdown_text(" ".join(facts[:3]), default="", limit=220) or "See lead detail."

    def _transition_paths_table(self, groups: list[dict[str, Any]]) -> list[str]:
        """At-a-glance transition paths: what each awardee built → what it could feed next."""

        lines = [
            "## Potential transition paths",
            "",
            "> Each row is one path to validate: what the awardee built, an open procurement "
            "it could feed, why they connect, and the response deadline. Plain-language "
            "summaries are review aids, not eligibility determinations.",
            "",
            "| Awardee | What they built | Possible next procurement | Why it connects "
            "| Respond by |",
            "|---|---|---|---|---|",
        ]
        for group in groups:
            primary = group["award"]
            company = _markdown_text(
                primary.get("company"), default="Company unavailable", limit=120
            )
            paths = [(entry, "direct-award") for entry in group["directed"]]
            paths += [(entry, "competitive") for entry in group["competitive"]]
            paths += [(entry, "needs more evidence") for entry in group["watchlist"]]
            if not paths:
                built = self._plain_award_summary(primary)
                end_date = _display(primary.get("recorded_end_date"))
                note = f"ends {end_date}" if end_date else "no recorded end date"
                lines.append(f"| {company} | {built} | — no matched procurement | — | {note} |")
                continue
            prior_award_identity: str | None = None
            for index, (entry, path_label) in enumerate(paths):
                award = _award_for_entry(group, entry)
                award_identity = _award_identity(award)
                built = self._plain_award_summary(award)
                procurement = _markdown_text(
                    _first_value(entry.get("opportunity_title"), entry.get("target_id")),
                    default="Untitled opportunity",
                    limit=140,
                )
                deadline = _markdown_text(
                    _date_label(
                        _first_value(
                            entry.get("opportunity_response_deadline"),
                            entry.get("target_response_deadline"),
                        )
                    ),
                    default="Not published",
                    limit=60,
                )
                why = self._why_it_connects(entry)
                awardee_cell = company if index == 0 else ""
                built_cell = built if award_identity != prior_award_identity else ""
                lines.append(
                    f"| {awardee_cell} | {built_cell} | {procurement} ({path_label}) | "
                    f"{why} | {deadline} |"
                )
                prior_award_identity = award_identity
        lines.append("")
        return lines

    def _packet(self, center: str, rows: pd.DataFrame, awards: pd.DataFrame) -> str:
        groups = group_candidates_by_awardee(rows, awards)
        directed_total = sum(len(group["directed"]) for group in groups)
        competitive_total = sum(len(group["competitive"]) for group in groups)
        relevant_total = directed_total + competitive_total
        awardee_total = len(groups)
        held_total = sum(
            1 for group in groups if not group["directed"] and not group["competitive"]
        )

        most_urgent = None
        for group in groups:
            for entry in (*group["directed"], *group["competitive"]):
                key = _deadline_sort_key(entry)
                if most_urgent is None or key < most_urgent[0]:
                    most_urgent = (key, group["award"], entry)

        awardee_label = "awardee" if awardee_total == 1 else "awardees"
        procurement_label = "procurement" if relevant_total == 1 else "procurements"
        directed_clause = (
            f"{directed_total:,} could support a direct award"
            if directed_total
            else "none yet cleared for a direct award"
        )
        lines = [
            f"# Monthly Procurement Transition Packet — {_markdown_text(center, limit=160)}",
            "",
            f"**Reporting month:** {self.report_month}",
            "",
            "> Use this packet to route leads for human review. Recorded performance-period "
            "end dates do not verify technical completion, and screening results do not prove "
            "Phase III eligibility.",
            "",
            "## Bottom line",
            "",
            f"- {awardee_total:,} {awardee_label} with {relevant_total:,} relevant open "
            f"{procurement_label} ({directed_clause}).",
        ]
        if most_urgent is not None:
            urgent_company = _markdown_text(
                most_urgent[1].get("company"), default="an awardee", limit=120
            )
            urgent_title = _markdown_text(
                _first_value(
                    most_urgent[2].get("opportunity_title"), most_urgent[2].get("target_id")
                ),
                default="an open procurement",
                limit=180,
            )
            urgent_deadline = _markdown_text(
                _date_label(
                    _first_value(
                        most_urgent[2].get("opportunity_response_deadline"),
                        most_urgent[2].get("target_response_deadline"),
                    )
                ),
                default="date not published",
                limit=80,
            )
            lines.append(
                f"- Most urgent: {urgent_company} — {urgent_title}, responses due "
                f"{urgent_deadline}."
            )
        lines += [
            f"- Hold: {held_total:,} of {awardee_total:,} {awardee_label} have only weaker "
            "matches or no matched procurement this month.",
            "",
            'For any lead, confirm the new work "derives from, extends, or completes" the '
            "awardee's prior SBIR/STTR-funded work before anything moves. A match here is a "
            "starting point for review, not a decision.",
            "",
        ]
        lines += self._transition_paths_table(groups)

        if not awards.empty:
            packet_awards = _sort_awards_for_packet(awards)
            lines += [
                "## Award pipeline",
                "",
                "| Award work | Company | Phase | Awarded | Recorded end | Amount | Why listed |",
                "|---|---|---|---|---|---:|---|",
            ]
            for _, award in packet_awards.iterrows():
                lines.append(
                    f"| {_markdown_text(award.get('title'), default='', limit=100)} | "
                    f"{_markdown_text(award.get('company'), default='', limit=80)} | "
                    f"{_markdown_text(award.get('phase'), default='', limit=30)} | "
                    f"{_markdown_text(award.get('award_date'), default='', limit=30)} | "
                    f"{_markdown_text(award.get('recorded_end_date'), default='', limit=30)} | "
                    f"{_money(award.get('amount'))} | "
                    f"{_markdown_text(_award_why_listed(award), default='', limit=180)} |"
                )
            lines.append("")

        lines += self._path_details_section(groups)

        lines += [
            "## Methodology and limits",
            "",
            "Directed and competitive candidates are ranked separately from public evidence. "
            "Detailed audit scores remain in the accompanying CSV files; the packet's screening "
            "rank is not a probability or eligibility decision. "
            "Non-SBIR awards and competitive relevance do not prove statutory Phase III lineage.",
            "",
        ]
        if any(column in rows.columns for column, _label in _ANNOTATION_FIELDS):
            lines += [
                "Mission-interest, technology, and transition-lane labels are screening "
                "annotations; they do not establish a validated requirement, endorsement, or "
                "confirmed transition decision.",
                "",
            ]
        return "\n".join(lines)

    def write(
        self,
        *,
        award_cohorts: pd.DataFrame,
        candidates: pd.DataFrame,
        opportunities: pd.DataFrame,
        source_manifest: dict[str, Any] | None = None,
    ) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # Render into a staging directory and swap it in, so rerunning a month with
        # a changed center set cannot leave a withdrawn center's packet behind as
        # apparently-current output.
        centers_dir = self.output_dir / ".centers.staging"
        if centers_dir.exists():
            shutil.rmtree(centers_dir)
        centers_dir.mkdir(parents=True)
        self._summary_attempts = 0
        master = self._master(award_cohorts, candidates, opportunities)
        self._summary_targets = self._select_summary_targets(master)
        corpus = [
            *award_cohorts.get("abstract", pd.Series(dtype="object")).tolist(),
            *opportunities.get("description", pd.Series(dtype="object")).tolist(),
        ]
        self._token_doc_freq = document_token_frequencies(corpus)
        _spreadsheet_safe_frame(master).to_csv(
            self.output_dir / "master_candidates.csv", index=False
        )

        evidence: list[dict[Any, Any]] = []
        groups = (
            {
                str(center): rows.copy()
                for center, rows in master.groupby("center_name", dropna=False)
            }
            if not master.empty
            else {}
        )
        for center in award_cohorts.get("branch", pd.Series(dtype=str)).fillna(
            award_cohorts.get("agency", pd.Series(dtype=str))
        ):
            groups.setdefault(_display(center) or "Unassigned", master.iloc[0:0].copy())

        # Center membership is the union of (a) awards linked to that center by a
        # candidate and (b) the center's own unlinked cohort awards. Computing the
        # linked set across every center first keeps a matched award out of a second
        # center's packet, where it would be listed as "no matched procurement",
        # while still emitting every awardee at a center that has any match.
        linked_by_center = {
            center: {
                value
                for value in _coalesce(
                    rows, "_report_award_key", "prior_award_key", "prior_award_id"
                ).map(_display)
                if value is not None
            }
            for center, rows in groups.items()
        }
        linked_anywhere = set().union(*linked_by_center.values()) if linked_by_center else set()
        cohort_award_ids = _coalesce(award_cohorts, "award_key", "award_id").map(
            lambda value: _display(value) or ""
        )

        if groups:
            for center, rows in groups.items():
                at_center = (
                    award_cohorts.get("agency", pd.Series(dtype="object")).fillna("") == str(center)
                ) | (
                    award_cohorts.get("branch", pd.Series(dtype="object")).fillna("") == str(center)
                )
                related_awards = award_cohorts.loc[
                    cohort_award_ids.isin(linked_by_center[center])
                    | (at_center & ~cohort_award_ids.isin(linked_anywhere))
                ]
                markdown = self._packet(str(center), rows, related_awards)
                slug = _slug(rows.iloc[0].get("center_code") if not rows.empty else center)
                (centers_dir / f"{slug}.md").write_text(markdown, encoding="utf-8")
                (centers_dir / f"{slug}.html").write_text(
                    _packet_html(
                        markdown,
                        title=f"Monthly Procurement Transition Packet — {center}",
                    ),
                    encoding="utf-8",
                )
                evidence.extend(rows.to_dict(orient="records"))
        else:
            markdown = self._packet(
                "Unassigned", master.assign(confidence_bucket=[]), award_cohorts
            )
            (centers_dir / "unassigned.md").write_text(markdown, encoding="utf-8")
            (centers_dir / "unassigned.html").write_text(
                _packet_html(
                    markdown,
                    title="Monthly Procurement Transition Packet — Unassigned",
                ),
                encoding="utf-8",
            )
        # Swap the freshly rendered centers in, replacing the month's prior output.
        final_centers_dir = self.output_dir / "centers"
        if final_centers_dir.exists():
            shutil.rmtree(final_centers_dir)
        centers_dir.rename(final_centers_dir)

        with (self.output_dir / "evidence.ndjson").open("w", encoding="utf-8") as handle:
            for record in evidence:
                handle.write(
                    json.dumps(
                        {str(key): _json_safe(value) for key, value in record.items()},
                        allow_nan=False,
                    )
                    + "\n"
                )
        high = master.loc[master["confidence_bucket"] == "HIGH"] if not master.empty else master
        audit = (
            high.sort_values(["signal_class", "candidate_id"], na_position="last")
            .groupby("signal_class", group_keys=False)
            .head(100)
            if not high.empty
            else high
        )
        _spreadsheet_safe_frame(audit).to_csv(self.output_dir / "audit_sample.csv", index=False)
        manifest = {
            "report_month": self.report_month,
            "generated_at": datetime.now(UTC).isoformat(),
            "award_cohort_rows": len(award_cohorts),
            "candidate_rows": len(master),
            "high_confidence_rows": len(high),
            "ai_summary_attempts": self._summary_attempts,
            "ai_summary_limit": self.max_summaries if self.summarizer else 0,
            "sources": source_manifest or {},
            "completion_semantics": "recorded performance-period end; technical completion unverified",
        }
        (self.output_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        return self.output_dir


__all__ = [
    "MonthlyReportBuilder",
    "build_award_cohorts",
    "group_candidates_by_awardee",
    "normalize_awards",
]
