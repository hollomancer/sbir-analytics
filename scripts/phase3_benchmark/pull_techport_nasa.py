"""NASA cross-agency source: paced/cached TechPort puller for SBIR/STTR projects.

NASA barely uses sam.gov Contract Opportunities (its award notices there carry no firm-link key —
AwardNumber ~6%, Awardee ~5%, FPDS solicitationID ~2.5%, all matching zero of our NASA Phase III firms).
NASA's own portfolio, **TechPort** (`techport.nasa.gov/api`, public), holds ~20k SBIR/STTR projects with a
performing firm organization and a rich project description — the NASA-specific replacement for the GSA
archive used for DoD.

Pure, testable core: `parse_project` (project JSON → normalized record) and `link_firm` (organization
name → SBIR firm UEI). The network fetch is paced + retried (the API rate-limits under rapid calls) and
cached per project; the run emits a provenance manifest matching the FPDS/described pullers.

FIRST-RUN GATE (documented, not yet run — API was throttling at authoring time): confirm whether a
TechPort SBIR project represents the **transition/Phase III** vs the original Phase I/II, via its
`program` / phase / date fields. If transition-bearing, its `description` is the ranker target text; if it
is the original award, it enriches the query side instead.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

API = "https://techport.nasa.gov/api"
Fetch = Callable[[str], bytes | None]
_SUFFIXES = ("INC", "LLC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LP", "LLP", "THE",
             "INCORPORATED", "TECHNOLOGIES", "TECHNOLOGY", "TECH", "SYSTEMS")
_NON_FIRM = ("CENTER", "UNIVERS", "INSTITUTE", "LABORATORY", "NASA")


def normalize_name(value: object) -> str:
    text = re.sub(r"[^A-Z0-9 ]", " ", str(value).upper())
    text = re.sub(r"\b(" + "|".join(_SUFFIXES) + r")\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_project(project: dict) -> dict[str, object]:
    """Normalize a TechPort project into id / program / dates / firm orgs / description."""
    program = project.get("program") or {}
    program_title = program.get("title", "") if isinstance(program, dict) else str(program)
    orgs: list[str] = [o.get("organizationName", "") for o in (project.get("otherOrganizations") or [])
                       if isinstance(o, dict)]
    lead = project.get("leadOrganization") or {}
    if isinstance(lead, dict) and lead.get("organizationName"):
        orgs.append(lead["organizationName"])
    firm_orgs = [o for o in orgs if o and not any(tok in o.upper() for tok in _NON_FIRM)]
    return {
        "project_id": project.get("projectId") or project.get("id"),
        "title": project.get("title", ""),
        "program": program_title,
        "start": project.get("startDateString") or project.get("startDate"),
        "end": project.get("endDateString") or project.get("endDate"),
        "firm_orgs": firm_orgs,
        "description": str(project.get("description", "")),
    }


def link_firm(firm_orgs: list[str], name_to_uei: dict[str, str]) -> str | None:
    """First firm org whose normalized name resolves to a known SBIR firm UEI."""
    for org in firm_orgs:
        uei = name_to_uei.get(normalize_name(org))
        if uei:
            return uei
    return None


def _fetch(url: str, *, tries: int = 5, delay: float = 1.5) -> bytes | None:
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "sbir-phase3/1.0",
                                                            "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=40) as response:
                return response.read()
        except Exception:
            time.sleep(delay * (attempt + 1))
    return None


def pull_sbir_projects(*, query: str = "SBIR", pace: float = 1.0, cache_dir: Path | None = None,
                       fetcher: Fetch = _fetch, source_vintage: str = "unknown",
                       limit: int | None = None) -> tuple[list[dict], dict[str, object]]:
    """Search TechPort for SBIR/STTR projects and pull each (paced, cached). Returns records + manifest."""
    run_at = datetime.now(UTC).isoformat()
    # search endpoint returns key "results" (not "projects"); under load it may 200-with-empty, so retry.
    ids: list = []
    search = b""
    for search_attempt in range(8):
        search = fetcher(f"{API}/projects/search?searchQuery={urllib.parse.quote(query)}") or b""
        listing = json.loads(search) if search else {}
        items = listing.get("results") or listing.get("projects") or []
        ids = [p.get("projectId") for p in items if isinstance(p, dict) and p.get("projectId")]
        if ids:
            break
        time.sleep(3 * (search_attempt + 1))
    if limit:
        ids = ids[:limit]
    records: list[dict] = []
    digest = hashlib.sha256(search or b"")
    throttled = 0
    for project_id in ids:
        cached = cache_dir / f"{project_id}.json" if cache_dir else None
        payload = cached.read_bytes() if (cached and cached.exists()) else fetcher(f"{API}/projects/{project_id}")
        if payload is None:
            throttled += 1
            continue
        if cached and not cached.exists():
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(payload)
        digest.update(payload)
        body = json.loads(payload)
        records.append(parse_project(body.get("project", body)))
        time.sleep(pace)
    manifest = {
        "query": query, "api": API, "source_vintage": source_vintage, "run_at": run_at,
        "search_hits": len(ids), "projects_pulled": len(records), "throttled": throttled,
        "raw_sha256": digest.hexdigest(),
        "with_firm_org": sum(bool(r["firm_orgs"]) for r in records),
        "with_rich_description": sum(len(r["description"]) > 120 for r in records),
        "retrieval_complete": throttled == 0 and bool(ids),
    }
    return records, manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="SBIR")
    parser.add_argument("--pace", type=float, default=1.0, help="seconds between project fetches")
    parser.add_argument("--cache", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    records, manifest = pull_sbir_projects(query=args.query, pace=args.pace, cache_dir=args.cache, limit=args.limit)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(records, indent=2))
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
