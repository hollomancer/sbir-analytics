#!/usr/bin/env python3
"""Detect M&A exit events for SBIR companies.

Extracts signals from Form D business combinations and EFTS mention
classifications, merges into a unified events dataset with confidence tiers.

Usage:
    python scripts/data/detect_sbir_ma_events.py
    python scripts/data/detect_sbir_ma_events.py --form-d data/form_d_details.jsonl
"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# Match tier accepted from form_d_details.jsonl. capital_events/sources/form_d.py
# hardcodes the same value, so the two paths keep the same records.
KEEP_MATCH_TIER = "high"


def has_business_combination(record: dict) -> bool:
    """Return whether a form_d_details.jsonl record has any combination offering."""
    return any(o.get("is_business_combination") for o in record.get("offerings") or [])


def extract_form_d_signals(records: list[dict]) -> list[dict]:
    """Extract M&A events from Form D business combination flags.

    For each company with at least one is_business_combination offering,
    produces one event using the earliest combo filing date.

    A record is used only when its SBIR-to-SEC match tier is ``high``. The
    join is fuzzy, and ``form_d_details.jsonl`` already carries the
    multi-signal verdict from ``compute_form_d_confidence`` in
    ``match_confidence.tier``. Without this filter a filing by an unrelated
    company is attributed to an SBIR firm. When this filter landed such a row
    was then graded ``high``; the Form D flag no longer grades an exit, so an
    unmatched filing now yields a low-tier acquirer-side row, or with this
    filter no row at all. Measured
    2026-09-08, 323 of the 374 business-combination records whose SEC filer
    name does not match the SBIR name under RECIPIENT_V1 were already tier
    ``low``. ``capital_events/sources/form_d.py`` keeps records on the same
    single value.

    ``high`` is not a score threshold. ``form_d_scoring.py`` assigns it when
    the best PI-to-officer name score is at least 0.7 **or** the SBIR ZIP
    matches a Form D ZIP; ``medium`` on state overlap alone; ``low``
    otherwise. Filer-name similarity is not used to assign the tier. So a
    ``high`` record may be ZIP-only, which is weak where many SBIR firms share
    a ZIP. The event carries ``match_person_score`` and ``match_address_score``
    so a consumer can tell the two apart.
    """
    events = []
    for r in records:
        confidence = r.get("match_confidence") or {}
        if confidence.get("tier") != KEEP_MATCH_TIER:
            continue
        combos = [o for o in r.get("offerings") or [] if o.get("is_business_combination")]
        if not combos:
            continue

        combos.sort(key=lambda o: str(o.get("filing_date", "")))
        earliest = combos[0]

        total_sold = sum(o.get("total_amount_sold") or 0 for o in combos)

        all_persons = []
        for o in combos:
            all_persons.extend(o.get("related_persons", []))

        events.append(
            {
                "company_name": r["company_name"],
                "event_date": str(earliest.get("filing_date", ""))[:10],
                "source": "form_d",
                "form_d_detail": {
                    "filing_date": str(earliest.get("filing_date", ""))[:10],
                    "total_amount_sold": total_sold if total_sold > 0 else None,
                    "combo_count": len(combos),
                    "related_persons": all_persons,
                    # Which signal earned the high tier. Recording the tier itself
                    # would be useless here — every kept record is "high". These
                    # two separate a ZIP-only match from a person-confirmed one.
                    "match_person_score": confidence.get("person_score"),
                    "match_address_score": confidence.get("address_score"),
                },
            }
        )

    return events


def extract_efts_signals(records: list[dict]) -> list[dict]:
    """Extract M&A events from EFTS mention classifications.

    Maps mention types to confidence levels and extracts acquirer
    candidates from mention_filers.
    """
    MA_TYPES = {
        "subsidiary": "high",
        "acquisition": "medium",
        "ma_definitive": "low",
        "ma_proxy": "low",
        "ownership_active": "low",
    }

    events = []
    for r in records:
        types = r.get("mention_types", [])
        ma_hits = {t: MA_TYPES[t] for t in types if t in MA_TYPES}
        if not ma_hits:
            continue

        tier_order = {"high": 0, "medium": 1, "low": 2}
        best_tier = min(ma_hits.values(), key=lambda t: tier_order[t])

        events.append(
            {
                "company_name": r["company_name"],
                "event_date": r.get("latest_mention_date", ""),
                "source": "efts",
                "efts_detail": {
                    "mention_filers": r.get("mention_filers", []),
                    "mention_types": sorted(ma_hits.keys()),
                    "latest_mention_date": r.get("latest_mention_date", ""),
                    "efts_tier": best_tier,
                },
            }
        )

    return events


def merge_events(
    form_d_events: list[dict],
    efts_events: list[dict],
) -> list[dict]:
    """Merge Form D and EFTS events by company name.

    When both sources have an event for the same company, combine into
    one record (one event per company). Uses the earliest valid ISO date
    across sources; an empty/missing date is treated as unknown and a
    valid date always wins over an empty one.

    Note: merging is by exact company name only. The 12-month date-window
    same-event deduplication described in the design spec is not implemented
    here; in practice a single company rarely has events far enough apart to
    require it, and the one-event-per-company model matches the actual output.
    """
    merged: dict[str, dict] = {}

    for e in form_d_events:
        name = e["company_name"]
        merged[name] = {
            "company_name": name,
            "event_date": e["event_date"],
            "form_d_detail": e["form_d_detail"],
            "efts_detail": None,
        }

    for e in efts_events:
        name = e["company_name"]
        efts_date = e["event_date"]
        if name in merged:
            existing = merged[name]
            # The EFTS date wins whenever there is one, even if it is later.
            # The competing date comes from a Form D business-combination
            # filing, which is acquirer-side: it dates the issuer raising
            # capital to buy something, not the SBIR firm being acquired.
            # Taking the earlier of the two put an acquirer-side date on the
            # exit for 30 of 36 overlapping companies - nLight Photonics was
            # dated 2013 from a Form D while its target-side evidence is 2026.
            # The Form D date is still available in form_d_detail.
            if efts_date:
                existing["event_date"] = efts_date
            existing["efts_detail"] = e["efts_detail"]
        else:
            merged[name] = {
                "company_name": name,
                "event_date": efts_date,
                "form_d_detail": None,
                "efts_detail": e["efts_detail"],
            }

    return list(merged.values())


EFTS_SIGNAL_KEYS = (
    "efts_subsidiary",
    "efts_ma_definitive",
    "efts_acquisition_text",
    "efts_ma_proxy",
    "efts_ownership_active",
)


def is_acquirer_side_only(signals: dict[str, bool]) -> bool:
    """True when the only evidence is a Form D business-combination flag.

    Form D Item 10 marks a Rule 145 transaction, a deemed offer and sale of
    securities *by the issuer*, so the filer is the acquirer. With no EFTS
    mention alongside it there is no target-side evidence at all, and the row
    is evidence that the SBIR firm *bought* something.

    Such rows do not belong in the exit artifact. Demoting them to low was not
    enough: agency_private_capital/asset.py, phase2_outcomes.py, and
    run_agency_private_capital_phase1.py all treat row presence as an exit and
    never read confidence, so a demoted row still counted. They are written to
    a sibling file instead, which keeps the evidence without letting an exit
    consumer mistake it.
    """
    if not signals.get("form_d_business_combination"):
        return False
    return not any(signals.get(key) for key in EFTS_SIGNAL_KEYS)


def assign_confidence(event: dict) -> str:
    """Grade how well the evidence supports the SBIR firm being *acquired*.

    A Form D business-combination flag does not contribute. Form D Item 10
    marks a Rule 145 transaction, which is a deemed offer and sale of
    securities *by the issuer* to the other company's holders, so the filer is
    the acquirer or surviving entity. A target issues nothing and has nothing
    to report on Form D. Of 23 ``clarificationOfResponse`` texts read from
    EDGAR on 2026-09-09, 18 state the issuer acquired, 5 describe a corporate
    reorganization, and none describe the issuer as acquired.

    The flag previously returned ``high`` on its own, which put a
    self-reported acquirer-side boolean above EFTS full text that names a
    filer and has passed directional review. 407 events carried it with no
    other signal.

    The flag is still recorded in ``signals.form_d_business_combination`` --
    it is real evidence of a combination, in the other direction, and which
    SBIR firms are doing the acquiring is a question worth keeping. It just
    does not grade an exit.
    """
    efts = event.get("efts_detail")
    has_efts_high = efts is not None and "subsidiary" in efts.get("mention_types", [])
    has_acq_text = efts is not None and ("acquisition" in efts.get("mention_types", []))

    if has_efts_high:
        return "high"
    elif has_acq_text:
        return "medium"
    else:
        return "low"


def build_signals_dict(event: dict) -> dict[str, bool]:
    """Build a flat dict of which signals fired."""
    efts_types = set()
    if event.get("efts_detail"):
        efts_types = set(event["efts_detail"].get("mention_types", []))

    return {
        "form_d_business_combination": event.get("form_d_detail") is not None,
        "efts_subsidiary": "subsidiary" in efts_types,
        "efts_ma_definitive": "ma_definitive" in efts_types,
        "efts_acquisition_text": "acquisition" in efts_types,
        "efts_ma_proxy": "ma_proxy" in efts_types,
        "efts_ownership_active": "ownership_active" in efts_types,
    }


def identify_acquirer(event: dict) -> str | None:
    """Best-effort acquirer identification from available signals."""
    efts = event.get("efts_detail")
    if efts and efts.get("mention_filers"):
        return efts["mention_filers"][0]
    return None


def load_sbir_context(awards_csv: str) -> dict[str, dict]:
    """Load SBIR award context per company.

    Keys the returned dict by normalised company name (upper-cased, stripped)
    so that SEC-derived event names (which are upper-cased) match correctly.
    """
    companies: dict[str, dict] = {}
    with open(awards_csv, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            name = row.get("Company", "").strip()
            if not name:
                continue
            key = name.upper()
            agency = row.get("Agency", "").strip()
            year_str = row.get("Award Year", "").strip()
            amt_str = row.get("Award Amount", "").strip()
            if not year_str:
                continue
            try:
                year = int(year_str)
                amt_clean = amt_str.replace(",", "").replace("$", "")
                amt = float(amt_clean) if amt_clean else 0
            except ValueError:
                continue

            if key not in companies:
                companies[key] = {
                    "agency": agency,
                    "total_awards": 0,
                    "total_award_amount": 0,
                    "first_award_year": year,
                    "last_award_year": year,
                }
            c = companies[key]
            c["total_awards"] += 1
            c["total_award_amount"] += amt
            if year < c["first_award_year"]:
                c["first_award_year"] = year
            if year > c["last_award_year"]:
                c["last_award_year"] = year
            c["agency"] = agency

    return companies


def main():
    parser = argparse.ArgumentParser(description="Detect SBIR M&A exit events")
    parser.add_argument("--form-d", default="data/form_d_details.jsonl")
    parser.add_argument("--efts", default="data/sec_edgar_scan.jsonl")
    parser.add_argument("--awards", default="/tmp/sbir_awards_full.csv")
    parser.add_argument("--output", default="data/sbir_ma_events.jsonl")
    parser.add_argument(
        "--acquirer-side-output",
        default="data/sbir_ma_acquirer_side.jsonl",
        help="Rows whose only evidence is an acquirer-side Form D flag.",
    )
    args = parser.parse_args()

    # Layer 1: Form D
    print("Loading Form D data...")
    form_d_records = []
    with open(args.form_d) as f:
        for line in f:
            form_d_records.append(json.loads(line))
    combo_records = sum(1 for r in form_d_records if has_business_combination(r))
    form_d_events = extract_form_d_signals(form_d_records)
    dropped = combo_records - len(form_d_events)
    print(
        f"  Form D business combinations: {len(form_d_events)} companies kept, "
        f"{dropped} dropped on match tier != {KEEP_MATCH_TIER} "
        f"(of {combo_records} combination records)"
    )

    # Layer 2: EFTS
    print("Loading EFTS scan data...")
    efts_records = []
    with open(args.efts) as f:
        for line in f:
            efts_records.append(json.loads(line))
    efts_events = extract_efts_signals(efts_records)
    print(f"  EFTS M&A signals: {len(efts_events)} companies")

    # Merge
    merged = merge_events(form_d_events, efts_events)
    print(f"  Merged (deduplicated): {len(merged)} companies")

    # Load SBIR context
    print(f"Loading SBIR awards from {args.awards}...")
    sbir_context = load_sbir_context(args.awards)

    # Enrich and write
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    acquirer_side_path = Path(args.acquirer_side_output)
    acquirer_side_path.parent.mkdir(parents=True, exist_ok=True)

    tiers = {"high": 0, "medium": 0, "low": 0}
    acquirer_side_n = 0
    with open(output_path, "w") as out, open(acquirer_side_path, "w") as aside:
        for event in merged:
            signals = build_signals_dict(event)
            confidence = assign_confidence(event)
            acquirer = identify_acquirer(event)

            record = {
                "company_name": event["company_name"],
                "event_date": event["event_date"],
                "acquirer": acquirer,
                "confidence": confidence,
                "signals": signals,
                "signal_count": sum(signals.values()),
                "form_d_detail": event.get("form_d_detail"),
                "efts_detail": event.get("efts_detail"),
                "sbir_context": sbir_context.get(event["company_name"].strip().upper()),
            }
            if is_acquirer_side_only(signals):
                aside.write(json.dumps(record, default=str) + "\n")
                acquirer_side_n += 1
                continue
            out.write(json.dumps(record, default=str) + "\n")
            tiers[confidence] += 1

    total = sum(tiers.values())
    print(f"\n{'=' * 60}")
    print(f"M&A EXIT DETECTION COMPLETE — {total:,} events")
    print(f"{'=' * 60}")
    print(f"  High confidence:   {tiers['high']:,}")
    print(f"  Medium confidence: {tiers['medium']:,}")
    print(f"  Low confidence:    {tiers['low']:,}")
    print(f"  Output: {output_path}")
    print(f"\n  Acquirer-side only (excluded from the exit artifact): {acquirer_side_n:,}")
    print(f"  Output: {acquirer_side_path}")


if __name__ == "__main__":
    main()
