# Proposal: Add DockerHub Publishing

## Why

The Docker image is currently built in CI but not published to any container registry. This means:
- Images must be rebuilt on every deployment target
- No centralized versioning or quick rollbacks
- Cannot pull pre-built images for local development or production
- No vulnerability scanning or image provenance tracking

Publishing to DockerHub enables fast deployments, version tracking, and better reproducibility.

## What Changes

- Add GitHub Actions workflow steps to authenticate and push to DockerHub
- Publish to `chollomon/sbir-etl` repository on every push to main
- Implement semantic tagging:
  - `latest` for main branch pushes
  - `sha-<commit>` for all commits (immutable reference)
  - `v<version>` for git tags matching `v*` pattern
- Build for `linux/amd64` platform initially (arm64 support deferred)
- Add OCI metadata labels (git commit, build timestamp, version)
- Update README with image pull instructions

## Impact

### Affected Specs
- `runtime-environment`: Add DockerHub publishing and OCI metadata requirements

### Affected Code
- `.github/workflows/container-ci.yml`: Add login and push steps
- `Dockerfile`: Add LABEL instructions for OCI metadata
- `README.md`: Document image pulling and tagging strategy

### Benefits
- Instant deployments via `docker pull`
- Immutable image references via SHA tags
- Foundation for future multi-platform support

### Risks
- **Public images**: Repository will be public initially
  - Mitigation: Ensure no secrets in image (already enforced via env vars)
- **DockerHub rate limits**: Free tier has pull limits
  - Mitigation: Use personal account; can migrate to private registry later if needed
