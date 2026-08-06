"""Tests for the USPTO browser-automation download pipeline.

`uspto_browser.py` was promoted out of `scripts/` at 0% line coverage. It is
reached from `download_uspto_op`, and the contract that matters to that op is
the one pinned here: `download_assignments` records a per-file failure in its
result list instead of raising, so a partial download looks like a successful
call. The op compensates with its own check (see
`tests/unit/assets/jobs/test_source_download_execution.py`); this file is the
other half of that pair.

Playwright is not installed in the test environment — and, as
`test_download_assignments_requires_playwright` records, is not declared as a
dependency anywhere in the repository. These tests inject a stub module so the
orchestration logic is exercised without a browser.
"""

import asyncio
import sys
import types
from pathlib import Path

import pytest

from sbir_etl.extractors.source_downloads import uspto_browser

pytestmark = [pytest.mark.fast, pytest.mark.unit]


class _Page:
    async def goto(self, url, **kwargs):
        return None


class _Context:
    async def new_page(self):
        return _Page()


class _Browser:
    def __init__(self):
        self.closed = False

    async def new_context(self, **kwargs):
        return _Context()

    async def close(self):
        self.closed = True


class _Chromium:
    def __init__(self, browser):
        self._browser = browser

    async def launch(self, **kwargs):
        return self._browser


class _Playwright:
    def __init__(self, browser):
        self.chromium = _Chromium(browser)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


@pytest.fixture
def stub_playwright(monkeypatch):
    """Install a stub `playwright.async_api` and skip the session-warmup sleep."""
    browser = _Browser()
    module = types.ModuleType("playwright.async_api")
    module.async_playwright = lambda: _Playwright(browser)
    package = types.ModuleType("playwright")
    package.async_api = module
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.async_api", module)

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    return browser


def test_download_assignments_records_a_failure_instead_of_raising(
    stub_playwright, tmp_path, monkeypatch
):
    """A per-file error becomes a result entry, so the call still "succeeds".

    This is why `download_uspto_op` inspects the returned list. Without that
    check the job would report success while holding a partial assignment set.
    """

    async def _boom(page, url, output_path, timeout_minutes=30):
        raise RuntimeError("403 Forbidden")

    monkeypatch.setattr(uspto_browser, "download_file", _boom)

    results = asyncio.run(
        uspto_browser.download_assignments(output_dir=tmp_path, files=["assignment"])
    )

    assert results == [{"file": "assignment", "error": "403 Forbidden"}]
    assert stub_playwright.closed, "the browser must be closed even when a file fails"


def test_download_assignments_reports_each_file_separately(stub_playwright, tmp_path, monkeypatch):
    """One failure does not abandon the remaining files."""

    async def _one_bad(page, url, output_path, timeout_minutes=30):
        if "assignor" in url:
            raise RuntimeError("timeout")
        return {"size": 10}

    monkeypatch.setattr(uspto_browser, "download_file", _one_bad)

    results = asyncio.run(
        uspto_browser.download_assignments(
            output_dir=tmp_path, files=["assignment", "assignor", "assignee"]
        )
    )

    assert [r["file"] for r in results] == ["assignment", "assignor", "assignee"]
    assert [("error" in r) for r in results] == [False, True, False]


def test_download_assignments_skips_an_unknown_file_key(stub_playwright, tmp_path, monkeypatch):
    """An unknown key is skipped silently rather than reported as a failure.

    Worth pinning because the op cannot distinguish "skipped" from "never
    requested": both produce a shorter result list, and only the op's own
    empty-set check catches the case where every key was unknown.
    """

    async def _ok(page, url, output_path, timeout_minutes=30):
        return {"size": 10}

    monkeypatch.setattr(uspto_browser, "download_file", _ok)

    results = asyncio.run(
        uspto_browser.download_assignments(
            output_dir=tmp_path, files=["assignment", "not-a-real-file"]
        )
    )

    assert [r["file"] for r in results] == ["assignment"]


def test_download_assignments_defaults_to_the_four_core_files(
    stub_playwright, tmp_path, monkeypatch
):
    async def _ok(page, url, output_path, timeout_minutes=30):
        return {"size": 10}

    monkeypatch.setattr(uspto_browser, "download_file", _ok)

    results = asyncio.run(uspto_browser.download_assignments(output_dir=tmp_path))

    assert [r["file"] for r in results] == ["assignment", "assignor", "assignee", "documentid"]


def test_download_assignments_creates_the_output_directory(stub_playwright, tmp_path, monkeypatch):
    async def _ok(page, url, output_path, timeout_minutes=30):
        return {"size": 10}

    monkeypatch.setattr(uspto_browser, "download_file", _ok)
    destination = tmp_path / "nested" / "assignments"

    asyncio.run(uspto_browser.download_assignments(output_dir=destination, files=["assignment"]))

    assert destination.is_dir()


def test_every_declared_assignment_file_has_a_uspto_url_and_size():
    for key, spec in uspto_browser.USPTO_ASSIGNMENT_FILES.items():
        assert spec["url"].startswith("https://data.uspto.gov/"), key
        assert spec["size_mb"] > 0, key


def test_download_assignments_requires_playwright(tmp_path):
    """Playwright is imported at call time and is declared nowhere in the repo.

    `grep -r playwright pyproject.toml packages/*/pyproject.toml` returns
    nothing, and no Makefile target or setup script installs it, yet
    `download_uspto_op` reaches this function on every run. On a host without a
    manual install the job fails with a bare ModuleNotFoundError from inside a
    Dagster op.

    This test pins the current behaviour rather than asserting it is correct.
    If the dependency is declared — or the failure is turned into an actionable
    message naming the install step — update this test along with it.
    """
    real_playwright = sys.modules.get("playwright")
    if real_playwright is not None:  # pragma: no cover - environment dependent
        pytest.skip("playwright is installed in this environment")

    with pytest.raises(ModuleNotFoundError, match="playwright"):
        asyncio.run(
            uspto_browser.download_assignments(output_dir=Path(tmp_path), files=["assignment"])
        )
