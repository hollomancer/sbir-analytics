"""Date handling on the C3 collision path (issue #879).

``collision.py`` is pinned as implementation by ``studies/ma-discovery-recall``
and is not edited here. Its private ``parse_event_date`` reads a timestamped
value such as ``2024-03-20T00:00:00`` as missing. The ``xfail(strict=True)``
tests record that defect. They turn into failures (XPASS) when the pinned
parser is routed through ``parse_iso_date_lenient``, so the marker must then be
removed. The ``monkeypatch`` tests show that the lenient parser alone fixes both
the missed join and the false join.
"""

from __future__ import annotations

from typing import Any

import pytest

from sbir_etl.enrichers.ma_discovery import collision
from sbir_etl.enrichers.ma_discovery.collision import apply_c3
from sbir_etl.utils.date_utils import parse_iso_date_lenient


pytestmark = pytest.mark.fast

_PINNED = (
    "collision.parse_event_date is pinned by studies/ma-discovery-recall and still "
    "reads a timestamped date as missing (#879)"
)


def _existing(event_date: str) -> list[dict[str, Any]]:
    return [
        {
            "company_name": "Aether Photonics, Inc.",
            "acquirer": "Helios Defense",
            "event_date": event_date,
            "confidence": "low",
            "signals": {"efts_acquisition_text": True},
        }
    ]


def _hit(event_date: str) -> list[dict[str, Any]]:
    return [
        {
            "company_name": "Aether Photonics",
            "acquirer": "Helios Defense",
            "event_date": event_date,
            "confidence": "medium",
        }
    ]


def _assert_joins(result: collision.CollisionResult) -> None:
    assert result.inserted == []
    assert len(result.rows) == 1
    assert result.rows[0]["signals"]["discovery_confirmed"] is True


def _assert_does_not_join(result: collision.CollisionResult) -> None:
    assert len(result.inserted) == 1
    assert len(result.rows) == 2
    assert "discovery_confirmed" not in result.rows[0]["signals"]


@pytest.fixture
def lenient_collision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collision, "parse_event_date", parse_iso_date_lenient)


@pytest.mark.xfail(strict=True, reason=_PINNED)
def test_timestamped_hit_joins_dated_row() -> None:
    _assert_joins(apply_c3(_existing("2024-03-01"), _hit("2024-03-20T00:00:00")))


@pytest.mark.xfail(strict=True, reason=_PINNED)
def test_timestamped_rows_with_distant_dates_do_not_join() -> None:
    # On the pinned parser the timestamped row looks dateless, and C3 joins any
    # same-company hit onto a dateless row, so these two events merge.
    _assert_does_not_join(apply_c3(_existing("2024-01-05T00:00:00"), _hit("2024-06-01")))


@pytest.mark.usefixtures("lenient_collision")
@pytest.mark.parametrize(
    ("existing", "hit"),
    [
        ("2024-03-01", "2024-03-20T00:00:00"),
        ("2024-03-01T09:15:00", "2024-03-20"),
        ("2024-03-01 09:15:00", "2024-03-20T23:59:00Z"),
        ("2024-03-01T22:00-05:00", "2024-03-31"),
    ],
)
def test_lenient_parser_joins_timestamped_rows(existing: str, hit: str) -> None:
    _assert_joins(apply_c3(_existing(existing), _hit(hit)))


@pytest.mark.usefixtures("lenient_collision")
@pytest.mark.parametrize(
    ("existing", "hit"),
    [
        ("2024-01-05T00:00:00", "2024-06-01"),
        ("2024-01-05", "2024-06-01T00:00:00"),
        # Local date as written: 2024-03-01T22:00-05:00 is March 1, so it is 31
        # days from April 1 and outside the 30-day window. A UTC conversion would
        # make it March 2 and wrongly bring it inside.
        ("2024-03-01T22:00-05:00", "2024-04-01"),
    ],
)
def test_lenient_parser_keeps_different_dates_apart(existing: str, hit: str) -> None:
    _assert_does_not_join(apply_c3(_existing(existing), _hit(hit)))
