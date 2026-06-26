# Enricher consolidation: BaseAsyncAPIClient migration

Status as of 2026-04-13 · see branch `claude/repo-analysis-AYGBQ`

Short version: **8 of 10 enricher clients** now inherit from
`sbir_etl.enrichers.base_client.BaseAsyncAPIClient`, sharing a single
implementation of retry, rate limiting, and typed error translation.
Two clients remain bespoke on purpose. This doc records the pattern,
the gotchas, and how to finish the remaining two if and when the
timing is right.

## Why this exists

Before the migration, each sync enricher client (`lens_patents`,
`orcid_client`, `opencorporates`, `fpds_atom`, `press_wire`,
`semantic_scholar`, `patentsview`, `openai_client`) had its own:

- `_get_with_retry` / `_post_with_retry` / `_request` / `_fetch_feed`
  — a hand-rolled `for attempt in range(MAX_RETRIES):` loop with
  `time.sleep(RETRY_BACKOFF_BASE ** (attempt + 1))`
- Manual `if resp.status_code == 429 or resp.status_code >= 500: ...`
  retry detection
- `rate_limiter: Any | None = None` parameter, typed as `Any` because
  the ORCID/PatentsView/etc. clients each duck-typed the limiter
- `try/except (ValueError, Exception)` swallow-all error handling
  returning `None` on every failure — no way for callers to
  distinguish "not found" from "server died"

The duplication wasn't identical (each copy was slightly different,
with its own subtle bugs) so it couldn't be fixed by a single shared
helper function. The right fix was inheritance: make every sync client
an async client behind a sync facade, so all the shared infrastructure
lives in `BaseAsyncAPIClient` once.

## Current state (8 of 10)

| Client | Base class | Sync facade | Tests |
|---|---|---|---|
| `usaspending.client.USAspendingAPIClient` | ✅ `BaseAsyncAPIClient` | `SyncUSAspendingClient` | pre-existing |
| `sam_gov.client.SAMGovAPIClient` | ✅ `BaseAsyncAPIClient` | `SyncSAMGovClient` | pre-existing |
| `semantic_scholar.SemanticScholarClient` | ✅ `BaseAsyncAPIClient` | `SyncSemanticScholarClient` | 24 |
| `fpds_atom.FPDSAtomClient` | ✅ `BaseAsyncAPIClient` | `SyncFPDSAtomClient` | 35 |
| `orcid_client.ORCIDClient` | ✅ `BaseAsyncAPIClient` | `SyncORCIDClient` | 28 |
| `opencorporates.OpenCorporatesClient` | ✅ `BaseAsyncAPIClient` | `SyncOpenCorporatesClient` | 21 |
| `press_wire.PressWireClient` | ✅ `BaseAsyncAPIClient` | `SyncPressWireClient` | 25 |
| `lens_patents.LensPatentClient` | ✅ `BaseAsyncAPIClient` | `SyncLensPatentClient` | 31 |
| `openai_client.OpenAIClient` | ❌ bespoke (by design — see below) | none | 7 |
| `patentsview.PatentsViewClient` | ❌ bespoke (deferred — see below) | none | 17 |

Every migrated client now has:

1. **Tenacity-backed retry** with exponential backoff, typed
   `APIError` / `RateLimitError` on exhaustion.
2. **Shared sliding-window rate limiting** via the base class's
   internal `request_times` deque, OR an injected shared
   `RateLimiter` for cross-thread budget sharing (see
   "asyncio.to_thread pattern" below).
3. **Sync facade** in `sync_wrappers.py` routing through `run_sync`,
   so scripts and Dagster ops call the client without an event loop.
4. **Structured error propagation**: 5xx raises, 404 / "not found"
   returns `None`, so callers can actually tell the two apart.
5. **Typed `APIError`** with `api_name`, `endpoint`, `http_status`,
   `retryable` fields — replacing `return None` on unknowable failures.

## The migration template

Use this template for any new client, or if you come back to finish
OpenAI / PatentsView.

### 1. Rewrite the client as an async subclass

```python
# sbir_etl/enrichers/<name>.py
from sbir_etl.enrichers.base_client import BaseAsyncAPIClient
from sbir_etl.enrichers.rate_limiting import RateLimiter
from sbir_etl.exceptions import APIError

class FooClient(BaseAsyncAPIClient):
    api_name = "foo"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: int = 30,
        rate_limit_per_minute: int = 60,
        shared_limiter: RateLimiter | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__()
        self.base_url = "https://api.foo.example.com/v1"
        self.rate_limit_per_minute = rate_limit_per_minute
        self._shared_limiter = shared_limiter
        self._api_key = api_key or os.environ.get("FOO_API_KEY", "")
        self._client = http_client or httpx.AsyncClient(timeout=timeout)

    def _build_headers(self) -> dict[str, str]:
        # Override for auth header injection
        headers = super()._build_headers()
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def _wait_for_rate_limit(self) -> None:
        # Override to honor an injected shared limiter — see gotcha #1
        if self._shared_limiter is not None:
            await asyncio.to_thread(self._shared_limiter.wait_if_needed)
            return
        await super()._wait_for_rate_limit()

    async def lookup(self, key: str) -> FooRecord | None:
        # High-level method — preserve the "not found → None" contract
        # at the public API but let APIError propagate for real failures.
        try:
            data = await self._make_request("GET", f"items/{key}")
        except APIError as e:
            if e.details.get("http_status") == 404:
                return None
            raise
        return FooRecord.from_json(data)
```

### 2. Add a sync facade

```python
# sbir_etl/enrichers/sync_wrappers.py
class SyncFooClient:
    def __init__(self, **kwargs) -> None:
        self._client = FooClient(**kwargs)

    def close(self) -> None:
        run_sync(self._client.aclose())

    def __enter__(self) -> SyncFooClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def lookup(self, key: str) -> FooRecord | None:
        return run_sync(self._client.lookup(key))
```

### 3. Update callers

- Replace `from sbir_etl.enrichers.foo import FooClient` with
  `from sbir_etl.enrichers.sync_wrappers import SyncFooClient`.
- If the caller passes `rate_limiter=`, rename to `shared_limiter=`.
- Public caller function signatures can keep the old param name
  for backward compat (see `pi_enrichment.lookup_pi_publications`).

### 4. Update tests

- Use `AsyncMock(spec=httpx.AsyncClient)` to mock the HTTP layer
  (see `test_base_client.py`, `test_semantic_scholar.py` for examples).
- Test the async client directly, not through the sync facade.
- Add a small number of sync-facade tests that verify delegation
  (e.g. `test_lookup_delegates_to_async`).
- If another test file patches the client in a caller namespace,
  update the patch target from `Client` to `SyncClient`.

## Gotchas — learnings from the POC

### 1. `run_sync` shares a persistent background event loop

`sbir_etl/utils/async_tools.run_sync` uses
`asyncio.run_coroutine_threadsafe` to submit coroutines to a single
process-wide daemon-thread event loop. That has two implications:

**Never call `time.sleep()` or `RateLimiter.wait_if_needed()` directly
from an async client.** It blocks the shared event loop, serializing
ALL async work in the process — not just your client.

**Always dispatch blocking sync calls via `asyncio.to_thread`**:

```python
async def _wait_for_rate_limit(self) -> None:
    if self._shared_limiter is not None:
        await asyncio.to_thread(self._shared_limiter.wait_if_needed)
        return
    await super()._wait_for_rate_limit()
```

This runs the blocking wait in the default thread pool executor. The
event loop stays responsive. The `RateLimiter`'s internal
`threading.Lock` guarantees cross-thread safety.

### 2. `shared_limiter` is load-bearing for `weekly_awards_report.py`

The weekly report creates six module-level `RateLimiter` instances
(semantic_scholar=100/min, orcid=60/min, opencorporates=30/min,
lens=50/min, sam_gov=60/min, usaspending=120/min) and shares them
across `ThreadPoolExecutor` workers. These are **global process
budgets**, not per-client budgets.

If you migrate a client and drop the injected limiter in favor of
the base client's per-instance `request_times` deque, three concurrent
workers would each get a fresh budget — 3× the intended rate. That
blows free-tier quotas.

Every migrated client must accept `shared_limiter:
RateLimiter | None = None` and override `_wait_for_rate_limit` to
honor it. See any of the 6 migrations in this branch for examples.

### 3. `_make_request` vs `_request_raw`

- `_make_request("GET", ...)` returns parsed JSON (`dict[str, Any]`).
  Use for JSON APIs (most of them).
- `_request_raw("GET", ...)` returns the raw `httpx.Response`. Use
  for XML, text, or binary responses. Decode the body yourself
  (`response.text`, `response.content`, etc.). Added in the
  `fpds_atom` migration to support Atom feeds.

Both methods share the same retry, rate limiting, and error
translation logic. `_make_request` is implemented as a thin wrapper
around `_request_raw` + `.json()`.

### 4. Absolute URLs bypass `base_url`

If `endpoint` starts with `http://` or `https://`, the base client
uses it as-is and ignores `self.base_url`. Added in the `press_wire`
migration because it polls three different hostnames
(prnewswire.com, businesswire.com, globenewswire.com) under one
client.

Clients using this pattern set `self.base_url = ""` and always pass
absolute URLs to `_make_request` / `_request_raw`.

### 5. POST body goes through the `params` parameter

`BaseAsyncAPIClient._make_request("POST", endpoint, params=body)`
sends `params` as the JSON request body (it becomes `json=params`
in the underlying `httpx.AsyncClient.post` call). Confusing name,
but it matches the existing USAspending POST convention and it's
not worth a breaking rename across the already-migrated clients.

See `lens_patents.LensPatentClient._search` for an example.

### 6. Preserve the "errors as None" contract at the public API

Many existing callers depend on the pre-migration behavior:
"on any failure, return `None`/`[]`/empty". They wrap the call in
`try/except Exception` and log + continue.

The migrated clients still return `None` from high-level methods
for "not found" cases, but they now **propagate `APIError`** for
real transport/server failures. Callers that already catch
`Exception` keep working and now get more informative log messages.
Callers that cared about `None` vs "not found" specifically get a
way to tell the difference.

The convention:

- **Low-level methods** (`search`, `get_profile`, `_request_raw`):
  propagate `APIError`, return empty/None only for legitimate empty
  responses.
- **High-level lookup methods** (`lookup`, `lookup_author`,
  `lookup_company`): return `None` for "not found" cases (empty
  search, 404 on detail fetch). Let `APIError` propagate for real
  failures — the caller is already catching it.

## What's left — and why

### `openai_client.py` (229 lines) — deliberately bespoke

**Recommendation: do not migrate.**

The OpenAI client uses `threading.Semaphore(max_concurrent=4)` to
cap **simultaneous in-flight requests**. That's a concurrency-limit
model, not a rate-limit model.  The two are orthogonal:

- Rate limit: "at most N requests per minute"
- Concurrency limit: "at most N requests in flight at any moment"

`BaseAsyncAPIClient` only implements the rate-limit model. Forcing
OpenAI to fit would mean one of:

1. Adding a concurrency-limit primitive to the base class (scope
   creep — no other client needs it).
2. Hiding the semaphore in a subclass override (keeps the
   duplication in a different shape).
3. Pretending the two models are the same (they're not — token-per-
   minute is negotiated separately with OpenAI, and the client's
   actual bottleneck is simultaneous connections, not request rate).

The current OpenAI client is also small (229 lines), has a clean
two-method public API (`chat`, `web_search`), returns typed
dataclasses, and has appropriate retry semantics for LLM APIs
(retry on 429/5xx, give up otherwise). There's no latent bug or
duplication to fix. Leaving it alone is the right call.

If you do want to migrate it later, you'd need to decide first
whether to (a) add a real concurrency primitive to the base class,
or (b) accept that OpenAI uses its own semaphore logic in a subclass
override. Option (a) is the better long-term move but only if a
second client ever needs concurrency limiting.

### `patentsview.py` (719 lines) — deferred, not abandoned

**Recommendation: migrate later, after the USPTO ODP migration has
settled.**

Three reasons this wasn't migrated in the first pass:

1. **Active module.** The client was migrated from the legacy
   PatentsView API (`search.patentsview.org`) to USPTO ODP
   (`data.uspto.gov`) on 2026-03-20 — three weeks before this
   consolidation work. Refactoring it now risks destabilizing a
   module the team is actively relying on. Wait until the ODP
   integration has a few more weeks of production soak time.

2. **Cache layer.** `PatentsViewClient` wraps requests in an
   `APICache` (`sbir_etl/utils/cache/api_cache.py`). The base
   client has no cache hook — adding one would be a significant
   scope extension. A cleaner path is to keep the cache as a
   subclass-only concept that bypasses `_make_request` on cache
   hits, but that's ad-hoc and leaks the caching concern into the
   subclass.

3. **Size and complexity.** 719 lines with multi-endpoint logic
   (patent search, assignee lookup, reassignment tracking), a
   legacy PatentsView compatibility shim, and its own
   `tenacity.retry`-decorated `_make_request` method. Mostly
   mechanical to migrate but a large diff with real regression
   risk.

Good news: `patentsview.py` already imports `RateLimiter` from
`sbir_etl.enrichers.rate_limiting` (fixed in commit `cb36611` this
session), so one of the fragmentation smells is already resolved.
The internal retry loop is the only remaining duplication.

**When you do migrate it:**

1. Start by writing characterization tests for the cache behavior
   (it's currently under-tested and the migration will touch it).
2. Decide whether to keep cache as a subclass wrapper or add a
   cache hook to `BaseAsyncAPIClient`. If only patentsview needs
   it, a subclass wrapper is fine.
3. The ODP API is JSON so `_make_request` works directly — no
   `_request_raw` needed.
4. `PatentsViewClient` is already the one client where
   `weekly_awards_report.py` does NOT use a shared limiter (it
   creates its own `RateLimiter` internally), so the
   `shared_limiter` plumbing can be skipped or added opportunistically.

## Test infrastructure

Every migrated client has a thorough test file under
`tests/unit/enrichers/test_<name>.py`. The pattern is:

```python
@pytest.fixture
def mock_http_client() -> AsyncMock:
    mock = AsyncMock(spec=httpx.AsyncClient)
    mock.aclose = AsyncMock()
    return mock

@pytest.fixture
def client(mock_http_client: AsyncMock) -> FooClient:
    return FooClient(http_client=mock_http_client)

def _mock_response(status: int = 200, payload: dict | None = None) -> Mock:
    resp = Mock()
    resp.status_code = status
    resp.json.return_value = payload or {}
    resp.text = str(payload or "")
    resp.raise_for_status = Mock()
    return resp
```

Async tests run via `pytest-asyncio` in auto mode (`asyncio_mode =
"auto"` in `pyproject.toml`) — no `@pytest.mark.asyncio` decorator
needed. Use `mock_http_client.get.return_value = ...` for single
responses and `mock_http_client.get.side_effect = [...]` for
sequenced responses (e.g. a two-step lookup that searches then
fetches details).

For retry tests that exercise tenacity's backoff, patch
`asyncio.sleep`:

```python
@patch("sbir_etl.enrichers.base_client.asyncio.sleep", new_callable=AsyncMock)
async def test_retries_on_transient_timeout(self, mock_sleep, ...):
    ...
```

`test_base_client.py` is the reference — it covers the base class
directly via a minimal `_StubAPIClient` subclass and is the
foundation everything else builds on. If you're confused about
expected behavior, read it first.
