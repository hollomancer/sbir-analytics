"""Pull and parse FPDS Element 10Q records for the Phase III benchmark.

This is a research utility, not a production source adapter. Network access is
isolated behind ``fetch_url`` so parsing and provenance behavior can be tested
without contacting FPDS.
"""

import argparse
import hashlib
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


FEED_URL = "https://www.fpds.gov/ezsearch/FEEDS/ATOM?FEEDNAME=PUBLIC"
USER_AGENT = "sbir-analytics-research/1.0 (Phase III benchmark)"
Fetch = Callable[[str], bytes]

FIELD_NAMES: tuple[str, ...] = (
    "PIID",
    "UEI",
    "vendorName",
    "descriptionOfContractRequirement",
    "signedDate",
    "effectiveDate",
    "currentCompletionDate",
    "productOrServiceCode",
    "principalNAICSCode",
    "research",
    "agencyID",
    "contractActionType",
    "extentCompeted",
    "contractingOfficeID",
    "contractingOfficeAgencyID",
    "fundingRequestingOfficeID",
    "contractAwardUniqueKey",
)
REQUIRED_COMPLETENESS_FIELDS: tuple[str, ...] = (
    "PIID",
    "agencyID",
    "referenced_idv_piid",
    "UEI",
    "descriptionOfContractRequirement",
)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1]


def _find_outside_reference(element: ET.Element, name: str) -> ET.Element | None:
    """Find a field without accidentally taking a PIID from referencedIDVID."""

    if _local_name(element.tag) == "referencedIDVID":
        return None
    if _local_name(element.tag) == name:
        return element
    for child in element:
        match = _find_outside_reference(child, name)
        if match is not None:
            return match
    return None


def _find_descendant(element: ET.Element, name: str) -> ET.Element | None:
    return next((node for node in element.iter() if _local_name(node.tag) == name), None)


def _value(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    value = "".join(element.itertext()).strip()
    return value or None


def parse_entry(entry: ET.Element, research_code: str) -> dict[str, str | None]:
    """Parse one ATOM entry, including the nested parent-IDV PIID."""

    record: dict[str, str | None] = {"_research_code": research_code.upper()}
    for name in FIELD_NAMES:
        node = _find_outside_reference(entry, name)
        output_name = "contract_award_unique_key" if name == "contractAwardUniqueKey" else name
        record[output_name] = _value(node)
        if node is not None:
            for attribute in ("description", "name"):
                if node.get(attribute):
                    record[f"{name}_{attribute}"] = node.get(attribute)

    reference = _find_descendant(entry, "referencedIDVID")
    record["referenced_idv_piid"] = (
        _value(_find_descendant(reference, "PIID")) if reference is not None else None
    )
    record["referenced_idv_agency_id"] = (
        _value(_find_descendant(reference, "agencyID")) if reference is not None else None
    )
    return record


def parse_feed(page_xml: bytes | str, research_code: str) -> tuple[pd.DataFrame, int | None]:
    """Parse an FPDS ATOM page into transaction rows and its reported total."""

    payload = page_xml.encode() if isinstance(page_xml, str) else page_xml
    root = ET.fromstring(payload)
    entries = [node for node in root.iter() if _local_name(node.tag) == "entry"]
    rows = [parse_entry(entry, research_code) for entry in entries]
    total_node = next(
        (node for node in root.iter() if _local_name(node.tag) == "totalResults"),
        None,
    )
    total_text = _value(total_node)
    total = int(total_text) if total_text and total_text.isdigit() else None
    return pd.DataFrame(rows), total


def build_query_url(research_code: str, start: int) -> str:
    query = urllib.parse.quote(f"RESEARCH:{research_code.upper()}")
    return f"{FEED_URL}&q={query}&start={start}"


def fetch_url(url: str) -> bytes:
    """Fetch one public FPDS page. Kept separate for deterministic tests."""

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return response.read()


def _read_page(url: str, cache_file: Path | None, fetcher: Fetch) -> bytes:
    if cache_file is not None and cache_file.exists():
        return cache_file.read_bytes()
    payload = fetcher(url)
    if cache_file is not None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(payload)
    return payload


def _field_completeness(frame: pd.DataFrame) -> dict[str, float]:
    if frame.empty:
        return dict.fromkeys(REQUIRED_COMPLETENESS_FIELDS, 0.0)
    result: dict[str, float] = {}
    for field in REQUIRED_COMPLETENESS_FIELDS:
        if field not in frame.columns:
            result[field] = 0.0
            continue
        populated = frame[field].fillna("").astype(str).str.strip().ne("")
        result[field] = round(float(populated.mean()), 6)
    return result


def pull_research_code(
    research_code: str,
    *,
    pages: int,
    fetcher: Fetch = fetch_url,
    cache_dir: Path | None = None,
    source_vintage: str = "unknown",
    retrieved_at: str | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Retrieve bounded ATOM pages and return rows plus a provenance manifest."""

    if pages < 1:
        raise ValueError("pages must be at least 1")

    code = research_code.upper()
    frames: list[pd.DataFrame] = []
    digest = hashlib.sha256()
    total_results: int | None = None
    pages_retrieved = 0

    for page_number in range(pages):
        start = page_number * 10
        url = build_query_url(code, start)
        cache_file = cache_dir / f"page_{start:06d}.xml" if cache_dir else None
        payload = _read_page(url, cache_file, fetcher)
        digest.update(payload)
        frame, page_total = parse_feed(payload, code)
        if total_results is None:
            total_results = page_total
        if frame.empty:
            break
        frames.append(frame)
        pages_retrieved += 1
        if total_results is not None and sum(len(item) for item in frames) >= total_results:
            break

    rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    retrieved = retrieved_at or datetime.now(UTC).isoformat()
    retrieval_complete = total_results is not None and len(rows) >= total_results
    manifest: dict[str, object] = {
        "query": f"RESEARCH:{code}",
        "feed_url": FEED_URL,
        "source_vintage": source_vintage,
        "retrieved_at": retrieved,
        "parameters": {"research_code": code, "pages_requested": pages},
        "pages_retrieved": pages_retrieved,
        "reported_total_results": total_results,
        "row_count": len(rows),
        "raw_pages_sha256": digest.hexdigest(),
        "field_completeness": _field_completeness(rows),
        "retrieval_complete": retrieval_complete,
        "completeness_note": (
            "feed exhausted" if retrieval_complete else "bounded page limit or empty page reached"
        ),
    }
    return rows, manifest


def write_outputs(
    frame: pd.DataFrame,
    manifest: dict[str, object],
    *,
    output_path: Path,
    manifest_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(output_path, index=False)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("research_code", help="FPDS Element 10Q code, for example SR3")
    parser.add_argument("--pages", type=int, required=True, help="maximum 10-row pages")
    parser.add_argument("--output", type=Path, required=True, help="output parquet path")
    parser.add_argument("--manifest", type=Path, required=True, help="run-manifest JSON path")
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--source-vintage", default="unknown")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    frame, manifest = pull_research_code(
        args.research_code,
        pages=args.pages,
        cache_dir=args.cache_dir,
        source_vintage=args.source_vintage,
    )
    write_outputs(frame, manifest, output_path=args.output, manifest_path=args.manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
