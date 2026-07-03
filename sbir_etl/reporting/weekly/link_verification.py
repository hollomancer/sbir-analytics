"""HTTP verification of report reference links (debug mode only)."""

import sys

import httpx


from sbir_etl.reporting.weekly.models import CompanyResearch
from sbir_etl.reporting.weekly.rendering import (
    build_sbir_award_url,
    build_solicitation_url,
    build_usaspending_url,
)


def verify_reference_links(
    awards: list[dict],
    company_research: dict[str, CompanyResearch] | None = None,
) -> dict[str, list[dict]]:
    """Verify that constructed reference links return valid HTTP responses.

    Performs HTTP HEAD requests on a sample of each link type to check
    for broken URLs. Returns a summary dict with results per link type.

    Only runs in --debug mode to avoid slowing down normal report generation.
    """
    link_checks: dict[str, list[dict]] = {
        "sbir_award": [],
        "solicitation": [],
        "usaspending": [],
        "company_research": [],
    }

    # Check a sample of up to 5 awards to avoid excessive requests
    sample = awards[:5] if len(awards) > 5 else awards

    with httpx.Client(timeout=10, follow_redirects=True) as client:
        for a in sample:
            title = str(a.get("Award Title", ""))[:60]

            # SBIR.gov award link
            sbir_url = build_sbir_award_url(a)
            try:
                resp = client.head(sbir_url)
                link_checks["sbir_award"].append(
                    {
                        "url": sbir_url,
                        "status": resp.status_code,
                        "award": title,
                    }
                )
            except Exception as e:
                link_checks["sbir_award"].append(
                    {
                        "url": sbir_url,
                        "status": f"error: {e}",
                        "award": title,
                    }
                )

            # Solicitation link
            sol_url = build_solicitation_url(a)
            if sol_url:
                try:
                    resp = client.head(sol_url)
                    link_checks["solicitation"].append(
                        {
                            "url": sol_url,
                            "status": resp.status_code,
                            "award": title,
                        }
                    )
                except Exception as e:
                    link_checks["solicitation"].append(
                        {
                            "url": sol_url,
                            "status": f"error: {e}",
                            "award": title,
                        }
                    )

            # USAspending link
            usa_url = build_usaspending_url(a)
            if usa_url:
                try:
                    resp = client.head(usa_url)
                    link_checks["usaspending"].append(
                        {
                            "url": usa_url,
                            "status": resp.status_code,
                            "award": title,
                        }
                    )
                except Exception as e:
                    link_checks["usaspending"].append(
                        {
                            "url": usa_url,
                            "status": f"error: {e}",
                            "award": title,
                        }
                    )

        # Check company research source URLs (sample)
        if company_research:
            checked_urls: set[str] = set()
            for cr in list(company_research.values())[:3]:
                for url in cr.source_urls[:2]:
                    if url in checked_urls:
                        continue
                    checked_urls.add(url)
                    try:
                        resp = client.head(url)
                        link_checks["company_research"].append(
                            {
                                "url": url,
                                "status": resp.status_code,
                            }
                        )
                    except Exception as e:
                        link_checks["company_research"].append(
                            {
                                "url": url,
                                "status": f"error: {e}",
                            }
                        )

    return link_checks


def _print_link_verification_report(link_checks: dict[str, list[dict]]) -> None:
    """Print link verification results to stderr."""
    print("\n[DEBUG] === Reference Link Verification ===", file=sys.stderr)
    for link_type, checks in link_checks.items():
        if not checks:
            print(f"[DEBUG] {link_type}: no links to check", file=sys.stderr)
            continue
        ok = sum(1 for c in checks if isinstance(c["status"], int) and c["status"] < 400)
        broken = [c for c in checks if not (isinstance(c["status"], int) and c["status"] < 400)]
        print(
            f"[DEBUG] {link_type}: {ok}/{len(checks)} OK",
            file=sys.stderr,
        )
        for b in broken:
            award_info = f" (award: {b['award']})" if "award" in b else ""
            print(
                f"[DEBUG]   BROKEN: {b['url']} -> {b['status']}{award_info}",
                file=sys.stderr,
            )
