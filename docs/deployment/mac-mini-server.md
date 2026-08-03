# Tailscale-Only Mac mini Server

A private, always-on deployment of SBIR Analytics on a single Apple-silicon
Mac mini. The stack is ARM64-native and reachable **only** over your Tailscale
tailnet — there is no public DNS, no port forwarding, and no LAN exposure.

## Live instance on this Mac mini

This machine hosts the live SBIR Analytics deployment.

- **Deployment checkout:** `/Users/conradhollomon/projects/sbir-analytics-server`
- **Development checkout:** `/Users/conradhollomon/projects/sbir-analytics` —
  never operate the live stack from here.
- **Installed baseline as of 2026-08-02:** tag `0.1`, commit `054bd862`. Always
  verify the deployment checkout with `git status --short` and
  `git describe --tags --always --dirty`; do not infer the live version from
  another checkout or from the image tag.
- **Persistent application data:** `/Volumes/SSDmini/sbir-analytics`
- **Local secrets:** `.env.server` in the deployment checkout. It is ignored,
  mode `0600`, and must never be printed, committed, or replaced.
- **Dagster metadata:** the Docker `dagster_home` named volume. Preserve it
  alongside SSD data; never use `docker compose down -v`.
- **Ingress:** Tailscale Serve over tailnet-only HTTPS/TLS. Tailscale Funnel,
  public port exposure, and LAN exposure are prohibited.
- **Current host state:** record data vintages, materialized subsets, Dagster
  run IDs, and temporary blockers in
  `docs/deployment/mac-mini-status.local.md`. That file is intentionally
  ignored; tracked documentation describes the operating contract, not a
  point-in-time snapshot of this machine.

Run every `make server-*` command and shell-driven live materialization from
the clean deployment checkout. Use the documented Make targets; do not run
`git clean`, destructive resets, or hand-written Compose teardown commands
there. Treat materialization as a live-data mutation: confirm the SSD is
mounted and the stack is healthy first. Keep schedules disabled until their
jobs have completed successfully by hand with the inputs available on this
host.

## What runs here

The `server` Compose profile (`docker-compose.server.yml`) runs exactly five
services:

| Service | Purpose | Host bind | Tailnet ingress |
|---------|---------|-----------|-----------------|
| `neo4j` | Graph store | `127.0.0.1:7474` / `7687` | TLS Bolt `17687` (opt-in) |
| `dagster-code-server` | Shared Dagster code location | none | none |
| `analytics-api` | Read-only API (bearer token) | `127.0.0.1:8010` | HTTPS `8443` |
| `dagster-webserver` | Orchestration UI (prod mode) | `127.0.0.1:3000` | HTTPS `443` |
| `dagster-daemon` | Schedules + sensors | — | none |

Heavy assets (ML/CET, fiscal, USPTO NLP) are **loaded but never scheduled**
(`DAGSTER_LOAD_HEAVY_ASSETS=true`), so they can be run by hand on this host now
that AWS Batch is gone. See [Heavy assets](#heavy-assets) for the capacity
caveat and [Workload placement](#workload-placement).

## Security boundary

- **Every host port binds to `127.0.0.1`.** Nothing listens on `0.0.0.0`, so
  the stack is invisible to other machines on the same LAN.
  Compose hardcodes this address; `make server-check` also rejects a legacy
  `SERVER_LOOPBACK` value that is anything other than loopback.
- **Tailscale Serve is the only ingress.** It provides tailnet-only HTTPS/TCP
  and terminates TLS automatically
  ([docs](https://tailscale.com/docs/features/tailscale-serve)):
  - `https://<host>/` → Dagster (`127.0.0.1:3000`)
  - `https://<host>:8443/` → analytics API (`127.0.0.1:8010`)
  - `bolt+s://<host>:17687` → Neo4j Bolt (`127.0.0.1:7687`, opt-in)
- **Neo4j remains loopback-only at the host boundary.** Tailscale Serve is the
  sole proxy to Bolt, and a separate least-privilege grant restricts that route
  to trusted operators. Neo4j Browser's HTTP port `7474` is never served.
- **Tailscale Funnel is prohibited.** The helper never enables Funnel; the
  services must never be reachable from the public internet.
- **Defense in depth.** The API keeps its bearer-token auth even behind
  Tailscale. Dagster relies on Tailscale identity plus a least-privilege grant.

## One-time device setup

### 1. External SSD

Prepare a directory tree on the external SSD and point the storage variables at
it in `.env.server`:

```bash
mkdir -p /Volumes/SSDmini/sbir-analytics/{data,reports,logs,artifacts,neo4j,backups}
```

```dotenv
SERVER_DATA_DIR=/Volumes/SSDmini/sbir-analytics/data
SERVER_REPORTS_DIR=/Volumes/SSDmini/sbir-analytics/reports
SERVER_LOGS_DIR=/Volumes/SSDmini/sbir-analytics/logs
SERVER_ARTIFACTS_DIR=/Volumes/SSDmini/sbir-analytics/artifacts
SERVER_NEO4J_DIR=/Volumes/SSDmini/sbir-analytics/neo4j
SERVER_BACKUP_DIR=/Volumes/SSDmini/sbir-analytics/backups
```

> The external SSD is **not a backup by itself.** Run `make server-backup`
> regularly and copy the dump to a second location.

### 2. Start-at-login

- **OrbStack** (recommended Docker runtime on macOS): enable *Start at login*.
- **Tailscale**: enable *Run at login* / *Start on boot* so the tailnet and
  Serve routes come back after a reboot.

### 3. One-time Tailscale HTTPS consent

The first HTTPS Serve route requires enabling HTTPS certificates for the
tailnet (MagicDNS + HTTPS in the admin console). Accept the one-time consent,
then configure persistent routes:

```bash
make server-tailscale-up     # tailscale serve --bg (persists across restarts)
make server-tailscale-status
```

`--bg` keeps the routes active after Tailscale or the device restarts. Setup
**refuses to replace** an existing route on port 443, 8443, or an enabled
17687 route. Neo4j tailnet access defaults to disabled.

### 4. MagicDNS URLs

With MagicDNS enabled the services are reachable at your node's DNS name:

- Dagster: `https://<node>.<tailnet>.ts.net/`
- API: `https://<node>.<tailnet>.ts.net:8443/` (send `Authorization: Bearer <token>`)
- Neo4j: `bolt+s://<node>.<tailnet>.ts.net:17687` (trusted operators only)

`make server-tailscale-up` prints the exact URLs for this node.

## Bring-up

```bash
cp .env.server.example .env.server     # fill in NEO4J_PASSWORD + API token
make server-check                      # docker, storage, ports, tailscale, bindings
make server-up                         # repeats preflight, then starts localhost-only stack
make server-tailscale-up               # expose via Tailscale Serve
make server-status
```

Generate the API token with `openssl rand -hex 32`.

`make server-up` builds the native Python base image from
`Dockerfile.python-base` before starting the stack. The first build takes
several minutes; later builds reuse Docker's layer cache and are quick unless
the base's inputs actually changed.

It no longer pulls the published image first. Nothing republishes
`ghcr.io/hollomancer/sbir-analytics-python-base:latest` since the image-build
workflow was retired, so preferring the pull pinned this host to a base that
will never be refreshed again.

To force a full refresh — including the upstream image the base builds `FROM`,
which is how OS and interpreter security updates arrive — use:

```bash
make server-rebuild     # rebuilds base + app images, then restarts the stack
docker image prune      # reclaim the superseded layers
```

`server-rebuild` recreates containers, so **any in-flight Dagster run is
killed**. Check `make server-status` for active runs before using it, and
prefer a quiet window.

## Tailscale grant (least privilege)

Restrict who can reach the server. Tag the Mac mini `tag:sbir-server`, grant
analysts access to the web services, and grant Neo4j separately to trusted
operators. Grants are the recommended current policy mechanism
([docs](https://tailscale.com/docs/reference/syntax/grants)). Apply this from
the admin console manually:

```jsonc
{
  "grants": [
    {
      "src": ["group:sbir-analysts"],
      "dst": ["tag:sbir-server"],
      "ip":  ["tcp:443", "tcp:8443"]
    },
    {
      "src": ["group:sbir-neo4j-operators"],
      "dst": ["tag:sbir-server"],
      "ip":  ["tcp:17687"]
    }
  ],
  "tagOwners": {
    "tag:sbir-server": ["autogroup:admin"]
  }
}
```

Define `group:sbir-neo4j-operators` in the same policy, or replace it with the
exact operator login email for a single-user grant.

Neo4j's host ports (`7474`/`7687`) remain absent. Operators reach only the
TLS-terminated Serve port `17687`; no grant should expose Browser HTTP or the
loopback Bolt port directly.

Apply the operator grant before enabling the route. Then set this in the live
`.env.server` and rerun `make server-tailscale-up`:

```dotenv
NEO4J_TAILNET_BOLT_ENABLED=true
NEO4J_TAILNET_BOLT_PORT=17687
```

Leave the flag false unless direct operator access is actively required.

## iPhone graph access

Install Tailscale and
[PocketGraph](https://apps.apple.com/us/app/pocketgraph/id1604368926) on the
iPhone. Sign in to the tailnet as a member of `group:sbir-neo4j-operators`,
enable the route only after its grant is active, then configure PocketGraph
with:

```text
Protocol: bolt+s
Host: <node>.<tailnet>.ts.net
Port: 17687
Database: neo4j
Username: neo4j
Password: <current rotated Neo4j password>
```

PocketGraph is a third-party client and can execute arbitrary Cypher. The
Community Edition deployment does not provide the repository's API-level
read-only guard for this direct connection, so restrict the grant and
credentials to trusted operators. Do not configure `7474`, use `bolt://`, or
enable Funnel.

## Day-2 operations

| Task | Command |
|------|---------|
| Status | `make server-status` |
| Logs | `make server-logs SERVICE=dagster-webserver` |
| Backup Neo4j | `make server-backup` |
| Stop (keep data) | `make server-down` |
| Remove Serve routes | `make server-tailscale-down` |

`make server-down` stops containers but **preserves** the `dagster_home` volume
and all bind-mounted data. `make server-tailscale-down` removes **only** the
443/8443/17687 routes and never runs the destructive global
`tailscale serve reset`.

Neo4j Community Edition cannot create an online `neo4j-admin` dump. The backup
helper therefore stops Neo4j briefly, writes the dump, and always attempts to
restart it—even if the dump fails or the command is interrupted. API requests
can fail during that short window. A completed dump is retained if restart
fails so recovery work cannot erase the backup.

### Schedules

- The daily all-assets schedule is gated off on the server
  (`SBIR_ETL__DAGSTER__SCHEDULES__DAILY_ALL_ASSETS_ENABLED=false`).
- A `weekly_core_refresh` schedule exists but stays **STOPPED** until you flip
  `SBIR_ETL__DAGSTER__SCHEDULES__WEEKLY_CORE_REFRESH_ENABLED=true` — do this
  only after a manual run of `core_refresh_job` succeeds.

### Bounded USAspending contract refresh

USAspending's public Award Data Archive does not require a login. Its
`Contracts_Full` ZIPs are much smaller than the complete PostgreSQL database,
but expand to several CSV members, so they must be streamed and filtered rather
than loaded into Pandas as a whole.

Run these commands from the deployment checkout. They write only below the
SSD-backed `/app/data` mount:

```bash
# Build the complete vendor frame from the current SBIR.gov source in bounded chunks.
docker exec sbir-server-dagster-code python \
  scripts/usaspending/extract_sbir_vendors.py \
  --awards-file /app/data/raw/sbir/award_data.csv \
  --output /app/data/transition/sbir_vendor_filters.json

# Discover and atomically download the current public fiscal-year archive.
# A .part file is retained for HTTP Range resume after interruption.
docker exec sbir-server-dagster-code python \
  scripts/usaspending/download_award_archive.py \
  --fiscal-year 2026 --type contracts
```

Set
`SBIR_ETL__TRANSITION__CONTRACTS__USE_AWARD_ARCHIVE=true` in `.env.server`
and run `make server-up` to recreate the code service with that explicit source
choice. Then materialize **only** `raw_contracts` from Dagster. The asset uses
the newest ZIP under
`data/raw/usaspending/award_archive/`, scans every CSV member in bounded Arrow
batches, filters to the SBIR UEI/DUNS/name frame, and atomically replaces
`data/transition/contracts_ingestion.parquet`. It fails closed on an empty
vendor frame, schema drift, incomplete downloads, or provenance mismatch.
The opt-in is intentionally false by default because one fiscal-year archive is
narrower than the full USAspending database source.

Do not run `core_refresh_job` or `sbir_weekly_refresh_job` as a substitute for
this targeted refresh. Keep schedules stopped until the targeted artifact and
its `.checks.json` sidecar have been reviewed.

### Source-data downloads

This host fetches upstream data itself; GitHub Actions no longer stages it.
Four download jobs carry the cron times the retired `data-refresh.yml` used:

| Schedule | Job | Cron (UTC) | Enable with |
|---|---|---|---|
| `weekly_sbir_awards_download` | `sbir_awards_download_job` | `0 9 * * 1` | `…__WEEKLY_SBIR_AWARDS_DOWNLOAD_ENABLED=true` |
| `monthly_sam_gov_download` | `sam_gov_download_job` | `0 3 15 * *` | `…__MONTHLY_SAM_GOV_DOWNLOAD_ENABLED=true` |
| `monthly_usaspending_download` | `usaspending_download_job` | `0 2 6 * *` | `…__MONTHLY_USASPENDING_DOWNLOAD_ENABLED=true` |
| `monthly_uspto_download` | `uspto_download_job` | `0 9 1 * *` | `…__MONTHLY_USPTO_DOWNLOAD_ENABLED=true` |

Env vars are prefixed `SBIR_ETL__DAGSTER__SCHEDULES__`; a matching
`…_CRON` variable overrides the time. All four default to **STOPPED** — run
each by hand first, then enable.

Before enabling, note:

- **SAM.gov** needs `SAM_GOV_API_KEY` in `.env.server`. Keys expire roughly
  every 60 days, so a failure here usually means rotate the key.
- **USAspending** is the long pole. The dump is large and the job may run for
  hours. It checks free space before downloading and resumes from a sidecar
  checkpoint next to the partial file, so an interrupted run is re-runnable
  rather than restarted. Confirm SSD headroom first.
- **USPTO** needs `USPTO_ODP_API_KEY` and a working Playwright/Chromium install.
  Anonymous downloads from data.uspto.gov ended 2026-06-18 and now return an
  HTML shell with HTTP 200, so the job fetches PatentsView and AI patents
  through the ODP mint flow and assignments through browser automation. A
  size/HTML guard fails the run rather than saving an error page as data.
- Downloads land under `SBIR_ETL__PATHS__DATA_ROOT`, which the server profile
  points at the SSD.

### Pipeline chaining

The retired `etl-pipeline.yml` ran the SBIR, USAspending, and USPTO pipelines on
a weekly cron. Instead of blind crons, run-status sensors fire each pipeline
when its download job succeeds, so a pipeline only runs when there is fresh
input:

| Sensor | Runs | After |
|---|---|---|
| `sbir_pipeline_after_download` | `sbir_weekly_refresh_job` | `sbir_awards_download_job` |
| `uspto_pipeline_after_download` | `uspto_validation_job` | `uspto_download_job` |
| `usaspending_pipeline_after_download` | `usaspending_iterative_enrichment_job` | `usaspending_download_job` |

All default to **STOPPED**; enable with
`SBIR_ETL__DAGSTER__SENSORS__<NAME>_ENABLED=true` after a manual pipeline run
succeeds. The SBIR sensor skips when the download reported no upstream change,
so an unchanged CSV does not trigger hours of re-enrichment.

### Monthly analysis

`monthly_phase_transition` (1st of the month, 14:00 UTC) runs
`phase_transition_latency_job`, and a sensor archives its outputs to
`<data_root>/processed/phase_transition/history/<date>/` afterwards. That dated
series replaces what the retired workflow published to S3; GitHub artifacts
expire, so this is now the only durable copy. Enable with
`SBIR_ETL__DAGSTER__SCHEDULES__MONTHLY_PHASE_TRANSITION_ENABLED=true` and
`SBIR_ETL__DAGSTER__SENSORS__PHASE_TRANSITION_ARCHIVE_AFTER_ANALYSIS_ENABLED=true`.

### Weekly awards report

`weekly_awards_report` (Monday 12:00 UTC) runs `weekly_awards_report_job`,
carrying the slot the retired `weekly.yml` job used. Each run writes
`<data_root>/reports/weekly_awards/<date>/weekly-awards.md`; the workflow only
kept a 30-day artifact, so this is now the durable copy. Enable with
`SBIR_ETL__DAGSTER__SCHEDULES__WEEKLY_AWARDS_REPORT_ENABLED=true`.

Before enabling:

- `OPENAI_API_KEY` and `SAM_GOV_API_KEY` belong in `.env.server`. Without them
  the script still produces a report, just without AI summaries or SAM.gov
  enrichment — it degrades rather than failing, so check the output rather than
  the exit code.
- The lookback defaults to 7 days. Override with
  `SBIR_ETL__REPORTS__WEEKLY_AWARDS_DAYS` for a backfill.
- The job fails if the script writes nothing, so an empty report is a loud
  failure rather than a silent success.
- **It depends on `weekly_sbir_awards_download`.** The report resolves the SBIR
  awards CSV locally and fails with `FileNotFoundError: Could not resolve SBIR
  awards CSV` when no vintage is present and the download is unreachable —
  confirmed by executing the job. The crons already order this correctly
  (download Monday 09:00 UTC, report Monday 12:00 UTC), but enabling the report
  *without* also enabling `weekly_sbir_awards_download` will fail every week.

### Heavy assets

`DAGSTER_LOAD_HEAVY_ASSETS` now defaults to **true**, so CET, fiscal,
modernbert, and USPTO AI extraction jobs load and can be triggered by hand.
**Nothing schedules them.** They previously ran on AWS Batch with more headroom
than this host has, and `dagster-code-server` is capped at 3G. Measure runtime
and memory on a manual run before automating any of them; set the variable back
to `false` if the code server starts hitting its limit.

## Recovery

- **After reboot:** OrbStack and Tailscale start at login; containers use
  `restart: unless-stopped` and Serve routes persist (`--bg`). Verify with
  `make server-status` and `make server-tailscale-status`.
- **After Tailscale reconnect:** routes resume automatically. If missing,
  re-run `make server-tailscale-up`.
- **After container restart:** Neo4j and Dagster metadata persist on the SSD /
  `dagster_home` volume; no data loss.
- **After external-drive failure:** re-mount the SSD, then `make server-up`.
  Restore Neo4j from the latest `server-backup` dump if the store is damaged.

## Verifying isolation

From a **non-Tailscale** device on the same LAN, the services must be
unreachable (connection refused/timeout):

```bash
curl -m 5 http://<mac-lan-ip>:3000/        # fails
curl -m 5 http://<mac-lan-ip>:8010/health  # fails
```

From a Tailscale analyst device, Dagster (443) and the API (8443, with a bearer
token) succeed while Neo4j remains unreachable. From a trusted operator device,
TLS Bolt succeeds on 17687; direct connections to 7474/7687 remain unreachable.

## Workload placement

- **Local, always-on:** API, Neo4j, Dagster, snapshots, DuckDB, core analytics.
- **Local, on-demand:** public USAspending Contracts_Full download and bounded
  SBIR-vendor filtering into Parquet.
- **Local, on-demand (PR 2):** CET/scikit-learn and bounded USPTO NLP.
- **Managed batch:** complete USAspending database extraction, fiscal analysis,
  and unfiltered transition jobs via S3 + AWS Batch/Fargate
  ([docs](https://docs.aws.amazon.com/batch/latest/userguide/fargate.html)).
- **Managed inference / vector search:** Hugging Face Inference Providers plus
  Qdrant Cloud, replacing exhaustive award-by-patent similarity in later PRs.
  Qdrant's free cluster is evaluation-only and requires S3 exports as the
  durable rebuild source
  ([docs](https://qdrant.tech/documentation/cloud/create-cluster/)).

## Follow-up PRs

1. Isolated local analysis runner; correct `Dockerfile.full` dependency drift.
2. Reconcile AWS Batch, CDK, and GitHub workflow handoffs.
3. Vector-store interface, Qdrant integration, chunked indexing, top-k retrieval.
