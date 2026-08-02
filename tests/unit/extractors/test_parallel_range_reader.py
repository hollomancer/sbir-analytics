"""Offline integrity tests for bounded parallel HTTP range ZIP reads."""

import gzip
import io
import struct
import threading
import time
import zipfile
from collections.abc import Mapping
from typing import Any

import pytest

from sbir_etl.extractors.parallel_range_reader import (
    ParallelRangeTransportError,
    ParallelRangeValidationError,
    ValidatedParallelRangeFile,
    ValidatedParallelRemoteZip,
)


pytestmark = pytest.mark.fast

_CANONICAL = "https://canonical.example.test/archive.zip"
_REPLICA_ONE = "https://replica-one.example.test/archive.zip"
_REPLICA_TWO = "https://replica-two.example.test/archive.zip"
_ETAG = '"strong-archive-etag"'


class _Response:
    def __init__(
        self,
        *,
        status: int,
        headers: Mapping[str, str],
        body: bytes,
    ) -> None:
        self.status_code = status
        self.headers = dict(headers)
        self.raw = io.BytesIO(body)
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _RangeServer:
    """Small synchronous range server double safe for executor threads."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.etags: dict[str, str] = {}
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.completions: list[int] = []
        self.delays: dict[int, float] = {}
        self.active = 0
        self.peak_active = 0
        self.lock = threading.Lock()
        self.override: Any = None

    def __call__(self, url: str, headers: Mapping[str, str]) -> _Response:
        request_headers = dict(headers)
        start_text, end_text = request_headers["Range"].removeprefix("bytes=").split("-")
        start, end = int(start_text), int(end_text)
        with self.lock:
            self.calls.append((url, request_headers))
            self.active += 1
            self.peak_active = max(self.peak_active, self.active)
        try:
            if delay := self.delays.get(start, 0):
                time.sleep(delay)
            if self.override is not None:
                response = self.override(url, request_headers, start, end)
                if response is not None:
                    return response
            body = self.payload[start : end + 1]
            etag = self.etags.get(url, _ETAG)
            return _Response(
                status=206,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{len(self.payload)}",
                    "Content-Length": str(len(body)),
                    "Content-Encoding": "identity",
                    "ETag": etag,
                },
                body=body,
            )
        finally:
            with self.lock:
                self.active -= 1
                # Identity probes are not part of the parallel completion audit.
                if "If-Match" in request_headers and end > 0:
                    self.completions.append(start)


def _response(
    server: _RangeServer,
    *,
    start: int,
    end: int,
    status: int = 206,
    body: bytes | None = None,
    content_range: str | None = None,
    etag: str = _ETAG,
) -> _Response:
    data = server.payload[start : end + 1] if body is None else body
    return _Response(
        status=status,
        headers={
            "Content-Range": content_range or f"bytes {start}-{end}/{len(server.payload)}",
            "Content-Length": str(end - start + 1),
            "Content-Encoding": "identity",
            "ETag": etag,
        },
        body=data,
    )


def test_parallel_reads_stay_ordered_and_use_at_most_four_payload_slots() -> None:
    payload = bytes(range(32))
    server = _RangeServer(payload)
    server.delays = {0: 0.08, 8: 0.06, 16: 0.04, 24: 0.01}

    with ValidatedParallelRangeFile(
        _CANONICAL,
        (_REPLICA_ONE, _REPLICA_TWO),
        _chunk_size=8,
        _workers=4,
        _retry_backoff_seconds=0,
        _requester=server,
    ) as source:
        source.enable_parallel_prefetch()
        assert source.read() == payload
        assert source.peak_payload_slots == 4

    assert server.completions[0] == 24
    assert 2 <= server.peak_active <= 4
    data_calls = [headers for _, headers in server.calls if headers["Range"] != "bytes=0-0"]
    assert data_calls
    assert all(headers["If-Match"] == _ETAG for headers in data_calls)
    assert all(headers["Accept-Encoding"] == "identity" for headers in data_calls)


def test_range_file_seek_and_read_match_bytesio_oracle() -> None:
    payload = bytes(range(31))
    server = _RangeServer(payload)
    oracle = io.BytesIO(payload)

    with ValidatedParallelRangeFile(
        _CANONICAL,
        _chunk_size=5,
        _workers=3,
        _retry_backoff_seconds=0,
        _requester=server,
    ) as source:
        operations = (
            ("read", 3, None),
            ("seek", 9, io.SEEK_SET),
            ("read", 11, None),
            ("seek", -6, io.SEEK_CUR),
            ("read", 4, None),
            ("seek", -7, io.SEEK_END),
            ("read", -1, None),
            ("seek", 0, io.SEEK_SET),
            ("read", -1, None),
        )
        for operation, value, whence in operations:
            if operation == "read":
                assert source.read(value) == oracle.read(value)
            else:
                assert source.seek(value, whence) == oracle.seek(value, whence)
            assert source.tell() == oracle.tell()


def test_truncated_range_retries_on_another_validated_replica() -> None:
    server = _RangeServer(b"abcdefgh")
    attempts: list[str] = []

    def truncate_once(url: str, headers: Mapping[str, str], start: int, end: int):
        if headers["Range"] == "bytes=0-3":
            attempts.append(url)
            if len(attempts) == 1:
                return _response(server, start=start, end=end, body=b"abc")
        return None

    server.override = truncate_once
    with ValidatedParallelRangeFile(
        _CANONICAL,
        (_REPLICA_ONE, _REPLICA_TWO),
        _chunk_size=4,
        _workers=1,
        _attempts=2,
        _retry_backoff_seconds=0,
        _requester=server,
    ) as source:
        assert source.read(4) == b"abcd"

    assert attempts == [_REPLICA_ONE, _REPLICA_TWO]


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        (
            lambda server, start, end: _response(
                server,
                start=start,
                end=end,
                content_range=f"bytes {start + 1}-{end}/{len(server.payload)}",
            ),
            "Content-Range",
        ),
        (
            lambda server, start, end: _response(
                server,
                start=start,
                end=end,
                etag='"different-etag"',
            ),
            "identity differs",
        ),
        (
            lambda server, start, end: _response(
                server,
                start=start,
                end=end,
                status=302,
            ),
            "exact 206 required",
        ),
    ],
)
def test_integrity_or_redirect_failures_are_terminal_without_replica_retry(
    replacement,
    message: str,
) -> None:
    server = _RangeServer(b"abcdefgh")
    data_calls = 0

    def invalid_data(url: str, headers: Mapping[str, str], start: int, end: int):
        nonlocal data_calls
        if headers["Range"] != "bytes=0-0":
            data_calls += 1
            return replacement(server, start, end)
        return None

    server.override = invalid_data
    with ValidatedParallelRangeFile(
        _CANONICAL,
        (_REPLICA_ONE, _REPLICA_TWO),
        _chunk_size=4,
        _workers=1,
        _attempts=3,
        _retry_backoff_seconds=0,
        _requester=server,
    ) as source:
        with pytest.raises(ParallelRangeValidationError, match=message):
            source.read(4)

    assert data_calls == 1


def test_replica_probe_requires_the_canonical_strong_identity() -> None:
    server = _RangeServer(b"abcdefgh")
    server.etags[_REPLICA_TWO] = '"stale-replica"'

    with pytest.raises(ParallelRangeValidationError, match="identity differs"):
        ValidatedParallelRangeFile(
            _CANONICAL,
            (_REPLICA_ONE, _REPLICA_TWO),
            _chunk_size=4,
            _requester=server,
        )


def test_replica_probe_requires_the_same_first_byte_under_matching_identity() -> None:
    server = _RangeServer(b"abcdefgh")

    def wrong_probe_byte(url: str, headers: Mapping[str, str], start: int, end: int):
        if url == _REPLICA_TWO and headers["Range"] == "bytes=0-0":
            return _response(server, start=start, end=end, body=b"z")
        return None

    server.override = wrong_probe_byte
    with pytest.raises(ParallelRangeValidationError, match="probe byte differs"):
        ValidatedParallelRangeFile(
            _CANONICAL,
            (_REPLICA_ONE, _REPLICA_TWO),
            _chunk_size=4,
            _requester=server,
        )


def test_canonical_redirect_to_even_an_explicit_replica_fails_closed() -> None:
    server = _RangeServer(b"abcdefgh")

    def canonical_redirect(url: str, headers: Mapping[str, str], start: int, end: int):
        if url != _CANONICAL:
            return None
        response = _response(server, start=start, end=end, status=302)
        response.headers["Location"] = _REPLICA_TWO
        return response

    server.override = canonical_redirect
    with pytest.raises(ParallelRangeValidationError, match="exact 206 required"):
        ValidatedParallelRangeFile(
            _CANONICAL,
            (_REPLICA_ONE, _REPLICA_TWO),
            _chunk_size=4,
            _workers=2,
            _retry_backoff_seconds=0,
            _requester=server,
        )

    assert [url for url, _ in server.calls] == [_CANONICAL]


def test_canonical_redirect_to_unlisted_url_fails_closed() -> None:
    server = _RangeServer(b"abcdefgh")

    def unlisted_redirect(url: str, headers: Mapping[str, str], start: int, end: int):
        response = _response(server, start=start, end=end, status=302)
        response.headers["Location"] = "https://unlisted.example.test/archive.zip"
        return response

    server.override = unlisted_redirect
    with pytest.raises(ParallelRangeValidationError, match="exact 206 required"):
        ValidatedParallelRangeFile(
            _CANONICAL,
            (_REPLICA_ONE, _REPLICA_TWO),
            _requester=server,
        )


def test_exhausted_short_body_retry_fails_closed() -> None:
    server = _RangeServer(b"abcdefgh")

    def always_short(url: str, headers: Mapping[str, str], start: int, end: int):
        if headers["Range"] != "bytes=0-0":
            return _response(server, start=start, end=end, body=b"")
        return None

    server.override = always_short
    with ValidatedParallelRangeFile(
        _CANONICAL,
        (_REPLICA_ONE,),
        _chunk_size=4,
        _workers=1,
        _attempts=2,
        _retry_backoff_seconds=0,
        _requester=server,
    ) as source:
        with pytest.raises(ParallelRangeTransportError, match="failed after 2 attempts"):
            source.read(4)


def test_unused_prefetch_failure_is_sticky_and_blocks_success() -> None:
    server = _RangeServer(b"abcdefgh")

    def bad_lookahead(url: str, headers: Mapping[str, str], start: int, end: int):
        if start == 4:
            return _response(server, start=start, end=end, etag='"bad-lookahead"')
        return None

    server.override = bad_lookahead
    with ValidatedParallelRangeFile(
        _CANONICAL,
        (_REPLICA_ONE,),
        _chunk_size=4,
        _workers=2,
        _retry_backoff_seconds=0,
        _requester=server,
    ) as source:
        source.enable_parallel_prefetch()
        assert source.read(4) == b"abcd"
        with pytest.raises(ParallelRangeValidationError, match="identity differs"):
            source.validate_pending()


def test_close_interrupts_a_blocked_active_response_before_waiting_for_workers() -> None:
    server = _RangeServer(b"abcdefgh")
    started = threading.Event()
    released = threading.Event()

    class _BlockingRaw:
        decode_content = False

        @staticmethod
        def read(size: int, decode_content: bool = False) -> bytes:
            started.set()
            if not released.wait(5):
                raise TimeoutError("test response was not interrupted")
            raise OSError("response closed")

    class _BlockingResponse(_Response):
        def __init__(self, start: int, end: int) -> None:
            super().__init__(
                status=206,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{len(server.payload)}",
                    "Content-Length": str(end - start + 1),
                    "Content-Encoding": "identity",
                    "ETag": _ETAG,
                },
                body=b"",
            )
            self.raw = _BlockingRaw()

        def close(self) -> None:
            released.set()
            super().close()

    def block_data(url: str, headers: Mapping[str, str], start: int, end: int):
        if headers["Range"] != "bytes=0-0":
            return _BlockingResponse(start, end)
        return None

    server.override = block_data
    source = ValidatedParallelRangeFile(
        _CANONICAL,
        (_REPLICA_ONE,),
        _chunk_size=4,
        _workers=1,
        _attempts=1,
        _retry_backoff_seconds=0,
        _requester=server,
    )
    errors: list[BaseException] = []

    def consume() -> None:
        try:
            source.read(4)
        except BaseException as error:
            errors.append(error)

    consumer = threading.Thread(target=consume)
    consumer.start()
    assert started.wait(1)

    before = time.monotonic()
    source.close()
    elapsed = time.monotonic() - before
    consumer.join(1)

    assert elapsed < 1
    assert not consumer.is_alive()
    assert errors and isinstance(errors[0], ParallelRangeTransportError)


def _zip_payload(member: bytes) -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("archive/member.dat.gz", member)
    return target.getvalue()


def test_zip_extfile_eof_validates_outer_crc() -> None:
    archive_bytes = bytearray(_zip_payload(gzip.compress(b"complete inner gzip")))
    central_directory = archive_bytes.index(b"PK\x01\x02")
    original_crc = struct.unpack_from("<I", archive_bytes, central_directory + 16)[0]
    struct.pack_into("<I", archive_bytes, central_directory + 16, original_crc ^ 0xFFFFFFFF)
    server = _RangeServer(bytes(archive_bytes))

    with ValidatedParallelRemoteZip(
        _CANONICAL,
        _range_file_kwargs={
            "_chunk_size": 16,
            "_workers": 4,
            "_retry_backoff_seconds": 0,
            "_requester": server,
        },
    ) as archive:
        info = archive.getinfo("archive/member.dat.gz")
        with archive.open(info) as member:
            with pytest.raises(zipfile.BadZipFile, match="Bad CRC-32"):
                while member.read(7):
                    pass


def test_inner_gzip_must_reach_a_valid_eof() -> None:
    server = _RangeServer(_zip_payload(b"not a gzip stream"))

    with ValidatedParallelRemoteZip(
        _CANONICAL,
        _range_file_kwargs={
            "_chunk_size": 16,
            "_workers": 4,
            "_retry_backoff_seconds": 0,
            "_requester": server,
        },
    ) as archive:
        info = archive.getinfo("archive/member.dat.gz")
        with archive.open(info) as member, gzip.GzipFile(fileobj=member) as inner:
            with pytest.raises(gzip.BadGzipFile):
                inner.read()
