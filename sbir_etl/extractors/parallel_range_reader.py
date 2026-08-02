"""Bounded, identity-checked parallel HTTP ranges for remote ZIP archives."""

import io
import re
import threading
import zipfile
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit


DEFAULT_CHUNK_SIZE = 32 * 1024 * 1024
DEFAULT_WORKERS = 4
DEFAULT_ATTEMPTS = 3
_TRANSIENT_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
_CONTENT_RANGE_RE = re.compile(r"bytes\s+(\d+)-(\d+)/(\d+)", re.IGNORECASE)


class ParallelRangeError(OSError):
    """A remote archive cannot be read without weakening an integrity invariant."""


class ParallelRangeTransportError(ParallelRangeError):
    """A transient request failure that may be retried for the exact same range."""


class ParallelRangeValidationError(ParallelRangeError):
    """A response does not prove that it contains the requested archive bytes."""


@dataclass(frozen=True)
class RemoteArchiveIdentity:
    """Strong identity shared by the canonical URL and every explicit replica."""

    etag: str
    total_bytes: int


class ValidatedParallelRangeFile(io.IOBase):
    """Seekable HTTP range file with one bounded foreground/prefetch window.

    The canonical URL is always probed. Explicit replicas are eligible for data
    requests only after a one-byte response proves the same strong ETag and total
    byte length. Metadata reads use a one-chunk window; callers explicitly enable
    parallel lookahead only when beginning the selected large member.
    """

    def __init__(
        self,
        canonical_url: str,
        replica_urls: Sequence[str] = (),
        *,
        _chunk_size: int = DEFAULT_CHUNK_SIZE,
        _workers: int = DEFAULT_WORKERS,
        _attempts: int = DEFAULT_ATTEMPTS,
        _retry_backoff_seconds: float = 0.25,
        _requester: Callable[[str, Mapping[str, str]], Any] | None = None,
    ) -> None:
        super().__init__()
        if _chunk_size <= 0:
            raise ValueError("chunk size must be greater than zero")
        if not 1 <= _workers <= 4:
            raise ValueError("parallel range workers must be between one and four")
        if _attempts <= 0:
            raise ValueError("range request attempts must be greater than zero")

        self._canonical_url = self._validated_url(canonical_url)
        replicas = tuple(self._validated_url(url) for url in replica_urls)
        self._replica_urls = tuple(
            url for index, url in enumerate(replicas) if url not in replicas[:index]
        )
        self._chunk_size = _chunk_size
        self._workers = _workers
        self._attempts = _attempts
        self._retry_backoff_seconds = _retry_backoff_seconds
        self._requester = requester = _requester or self._request_http
        self._sessions: list[Any] = []
        self._sessions_lock = threading.Lock()
        self._thread_state = threading.local()
        self._executor: ThreadPoolExecutor | None = None
        self._pending: dict[int, Future[bytes]] = {}
        self._cache: dict[int, bytes] = {}
        self._fatal_error: ParallelRangeError | None = None
        self._fatal_error_lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._active_responses: dict[int, Any] = {}
        self._active_responses_lock = threading.Lock()
        self._position = 0
        self._prefetch_enabled = False
        self._peak_payload_slots = 0

        try:
            canonical_byte, identity = self._fetch_once(
                self._canonical_url,
                0,
                0,
                expected_identity=None,
                requester=requester,
            )
            for replica_url in self._replica_urls:
                replica_byte, _ = self._fetch_once(
                    replica_url,
                    0,
                    0,
                    expected_identity=identity,
                    requester=requester,
                )
                if replica_byte != canonical_byte:
                    raise ParallelRangeValidationError(
                        "Replica probe byte differs from the canonical archive"
                    )
        except BaseException:
            self._close_sessions()
            raise

        self.identity = identity
        # Explicit replicas are the requested data plane; the direct canonical
        # endpoint remains the identity anchor.
        self._data_urls = self._replica_urls or (self._canonical_url,)
        self._chunk_count = (identity.total_bytes + _chunk_size - 1) // _chunk_size
        self._executor = ThreadPoolExecutor(
            max_workers=_workers,
            thread_name_prefix="validated-range",
        )

    @staticmethod
    def _validated_url(url: str) -> str:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError("parallel range URLs must be credential-free https URLs")
        return url

    @property
    def canonical_url(self) -> str:
        return self._canonical_url

    @property
    def replica_urls(self) -> tuple[str, ...]:
        return self._replica_urls

    @property
    def chunk_size(self) -> int:
        return self._chunk_size

    @property
    def workers(self) -> int:
        return self._workers

    @property
    def peak_payload_slots(self) -> int:
        """Largest active/completed/cache payload window observed (for audits/tests)."""

        return self._peak_payload_slots

    def enable_parallel_prefetch(self) -> None:
        """Enable bounded lookahead after archive metadata selects the large member."""

        self._checkClosed()
        self._prefetch_enabled = True

    def _session_for_thread(self) -> Any:
        session = getattr(self._thread_state, "session", None)
        if session is None:
            import requests

            session = requests.Session()
            self._thread_state.session = session
            with self._sessions_lock:
                self._sessions.append(session)
        return session

    def _request_http(self, url: str, headers: Mapping[str, str]) -> Any:
        """Issue one non-redirecting raw response; validation reads the bounded body."""

        if self._cancel_event.is_set():
            raise ParallelRangeTransportError("Parallel range reader is closing")
        session = self._session_for_thread()
        if self._cancel_event.is_set():
            session.close()
            raise ParallelRangeTransportError("Parallel range reader is closing")
        try:
            return session.get(
                url,
                headers=dict(headers),
                stream=True,
                allow_redirects=False,
                timeout=(30, 180),
            )
        except Exception as error:
            raise ParallelRangeTransportError(f"HTTP range request failed: {error}") from error

    @staticmethod
    def _normalized_headers(response: Any) -> dict[str, str]:
        try:
            return {str(key).lower(): str(value).strip() for key, value in response.headers.items()}
        except Exception as error:
            raise ParallelRangeValidationError("Range response has unreadable headers") from error

    def _fetch_once(
        self,
        url: str,
        start: int,
        end: int,
        *,
        expected_identity: RemoteArchiveIdentity | None,
        requester: Callable[[str, Mapping[str, str]], Any],
    ) -> tuple[bytes, RemoteArchiveIdentity]:
        headers = {
            "Accept-Encoding": "identity",
            "Range": f"bytes={start}-{end}",
            "User-Agent": "sbir-analytics-validated-range/1",
        }
        if expected_identity is not None:
            headers["If-Match"] = expected_identity.etag

        try:
            response = requester(url, headers)
        except ParallelRangeError:
            raise
        except Exception as error:
            raise ParallelRangeTransportError(f"HTTP range request failed: {error}") from error

        with self._active_responses_lock:
            cancelled = self._cancel_event.is_set()
            if not cancelled:
                self._active_responses[id(response)] = response
        if cancelled:
            try:
                response.close()
            except Exception:
                pass
            raise ParallelRangeTransportError("Parallel range reader closed during request")

        try:
            status = int(response.status_code)
            if status in _TRANSIENT_HTTP_STATUSES:
                raise ParallelRangeTransportError(
                    f"Range endpoint returned transient HTTP {status}"
                )
            if status == 412:
                raise ParallelRangeValidationError("Range endpoint rejected the archive If-Match")
            if status != 206:
                raise ParallelRangeValidationError(
                    f"Range endpoint returned HTTP {status}; exact 206 required"
                )

            response_headers = self._normalized_headers(response)
            content_encoding = response_headers.get("content-encoding", "identity").lower()
            if content_encoding != "identity":
                raise ParallelRangeValidationError(
                    f"Range endpoint used forbidden Content-Encoding {content_encoding!r}"
                )

            content_range = response_headers.get("content-range", "")
            match = _CONTENT_RANGE_RE.fullmatch(content_range)
            if match is None:
                raise ParallelRangeValidationError("Range response has invalid Content-Range")
            actual_start, actual_end, total_bytes = (int(value) for value in match.groups())
            if (actual_start, actual_end) != (start, end):
                raise ParallelRangeValidationError(
                    "Range response Content-Range does not match the exact requested bytes"
                )
            if total_bytes <= end:
                raise ParallelRangeValidationError("Range response has an invalid total byte size")

            etag = response_headers.get("etag", "")
            if len(etag) < 2 or not etag.startswith('"') or not etag.endswith('"'):
                raise ParallelRangeValidationError("Range response has no strong quoted ETag")
            if etag[:2].lower() == "w/":
                raise ParallelRangeValidationError("Weak ETags cannot identify a remote archive")

            identity = RemoteArchiveIdentity(etag=etag, total_bytes=total_bytes)
            if expected_identity is not None and identity != expected_identity:
                raise ParallelRangeValidationError(
                    "Range response archive identity differs from the canonical source"
                )

            expected_bytes = end - start + 1
            content_length = response_headers.get("content-length", "")
            if not content_length.isdigit() or int(content_length) != expected_bytes:
                raise ParallelRangeValidationError(
                    "Range response Content-Length does not match the requested bytes"
                )

            raw = response.raw
            if hasattr(raw, "decode_content"):
                raw.decode_content = False
            try:
                body = raw.read(expected_bytes + 1, decode_content=False)
            except TypeError:
                # Minimal response doubles may implement only ``read(size)``.
                body = raw.read(expected_bytes + 1)
            except Exception as error:
                raise ParallelRangeTransportError(
                    f"Range response body terminated while reading: {error}"
                ) from error
            if not isinstance(body, bytes):
                body = bytes(body)
            if len(body) < expected_bytes:
                raise ParallelRangeTransportError(
                    f"Range response was truncated: expected {expected_bytes}, got {len(body)}"
                )
            if len(body) != expected_bytes:
                raise ParallelRangeValidationError(
                    "Range response exceeded its declared byte range"
                )
            return body, identity
        finally:
            try:
                response.close()
            except Exception:
                pass
            finally:
                with self._active_responses_lock:
                    self._active_responses.pop(id(response), None)

    def _fetch_chunk(self, chunk_index: int) -> bytes:
        start = chunk_index * self._chunk_size
        end = min(self.identity.total_bytes, start + self._chunk_size) - 1
        transport_errors: list[str] = []
        for attempt in range(self._attempts):
            if self._cancel_event.is_set():
                raise ParallelRangeTransportError("Parallel range reader is closing")
            url = self._data_urls[(chunk_index + attempt) % len(self._data_urls)]
            try:
                body, _ = self._fetch_once(
                    url,
                    start,
                    end,
                    expected_identity=self.identity,
                    requester=self._requester,
                )
                return body
            except ParallelRangeValidationError:
                # Identity/header violations poison this run; mixing in another
                # endpoint after one cannot prove the same object is not allowed.
                raise
            except ParallelRangeTransportError as error:
                transport_errors.append(f"{url}: {error}")
                if attempt + 1 < self._attempts and self._retry_backoff_seconds:
                    if self._cancel_event.wait(self._retry_backoff_seconds * (2**attempt)):
                        raise ParallelRangeTransportError(
                            "Parallel range reader closed during retry backoff"
                        ) from error
        detail = "; ".join(transport_errors)
        raise ParallelRangeTransportError(
            f"Exact range {start}-{end} failed after {self._attempts} attempts: {detail}"
        )

    def _payload_slots(self) -> int:
        # A Future is one payload slot whether its worker is active or its result
        # is complete. Moving the same bytes object into cache never adds a slot.
        return len(self._pending) + len(self._cache)

    def _remember_future_error(self, future: Future[bytes]) -> None:
        """Make every scheduled range failure terminal, including stale lookahead."""

        try:
            error = future.exception()
        except CancelledError:
            return
        if not isinstance(error, ParallelRangeError):
            return
        self._remember_error(error)

    def _remember_error(self, error: ParallelRangeError) -> None:
        with self._fatal_error_lock:
            if self._fatal_error is None:
                self._fatal_error = error

    def _raise_fatal_error(self) -> None:
        with self._fatal_error_lock:
            error = self._fatal_error
        if error is not None:
            raise error

    def _observe_slots(self) -> None:
        self._peak_payload_slots = max(self._peak_payload_slots, self._payload_slots())
        if self._payload_slots() > self._workers:  # pragma: no cover - invariant guard
            raise ParallelRangeError("Parallel range payload window exceeded its worker bound")

    def _desired_chunks(self, current_index: int) -> tuple[int, ...]:
        width = self._workers if self._prefetch_enabled else 1
        return tuple(range(current_index, min(self._chunk_count, current_index + width)))

    def _drop_stale(self, desired: set[int]) -> None:
        for chunk_index in tuple(self._cache):
            if chunk_index not in desired:
                self._cache.pop(chunk_index)
        for chunk_index, future in tuple(self._pending.items()):
            if chunk_index in desired:
                continue
            if future.cancel():
                self._pending.pop(chunk_index)
                continue
            # A running stale request still owns a payload slot. Wait for it and
            # discard it before scheduling the new seek target, preserving the
            # one-window memory bound and preventing stale lookahead starvation.
            self._pending.pop(chunk_index)
            try:
                future.result()
            except ParallelRangeError as error:
                self._remember_error(error)
        self._observe_slots()
        self._raise_fatal_error()

    def _schedule_window(self, current_index: int) -> None:
        self._raise_fatal_error()
        desired = self._desired_chunks(current_index)
        desired_set = set(desired)
        self._drop_stale(desired_set)
        executor = self._executor
        if executor is None:  # pragma: no cover - closed-object guard
            raise ValueError("I/O operation on closed parallel range file")
        for chunk_index in desired:
            if chunk_index in self._cache or chunk_index in self._pending:
                continue
            if self._payload_slots() >= self._workers:  # pragma: no cover - invariant guard
                raise ParallelRangeError("No bounded payload slot available for requested chunk")
            future = executor.submit(self._fetch_chunk, chunk_index)
            self._pending[chunk_index] = future
            future.add_done_callback(self._remember_future_error)
            self._observe_slots()

    def _chunk(self, chunk_index: int) -> bytes:
        self._schedule_window(chunk_index)
        if chunk_index in self._cache:
            return self._cache[chunk_index]
        future = self._pending.pop(chunk_index)
        try:
            payload = future.result()
        except BaseException:
            self._drop_stale(set())
            raise
        self._cache[chunk_index] = payload
        self._observe_slots()
        return payload

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        self._checkClosed()
        self._raise_fatal_error()
        return self._position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        self._checkClosed()
        self._raise_fatal_error()
        if whence == io.SEEK_SET:
            position = offset
        elif whence == io.SEEK_CUR:
            position = self._position + offset
        elif whence == io.SEEK_END:
            position = self.identity.total_bytes + offset
        else:
            raise ValueError(f"Unsupported seek mode: {whence}")
        if position < 0:
            raise ValueError("Negative seek position")
        self._position = position
        if position < self.identity.total_bytes:
            self._drop_stale(set(self._desired_chunks(position // self._chunk_size)))
        else:
            self._drop_stale(set())
        return position

    def read(self, size: int = -1) -> bytes:
        self._checkClosed()
        self._raise_fatal_error()
        if size == 0 or self._position >= self.identity.total_bytes:
            return b""
        if size is None or size < 0:
            size = self.identity.total_bytes - self._position
        end_position = min(self.identity.total_bytes, self._position + size)
        cursor = self._position
        pieces: list[bytes] = []
        while cursor < end_position:
            chunk_index = cursor // self._chunk_size
            chunk = self._chunk(chunk_index)
            chunk_offset = cursor - (chunk_index * self._chunk_size)
            piece_size = min(end_position - cursor, len(chunk) - chunk_offset)
            if piece_size <= 0:  # pragma: no cover - validated response invariant
                raise ParallelRangeError("Validated range chunk cannot satisfy requested position")
            pieces.append(chunk[chunk_offset : chunk_offset + piece_size])
            cursor += piece_size
        self._position = end_position
        if self._position < self.identity.total_bytes:
            self._schedule_window(self._position // self._chunk_size)
        else:
            self._drop_stale(set())
        return b"".join(pieces)

    def readinto(self, buffer: Any) -> int:
        data = self.read(len(buffer))
        buffer[: len(data)] = data
        return len(data)

    def validate_pending(self) -> None:
        """Wait for every scheduled payload and surface any prefetch failure."""

        self._checkClosed()
        for future in tuple(self._pending.values()):
            try:
                future.result()
            except ParallelRangeError as error:
                self._remember_error(error)
        self._raise_fatal_error()

    def _close_sessions(self) -> None:
        with self._sessions_lock:
            sessions, self._sessions = self._sessions, []
        for session in sessions:
            try:
                session.close()
            except Exception:
                pass

    def close(self) -> None:
        if self.closed:
            return
        self._cancel_event.set()
        with self._active_responses_lock:
            active_responses = tuple(self._active_responses.values())
        for response in active_responses:
            try:
                response.close()
            except Exception:
                pass
        # Closing sessions before waiting on workers interrupts active sockets
        # instead of allowing shutdown to inherit the full request read timeout.
        self._close_sessions()
        executor, self._executor = self._executor, None
        if executor is not None:
            for future in self._pending.values():
                future.cancel()
            executor.shutdown(wait=True, cancel_futures=True)
        self._pending.clear()
        self._cache.clear()
        super().close()


class ValidatedParallelRemoteZip(zipfile.ZipFile):
    """A ``ZipFile`` backed by :class:`ValidatedParallelRangeFile`."""

    def __init__(
        self,
        canonical_url: str,
        replica_urls: Sequence[str] = (),
        *,
        _range_file_kwargs: Mapping[str, Any] | None = None,
    ) -> None:
        self.range_file = ValidatedParallelRangeFile(
            canonical_url,
            replica_urls,
            **dict(_range_file_kwargs or {}),
        )
        try:
            super().__init__(self.range_file, mode="r")
        except BaseException:
            self.range_file.close()
            raise

    @property
    def identity(self) -> RemoteArchiveIdentity:
        return self.range_file.identity

    def enable_parallel_prefetch(self) -> None:
        self.range_file.enable_parallel_prefetch()

    def close(self) -> None:
        try:
            super().close()
        finally:
            range_file = getattr(self, "range_file", None)
            if range_file is not None:
                range_file.close()
