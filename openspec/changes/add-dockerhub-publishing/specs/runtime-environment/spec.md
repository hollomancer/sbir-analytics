# runtime-environment Spec Delta

## ADDED Requirements

### Requirement: DockerHub Image Publishing
The CI pipeline SHALL publish Docker images to DockerHub on every push to the main branch with semantic versioning tags.

#### Scenario: Publish image on main branch push
- **WHEN** a commit is pushed to the `main` branch
- **THEN** the CI workflow authenticates with DockerHub using repository secrets
- **AND** builds the image for `linux/amd64` platform
- **AND** pushes the image to `chollomon/sbir-etl` with tags `latest` and `sha-<commit-sha>`
- **AND** the image is publicly available within 5 minutes

#### Scenario: Publish versioned release image  
- **WHEN** a git tag matching pattern `v*` is pushed (e.g., `v1.2.3`)
- **THEN** the CI workflow builds and publishes with tags `latest`, `v1.2.3`, and `sha-<commit-sha>`
- **AND** users can pull specific versions via `docker pull chollomon/sbir-etl:v1.2.3`

#### Scenario: Immutable commit reference
- **WHEN** any commit to main is published
- **THEN** it receives a `sha-<commit-sha>` tag (e.g., `sha-abc1234`)
- **AND** this tag provides an immutable reference for reproducible deployments

### Requirement: OCI Image Metadata Labels
Published Docker images SHALL include OCI-compliant metadata labels for version tracking, provenance, and security scanning integration.

#### Scenario: Image metadata for provenance
- **WHEN** an image is inspected via `docker inspect chollomon/sbir-etl:latest`
- **THEN** the output includes OCI labels:
  - `org.opencontainers.image.created` with ISO 8601 build timestamp
  - `org.opencontainers.image.source` with GitHub repository URL
  - `org.opencontainers.image.version` with git tag or commit SHA
  - `org.opencontainers.image.revision` with full git commit SHA
  - `org.opencontainers.image.title` set to `sbir-etl`
  - `org.opencontainers.image.description` with project summary

#### Scenario: Security scanner integration
- **WHEN** DockerHub scans the published image for vulnerabilities
- **THEN** it extracts metadata labels to associate findings with specific commits
- **AND** developers can trace vulnerabilities to source code via `org.opencontainers.image.revision`

### Requirement: Image Pull Documentation
The project README SHALL document how to pull and run published images from DockerHub with clear examples.

#### Scenario: Quick start with published image
- **WHEN** a developer reads the README "Container Images" section
- **THEN** they find:
  - DockerHub repository link (`https://hub.docker.com/r/chollomon/sbir-etl`)
  - Explanation of available tags (`latest`, `sha-*`, `v*`)
  - Pull command: `docker pull chollomon/sbir-etl:latest`
  - Example run command with required environment variables

#### Scenario: Version pinning for production
- **WHEN** deploying to production
- **THEN** documentation recommends pinning to SHA tags for immutability
- **AND** provides example: `docker pull chollomon/sbir-etl:sha-abc1234`

## MODIFIED Requirements

### Requirement: Multi-Stage SBIR ETL Image Build
The project SHALL provide a deterministic multi-stage Docker build that separates dependency resolution from the runtime image, enforces non-root execution, and includes OCI metadata labels.

#### Scenario: Build deterministic runtime layer
- **WHEN** `docker build -t sbir-etl:latest .` runs
- **THEN** the builder stage installs Poetry dependencies with `poetry install --only main --no-root`
- **AND** the runtime stage copies installed packages, application code, and scripts to `/app`
- **AND** the final image includes `tini` as PID 1 and runs as non-root user `sbir`
- **AND** OCI metadata labels are embedded via build args

#### Scenario: Cache-friendly dependency install
- **WHEN** only `src/` files change between builds
- **THEN** Docker reuses cached layers up to the Poetry install step
- **AND** rebuild completes in under 30 seconds with warm cache

#### Scenario: OCI metadata via build args
- **WHEN** building with `--build-arg VERSION=1.2.3 --build-arg GIT_SHA=abc123 --build-arg BUILD_DATE=2025-10-27T10:00:00Z`
- **THEN** the Dockerfile uses these args to populate OCI labels
- **AND** defaults to empty values for local builds without args
