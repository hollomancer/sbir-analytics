import json
from datetime import UTC, datetime

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_negative_controls.nih_reporter import (
    NIHReporterExtractor,
    canonicalize_nih_query_key,
)
from sbir_analytics.assets.phase_iii_negative_controls.source_keys import (
    NIH_CORE_PROJECT_ADAPTER,
    NIH_PROJECT_ADAPTER,
)


pytestmark = pytest.mark.fast


def _attempts() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "adapter": NIH_PROJECT_ADAPTER,
                "award_year_key": "2024",
                "source_award_key": " 5 F32 DK132864-03, ",
            },
            {
                "adapter": NIH_CORE_PROJECT_ADAPTER,
                "award_year_key": "2024",
                "source_award_key": "F32DK132864",
            },
        ]
    )


def test_nih_query_format_preserves_structural_punctuation() -> None:
    assert canonicalize_nih_query_key(" 5 F32 DK132864-03, ") == "5F32DK132864-03"


def test_exact_nih_extraction_records_identifiers_and_response_digest() -> None:
    payloads: list[dict[str, object]] = []

    def requester(payload: dict[str, object]) -> bytes:
        payloads.append(payload)
        return json.dumps(
            {
                "meta": {"total": 1, "offset": 0, "limit": 50},
                "results": [
                    {
                        "appl_id": 10824314,
                        "fiscal_year": 2024,
                        "project_num": "5F32DK132864-03",
                        "core_project_num": "F32DK132864",
                        "organization": {
                            "org_ueis": ["DPMGH9MG1X67"],
                            "org_duns": ["076580745"],
                        },
                    }
                ],
            },
            separators=(",", ":"),
        ).encode()

    extractor = NIHReporterExtractor(
        _attempts(),
        requester=requester,
        retrieval_time=datetime(2026, 8, 3, tzinfo=UTC),
    )
    result = extractor.extract()

    assert len(payloads) == 1
    assert payloads[0]["criteria"] == {
        "project_nums": ["5F32DK132864-03", "F32DK132864"],
        "fiscal_years": [2024],
    }
    assert result.to_dict("records") == [
        {
            "official_record_id": "10824314",
            "project_num": "5F32DK132864-03",
            "core_project_num": "F32DK132864",
            "fiscal_year": 2024,
            "recipient_uei": "DPMGH9MG1X67",
            "recipient_duns": "076580745",
        }
    ]
    assert extractor.provenance["request_count"] == 1
    assert len(extractor.provenance["source_digest"]) == 64


def test_nih_extraction_paginates_to_declared_total() -> None:
    offsets: list[int] = []

    def requester(payload: dict[str, object]) -> bytes:
        offset = int(payload["offset"])
        offsets.append(offset)
        result = {
            "appl_id": offset + 1,
            "fiscal_year": 2024,
            "project_num": "5F32DK132864-03",
            "core_project_num": "F32DK132864",
            "organization": {"primary_uei": "DPMGH9MG1X67"},
        }
        return json.dumps(
            {
                "meta": {"total": 2, "offset": offset, "limit": 50},
                "results": [result],
            }
        ).encode()

    result = NIHReporterExtractor(_attempts(), requester=requester).extract()

    assert offsets == [0, 1]
    assert len(result) == 2
