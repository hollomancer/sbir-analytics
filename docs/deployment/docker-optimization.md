# Docker Image Optimization Guide

## Current Optimizations

### Multi-Stage Build
- **Builder stage**: Compiles wheels, installs build dependencies
- **Runtime stage**: Only includes runtime dependencies and wheels
- **Impact**: ~60% smaller final image

### Layer Caching
- Dependencies copied before code for better cache hits
- UV cache mounted for faster builds
- Pip cache mounted for wheel building
- **Impact**: 2-3x faster rebuilds

### .dockerignore Optimization
- Excludes 100+ MB of unnecessary files:
  - Test data and fixtures
  - CI/CD configurations
  - Documentation and notebooks
  - Build artifacts and caches
  - Development tools
- **Impact**: Faster context transfer, smaller image

### Conditional R Installation
- R packages only installed when needed
- Pre-built R base image option for faster builds
- **Impact**: 40% faster builds without R

## Image Size Comparison

| Build Type | Size | Build Time |
|------------|------|------------|
| Full (with R) | ~1.2 GB | ~5 min |
| With R cache | ~1.2 GB | ~2 min |
| Without R (CI) | ~800 MB | ~2 min |

## Build Optimization Tips

### 1. Use BuildKit
```bash
DOCKER_BUILDKIT=1 docker build -t sbir-analytics .
```

### 2. Use Cache Mounts
Already implemented in Dockerfile:
```dockerfile
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cache/pip
```

### 3. Layer Ordering
Dependencies before code for better caching:
```dockerfile
COPY pyproject.toml uv.lock* /workspace/  # Changes rarely
# ... build dependencies ...
COPY . /workspace/  # Changes frequently
```

### 4. Multi-Platform Builds
```bash
docker buildx build --platform linux/amd64,linux/arm64 -t sbir-analytics .
```

## Runtime Optimizations

### 1. Non-Root User
- Runs as `sbir` user (UID 1000)
- Better security posture
- Compatible with Kubernetes security policies

### 2. Minimal Runtime Dependencies
- Only essential packages in runtime stage
- Build tools excluded
- Test dependencies excluded

### 3. Tini for PID 1
- Proper signal handling
- Zombie process reaping
- Clean shutdown

## Further Optimization Opportunities

### 1. Distroless Base (Advanced)
Switch to distroless for even smaller images:
```dockerfile
FROM gcr.io/distroless/python3-debian12
```
**Trade-off**: No shell, harder debugging

### 2. Alpine Base (Not Recommended)
Alpine is smaller but has compatibility issues:
- musl vs glibc differences
- Slower Python performance
- Wheel compatibility problems

### 3. Slim Down Python
Remove unnecessary Python stdlib modules:
```dockerfile
RUN find /usr/local/lib/python3.11 -name "test" -type d -exec rm -rf {} +
RUN find /usr/local/lib/python3.11 -name "*.pyc" -delete
```
**Impact**: ~50 MB saved

## Monitoring Image Size

### Check Layer Sizes
```bash
docker history sbir-analytics:latest --human --no-trunc
```

### Analyze Image
```bash
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  wagoodman/dive sbir-analytics:latest
```

### Compare Builds
```bash
docker images sbir-analytics --format "table {{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
```

## CI/CD Integration

### GitHub Actions Cache
Already implemented in ci.yml:
```yaml
cache-from: |
  type=registry,ref=ghcr.io/${{ github.repository }}:latest
  type=gha,scope=ci-no-r
cache-to: type=gha,mode=max,scope=ci-no-r
```

### Registry Cache
Push to GHCR for cross-runner caching:
```yaml
push: ${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}
```

## Best Practices

1. ✅ **Multi-stage builds** - Separate build and runtime
2. ✅ **Layer caching** - Order layers by change frequency
3. ✅ **Cache mounts** - Use BuildKit cache mounts
4. ✅ **.dockerignore** - Exclude unnecessary files
5. ✅ **Minimal base** - Use slim images
6. ✅ **Non-root user** - Security best practice
7. ✅ **Conditional features** - R installation optional
8. ✅ **Registry caching** - Push cache layers to registry

## Troubleshooting

### Large Image Size
```bash
# Find large layers
docker history sbir-analytics:latest --human | head -20

# Check what's in the image
docker run --rm sbir-analytics:latest du -sh /app/* | sort -h
```

### Slow Builds
```bash
# Check cache hits
DOCKER_BUILDKIT=1 docker build --progress=plain -t sbir-analytics . 2>&1 | grep CACHED

# Use build cache from registry
docker build --cache-from ghcr.io/your-repo/sbir-analytics:latest .
```

### Build Failures
```bash
# Debug specific stage
docker build --target builder -t debug .
docker run --rm -it debug /bin/bash
```

## References

- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [BuildKit Documentation](https://docs.docker.com/build/buildkit/)
- [Multi-stage Builds](https://docs.docker.com/build/building/multi-stage/)
