"""Deterministic monthly procurement-center packet generation."""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from collections.abc import Callable
from typing import Any

import pandas as pd


def _pick(df: pd.DataFrame, *names: str) -> pd.Series:
    for name in names:
        if name in df.columns:
            return df[name]
    return pd.Series([None] * len(df), index=df.index)


def _stable_award_id(row: pd.Series) -> str:
    for name in ("Agency Tracking Number", "Contract", "award_id"):
        value = row.get(name)
        if value is not None and str(value).strip() not in {"", "nan"}:
            return str(value).strip()
    material = "|".join(
        str(row.get(name) or "")
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
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "unassigned").lower()).strip("-")
    return slug or "unassigned"


def _money(value: Any) -> str:
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "N/A"


class MonthlyReportBuilder:
    """Join normalized public evidence and write auditable center packets."""

    def __init__(
        self,
        *,
        report_month: str,
        output_root: Path | str,
        summarizer: Callable[[dict[str, Any]], str | None] | None = None,
    ) -> None:
        _month_bounds(report_month)
        self.report_month = report_month
        self.output_dir = Path(output_root) / report_month
        self.summarizer = summarizer

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
            master = master.merge(awards, left_on="prior_award_id", right_on="award_id", how="left")
        if "target_id" in master and "notice_id" in opportunities:
            master = master.merge(
                opportunities,
                left_on="target_id",
                right_on="notice_id",
                how="left",
                suffixes=("", "_opp"),
            )
            # The award frame also emits a (usually null) source_url that would shadow
            # the opportunity's own link; prefer the opportunity value for packets.
            if "source_url_opp" in master.columns:
                master["source_url"] = master["source_url_opp"].combine_first(
                    master.get("source_url", pd.Series(index=master.index, dtype="object"))
                )
        confidence = master.get("is_high_confidence", pd.Series(False, index=master.index))
        master["confidence_bucket"] = confidence.map(
            lambda value: "HIGH" if bool(value) else "WATCHLIST"
        )
        office = _pick(master, "office", "target_office")
        subtier = _pick(master, "sub_tier", "target_sub_agency")
        agency = _pick(master, "agency_opp", "target_agency", "agency")
        master["center_name"] = office.fillna(subtier).fillna(agency).fillna("Unassigned")
        master["center_code"] = _pick(master, "office_code", "full_parent_path_code")
        master["center_code"] = master["center_code"].fillna(master["center_name"].map(_slug))
        master["report_month"] = self.report_month
        return master

    def _packet(self, center: str, rows: pd.DataFrame, awards: pd.DataFrame) -> str:
        lines = [
            f"# Monthly Procurement Transition Packet — {center}",
            "",
            f"**Reporting month:** {self.report_month}",
            "",
            "> Recorded performance-period end dates do not verify technical completion.",
            "",
        ]
        for signal, heading in (
            ("directed", "High-confidence directed Phase III candidates"),
            ("followon", "High-confidence competitive follow-on candidates"),
        ):
            subset = rows.loc[
                (rows.get("signal_class", "") == signal) & (rows["confidence_bucket"] == "HIGH")
            ]
            lines += [f"## {heading}", ""]
            if subset.empty:
                lines += ["None identified.", ""]
            for _, row in subset.iterrows():
                label = (
                    "potential Phase III path"
                    if signal == "directed"
                    else "competitive relevance; not necessarily Phase III"
                )
                summary = self.summarizer(row.to_dict()) if self.summarizer else None
                lines += [
                    f"### {row.get('title_opp') or row.get('title') or row.get('target_id')}",
                    "",
                    f"- Company: {row.get('company') or 'Unknown'}",
                    f"- Prior award phase: {row.get('phase') or 'Unknown'}",
                    f"- Score: {float(row.get('candidate_score') or 0):.2f}",
                    f"- Interpretation: {label}",
                    f"- Response deadline: {row.get('response_deadline') or 'Not published'}",
                    f"- Public source: {row.get('source_url') or row.get('ui_url') or 'Unavailable'}",
                    "",
                ]
                if summary:
                    lines += [f"- Evidence summary: {summary}", ""]
        lines += ["## Watchlist", ""]
        watch = rows.loc[rows["confidence_bucket"] == "WATCHLIST"]
        if watch.empty:
            lines += ["None identified.", ""]
        else:
            lines += ["Lower-confidence candidates require analyst review before outreach.", ""]
            for _, row in watch.iterrows():
                lines.append(
                    f"- {row.get('title_opp') or row.get('target_id')} — score {float(row.get('candidate_score') or 0):.2f}"
                )
            lines.append("")
        if not awards.empty:
            lines += [
                "## Award pipeline",
                "",
                "| Company | Phase | Awarded | Recorded end | Amount |",
                "|---|---|---|---|---:|",
            ]
            for _, award in awards.iterrows():
                lines.append(
                    f"| {award.get('company') or ''} | {award.get('phase') or ''} | "
                    f"{award.get('award_date') or ''} | {award.get('recorded_end_date') or ''} | "
                    f"{_money(award.get('amount'))} |"
                )
            lines.append("")
        lines += [
            "## Methodology",
            "",
            "Directed and competitive candidates are scored separately from public evidence. Non-SBIR awards and competitive relevance are not proof of statutory Phase III lineage.",
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
            groups.setdefault(str(center or "Unassigned"), master.iloc[0:0].copy())

        if groups:
            for center, rows in groups.items():
                related_awards = award_cohorts.loc[
                    (award_cohorts["agency"].fillna("") == str(center))
                    | (award_cohorts["branch"].fillna("") == str(center))
                ]
                markdown = self._packet(str(center), rows, related_awards)
                slug = _slug(rows.iloc[0].get("center_code") if not rows.empty else center)
                (centers_dir / f"{slug}.md").write_text(markdown, encoding="utf-8")
                (centers_dir / f"{slug}.html").write_text(
                    "<!doctype html><meta charset='utf-8'><pre>" + html.escape(markdown) + "</pre>",
                    encoding="utf-8",
                )
                evidence.extend(rows.to_dict(orient="records"))
        else:
            markdown = self._packet(
                "Unassigned", master.assign(confidence_bucket=[]), award_cohorts
            )
            (centers_dir / "unassigned.md").write_text(markdown, encoding="utf-8")
            (centers_dir / "unassigned.html").write_text(
                "<!doctype html><meta charset='utf-8'><pre>" + html.escape(markdown) + "</pre>",
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
            "sources": source_manifest or {},
            "completion_semantics": "recorded performance-period end; technical completion unverified",
        }
        (self.output_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        return self.output_dir


__all__ = ["MonthlyReportBuilder", "build_award_cohorts", "normalize_awards"]
