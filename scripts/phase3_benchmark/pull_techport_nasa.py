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


def _organization(org: object, role: str) -> dict[str, object] | None:
    if not isinstance(org, dict):
        return None
    name = org.get("organizationName") or org.get("organization_name") or org.get("name") or ""
    if not name:
        return None
    return {
        "organization_id": org.get("organizationId") or org.get("organization_id") or org.get("id"),
        "name": str(name),
        "type": org.get("organizationType") or org.get("organization_type") or org.get("type"),
        "role": role,
    }


def parse_project(project: dict) -> dict[str, object]:
    """Normalize a project without discarding linkage or transition fields."""
    program = project.get("program") or {}
    program_title = program.get("title", "") if isinstance(program, dict) else str(program)
    organizations = [
        parsed
        for org in (project.get("otherOrganizations") or project.get("other_organizations") or [])
        if (parsed := _organization(org, "supporting")) is not None
    ]
    lead = project.get("leadOrganization") or project.get("lead_organization") or {}
    if parsed_lead := _organization(lead, "lead"):
        organizations.insert(0, parsed_lead)
    firm_orgs = [
        str(org["name"])
        for org in organizations
        if not any(tok in str(org["name"]).upper() for tok in _NON_FIRM)
    ]
    trl = project.get("technologyReadinessLevel") or project.get("technology_readiness_level") or {}
    return {
        "project_id": project.get("projectId") or project.get("id"),
        "title": project.get("title", ""),
        "program": program_title,
        "phase": project.get("phase") or project.get("projectPhase") or project.get("project_phase"),
        "start": project.get("startDateString") or project.get("startDate"),
        "end": project.get("endDateString") or project.get("endDate"),
        "firm_orgs": firm_orgs,
        "organizations": organizations,
        "trl_begin": trl.get("begin") if isinstance(trl, dict) else None,
        "trl_current": trl.get("current") if isinstance(trl, dict) else None,
        "trl_end": trl.get("end") if isinstance(trl, dict) else None,
        "outcomes": project.get("projectOutcomes") or project.get("project_outcomes")
        or project.get("outcomes"),
        "destination": project.get("destination") or project.get("primaryDestination"),
        "description": str(project.get("description", "")),
    }


def link_firm(
    firm_orgs: list[str], name_to_ueis: dict[str, str | set[str]]
) -> dict[str, object]:
    """Resolve all organization matches and expose ambiguity instead of taking the first."""
    matches: dict[str, set[str]] = {}
    for org in firm_orgs:
        values = name_to_ueis.get(normalize_name(org))
        if values:
            matches[org] = {values} if isinstance(values, str) else set(values)
    ueis = sorted({uei for values in matches.values() for uei in values})
    status = "unique" if len(ueis) == 1 else "ambiguous" if ueis else "unmatched"
    return {
        "status": status,
        "uei": ueis[0] if len(ueis) == 1 else None,
        "ueis": ueis,
        "matched_orgs": sorted(matches),
    }


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
    total_search_hits = len(ids)
    if limit is not None:
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
        "search_hits": len(ids), "total_search_hits": total_search_hits,
        "selected_hits": len(ids), "projects_pulled": len(records), "throttled": throttled,
        "raw_sha256": digest.hexdigest(),
        "with_firm_org": sum(bool(r["firm_orgs"]) for r in records),
        "with_rich_description": sum(len(r["description"]) > 120 for r in records),
        "retrieval_limited": len(ids) < total_search_hits,
        "retrieval_complete": throttled == 0 and bool(ids) and len(ids) == total_search_hits,
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
