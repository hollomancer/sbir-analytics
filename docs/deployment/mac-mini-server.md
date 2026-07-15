# Tailscale-Only Mac mini Server

A private, always-on deployment of SBIR Analytics on a single Apple-silicon
Mac mini. The stack is ARM64-native and reachable **only** over your Tailscale
tailnet — there is no public DNS, no port forwarding, and no LAN exposure.

## What runs here

The `server` Compose profile (`docker-compose.server.yml`) runs exactly four
services:

| Service | Purpose | Host bind | Tailnet ingress |
|---------|---------|-----------|-----------------|
| `neo4j` | Graph store | `127.0.0.1:7474` / `7687` | **none** (private) |
| `analytics-api` | Read-only API (bearer token) | `127.0.0.1:8010` | HTTPS `8443` |
| `dagster-webserver` | Orchestration UI (prod mode) | `127.0.0.1:3000` | HTTPS `443` |
| `dagster-daemon` | Schedules + sensors | — | none |

Heavy assets (ML/CET, fiscal, USPTO NLP) are **disabled** on the server
(`DAGSTER_LOAD_HEAVY_ASSETS=false`). See
[Workload placement](#workload-placement).

## Security boundary

- **Every host port binds to `127.0.0.1`.** Nothing listens on `0.0.0.0`, so
  the stack is invisible to other machines on the same LAN.
  `make server-check` refuses to start if `SERVER_LOOPBACK` is anything other
  than loopback.
- **Tailscale Serve is the only ingress.** It provides tailnet-only HTTPS and
  terminates TLS automatically
  ([docs](https://tailscale.com/docs/features/tailscale-serve)):
  - `https://<host>/` → Dagster (`127.0.0.1:3000`)
  - `https://<host>:8443/` → analytics API (`127.0.0.1:8010`)
- **Neo4j is never served over Tailscale.** It stays private to the host and
  the Compose network.
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
**refuses to replace** an existing route on port 443 or 8443.

### 4. MagicDNS URLs

With MagicDNS enabled the services are reachable at your node's DNS name:

- Dagster: `https://<node>.<tailnet>.ts.net/`
- API: `https://<node>.<tailnet>.ts.net:8443/` (send `Authorization: Bearer <token>`)

`make server-tailscale-up` prints the exact URLs for this node.

## Bring-up

```bash
cp .env.server.example .env.server     # fill in NEO4J_PASSWORD + API token
make server-check                      # docker, storage, ports, tailscale, bindings
make server-up                         # localhost-only stack
make server-tailscale-up               # expose via Tailscale Serve
make server-status
```

Generate the API token with `openssl rand -hex 32`.

## Tailscale grant (least privilege)

Restrict who can reach the server. Tag the Mac mini `tag:sbir-server` and grant
only selected users/groups access to `tcp:443` and `tcp:8443`. Grants are the
recommended current policy mechanism
([docs](https://tailscale.com/docs/reference/syntax/grants)). Apply this from
the admin console manually:

```jsonc
{
  "grants": [
    {
      "src": ["group:sbir-analysts"],
      "dst": ["tag:sbir-server"],
      "ip":  ["tcp:443", "tcp:8443"]
    }
  ],
  "tagOwners": {
    "tag:sbir-server": ["autogroup:admin"]
  }
}
```

Neo4j's ports (7474/7687) are deliberately absent — they are never reachable
over the tailnet.

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
443/8443 routes and never runs the destructive global
`tailscale serve reset`.

### Schedules

- The daily all-assets schedule is gated off on the server
  (`SBIR_ETL__DAGSTER__SCHEDULES__DAILY_ALL_ASSETS_ENABLED=false`).
- A `weekly_core_refresh` schedule exists but stays **STOPPED** until you flip
  `SBIR_ETL__DAGSTER__SCHEDULES__WEEKLY_CORE_REFRESH_ENABLED=true` — do this
  only after a manual run of `core_refresh_job` succeeds.

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

From a Tailscale device with the grant, Dagster (443) and the API (8443, with a
bearer token) succeed, while Neo4j remains unreachable over the tailnet.

## Workload placement

- **Local, always-on:** API, Neo4j, Dagster, snapshots, DuckDB, core analytics.
- **Local, on-demand (PR 2):** CET/scikit-learn and bounded USPTO NLP.
- **Managed batch:** full USAspending extraction, fiscal analysis, and large
  transition jobs via S3 + AWS Batch/Fargate
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
