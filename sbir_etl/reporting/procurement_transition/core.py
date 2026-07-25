"""Deterministic monthly procurement-center packet generation."""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import pandas as pd
from markdown_it import MarkdownIt

from sbir_etl.utils.procurement_text import find_lineage_phrases, tokenize_technical_text


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


def _stable_award_id(row: pd.Series) -> str:
    for name in ("Agency Tracking Number", "Contract", "award_id"):
        value = row.get(name)
        if value is not None and str(value).strip() not in {"", "nan"}:
            return str(value).strip()
    material = "|".join(
        _display(row.get(name)) or ""
        for name in ("Company", "Agency", "Phase", "Proposal Award Date", "Award Title")
    )
    return "sbir-" + hashlib.sha256(material.encode()).hexdigest()[:20]


def normalize_awards(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize the public SBIR.gov CSV while preserving every phase label."""

    if raw.empty:
        return pd.DataFrame(
            columns=[
                "award_id",
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
                "naics_code",
                "psc_code",
                "office",
                "cet",
                "source_url",
            ]
        )
    out = pd.DataFrame(index=raw.index)
    out["award_id"] = raw.apply(_stable_award_id, axis=1)
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
    material = out.fillna("").astype(str).agg("|".join, axis=1)
    out["row_hash"] = material.map(lambda value: hashlib.sha256(value.encode()).hexdigest())
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
    current = normalize_awards(current) if "row_hash" not in current.columns else current.copy()
    prior = (
        normalize_awards(previous)
        if previous is not None and "row_hash" not in previous.columns
        else (previous.copy() if previous is not None else pd.DataFrame())
    )
    start, end = _month_bounds(report_month)
    horizon = (pd.Timestamp(end) + pd.Timedelta(days=approaching_days)).date()
    prior_hash = dict(zip(prior.get("award_id", []), prior.get("row_hash", []), strict=False))
    current["newly_observed"] = ~current["award_id"].isin(prior.get("award_id", []))
    current["changed_since_prior_report"] = current.apply(
        lambda row: row["award_id"] in prior_hash
        and prior_hash[row["award_id"]] != row["row_hash"],
        axis=1,
    )
    current["awarded_in_period"] = current["award_date"].map(
        lambda value: bool(value and start <= value <= end)
    )
    current["recent_recorded_end"] = current["recorded_end_date"].map(
        lambda value: bool(value and start <= value <= end)
    )
    current["approaching_recorded_end"] = current["recorded_end_date"].map(
        lambda value: bool(value and end < value <= horizon)
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


def _matching_organization_fact(row: pd.Series) -> str | None:
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
            return f"The award and notice list the same {label} ({award_value})."
    return None


def _public_field_facts(
    row: pd.Series,
    *,
    award_abstract: str | None,
    opportunity_description: str | None,
) -> list[str]:
    """Describe deterministic, reader-verifiable links in the merged public fields."""

    facts: list[str] = []
    award_uei = _first_value(row.get("award_uei"), row.get("uei"), row.get("recipient_uei"))
    opportunity_uei = _first_value(
        row.get("opportunity_awardee_uei"),
        row.get("awardee_uei"),
        row.get("ueiSAM"),
        row.get("target_recipient_uei"),
    )
    normalized_award_uei = _normalized_identifier(award_uei)
    if normalized_award_uei and normalized_award_uei == _normalized_identifier(opportunity_uei):
        facts.append(f"The notice names the SBIR/STTR awardee (UEI {normalized_award_uei}).")

    if organization_fact := _matching_organization_fact(row):
        facts.append(organization_fact)

    lineage_phrases = find_lineage_phrases(opportunity_description)
    if lineage_phrases:
        labels = [
            "Phase III" if phrase == "phase iii" else "Phase 3" if phrase == "phase 3" else phrase
            for phrase in lineage_phrases
        ]
        quoted = [f"“{label}”" for label in labels]
        facts.append(f"The notice text contains {_human_list(quoted)}.")

    award_text = " ".join(
        text
        for text in (
            _display(_first_value(row.get("award_title"), row.get("prior_title"))),
            award_abstract,
        )
        if text
    )
    shared_terms = sorted(
        tokenize_technical_text(award_text) & tokenize_technical_text(opportunity_description)
    )[:8]
    if shared_terms:
        facts.append(f"Both texts mention {_human_list(shared_terms)}.")

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
    ) -> None:
        _month_bounds(report_month)
        if max_summaries < 0:
            raise ValueError("max_summaries must be non-negative")
        self.report_month = report_month
        self.output_dir = Path(output_root) / report_month
        self.summarizer = summarizer
        self.max_summaries = max_summaries
        self._summary_attempts = 0

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
                }
            )
            master = master.merge(
                award_fields,
                left_on="prior_award_id",
                right_on="award_id",
                how="left",
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

    def _candidate_card(self, row: pd.Series) -> list[str]:
        signal = _display(row.get("signal_class")) or "unknown"
        confidence = _display(row.get("confidence_bucket")) or "WATCHLIST"
        opportunity_title = _markdown_text(
            _first_value(row.get("opportunity_title"), row.get("target_id")),
            default="Untitled opportunity",
            limit=180,
        )
        award_title = _markdown_text(
            _first_value(row.get("award_title"), row.get("prior_title")),
            default="Award title unavailable",
            limit=180,
        )
        award_abstract = _display(
            _first_value(row.get("award_abstract"), row.get("prior_abstract"))
        )
        opportunity_description = _display(
            _first_value(row.get("opportunity_description"), row.get("target_description"))
        )
        if _same_text(opportunity_description, row.get("opportunity_title")):
            opportunity_description = None

        if confidence == "WATCHLIST":
            disposition = "Needs more evidence before routing"
        elif signal == "directed":
            disposition = "Potential directed Phase III path — validate lineage"
        else:
            disposition = "Competitive opportunity with technical overlap"

        deadline = _markdown_text(
            _date_label(
                _first_value(
                    row.get("opportunity_response_deadline"), row.get("target_response_deadline")
                )
            ),
            default="Not published",
            limit=80,
        )
        transition_lane = _display(row.get("potential_transition_lane"))
        interest = _display(row.get("interest_alignment"))
        routing = " · ".join(
            _markdown_text(value, limit=160) for value in (transition_lane, interest) if value
        )
        solicitation_number = _display(row.get("solicitation_number"))
        summary = None
        if (
            self.summarizer
            and confidence == "HIGH"
            and award_abstract
            and opportunity_description
            and self._summary_attempts < self.max_summaries
        ):
            self._summary_attempts += 1
            summary = self.summarizer(row.to_dict())
        rationale = _display(row.get("alignment_rationale"))
        public_facts = _public_field_facts(
            row,
            award_abstract=award_abstract,
            opportunity_description=opportunity_description,
        )

        amount = _money(row.get("amount"))
        award_details = [
            _markdown_text(row.get("company"), default="Company unavailable", limit=120),
            _markdown_text(row.get("phase"), default="Phase unavailable", limit=40),
        ]
        if amount != "N/A":
            award_details.append(amount)

        lines = [
            f"### {opportunity_title}",
            "",
            f"**Disposition:** {disposition}",
            "",
            "**Review question:** Does the SBIR/STTR-funded capability below satisfy the "
            "solicitation need as written?",
            "",
            f"**Response deadline:** {deadline}",
        ]
        if routing:
            lines.append(f"**Suggested routing:** {routing}")
        if solicitation_number:
            lines.append(f"**Solicitation:** {_markdown_text(solicitation_number, limit=100)}")
        lines += [
            "",
            "#### What the award funded",
            "",
            f"**{award_title}** — {' · '.join(award_details)}",
            "",
        ]
        if award_abstract:
            lines += [f"> {_markdown_text(award_abstract)}", ""]
        else:
            lines += [
                "> The award abstract was not available in the supplied SBIR/STTR data. "
                "Review the award record before routing.",
                "",
            ]
        lines += ["#### What the solicitation asks for", "", f"**{opportunity_title}**", ""]
        if opportunity_description:
            lines += [f"> {_markdown_text(opportunity_description)}", ""]
        else:
            lines += [
                "> Detailed solicitation text was not retrieved. Open the SAM.gov source "
                "record and review the statement of need before routing.",
                "",
            ]
        lines += ["#### Technical connection to validate", ""]
        if public_facts:
            lines += [
                f"**Public-field comparison:** "
                f"{_markdown_text(' '.join(public_facts), limit=1_200)}",
                "",
            ]
        else:
            lines += [
                "**Public-field comparison:** The supplied public fields expose no same-firm "
                "identifier, shared lineage phrase, shared technical term, or matching "
                "acquisition code. Compare the full source records before routing.",
                "",
            ]
        if summary:
            lines += [f"**Evidence-bounded comparison:** {_markdown_text(summary)}", ""]
        if rationale:
            lines += [f"**Analyst screening note:** {_markdown_text(rationale)}", ""]

        lines += ["#### Why this was surfaced", ""]
        candidate_type = (
            "Possible directed path" if signal == "directed" else "Competitive follow-on"
        )
        lines.append(f"- Candidate type: {candidate_type}")
        if interest:
            lines.append(f"- Mission interest: {_markdown_text(interest, limit=180)}")
        if technology := _display(row.get("technology_ecosystem")):
            lines.append(f"- Technology tags: {_markdown_text(technology, limit=220)}")
        for fact in public_facts:
            lines.append(f"- {_markdown_text(fact, limit=320)}")
        rank = "Priority lead" if confidence == "HIGH" else "Evidence watchlist"
        lines.append(
            f"- Screening rank: {rank}. This is a triage rank, not a probability or "
            "eligibility decision."
        )

        lines += ["", "#### Representative check", ""]
        if signal == "directed":
            lines.append(
                "Confirm that the solicitation derives from, extends, or completes the cited "
                "SBIR/STTR-funded work, and that the funded capability covers the stated need. "
                "The screening rank does not establish statutory Phase III lineage."
            )
        else:
            lines.append(
                "Assess the technical fit, acquisition strategy, and competition requirements. "
                "Topical overlap alone does not make a competitive opportunity a Phase III path."
            )

        award_url = _safe_url(
            _first_value(row.get("award_source_url"), row.get("prior_source_url"))
        )
        opportunity_url = _safe_url(
            _first_value(
                row.get("opportunity_source_url"),
                row.get("opportunity_ui_url"),
                row.get("target_source_url"),
                row.get("opportunity_description_url"),
            )
        )
        source_links = []
        if award_url:
            source_links.append(f"[SBIR/STTR award record]({award_url})")
        if opportunity_url:
            source_links.append(f"[SAM.gov solicitation]({opportunity_url})")
        source_text = " · ".join(source_links) if source_links else "Not supplied in this input"
        lines += ["", f"**Source records:** {source_text}", ""]
        return lines

    def _packet(self, center: str, rows: pd.DataFrame, awards: pd.DataFrame) -> str:
        confidence = rows.get("confidence_bucket", pd.Series(index=rows.index, dtype="object"))
        signals = rows.get("signal_class", pd.Series(index=rows.index, dtype="object"))
        high = rows.loc[confidence == "HIGH"]
        high_signal = signals.loc[high.index]
        directed_count = int((high_signal == "directed").sum())
        followon_count = int((high_signal == "followon").sum())
        watchlist_count = int((confidence == "WATCHLIST").sum())
        directed_label = "path" if directed_count == 1 else "paths"
        followon_label = "opportunity" if followon_count == 1 else "opportunities"
        watchlist_label = "lead" if watchlist_count == 1 else "leads"
        award_total = pd.to_numeric(
            awards.get("amount", pd.Series(dtype="float64")), errors="coerce"
        ).sum(min_count=1)
        lines = [
            f"# Monthly Procurement Transition Packet — {_markdown_text(center, limit=160)}",
            "",
            f"**Reporting month:** {self.report_month}",
            "",
            "> Use this packet to route leads for human review. Recorded performance-period "
            "end dates do not verify technical completion, and screening results do not prove "
            "Phase III eligibility.",
            "",
            "## How to read this packet",
            "",
            "- A potential directed path is a government notice that may support a direct award "
            "and has public evidence pointing back to SBIR/STTR-funded work; it is not a Phase III "
            "determination.",
            "- A competitive follow-on is an open competition whose subject overlaps an award; "
            "topical overlap alone does not make it Phase III.",
            "- A Priority lead passed enough screening checks to review first, but still requires "
            "human validation.",
            "- Needs more evidence before routing means the public connection is incomplete or "
            "weak and should be held from representative routing.",
            "- For any Phase III path, confirm that the proposed work derives from, extends, or "
            "completes the prior SBIR/STTR-funded work.",
            "",
            "## Snapshot",
            "",
            f"- Awards in this packet: {len(awards):,} (new, changed, recently ended, or ending "
            f"soon), totaling {_money(award_total)}",
            f"- Priority leads: {len(high):,} ({directed_count:,} possible directed "
            f"{directed_label}; {followon_count:,} competitive {followon_label})",
            f"- Needs more evidence before routing: {watchlist_count:,}",
            "",
            "## Representative action queue",
            "",
            f"- Validate SBIR/STTR lineage and technical fit for {directed_count:,} possible "
            f"directed {directed_label}.",
            f"- Assess technical fit and acquisition strategy for {followon_count:,} "
            f"competitive {followon_label}.",
            f"- Hold {watchlist_count:,} watchlist {watchlist_label} until the stated evidence "
            "gaps are "
            "resolved.",
            "",
        ]
        for signal, heading in (
            ("directed", "Potential directed paths — validate lineage"),
            ("followon", "Competitive opportunities with technical overlap"),
        ):
            subset = rows.loc[(signals == signal) & (confidence == "HIGH")]
            if not subset.empty:
                subset = subset.assign(
                    _report_sort_score=pd.to_numeric(
                        subset.get(
                            "candidate_score",
                            pd.Series(index=subset.index, dtype="float64"),
                        ),
                        errors="coerce",
                    ).fillna(-1.0)
                ).sort_values("_report_sort_score", ascending=False, kind="stable")
            lines += [f"## {heading}", ""]
            if subset.empty:
                lines += ["None identified.", ""]
            for _, row in subset.iterrows():
                lines += self._candidate_card(row)

        lines += ["## Needs more evidence before routing", ""]
        watch = rows.loc[confidence == "WATCHLIST"]
        if watch.empty:
            lines += ["None identified.", ""]
        else:
            lines += [
                "These leads receive the same evidence review as priority leads, but should not "
                "be routed until a representative resolves the missing or weak connection.",
                "",
            ]
            for _, row in watch.iterrows():
                lines += self._candidate_card(row)

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
        centers_dir = self.output_dir / "centers"
        centers_dir.mkdir(exist_ok=True)
        self._summary_attempts = 0
        master = self._master(award_cohorts, candidates, opportunities)
        master.to_csv(self.output_dir / "master_candidates.csv", index=False)

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

        if groups:
            for center, rows in groups.items():
                linked_award_ids = set(
                    rows.get("prior_award_id", pd.Series(dtype="object")).dropna().astype(str)
                )
                related_awards = award_cohorts.loc[
                    award_cohorts["award_id"].astype(str).isin(linked_award_ids)
                ]
                if related_awards.empty:
                    related_awards = award_cohorts.loc[
                        (award_cohorts["agency"].fillna("") == str(center))
                        | (award_cohorts["branch"].fillna("") == str(center))
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
        with (self.output_dir / "evidence.ndjson").open("w", encoding="utf-8") as handle:
            for record in evidence:
                handle.write(json.dumps(record, default=str) + "\n")
        high = master.loc[master["confidence_bucket"] == "HIGH"] if not master.empty else master
        audit = (
            high.sort_values(["signal_class", "candidate_id"], na_position="last")
            .groupby("signal_class", group_keys=False)
            .head(100)
            if not high.empty
            else high
        )
        audit.to_csv(self.output_dir / "audit_sample.csv", index=False)
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


__all__ = ["MonthlyReportBuilder", "build_award_cohorts", "normalize_awards"]
