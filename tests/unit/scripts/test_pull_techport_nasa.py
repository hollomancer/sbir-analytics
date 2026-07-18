"""Fixture tests for the TechPort NASA puller (canned fetcher, no network)."""

from __future__ import annotations

import json

from scripts.phase3_benchmark.pull_techport_nasa import (
    link_firm,
    normalize_name,
    parse_project,
    pull_sbir_projects,
)

_PROJECT = {
    "projectId": 12345,
    "title": "Deployable Membrane Optics for Laser Comm",
    "program": {"title": "Small Business Innovation Research/Small Business Technology Transfer"},
    "startDateString": "2018-01-01",
    "endDateString": "2020-12-31",
    "leadOrganization": {"organizationId": 1, "organizationName": "Langley Research Center"},
    "otherOrganizations": [{"organizationId": 2, "organizationName": "Acme Photonics, Inc."}],
    "phase": "Phase II",
    "technologyReadinessLevel": {"begin": 3, "current": 5, "end": 6},
    "description": "Deployable membrane optics for spaceborne laser communication, matured toward flight.",
}


def test_parse_project_extracts_firm_org_and_drops_nasa_center() -> None:
    rec = parse_project(_PROJECT)
    assert rec["project_id"] == 12345
    assert rec["program"].startswith("Small Business")
    assert rec["firm_orgs"] == ["Acme Photonics, Inc."]  # NASA center excluded
    assert rec["organizations"][0]["role"] == "lead"
    assert rec["organizations"][1]["organization_id"] == 2
    assert rec["phase"] == "Phase II"
    assert rec["trl_current"] == 5
    assert len(rec["description"]) > 40


def test_link_firm_resolves_org_name_to_uei() -> None:
    name_to_uei = {normalize_name("Acme Photonics, Inc."): "UEIACME01"}
    assert link_firm(["Acme Photonics, Inc."], name_to_uei)["uei"] == "UEIACME01"
    assert link_firm(["Unknown Corp"], name_to_uei)["status"] == "unmatched"
    ambiguous = {normalize_name("Acme Photonics, Inc."): {"UEI1", "UEI2"}}
    assert link_firm(["Acme Photonics, Inc."], ambiguous)["status"] == "ambiguous"


def test_pull_sbir_projects_paces_and_emits_manifest() -> None:
    def fetcher(url: str) -> bytes:
        if "search" in url:
            return json.dumps({"results": [{"projectId": 12345}]}).encode()
        return json.dumps({"project": _PROJECT}).encode()

    records, manifest = pull_sbir_projects(pace=0.0, fetcher=fetcher, source_vintage="test")
    assert len(records) == 1 and records[0]["firm_orgs"] == ["Acme Photonics, Inc."]
    assert manifest["search_hits"] == 1
    assert manifest["projects_pulled"] == 1
    assert manifest["with_firm_org"] == 1
    assert manifest["throttled"] == 0
    assert manifest["retrieval_complete"] is True
    assert len(manifest["raw_sha256"]) == 64


def test_limited_pull_is_not_reported_complete() -> None:
    def fetcher(url: str) -> bytes:
        if "search" in url:
            return json.dumps({"results": [{"projectId": 12345}, {"projectId": 99999}]}).encode()
        return json.dumps({"project": _PROJECT}).encode()

    _, manifest = pull_sbir_projects(pace=0.0, fetcher=fetcher, limit=1)
    assert manifest["total_search_hits"] == 2
    assert manifest["selected_hits"] == 1
    assert manifest["retrieval_limited"] is True
    assert manifest["retrieval_complete"] is False
