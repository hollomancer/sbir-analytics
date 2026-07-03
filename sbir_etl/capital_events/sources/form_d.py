"""Form D filings → CapitalEvent builder.

Reads form_d_details.jsonl. Records are kept when match_confidence.tier
is "high" and the matched company_name is in the cohort. One event per
offering on the matched record; business-combination offerings get the
special `combination` subtype regardless of declared securities type.
"""

import json
from collections.abc import Iterable, Iterator
from pathlib import Path

from sbir_etl.capital_events.schema import EventType

_SECURITY_KEYWORDS = {
    "equity": "equity",
    "debt": "debt",
    "option": "option_warrant",
    "warrant": "option_warrant",
    "convertible": "debt",
}


def classify_securities_types(types: list[str] | None) -> str:
    """Project Form D securities_types list to a single subtype label.

    Returns one of: equity / debt / option_warrant / other.
    Mixed-type offerings → "other" (full list preserved in metadata).
    """
    if not types:
        return "other"
    matched: set[str] = set()
    for t in types:
        lowered = t.lower()
        for keyword, label in _SECURITY_KEYWORDS.items():
            if keyword in lowered:
                matched.add(label)
                break
    if len(matched) == 1:
        return matched.pop()
    return "other"


def build_form_d_events(cohort: Iterable[dict], source_path: Path) -> Iterator[dict]:
    """Yield CapitalEvent rows for Form D offerings against cohort firms."""
    if not source_path.exists():
        return
    cohort_names = {row["company_name"] for row in cohort}
    with source_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = rec.get("company_name")
            if name not in cohort_names:
                continue
            tier = (rec.get("match_confidence") or {}).get("tier")
            if tier != "high":
                continue
            for offering in rec.get("offerings") or []:
                securities = offering.get("securities_types") or []
                subtype = (
                    "combination"
                    if offering.get("is_business_combination")
                    else classify_securities_types(securities)
                )
                yield {
                    "company_name": name,
                    "event_date": offering.get("filing_date") or "",
                    "event_type": EventType.FORM_D_FILING.value,
                    "event_subtype": subtype,
                    "amount_usd": offering.get("total_amount_sold"),
                    "counterparty": None,
                    "source_id": offering.get("accession_number") or "",
                    "metadata": json.dumps(
                        {
                            "securities_types": securities,
                            "minimum_investment": offering.get("minimum_investment"),
                            "num_investors": offering.get("num_investors"),
                            "business_combination": bool(offering.get("is_business_combination")),
                            "is_amendment": bool(offering.get("is_amendment")),
                        }
                    ),
                }
