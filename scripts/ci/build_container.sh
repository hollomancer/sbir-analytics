#!/usr/bin/env bash
#
# sbir-analytics/scripts/ci/build_container.sh
#
# CI-friendly container build script using Docker Buildx.
#
# Purpose:
#  - Build a multi-arch or single-arch container image using buildx.
#  - Support layer caching (cache-from / cache-to) when provided by CI.
#  - Optionally push the built image to a registry when PUBLISH=1.
#  - Provide sensible defaults and environment-driven configuration for CI pipelines.
#
# Usage:
#  - Local build (loads image into local Docker):
#      ./sbir-analytics/scripts/ci/build_container.sh
#
#  - CI build + push (example using GH Actions secrets):
#      REGISTRY=ghcr.io/my-org IMAGE_NAME=sbir-analytics IMAGE_TAG=ci-${GITHUB_SHA} PUBLISH=1 \
#        ./sbir-analytics/scripts/ci/build_container.sh
#
#  - Enable build cache via BuildKit cache (when CI supports it):
#      BUILDX_CACHE_FROM="type=gha" BUILDX_CACHE_TO="type=gha,mode=max" \
#        ./sbir-analytics/scripts/ci/build_container.sh
#
# Environment variables (defaults shown):
#  IMAGE_NAME        -> sbir-analytics
#  IMAGE_TAG         -> ci-${GITHUB_SHA:-local-<timestamp>}
#  REGISTRY          -> (empty) // if set, image is pushed to ${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}
#  DOCKERFILE        -> Dockerfile
#  CONTEXT           -> repository root (.)
#  PLATFORMS         -> linux/amd64 (comma separated for multi-arch)
#  BUILDX_BUILDER    -> sbir-builder
#  BUILDX_CACHE_FROM -> optional passed to buildx --cache-from (e.g., "type=gha")
#  BUILDX_CACHE_TO   -> optional passed to buildx --cache-to   (e.g., "type=gha,mode=max")
#  PUBLISH           -> if "1", perform push; otherwise load into local docker when possible
#  EXTRA_BUILD_ARGS  -> additional args to pass to docker buildx build
#
# Notes:
#  - This script attempts to create a buildx builder if none exists.
#  - In CI you should provide a registry and authentication (for example, GHCR login).
#  - When PUBLISH=1 the script uses `--push` (no local image load).
#  - When PUBLISH!=1 the script uses `--load` to make the image available locally.
#
set -euo pipefail

# -------------------------
# Configuration (defaults)
# -------------------------
REPO_ROOT_DIR="$(cd "$(dirname "$0")"/../.. >/dev/null 2>&1 || true; pwd -P)"
CONTEXT="${CONTEXT:-${REPO_ROOT_DIR}}"
DOCKERFILE="${DOCKERFILE:-${CONTEXT}/Dockerfile}"

IMAGE_NAME="${IMAGE_NAME:-sbir-analytics}"
# Default tag uses GITHUB_SHA if present, otherwise timestamp-local
if [ -n "${IMAGE_TAG:-}" ]; then
  IMAGE_TAG="${IMAGE_TAG}"
else
  if [ -n "${GITHUB_SHA:-}" ]; then
    IMAGE_TAG="${GITHUB_SHA}"
  else
    IMAGE_TAG="local-$(date -u +%Y%m%dT%H%M%SZ)"
  fi
fi

REGISTRY="${REGISTRY:-}"         # e.g. ghcr.io/my-org (leave empty to build local image only)
PLATFORMS="${PLATFORMS:-linux/amd64}"
BUILDX_BUILDER="${BUILDX_BUILDER:-sbir-builder}"
BUILDX_CACHE_FROM="${BUILDX_CACHE_FROM:-}"
BUILDX_CACHE_TO="${BUILDX_CACHE_TO:-}"
EXTRA_BUILD_ARGS="${EXTRA_BUILD_ARGS:-}"
PUBLISH="${PUBLISH:-0}"          # set to "1" to push to registry
DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-1}"

# Derived
if [ -n "${REGISTRY}" ]; then
  FULL_TAG="${REGISTRY%/}/${IMAGE_NAME}:${IMAGE_TAG}"
else
  FULL_TAG="${IMAGE_NAME}:${IMAGE_TAG}"
fi

# Buildx flags
BUILDX_FLAGS=()
# enable platforms if multi-arch requested
BUILDX_FLAGS+=(--platform "${PLATFORMS}")

# attach Dockerfile and context
BUILDX_FLAGS+=(--file "${DOCKERFILE}" "${CONTEXT}")

# tagging
BUILDX_FLAGS+=(--tag "${FULL_TAG}")

# progress/plain is more CI-friendly
BUILDX_FLAGS+=(--progress=plain)

# cache flags (optional)
if [ -n "${BUILDX_CACHE_FROM}" ]; then
  BUILDX_FLAGS+=(--cache-from "${BUILDX_CACHE_FROM}")
fi
if [ -n "${BUILDX_CACHE_TO}" ]; then
  BUILDX_FLAGS+=(--cache-to "${BUILDX_CACHE_TO}")
fi

# If not publishing, attempt to load built image into local Docker for testing.
if [ "${PUBLISH}" = "1" ]; then
  ACTION="push"
  BUILDX_FLAGS+=(--push)
else
  ACTION="load"
  # Using --load only works for single-platform builds. If multi-platform is requested and not publishing,
  # fall back to building for the first platform only to support local load.
  if echo "${PLATFORMS}" | grep -q ','; then
    # pick first platform for local load
    FIRST_PLATFORM="$(printf '%s' "${PLATFORMS}" | awk -F',' '{print $1}')"
    echo "Multi-platform requested (${PLATFORMS}) but PUBLISH!=1; switching to single-platform build '${FIRST_PLATFORM}' for --load compatibility."
    PLATFORMS="${FIRST_PLATFORM}"
    # override the existing platform flag in BUILDX_FLAGS
    # rebuild BUILDX_FLAGS minimal platform portion (this is acceptable because we rebuild below with --platform)
    # easiest approach: remove previous platform flag and append new one
    # (we keep other elements intact)
    # Not doing a surgical edit; just pass --platform again as last occurrence wins for buildx
    BUILDX_FLAGS+=(--platform "${PLATFORMS}")
  fi
  BUILDX_FLAGS+=(--load)
fi

# Allow additional custom build args (e.g., --build-arg SOME_VAR=val)
if [ -n "${EXTRA_BUILD_ARGS}" ]; then
  # shellcheck disable=SC2086
  BUILDX_FLAGS+=(${EXTRA_BUILD_ARGS})
fi

# -------------------------
# Helpers
# -------------------------
log() {
  printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

die() {
  echo >&2 "ERROR: $*"
  exit 1
}

# -------------------------
# Entrypoint
# -------------------------
log "CI build script starting"
log "Context: ${CONTEXT}"
log "Dockerfile: ${DOCKERFILE}"
log "Image: ${FULL_TAG}"
log "Action: ${ACTION}"
log "Platforms: ${PLATFORMS}"
if [ -n "${BUILDX_CACHE_FROM}" ]; then
  log "Cache-from: ${BUILDX_CACHE_FROM}"
fi
if [ -n "${BUILDX_CACHE_TO}" ]; then
  log "Cache-to: ${BUILDX_CACHE_TO}"
fi

# Ensure docker is available
if ! command -v docker >/dev/null 2>&1; then
  die "docker is not installed or not on PATH"
fi

# Ensure docker buildx is available
if ! docker buildx version >/dev/null 2>&1; then
  die "docker buildx is not available; ensure Docker >= 19.03 with buildx plugin"
fi

# Create and bootstrap builder if needed
if ! docker buildx inspect "${BUILDX_BUILDER}" >/dev/null 2>&1; then
  log "Creating buildx builder: ${BUILDX_BUILDER}"
  docker buildx create --name "${BUILDX_BUILDER}" --use >/dev/null 2>&1 || {
    # try without --use fallback
    docker buildx create --name "${BUILDX_BUILDER}" >/dev/null 2>&1 || die "failed to create buildx builder ${BUILDX_BUILDER}"
    docker buildx use "${BUILDX_BUILDER}" || die "failed to use buildx builder ${BUILDX_BUILDER}"
  }
else
  log "Using existing buildx builder: ${BUILDX_BUILDER}"
  docker buildx use "${BUILDX_BUILDER}" >/dev/null 2>&1 || true
fi

# Export DOCKER_BUILDKIT to ensure BuildKit mode
export DOCKER_BUILDKIT

# Build command
log "Invoking docker buildx build..."
# Buildx expects build flags before context; we assembled them accordingly.
# We use eval with an array to preserve quoting and spaces.
# Construct an array for the final invocation
cmd=(docker buildx build)
# append flags from BUILDX_FLAGS (they already include file/context/tag/platform/progress)
cmd+=("${BUILDX_FLAGS[@]}")

log "Final build command: ${cmd[*]}"

# Execute build
if "${cmd[@]}"; then
  log "Build succeeded: ${FULL_TAG}"
else
  die "Build failed for ${FULL_TAG}"
fi

# If we loaded the image locally, print a short summary
if [ "${PUBLISH}" != "1" ]; then
  log "Image was loaded into local docker. Showing image info:"
  docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}' | grep "${IMAGE_NAME}" || true
fi

# If publishing, we already used --push; final confirmation
if [ "${PUBLISH}" = "1" ]; then
  log "Image was pushed to registry: ${FULL_TAG}"
fi

log "CI build script completed successfully."
