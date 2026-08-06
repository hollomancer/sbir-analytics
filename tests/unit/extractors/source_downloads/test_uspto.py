"""Tests for the promoted USPTO download pipeline.

`sbir_etl/extractors/source_downloads/uspto.py` moved out of `scripts/` — from
exploratory tier to pipelines tier — at 0% line coverage. It is also the most
brittle integration in the set: anonymous downloads from data.uspto.gov ended
2026-06-18 and the endpoint now answers unauthorized and expired-presigned
requests with an HTML shell under HTTP 200, so a naive download succeeds while
writing garbage.

The module's defences against that are what these tests pin, at both layers it
checks: the declared Content-Type, and the magic bytes of what actually
arrived. Nothing here touches the network — a stub session stands in for
`requests`.
"""

import io
from pathlib import Path

import pytest

from sbir_etl.extractors.source_downloads import uspto

pytestmark = [pytest.mark.fast, pytest.mark.unit]

ZIP_MAGIC = b"PK\x03\x04"


class _Response:
    """Minimal stand-in for the parts of requests.Response the module uses."""

    def __init__(self, *, body: bytes = b"", headers: dict | None = None, text: str = ""):
        self._body = body
        self.headers = headers or {}
        self._text = text

    def raise_for_status(self) -> None:
        return None

    @property
    def text(self) -> str:
        return self._text or self._body.decode(errors="replace")

    def iter_content(self, chunk_size: int = 1):
        stream = io.BytesIO(self._body)
        while chunk := stream.read(chunk_size):
            yield chunk


class _Session:
    """Returns queued responses in order and records the requests made."""

    def __init__(self, *responses: _Response):
        self._responses = list(responses)
        self.calls: list[tuple[str, dict]] = []
        self.headers: dict[str, str] = {}

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        return self._responses.pop(0)


# --------------------------------------------------------------------------
# URL redaction
# --------------------------------------------------------------------------


def test_redact_url_strips_the_signature_from_a_presigned_url():
    """Presigned URLs carry credentials in the query string and get printed."""
    redacted = uspto._redact_url(
        "https://cf.uspto.gov/g_patent.tsv.zip?X-Amz-Signature=deadbeef&X-Amz-Expires=30"
    )

    assert redacted == "https://cf.uspto.gov/g_patent.tsv.zip?<redacted>"
    assert "deadbeef" not in redacted


def test_redact_url_leaves_a_plain_url_alone():
    assert uspto._redact_url("https://data.uspto.gov/file.zip") == "https://data.uspto.gov/file.zip"


# --------------------------------------------------------------------------
# API key resolution
# --------------------------------------------------------------------------


def test_resolve_api_key_prefers_the_explicit_value(monkeypatch):
    monkeypatch.setenv(uspto.API_KEY_ENV_VAR, "from-env")

    assert uspto.resolve_api_key("from-cli") == "from-cli"


def test_resolve_api_key_falls_back_to_the_environment(monkeypatch):
    monkeypatch.setenv(uspto.API_KEY_ENV_VAR, "from-env")

    assert uspto.resolve_api_key(None) == "from-env"


def test_resolve_api_key_reads_the_repo_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv(uspto.API_KEY_ENV_VAR, raising=False)
    (tmp_path / ".env").write_text(f"OTHER=1\n{uspto.API_KEY_ENV_VAR}=from-dotenv\n")
    monkeypatch.setattr(uspto, "REPO", tmp_path)

    assert uspto.resolve_api_key(None) == "from-dotenv"


def test_resolve_api_key_ignores_a_blank_env_file_entry(monkeypatch, tmp_path):
    """`USPTO_ODP_API_KEY=` is an unset key, not a key whose value is empty."""
    monkeypatch.delenv(uspto.API_KEY_ENV_VAR, raising=False)
    (tmp_path / ".env").write_text(f"{uspto.API_KEY_ENV_VAR}=\n")
    monkeypatch.setattr(uspto, "REPO", tmp_path)

    with pytest.raises(ValueError, match="No USPTO ODP API key found"):
        uspto.resolve_api_key(None)


def test_resolve_api_key_raises_with_the_remedy_when_nothing_is_set(monkeypatch, tmp_path):
    monkeypatch.delenv(uspto.API_KEY_ENV_VAR, raising=False)
    monkeypatch.setattr(uspto, "REPO", tmp_path)

    with pytest.raises(ValueError, match=uspto.API_KEY_ENV_VAR):
        uspto.resolve_api_key(None)


# --------------------------------------------------------------------------
# Session configuration
# --------------------------------------------------------------------------


def test_session_retries_server_errors_but_not_client_mistakes():
    session = uspto.create_session_with_retries()
    retry = session.get_adapter("https://data.uspto.gov").max_retries

    assert retry.total == 3
    assert 429 in retry.status_forcelist and 503 in retry.status_forcelist
    # A 404 or 403 is a wrong URL or a bad key; retrying spends mint quota.
    assert 404 not in retry.status_forcelist
    assert 403 not in retry.status_forcelist
    assert session.headers["User-Agent"] == uspto.USER_AGENT


# --------------------------------------------------------------------------
# stream_download: the two HTML-shell defences
# --------------------------------------------------------------------------


def test_stream_download_writes_the_file_and_reports_its_digest(tmp_path):
    payload = ZIP_MAGIC + b"real archive bytes"
    session = _Session(_Response(body=payload, headers={"content-type": "application/zip"}))
    dest = tmp_path / "out.zip"

    result = uspto.stream_download("https://data.uspto.gov/f.zip", dest, session)

    assert dest.read_bytes() == payload
    assert result["size"] == len(payload)

    import hashlib

    assert result["sha256"] == hashlib.sha256(payload).hexdigest()


def test_stream_download_rejects_an_html_content_type(tmp_path):
    """Layer one: the server declares HTML, so never write the body at all."""
    session = _Session(
        _Response(body=b"<html>expired</html>", headers={"content-type": "text/html"})
    )
    dest = tmp_path / "out.zip"

    with pytest.raises(ValueError, match="HTML instead of a file"):
        uspto.stream_download("https://cf.uspto.gov/f.zip?sig=x", dest, session)

    assert not dest.exists()


def test_stream_download_deletes_an_html_body_served_as_binary(tmp_path):
    """Layer two: the declared type lied, so judge the bytes that arrived.

    A truncated HTML shell left on disk under a .zip name is the failure this
    guards — downstream would read it as a corrupt archive rather than as the
    expired-mint message it is.
    """
    session = _Session(
        _Response(
            body=b"<!DOCTYPE html><html>expired mint</html>",
            headers={"content-type": "application/octet-stream"},
        )
    )
    dest = tmp_path / "out.zip"

    with pytest.raises(ValueError, match="HTML, not a ZIP archive"):
        uspto.stream_download("https://cf.uspto.gov/f.zip?sig=x", dest, session)

    assert not dest.exists()


def test_stream_download_keeps_a_non_zip_that_is_not_html(tmp_path, capsys):
    """An unexpected magic number warns but is not treated as an error."""
    session = _Session(
        _Response(body=b"\x1f\x8bgzip data", headers={"content-type": "application/gzip"})
    )
    dest = tmp_path / "out.gz"

    result = uspto.stream_download("https://data.uspto.gov/f.gz", dest, session)

    assert dest.exists()
    assert result["size"] == len(b"\x1f\x8bgzip data")
    assert "does not appear to be a ZIP" in capsys.readouterr().out


# --------------------------------------------------------------------------
# download_odp_file: the three response modes
# --------------------------------------------------------------------------


def test_odp_file_streams_a_direct_zip_response(tmp_path):
    payload = ZIP_MAGIC + b"x" * 8192
    session = _Session(_Response(body=payload, headers={"content-type": "application/zip"}))
    dest = tmp_path / "pv.zip"

    result = uspto.download_odp_file("PVGPATDIS/g_patent.tsv.zip", "key", dest, session)

    assert dest.read_bytes() == payload
    assert result["size"] == len(payload)
    url, kwargs = session.calls[0]
    assert url == f"{uspto.ODP_FILES_API}/PVGPATDIS/g_patent.tsv.zip"
    assert kwargs["headers"]["X-API-KEY"] == "key"


def test_odp_file_follows_a_presigned_url_from_a_mint_message(tmp_path):
    """Large files answer with a JSON mint message; the URL expires in ~30s."""
    payload = ZIP_MAGIC + b"archive"
    session = _Session(
        _Response(
            text='{"message": "https://cf.uspto.gov/signed.zip?sig=abc. you submitted 3 of 20"}',
            headers={"content-type": "application/json"},
        ),
        _Response(body=payload, headers={"content-type": "application/zip"}),
    )
    dest = tmp_path / "pv.zip"

    result = uspto.download_odp_file("PVGPATDIS/g_patent.tsv.zip", "key", dest, session)

    assert dest.read_bytes() == payload
    assert result["size"] == len(payload)
    # The trailing sentence punctuation must not be taken as part of the URL.
    assert session.calls[1][0] == "https://cf.uspto.gov/signed.zip?sig=abc"


def test_odp_file_rejects_an_html_response_as_a_key_problem(tmp_path):
    session = _Session(_Response(body=b"<html>", headers={"content-type": "text/html"}))

    with pytest.raises(ValueError, match=uspto.API_KEY_ENV_VAR):
        uspto.download_odp_file("PVGPATDIS/g_patent.tsv.zip", "bad", tmp_path / "x.zip", session)


def test_odp_file_chases_a_mint_message_served_with_a_binary_content_type(tmp_path):
    """A short non-ZIP body carrying a URL is a mint message, not the file."""
    payload = ZIP_MAGIC + b"archive"
    session = _Session(
        _Response(
            body=b'{"url": "https://cf.uspto.gov/signed.zip?sig=abc"}',
            headers={"content-type": "application/octet-stream"},
        ),
        _Response(body=payload, headers={"content-type": "application/zip"}),
    )
    dest = tmp_path / "pv.zip"

    result = uspto.download_odp_file("PVGPATDIS/g_patent.tsv.zip", "key", dest, session)

    assert dest.read_bytes() == payload
    assert result["size"] == len(payload)


def test_odp_file_raises_when_a_mint_message_carries_no_url(tmp_path):
    session = _Session(
        _Response(
            text='{"message": "quota exceeded"}', headers={"content-type": "application/json"}
        )
    )

    with pytest.raises(ValueError, match="no presigned URL"):
        uspto.download_odp_file("PVGPATDIS/g.zip", "key", tmp_path / "x.zip", session)


def test_patentsview_tables_are_declared_for_the_product_the_op_requests():
    """The op builds `PATENTSVIEW_PRODUCT/PATENTSVIEW_TABLES['patent']`."""
    assert "patent" in uspto.PATENTSVIEW_TABLES
    assert uspto.PATENTSVIEW_PRODUCT
    assert Path(uspto.DEFAULT_LOCAL_DIR).parts[:2] == ("data", "raw")
