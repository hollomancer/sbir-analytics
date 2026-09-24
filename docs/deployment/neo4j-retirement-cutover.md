---
Type: Runbook
Maintainer: Conrad Hollomon
Last-Reviewed: 2026-09-23
Status: active until retirement deployment completes
---

# Neo4j retirement cutover

Use this procedure once. Complete it before the first deployment that contains ADR-006.

## Preconditions

1. Confirm that PR #788 is merged.
2. Confirm that `v0.18.0` is an annotated tag.
3. Confirm that `v0.18.0` resolves to the reviewed release tree.
4. Read the live-host status file named by the self-hosted server runbook.
5. Use only the recorded deployment checkout.
6. Confirm that the current deployment still runs the `v0.18.0` graph service.

## Create the final dump

1. Keep the deployment checkout on `v0.18.0`.
2. Run `make server-backup` with the existing server environment.
3. Confirm that the command reports a completed dump.
4. Confirm that the dump file is nonempty.
5. Record the dump's absolute path outside the repository.
6. Record the dump's byte count.
7. Record the dump's SHA-256.
8. Copy the dump to the approved backup location.
9. Verify the copied file has the same byte count and SHA-256.

Stop if any check fails. Do not deploy the retirement build without a verified dump.

## Deploy the retirement build

1. Follow the normal clean-checkout and persistent-storage checks.
2. Keep the deployment checkout on `v0.18.0`.
3. Run `make server-tailscale-down` to remove the managed Dagster and graph routes.
4. Confirm with `make server-tailscale-status` that both managed routes are absent.
5. Update the deployment checkout to the approved retirement release.
6. Render `docker-compose.server.yml` and inspect its service list.
7. Confirm that the service list has no graph database.
8. Run `make server-rebuild`. This target enables Compose orphan removal.
9. Confirm that the old graph container is absent.
10. Run `make server-tailscale-up` to restore only the managed Dagster route.
11. Confirm with `make server-tailscale-status` that no graph route remains.
12. Confirm that Dagster definitions load.
13. Confirm that the webserver and daemon are healthy.

## Preserve recovery data

1. Leave the historical host graph directory unchanged.
2. Leave old Docker volumes unchanged.
3. Leave the verified dump unchanged.
4. Record the retirement deployment time in the ignored live-host status file.
5. Record the dump path, byte count, and SHA-256 in that file.

Do not delete graph data as part of this procedure. A later deletion requires a separate
authorized operation with an exact target.
