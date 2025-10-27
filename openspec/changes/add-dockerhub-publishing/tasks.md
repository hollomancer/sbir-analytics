# Implementation Tasks

## 1. GitHub Secrets Configuration
- [ ] 1.1 Add `DOCKERHUB_USERNAME` secret to repository (value: `chollomon`)
- [ ] 1.2 Generate and add `DOCKERHUB_TOKEN` secret from DockerHub account settings
- [ ] 1.3 Verify secrets are accessible in workflow runs

## 2. Update Container CI Workflow
- [ ] 2.1 Add DockerHub login step using `docker/login-action@v3`
- [ ] 2.2 Update docker/build-push-action to enable `push: true` for main branch
- [ ] 2.3 Configure image tags using docker/metadata-action:
  - [ ] 2.3.1 Tag `latest` for main branch
  - [ ] 2.3.2 Tag `sha-{{sha}}` for commit reference
  - [ ] 2.3.3 Tag `{{version}}` for git tags matching `v*`
- [ ] 2.4 Add build-args for OCI labels (VERSION, GIT_SHA, BUILD_DATE)
- [ ] 2.5 Set target repository to `chollomon/sbir-etl`

## 3. Update Dockerfile for OCI Metadata
- [ ] 3.1 Add ARG declarations for VERSION, GIT_SHA, BUILD_DATE
- [ ] 3.2 Add LABEL instructions in runtime stage:
  - [ ] 3.2.1 `org.opencontainers.image.created`
  - [ ] 3.2.2 `org.opencontainers.image.source`
  - [ ] 3.2.3 `org.opencontainers.image.version`
  - [ ] 3.2.4 `org.opencontainers.image.revision`
  - [ ] 3.2.5 `org.opencontainers.image.title="sbir-etl"`
  - [ ] 3.2.6 `org.opencontainers.image.description`

## 4. Update Documentation
- [ ] 4.1 Add "Container Images" section to README.md with:
  - [ ] 4.1.1 DockerHub repository URL
  - [ ] 4.1.2 Available tags explanation
  - [ ] 4.1.3 Pull command example
  - [ ] 4.1.4 Run command example with env vars
- [ ] 4.2 Document tagging strategy in deployment docs (if applicable)

## 5. Testing & Validation
- [ ] 5.1 Test workflow by pushing to main branch
- [ ] 5.2 Verify image appears on DockerHub with correct tags
- [ ] 5.3 Pull published image and verify it runs: `docker pull chollomon/sbir-etl:latest`
- [ ] 5.4 Inspect image labels: `docker inspect chollomon/sbir-etl:latest`
- [ ] 5.5 Run `openspec validate add-dockerhub-publishing --strict`
