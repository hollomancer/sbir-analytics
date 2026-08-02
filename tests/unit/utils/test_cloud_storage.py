"""Unit tests for local data-file discovery and resolution.

Formerly covered S3-first resolution; the module now locates files under the
configured data root (see docs/deployment/aws-decommission-plan.md).
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sbir_etl.utils.cloud_storage import (
    DATA_ROOT_ENV,
    SbirAwardsSource,
    check_sbir_data_freshness,
    find_latest_recipient_lookup_parquet,
    find_latest_sam_gov_parquet,
    find_latest_sbir_awards,
    find_latest_usaspending_dump,
    get_data_root,
    resolve_data_path,
    resolve_sbir_awards_csv,
)


class TestGetDataRoot:
    def test_defaults_to_data(self, monkeypatch):
        monkeypatch.delenv(DATA_ROOT_ENV, raising=False)
        assert get_data_root() == Path("data")

    def test_honours_env_override(self, monkeypatch):
        monkeypatch.setenv(DATA_ROOT_ENV, "/Volumes/SSDmini/sbir-analytics/data")
        assert get_data_root() == Path("/Volumes/SSDmini/sbir-analytics/data")


class TestResolveDataPath:
    def test_returns_existing_path(self, tmp_path):
        f = tmp_path / "a.csv"
        f.write_text("x")
        assert resolve_data_path(f) == f

    def test_falls_back_when_primary_missing(self, tmp_path):
        fallback = tmp_path / "fallback.csv"
        fallback.write_text("x")
        assert resolve_data_path(tmp_path / "missing.csv", local_fallback=fallback) == fallback

    def test_prefer_local_wins_over_existing_primary(self, tmp_path):
        primary = tmp_path / "primary.csv"
        primary.write_text("p")
        fallback = tmp_path / "fallback.csv"
        fallback.write_text("f")

        result = resolve_data_path(primary, local_fallback=fallback, prefer_local=True)

        assert result == fallback

    def test_prefer_local_ignored_when_fallback_missing(self, tmp_path):
        primary = tmp_path / "primary.csv"
        primary.write_text("p")

        result = resolve_data_path(primary, local_fallback=tmp_path / "nope.csv", prefer_local=True)

        assert result == primary

    def test_raises_when_nothing_exists(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="File not found"):
            resolve_data_path(tmp_path / "a.csv", local_fallback=tmp_path / "b.csv")

    def test_accepts_string_path(self, tmp_path):
        f = tmp_path / "a.csv"
        f.write_text("x")
        assert resolve_data_path(str(f)) == f


class TestFindLatestSbirAwards:
    def test_prefers_canonical(self, tmp_path):
        base = tmp_path / "raw" / "sbir"
        base.mkdir(parents=True)
        (base / "award_data.csv").write_text("canonical")
        vintage = base / "history" / "2026-01-01"
        vintage.mkdir(parents=True)
        (vintage / "award_data.csv").write_text("old")

        assert find_latest_sbir_awards(tmp_path) == str(base / "award_data.csv")

    def test_falls_back_to_newest_vintage(self, tmp_path):
        history = tmp_path / "raw" / "sbir" / "history"
        for date in ("2026-01-01", "2026-03-05", "2026-02-09"):
            d = history / date
            d.mkdir(parents=True)
            (d / "award_data.csv").write_text("x")

        found = find_latest_sbir_awards(tmp_path)

        assert found == str(history / "2026-03-05" / "award_data.csv")

    def test_ignores_vintage_without_csv(self, tmp_path):
        (tmp_path / "raw" / "sbir" / "history" / "2026-01-01").mkdir(parents=True)
        assert find_latest_sbir_awards(tmp_path) is None

    def test_returns_none_when_absent(self, tmp_path):
        assert find_latest_sbir_awards(tmp_path) is None


class TestFindLatestUsaspendingDump:
    def test_finds_full_dump(self, tmp_path):
        d = tmp_path / "usaspending"
        d.mkdir(parents=True)
        dump = d / "usaspending-db_20260101.zip"
        dump.write_text("x")

        assert find_latest_usaspending_dump(tmp_path, "full") == str(dump)

    def test_finds_subset_dump_for_test_type(self, tmp_path):
        d = tmp_path / "usaspending"
        d.mkdir(parents=True)
        subset = d / "usaspending-db-subset_20260101.zip"
        subset.write_text("x")

        assert find_latest_usaspending_dump(tmp_path, "test") == str(subset)

    def test_full_does_not_match_subset(self, tmp_path):
        d = tmp_path / "usaspending"
        d.mkdir(parents=True)
        (d / "usaspending-db-subset_20260101.zip").write_text("x")

        assert find_latest_usaspending_dump(tmp_path, "full") is None

    def test_searches_nested_directories(self, tmp_path):
        nested = tmp_path / "usaspending" / "2026-01-01"
        nested.mkdir(parents=True)
        dump = nested / "usaspending-db_20260101.zip"
        dump.write_text("x")

        assert find_latest_usaspending_dump(tmp_path, "full") == str(dump)

    def test_unknown_type_returns_none(self, tmp_path):
        assert find_latest_usaspending_dump(tmp_path, "bogus") is None

    def test_returns_none_when_absent(self, tmp_path):
        assert find_latest_usaspending_dump(tmp_path, "full") is None


class TestFindLatestSamGovParquet:
    def test_prefers_canonical_over_partial(self, tmp_path):
        base = tmp_path / "raw" / "sam_gov"
        base.mkdir(parents=True)
        canonical = base / "sam_entity_records.parquet"
        canonical.write_text("full")
        (base / "sam_entity_records_20260101.parquet").write_text("dated")

        assert find_latest_sam_gov_parquet(tmp_path) == str(canonical)

    def test_falls_back_to_dated(self, tmp_path):
        base = tmp_path / "raw" / "sam_gov"
        base.mkdir(parents=True)
        dated = base / "sam_entity_records_20260101.parquet"
        dated.write_text("x")

        assert find_latest_sam_gov_parquet(tmp_path) == str(dated)

    def test_returns_none_when_absent(self, tmp_path):
        assert find_latest_sam_gov_parquet(tmp_path) is None


class TestFindLatestRecipientLookup:
    def test_finds_parquet(self, tmp_path):
        d = tmp_path / "raw" / "usaspending" / "recipient_lookup" / "2026-01-01"
        d.mkdir(parents=True)
        f = d / "recipient_lookup.parquet"
        f.write_text("x")

        assert find_latest_recipient_lookup_parquet(tmp_path) == str(f)

    def test_returns_none_when_absent(self, tmp_path):
        assert find_latest_recipient_lookup_parquet(tmp_path) is None


class TestCheckSbirDataFreshness:
    @staticmethod
    def _recent_date(days_ago: int) -> str:
        return (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y-%m-%d")

    def test_fresh_data_no_warnings(self):
        source = SbirAwardsSource(
            path=Path("/tmp/test.csv"), origin="vintage", vintage_date=self._recent_date(2)
        )
        assert check_sbir_data_freshness(source, self._recent_date(2), days=7) == []

    def test_stale_vintage_warns(self):
        source = SbirAwardsSource(
            path=Path("/tmp/test.csv"), origin="vintage", vintage_date=self._recent_date(30)
        )

        warnings = check_sbir_data_freshness(source, self._recent_date(1), days=7)

        assert len(warnings) == 1
        assert "Local data is" in warnings[0]

    def test_no_vintage_date_skips_that_check(self):
        source = SbirAwardsSource(path=Path("/tmp/test.csv"), origin="download")

        warnings = check_sbir_data_freshness(source, self._recent_date(30), days=7)

        assert all("Local data is" not in w for w in warnings)

    def test_stale_award_data_warns(self):
        source = SbirAwardsSource(
            path=Path("/tmp/test.csv"), origin="vintage", vintage_date=self._recent_date(1)
        )

        warnings = check_sbir_data_freshness(source, self._recent_date(60), days=7)

        assert any("Most recent award in data" in w for w in warnings)

    def test_both_stale_yields_two_warnings(self):
        source = SbirAwardsSource(
            path=Path("/tmp/test.csv"), origin="vintage", vintage_date=self._recent_date(30)
        )

        warnings = check_sbir_data_freshness(source, self._recent_date(60), days=7)

        assert len(warnings) == 2

    def test_missing_max_award_date_skips_that_check(self):
        source = SbirAwardsSource(
            path=Path("/tmp/test.csv"), origin="vintage", vintage_date=self._recent_date(1)
        )
        assert check_sbir_data_freshness(source, None, days=7) == []


class TestResolveSbirAwardsCsv:
    def test_uses_canonical_and_reads_sidecar_date(self, tmp_path, monkeypatch):
        base = tmp_path / "raw" / "sbir"
        base.mkdir(parents=True)
        (base / "award_data.csv").write_text("x")
        (base / "award_data.meta.json").write_text(
            json.dumps({"downloaded_at": "2026-08-02T12:00:00+00:00"})
        )
        monkeypatch.setenv(DATA_ROOT_ENV, str(tmp_path))

        source = resolve_sbir_awards_csv()

        assert source.origin == "local"
        assert source.vintage_date == "2026-08-02"

    def test_vintage_date_comes_from_path(self, tmp_path, monkeypatch):
        d = tmp_path / "raw" / "sbir" / "history" / "2026-07-01"
        d.mkdir(parents=True)
        (d / "award_data.csv").write_text("x")
        monkeypatch.setenv(DATA_ROOT_ENV, str(tmp_path))

        source = resolve_sbir_awards_csv()

        assert source.origin == "vintage"
        assert source.vintage_date == "2026-07-01"

    def test_missing_sidecar_leaves_date_none(self, tmp_path, monkeypatch):
        base = tmp_path / "raw" / "sbir"
        base.mkdir(parents=True)
        (base / "award_data.csv").write_text("x")
        monkeypatch.setenv(DATA_ROOT_ENV, str(tmp_path))

        assert resolve_sbir_awards_csv().vintage_date is None
