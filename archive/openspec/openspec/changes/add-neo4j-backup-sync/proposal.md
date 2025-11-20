# Add Neo4j Backup Sync (openspec proposal)

Status: Draft
Owners: infra-team / data-platform
Reviewers: devops, security, DBAs

## Summary

Add a repeatable, secure, and auditable remote-sync capability for Neo4j logical backups produced by the repository's local `scripts/neo4j/backup.sh`. This change ("add-neo4j-backup-sync") defines the design, automation, CI integration, IAM requirements, retention rules, monitoring, and restore verification for synchronizing backups to cloud object storage (S3-compatible). The implementation will be split so that local backup/restore remains usable without cloud access, and cloud sync is an opt-in, well-documented feature.

Goals

- Provide safe, automated upload of Neo4j backups to a remote object store (initial target: AWS S3).
- Ensure uploads are secure (encrypted in transit and at rest), use least privilege credentials, and are auditable.
- Support retention policies and lifecycle (expiration, transition).
- Provide CI / scheduler integration to perform periodic backups and test restores in a staging context.
- Keep local offline workflows unchanged; cloud sync is additive.

Non-goals

- Replace enterprise backup products or on-prem backup strategies.
- Implement cross-region replication or complex disaster recovery workflows beyond object storage retention and restore verification (those are out-of-scope for this ticket and can be added later as a follow-up change).

Motivation / Background

We added local Neo4j backup and restore tooling in the repo, with `scripts/neo4j/backup.sh` and `scripts/neo4j/restore.sh`. Many teams need durable, remote copies of backups (e.g., S3) for retention and DR. This change adds an official, secure method to push backups to cloud storage from CI / scheduled runners or from an operator-run job, and documents the procedure and IAM requirements.

Constraints & Assumptions

- Primary object store will be AWS S3. The design should be cloud-agnostic and refer to S3 semantics, but optionally support S3-compatible endpoints (minio) or other providers in future.
- CI runs will have access to secure secrets or OIDC to assume short-lived credentials. We prefer GitHub OIDC where available.
- Backups are logical neo4j-admin dumps (files produced by `backup.sh`).
- We rely on existing backup script to produce a dump file at a known host path (e.g., `backups/neo4j/<filename>.dump`).

Design

1) Storage organization and naming

- Bucket prefix: `sbir-analytics-neo4j-backups`
- Bucket layout:
  - s3://<bucket>/environment=<env>/year=YYYY/month=MM/day=DD/<db_name>-<timestamp>.dump
  - Example: `s3://sbir-analytics-neo4j-backups/environment=prod/year=2025/month=11/day=01/neo4j-20251101T230000Z.dump`
- Metadata: store a small JSON metadata alongside or as S3 object metadata:
  - fields: sha256 checksum, db_name, dump_tool_version (scripts commit sha), rows_estimate (if available), hostname, created_by, created_at
- Naming and metadata allow programmatic pruning and verification.

2) Upload mechanism

- Add a new script `scripts/neo4j/upload_backup_to_s3.sh` that:
  - Validates presence of the backup file.
  - Computes `sha256` and optionally `gzip` (if desired).
  - Uploads via `aws s3 cp` or `aws s3api put-object` (or `s3cmd`/`minio` client if configured).
  - Optionally sets S3 object metadata and server-side encryption (SSE-S3 or SSE-KMS).
  - Optionally writes a small `.meta.json` file next to the dump with extended metadata.
  - Option to create pre-signed URL or immediate ETag verification post upload.
- The script must be idempotent (if an object with same key+checksum exists, skip upload or annotate).

3) Security & credentials

- Use OIDC-based GitHub Actions workflows to assume an IAM role with limited permissions (preferred).
- Minimal IAM policy example (S3 + kms decrypt/encrypt if using SSE-KMS):
  - `s3:PutObject`, `s3:GetObject`, `s3:ListBucket`, `s3:DeleteObject` (if cleanup via CI allowed)
  - Restrict prefix to `sbir-analytics-neo4j-backups/*`
  - If SSE-KMS used: `kms:Encrypt`, `kms:Decrypt`, `kms:GenerateDataKey`
- Never store long-lived static credentials in the repo. Use GitHub Secrets or an OIDC-based role assumption.
- When local operators run uploads manually, document how to configure `aws cli` credentials or mount credentials at runtime from secure locations.

4) Retention & lifecycle

- Set S3 bucket lifecycle rules to prune objects older than `N` days (N configurable; default 30 for dev, 90 for prod).
- Optionally transition older backups to Glacier or Cold Storage per policy.
- Retention policy must be configurable via `config/docker.yaml` or sysadmin docs.

5) Restore verification

- Provide a "verify-restore" ephemeral job that:
  - Downloads a backup to ephemeral environment.
  - Attempts to load it into a staging Neo4j instance (or runs `neo4j-admin check-consistency` where supported).
  - Runs a smoke query to ensure data is accessible.
- This job can be executed periodically (weekly) or after a backup upload (short test) depending on resource constraints.

6) Monitoring & alerting

- Success/failure logs produced by the upload script are archived.
- CI workflow should upload the logs as artifacts on failure.
- Optionally send Slack/email on failure (configurable, not in initial scope).

7) CI integration and schedule

- Add a GitHub Actions workflow `ci/neo4j-backup-sync.yml` (or reuse container-ci) that:
  - Runs on schedule (cron) for `prod` (or staging) backups (e.g., daily at 02:00 UTC).
  - Uses `scripts/ci/build_container.sh` to ensure a known image is available (if uploads must run inside containerized environment).
  - Runs `scripts/neo4j/backup.sh` to produce backup into workspace or an attached volume.
  - Runs `scripts/neo4j/upload_backup_to_s3.sh` to push it to S3. Use OIDC to assume role.
  - On success, optionally run `scripts/neo4j/verify_restore.sh` in a short mode (or schedule verify jobs separately).
  - On failure, upload logs as artifacts and emit an alert.

8) Documentation

- Update `docs/neo4j/server.md` to describe S3 sync:
  - How to configure bucket name, prefix, region, KMS key (optional).
  - How to provision an IAM role for CI with example policy and trusted entity config (use OIDC).
  - How to run upload locally and how to run the scheduled job.
  - How to test restores locally with `scripts/neo4j/restore.sh`.

Implementation details & example snippets

- Example minimal IAM policy (least privilege):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowBackupWrites",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:PutObjectAcl",
        "s3:GetObject",
        "s3:ListBucket",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::sbir-analytics-neo4j-backups",
        "arn:aws:s3:::sbir-analytics-neo4j-backups/*"
      ]
    },
    {
      "Sid": "AllowKMSForSSE",
      "Effect": "Allow",
      "Action": [
        "kms:Encrypt",
        "kms:Decrypt",
        "kms:GenerateDataKey"
      ],
      "Resource": ["arn:aws:kms:us-east-1:123456789012:key/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"]
    }
  ]
}
```

- CI OIDC setup (high-level):
  - Configure AWS IAM role trust policy to allow GitHub Actions OIDC provider with repository-specific conditions.
  - In GitHub Actions workflow, use `aws-actions/configure-aws-credentials` with `role-to-assume` via OIDC.
  - Use `aws s3 cp` to upload.

- Upload script behavior (pseudocode):
  - Accept args: `--file`, `--bucket`, `--prefix`, `--kms-key`, `--sse`.
  - Compute sha256, write a `.meta.json` with metadata.
  - If object exists and ETag/sha matches, skip upload.
  - Use `aws s3api put-object --bucket ... --key ... --body FILE --metadata filehash=... --server-side-encryption aws:kms --ssekms-key-id ...` (if kms-key provided).
  - Verify `aws s3api head-object` success and stored metadata.

Acceptance criteria

- Script `scripts/neo4j/upload_backup_to_s3.sh` exists and is executable and tested locally against a test bucket.
- A GitHub Actions workflow `ci/neo4j-backup-sync.yml` exists that can:
  - run in dry-run mode and simulate uploads without credentials,
  - when provided proper OIDC/credentials, produce a backup and upload to S3.
- `docs/neo4j/server.md` and `config/README.md` are updated to include S3 sync configuration and IAM guidance.
- The S3 bucket lifecycle rule is documented and sample lifecycle JSON is provided in docs.
- Restore verification script `scripts/neo4j/verify_restore.sh` (or an invocation pattern documented) exists and can exercise a download+restore into ephemeral Neo4j (or run `neo4j-admin check-consistency`).

Security considerations

- Use short-lived credentials (OIDC or CI role assumption) for uploads. Avoid long-lived secrets in repo.
- Use SSE-S3 or SSE-KMS for server-side encryption; prefer SSE-KMS for auditable keys and kms policy separation.
- Harden bucket policies to restrict access to known principals and the repository prefix.
- Log uploads and record checksums to avoid silent corruption. Consider cross-checking ETag vs computed checksum where feasible.
- Avoid leaving backup files in CI runner workspace; ensure artifacts are removed after successful upload (or move to an ephemeral artifact store for short-term availability).

Data governance & retention

- Define retention settings per environment:
  - dev: keep 7 days
  - staging: keep 30 days
  - prod: keep 90–365 days depending on org policy
- Document policy and point to `config/docker.yaml` or a new `config/backups.yaml` to record policy values.

Migration & rollout plan

1. Create cloud bucket (S3) and set lifecycle policy (manual or via infra-as-code).
2. Create IAM role for the repo’s CI with the policy above (or similar minimal policy).
3. Add GitHub Secrets or OIDC role config in Actions to allow role assumption.
4. Add `scripts/neo4j/upload_backup_to_s3.sh` to repo, update `docs/neo4j/server.md`.
5. Add GitHub Actions workflow `ci/neo4j-backup-sync.yml` in draft mode (dry-run).
6. Run a test upload using a staging bucket and the OIDC role in CI.
7. Enable scheduled runs (cron) after verifying successful uploads.
8. Optionally add a scheduled verify-restore job.

Testing & verification

- Unit test: script-level testing using a local minio instance (S3-compatible) or mocking `aws` calls.
- Integration test: CI job that runs backup, uploads to a test S3 bucket, downloads and verifies checksum, and optionally does a restore into an ephemeral Neo4j instance.
- Acceptance: When run in prod configuration, the backup+upload+verify workflow completes successfully and uploads exist under the expected prefix and include metadata + checksum.

Operational runbook summary (for operators)

- How to trigger a manual upload:
  - Produce a local backup: `scripts/neo4j/backup.sh`
  - Upload: `scripts/neo4j/upload_backup_to_s3.sh --file backups/neo4j/<file>.dump --bucket sbir-analytics-neo4j-backups --prefix environment=prod`
- How to restore from S3:
  - Download: `aws s3 cp s3://.../<file>.dump /tmp/`
  - Restore: `scripts/neo4j/restore.sh --backup-path /tmp/<file>.dump`
- How to verify uploaded backup:
  - Ensure `.meta.json` exists and computed sha256 matches stored metadata.
  - Optionally run the verify-restore flow.

Open questions / decisions needed from stakeholders

- Which environments should have scheduled backups (prod only or staging too)?
- Desired retention per environment.
- KMS usage: use centralized KMS key or per-environment keys?
- Should uploads be immediate (post-backup) or batched (e.g., DR windows)?

Implementation tasks (high-level checklist)

- [ ] Create `scripts/neo4j/upload_backup_to_s3.sh` (implement upload, metadata, checksum).
- [ ] Create `scripts/neo4j/verify_restore.sh` (ephemeral restore/verify workflow).
- [ ] Add GitHub Actions workflow `ci/neo4j-backup-sync.yml`:
  - scheduled cron
  - uses OIDC role to upload (supports dry-run)
  - saves logs and artifacts on failure
- [ ] Update `docs/neo4j/server.md` and `config/README.md` with S3 sync docs and IAM sample policies.
- [ ] Add sample lifecycle JSON and a Terraform/CloudFormation snippet for bucket + lifecycle + policy (optional).
- [ ] Add unit/integration tests targeting a local minio endpoint.
- [ ] Run integration verification in staging and confirm policy and retention are correct.

Timeline & estimate

- Design & docs: 1 day
- Upload script + basic unit tests: 1 day
- CI workflow + OIDC role config (coordination with infra): 1 day (plus infra lead time)
- Integration tests + verification: 1 day

Total: ~4 working days (excluding infra provisioning lead time).

Notes about provider-agnostic support

- The script will accept S3 endpoint overrides to support minio or S3-compatible providers. Abstract the upload mechanism so we can later add GCS / Azure Blob support with a different CLI/SDK.

Appendix: Example GitHub Actions job (high-level)

```yaml
name: neo4j-backup-sync
on:
  schedule:

    - cron: '0 2 * * *' # daily 02:00 UTC

  workflow_dispatch:

jobs:
  backup-and-upload:
    runs-on: ubuntu-latest
    permissions:
      id-token: write  # for OIDC
      contents: read
    steps:

      - uses: actions/checkout@v4
      - name: Assume AWS role via OIDC

        uses: aws-actions/configure-aws-credentials@v2
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1

      - name: Build/test environment or use runner

        run: |
          ./scripts/neo4j/backup.sh

      - name: Upload to S3

        env:
          BUCKET: sbir-analytics-neo4j-backups
          PREFIX: environment=prod
        run: |
          ./scripts/neo4j/upload_backup_to_s3.sh --file ./backups/neo4j/*.dump --bucket "${BUCKET}" --prefix "${PREFIX}"

      - name: Verify upload (optional)

        run: |
          ./scripts/neo4j/verify_restore.sh --s3-uri s3://${BUCKET}/${PREFIX}/... --db neo4j --dry-run
```

---

If approved, I will:

1. Create `scripts/neo4j/upload_backup_to_s3.sh` and `scripts/neo4j/verify_restore.sh` with robust error handling and CLI options.
2. Add the GitHub Actions workflow `ci/neo4j-backup-sync.yml` in draft mode (dry-run) and coordinate how to provision OIDC/role access with infra.
3. Update docs (`docs/neo4j/server.md` and `config/README.md`) to include the operational steps and example IAM policy.
4. Add basic tests for the upload script using a `minio` local container in CI or via a local test runner.

Please confirm approval to proceed and indicate the following choices:

- preferred bucket name / prefix pattern (or if I should use a sandbox/test bucket),
- target retention days for prod/staging/dev,
- whether to require SSE-KMS or allow SSE-S3 initially.
