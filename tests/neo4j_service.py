"""Lazy singleton that provides a Neo4j connection for integration tests.

Resolution order:
1. Try connecting to an existing Neo4j instance (env vars or localhost defaults).
2. If that fails, spin up a disposable Neo4j via testcontainers.
3. If *that* fails and REQUIRE_NEO4J is set (CI), raise immediately so the
   test run errors out instead of silently skipping.

The module exposes ``get_neo4j_service()`` which returns a ``Neo4jServiceInfo``
on success or ``None`` on failure.  Connection details are also written into
``os.environ`` so that downstream fixtures (``neo4j_config``, ``neo4j_driver``,
etc.) that read env vars pick them up automatically.
"""

from __future__ import annotations

import atexit
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger


# Neo4j opens its bolt port before the auth subsystem is ready. Early connects
# fail with Unauthorized and, after a few failures, the server rate-limits auth
# (Neo.ClientError.Security.AuthenticationRateLimit) — rejecting even the
# correct credentials until a short cooldown elapses. Both clear on their own,
# so retry them with exponential backoff. A genuine "no server" error
# (ServiceUnavailable) is NOT treated as transient, so local runs without Neo4j
# fall back to testcontainers immediately instead of waiting out the retries.
_AUTH_RETRY_ATTEMPTS = 8
_AUTH_RETRY_MAX_DELAY = 10.0


def _is_transient_auth_error(exc: BaseException) -> bool:
    from neo4j.exceptions import AuthError, ClientError

    if isinstance(exc, AuthError):
        return True
    if isinstance(exc, ClientError):
        return "AuthenticationRateLimit" in (getattr(exc, "code", "") or "")
    return False


def connect_with_retry(connect: Callable[[], Any]) -> Any:
    """Run ``connect`` (returns a verified driver), retrying transient Neo4j
    auth / rate-limit errors with exponential backoff.

    Re-raises immediately for non-transient failures, and re-raises the last
    transient error once the retries are exhausted.
    """
    last_exc: BaseException | None = None
    for attempt in range(_AUTH_RETRY_ATTEMPTS):
        try:
            return connect()
        except Exception as exc:
            if not _is_transient_auth_error(exc):
                raise
            last_exc = exc
            delay = min(2.0 * (2**attempt), _AUTH_RETRY_MAX_DELAY)
            logger.warning(
                "Neo4j auth not ready (attempt {}/{}): {}; retrying in {:.0f}s",
                attempt + 1,
                _AUTH_RETRY_ATTEMPTS,
                exc,
                delay,
            )
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc


@dataclass(frozen=True)
class Neo4jServiceInfo:
    uri: str
    username: str
    password: str


_service: Neo4jServiceInfo | None = None
_container = None  # testcontainers instance, if we started one
_resolved = False  # ensures we only attempt resolution once


def _try_existing_instance() -> Neo4jServiceInfo | None:
    """Connect to a pre-existing Neo4j (docker-compose, CI action, etc.)."""
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", os.getenv("NEO4J_USERNAME", "neo4j"))
    password = os.getenv("NEO4J_PASSWORD", "password")

    try:
        from neo4j import GraphDatabase

        def _connect() -> Any:
            driver = GraphDatabase.driver(uri, auth=(user, password))
            try:
                driver.verify_connectivity()
            except Exception:
                driver.close()
                raise
            return driver

        driver = connect_with_retry(_connect)
        driver.close()
        logger.info("Connected to existing Neo4j at {}", uri)
        return Neo4jServiceInfo(uri=uri, username=user, password=password)
    except Exception:
        return None


def _try_testcontainer() -> Neo4jServiceInfo | None:
    """Start a disposable Neo4j via testcontainers."""
    global _container
    try:
        from testcontainers.neo4j import Neo4jContainer

        # Pin the password explicitly so it always matches what callers connect
        # with (neo4j/password), rather than parsing it back out of the
        # container env where a default mismatch could cause auth failures.
        password = "password"  # pragma: allowlist secret
        _container = Neo4jContainer("neo4j:5", password=password)
        _container.start()

        uri = _container.get_connection_url()

        logger.info("Started testcontainer Neo4j at {}", uri)
        return Neo4jServiceInfo(uri=uri, username="neo4j", password=password)
    except Exception as exc:
        logger.warning("Could not start Neo4j testcontainer: {}", exc)
        _container = None
        return None


def _publish_env(info: Neo4jServiceInfo) -> None:
    """Write connection details into env vars so existing fixtures pick them up."""
    os.environ["NEO4J_URI"] = info.uri
    os.environ["NEO4J_USER"] = info.username
    os.environ["NEO4J_USERNAME"] = info.username
    os.environ["NEO4J_PASSWORD"] = info.password


def get_neo4j_service() -> Neo4jServiceInfo | None:
    """Return Neo4j connection info, starting a container if necessary.

    Returns ``None`` only when Neo4j is genuinely unavailable *and*
    ``REQUIRE_NEO4J`` is not set.  When ``REQUIRE_NEO4J`` is truthy (CI),
    raises ``RuntimeError`` instead.
    """
    global _service, _resolved

    if _resolved:
        return _service

    _resolved = True

    # 1. Try existing instance
    _service = _try_existing_instance()

    # 2. Fall back to testcontainers
    if _service is None:
        _service = _try_testcontainer()

    # 3. Publish env vars for downstream fixtures
    if _service is not None:
        _publish_env(_service)

    # 4. CI enforcement
    if _service is None and os.getenv("REQUIRE_NEO4J"):
        raise RuntimeError(
            "REQUIRE_NEO4J is set but Neo4j could not be reached or started. "
            "Ensure Docker is available for testcontainers, or that the "
            "start-neo4j CI action ran successfully."
        )

    return _service


def stop_neo4j_service() -> None:
    """Stop the testcontainer if we started one."""
    global _container, _service, _resolved
    if _container is not None:
        try:
            _container.stop()
            logger.info("Stopped Neo4j testcontainer")
        except Exception as exc:
            logger.warning("Error stopping Neo4j testcontainer: {}", exc)
        _container = None
    _service = None
    _resolved = False


# Safety net: stop the container on interpreter exit even if pytest cleanup
# fixtures don't run (e.g. KeyboardInterrupt during collection).
atexit.register(stop_neo4j_service)
