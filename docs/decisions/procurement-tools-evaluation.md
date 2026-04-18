# Evaluation: procurement-tools / tandemgov-fpds for Federal Procurement Plumbing

**Date:** 2026-04-18
**Status:** Evaluation / Not Recommended

## Question

Could a third-party Python helper save plumbing time on FPDS / USASpending
quirks instead of maintaining our own clients in
`sbir_etl/enrichers/fpds_atom.py` and `sbir_etl/enrichers/usaspending/client.py`?

Two candidates surfaced:

1. **`makegov/procurement-tools`** (PyPI: `procurement-tools`) — originally
   referenced as "tandemgov" but the maintained fork lives under `makegov`.
2. **`tandemgov/fpds`** — a narrower FPDS Atom parser.

## Findings

### `makegov/procurement-tools`

| Property | Value |
|----------|-------|
| License | Apache 2.0 |
| Latest release | 0.2.2 (Jan 2024) — ~27 months stale |
| Stars / forks | 12 / 3 |
| Python style | Sync only |
| Scope | USASpending URL builder + `get_entity_awards`, SAM entity lookup (needs `SAM_API_KEY`), FAR section lookup, `UEI.is_valid`, FAI "periodic table" helper |
| FPDS coverage | **None** |
| Rate limiting / retry | Not provided |

Overlap with our code: trivial. `UEI.is_valid` is a regex; our SAM.gov integration
(`docs/SAM_GOV_INTEGRATION.md`) already handles entity lookups; USASpending URL
generation is one f-string.

### `tandemgov/fpds`

| Property | Value |
|----------|-------|
| License | MIT |
| Releases | 0 published |
| Stars / forks | 0 / 0 |
| Python style | Sync only |
| Scope | FPDS Atom XML → JSON via `fpdsRequest`, handles the 10-record page limit, preserves tag attributes as `field__description` keys |
| Rate limiting / retry / typed errors | Not provided |
| Async | No |

Returns plain dicts, not typed records. No SBIR/STTR research-code awareness
(SR1–SR3, ST1–ST3). Does not model the PIID vs. `REF_IDV_PIID` distinction for
task orders under IDVs.

## What We Already Have

- `FPDSAtomClient` (`sbir_etl/enrichers/fpds_atom.py`, 342 lines): async,
  rate-limited via shared `BaseAsyncAPIClient`, typed `FPDSRecord` dataclass,
  SBIR/STTR research-code extraction, PIID + `REF_IDV_PIID` dual search, batch
  description fetching.
- `USAspendingAPIClient` (`sbir_etl/enrichers/usaspending/client.py`, 610 lines):
  async, contract vs. assistance type-code routing, PIID/FAIN classifier
  (`build_award_type_groups`), batched `search_awards`, recipient lookup by
  UEI/DUNS/CAGE, delta-hash + freshness-record integration, state persistence.
- Shared base client with retry, rate limiting, and typed `APIError`
  translation used by all enrichers.
- Integration tests under `tests/unit/enrichers/` and
  `tests/integration/test_usaspending_iterative_enrichment.py`.

## Recommendation

**Do not adopt either library.** Our in-tree clients already cover the
surface area these libraries expose and go further (async, rate limiting,
retries, typed records, SBIR research codes, PIID/FAIN routing, delta
detection). Adopting them would mean giving up async + rate-limiting, losing
typed records, and depending on sparsely maintained packages (0-star,
~2-years-stale) for public endpoints we already call correctly.

### Worth borrowing

- **Pagination detail from `tandemgov/fpds`**: the FPDS Atom feed caps at
  10 records per page. Our current use-cases are single-PIID lookups and
  small vendor searches (`num=10` default), so we are not yet affected. If
  we ever need bulk FPDS sweeps, crib the pagination loop rather than pulling
  in the dep.
- **`UEI.is_valid` regex from `procurement-tools`**: easy to copy if we need
  stricter UEI validation; not worth a dependency.

### Revisit if

- FPDS Atom pagination becomes a blocker for bulk extraction.
- A third party publishes a well-maintained async FPDS/USASpending client
  with rate-limit and delta semantics compatible with `BaseAsyncAPIClient`.
