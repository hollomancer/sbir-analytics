---
Type: Guide
Owner: devops@project
Last-Reviewed: 2025-01-XX
Status: active
---

# Docker Troubleshooting Guide

This guide helps you diagnose and fix common issues with the Docker development setup.

## Quick Diagnostics

**First, run these checks:**

```bash
# 1. Check prerequisites
make docker-check-prerequisites

# 2. Check service status
docker compose --profile dev ps

# 3. Verify setup
make docker-verify

# 4. Check logs
make docker-logs SERVICE=<service-name>
```

## Common Issues

### Prerequisites Issues

#### Problem: Docker not found

**Symptoms:**
```
✖ Docker CLI not found
```

**Solutions:**
1. **Install Docker Desktop:**
   - macOS/Windows: https://www.docker.com/products/docker-desktop
   - Linux: https://docs.docker.com/engine/install/

2. **Verify installation:**
   ```bash
   docker --version
   # Should show: Docker version 20.10 or higher
   ```

3. **Add to PATH** (if needed):
   - Docker Desktop usually handles this automatically
   - Linux: May need to add user to `docker` group

#### Problem: Docker daemon not running

**Symptoms:**
```
✖ Docker daemon is not running or not accessible
```

**Solutions:**
1. **Start Docker Desktop:**
   - macOS: Open Docker Desktop app
   - Windows: Start Docker Desktop
   - Linux: `sudo systemctl start docker`

2. **Verify daemon:**
   ```bash
   docker info
   # Should show Docker system information
   ```

3. **Check Docker Desktop status:**
   - Look for Docker icon in system tray
   - Ensure it shows "Docker Desktop is running"

#### Problem: Docker Compose V2 not found

**Symptoms:**
```
✖ Docker Compose V2 not found
```

**Solutions:**
1. **Docker Desktop includes Compose V2:**
   - Update Docker Desktop to latest version
   - Compose V2 is included automatically

2. **Verify Compose:**
   ```bash
   docker compose version
   # Should show: Docker Compose version v2.x.x
   ```

3. **Linux manual install:**
   ```bash
   # See: https://docs.docker.com/compose/install/
   ```

#### Problem: Ports already in use

**Symptoms:**
```
⚠ Port 3000 is in use (may cause conflicts)
```

**Solutions:**
1. **Find what's using the port:**
   ```bash
   # macOS/Linux
   lsof -i :3000
   
   # Or
   netstat -an | grep 3000
   ```

2. **Stop conflicting service:**
   ```bash
   # If it's another Docker container
   docker ps
   docker stop <container-id>
   
   # If it's a local process
   kill <pid>
   ```

3. **Use different ports:**
   ```bash
   # In .env
   DAGSTER_PORT=3001
   NEO4J_HTTP_PORT=7475
   NEO4J_BOLT_PORT=7688
   ```

4. **Update docker-compose.yml** (if changing ports):
   - Modify port mappings in `docker-compose.yml`
   - Restart services: `make docker-down && make docker-up-dev`

### Build Issues

#### Problem: Build fails with "out of space"

**Symptoms:**
```
ERROR: failed to solve: no space left on device
```

**Solutions:**
1. **Check disk space:**
   ```bash
   docker system df
   # Shows Docker disk usage
   ```

2. **Clean up Docker:**
   ```bash
   # Remove unused images, containers, volumes
   docker system prune -a
   
   # Remove unused volumes (careful - deletes data)
   docker volume prune
   ```

3. **Free up space:**
   - Delete old Docker images: `docker image prune -a`
   - Remove stopped containers: `docker container prune`
   - Clear build cache: `docker builder prune`

4. **Increase Docker disk space:**
   - Docker Desktop: Settings → Resources → Advanced
   - Increase disk image size

#### Problem: Build is very slow (R packages)

**Symptoms:**
- Build takes 20+ minutes
- Stuck at "Installing R packages"

**Solutions:**
1. **This is normal for first build:**
   - R package installation takes 5-10 minutes
   - Subsequent builds are faster (caching)

2. **Check Docker resources:**
   - Docker Desktop: Settings → Resources
   - Allocate more CPU/RAM if available
   - Recommended: 4GB+ RAM, 2+ CPUs

3. **Monitor build progress:**
   ```bash
   # Build with verbose output
   DOCKER_BUILDKIT=1 docker build --progress=plain -t sbir-analytics:latest .
   ```

4. **Use build cache:**
   - Don't use `--no-cache` unless necessary
   - Rebuilds are faster due to layer caching

#### Problem: Build fails with R package errors

**Symptoms:**
```
Error in install.packages: package 'arrow' failed to install
```

**Solutions:**
1. **Check Docker resources:**
   - R package compilation needs memory
   - Increase Docker RAM: Settings → Resources → Advanced

2. **Retry build:**
   ```bash
   # Sometimes network issues cause failures
   make docker-build
   ```

3. **Check logs:**
   ```bash
   # Build with output
   docker build -t sbir-analytics:latest . 2>&1 | tee build.log
   # Review build.log for specific errors
   ```

4. **Manual R package install (if needed):**
   ```bash
   # Enter builder container
   docker run -it --rm python:3.11-slim bash
   
   # Install R packages manually to debug
   ```

### Service Startup Issues

#### Problem: Services won't start

**Symptoms:**
```
Error: failed to start containers
```

**Solutions:**
1. **Check service status:**
   ```bash
   docker compose --profile dev ps
   # Shows which services are running/failed
   ```

2. **Check logs:**
   ```bash
   make docker-logs SERVICE=neo4j
   make docker-logs SERVICE=dagster-webserver
   ```

3. **Check prerequisites:**
   ```bash
   make docker-check-prerequisites
   ```

4. **Restart services:**
   ```bash
   make docker-down
   make docker-up-dev
   ```

#### Problem: Neo4j won't start

**Symptoms:**
```
neo4j | Error starting Neo4j
```

**Solutions:**
1. **Check Neo4j logs:**
   ```bash
   make docker-logs SERVICE=neo4j
   ```

2. **Check credentials:**
   ```bash
   # Verify .env has correct credentials
   grep NEO4J .env
   ```

3. **Check port conflicts:**
   ```bash
   lsof -i :7474
   lsof -i :7687
   ```

4. **Reset Neo4j volumes:**
   ```bash
   make neo4j-reset
   # WARNING: This deletes all Neo4j data
   ```

5. **Check memory:**
   - Neo4j needs memory to start
   - Increase Docker RAM if needed
   - Check Neo4j memory settings in `config/neo4j/neo4j.conf`

#### Problem: Dagster webserver won't start

**Symptoms:**
```
dagster-webserver | Error: Failed to start
```

**Solutions:**
1. **Check Dagster logs:**
   ```bash
   make docker-logs SERVICE=dagster-webserver
   ```

2. **Check Neo4j is ready:**
   ```bash
   make neo4j-check
   # Dagster waits for Neo4j, but may timeout
   ```

3. **Check port 3000:**
   ```bash
   lsof -i :3000
   ```

4. **Increase startup timeout:**
   ```bash
   # In .env
   SERVICE_STARTUP_TIMEOUT=180
   ```

5. **Check Python path:**
   ```bash
   # Verify PYTHONPATH is set
   docker compose --profile dev exec dagster-webserver env | grep PYTHON
   ```

### Connection Issues

#### Problem: Can't connect to Neo4j

**Symptoms:**
```
make docker-verify
✖ Neo4j is not accessible
```

**Solutions:**
1. **Check Neo4j is running:**
   ```bash
   docker compose --profile dev ps neo4j
   # Should show "Up" status
   ```

2. **Check credentials:**
   ```bash
   # Verify .env credentials match Neo4j container
   grep NEO4J .env
   ```

3. **Test connection manually:**
   ```bash
   docker compose --profile dev exec neo4j \
     cypher-shell -u neo4j -p test 'RETURN 1'
   ```

4. **Check Neo4j logs:**
   ```bash
   make docker-logs SERVICE=neo4j
   # Look for authentication errors
   ```

5. **Verify port mapping:**
   ```bash
   # Check port 7687 is accessible
   nc -zv localhost 7687
   ```

#### Problem: Can't access Dagster UI

**Symptoms:**
```
make docker-verify
✖ Dagster UI is not accessible
```

**Solutions:**
1. **Check Dagster is running:**
   ```bash
   docker compose --profile dev ps dagster-webserver
   ```

2. **Check port 3000:**
   ```bash
   lsof -i :3000
   # Should show dagster-webserver container
   ```

3. **Check Dagster logs:**
   ```bash
   make docker-logs SERVICE=dagster-webserver
   # Look for startup errors
   ```

4. **Wait for startup:**
   - Dagster takes 30-60 seconds to start
   - Check logs for "Server started" message

5. **Try direct connection:**
   ```bash
   curl http://localhost:3000/server_info
   # Should return JSON
   ```

### Performance Issues

#### Problem: Services are slow

**Symptoms:**
- Slow response times
- Timeouts
- High CPU/memory usage

**Solutions:**
1. **Check Docker resources:**
   - Docker Desktop: Settings → Resources
   - Allocate more CPU/RAM
   - Recommended: 4GB+ RAM, 2+ CPUs

2. **Check system resources:**
   ```bash
   # macOS
   Activity Monitor
   
   # Linux
   htop
   ```

3. **Check container resources:**
   ```bash
   docker stats
   # Shows CPU/memory usage per container
   ```

4. **Optimize Neo4j memory:**
   ```bash
   # In config/neo4j/neo4j.conf or .env
   NEO4J_server_memory_heap_max__size=1G
   NEO4J_server_memory_pagecache_size=512M
   ```

5. **Reduce data size:**
   - Use sample data for development
   - Set `SBIR_ETL__EXTRACTION__SAMPLE_LIMIT=1000` in `.env`

### Data Issues

#### Problem: Data not persisting

**Symptoms:**
- Data disappears after restart
- Volumes not mounted correctly

**Solutions:**
1. **Check volume mounts:**
   ```bash
   docker compose --profile dev config
   # Shows volume configuration
   ```

2. **Check data directory:**
   ```bash
   ls -la data/
   # Should show data files
   ```

3. **Verify bind mounts:**
   - Development profile uses bind mounts
   - Data should persist in `./data` directory

4. **Check Neo4j volumes:**
   ```bash
   docker volume ls | grep neo4j
   # Should show neo4j_data, neo4j_logs, neo4j_import
   ```

### Environment Variable Issues

#### Problem: Environment variables not working

**Symptoms:**
- Variables in `.env` not taking effect
- Wrong values being used

**Solutions:**
1. **Check `.env` location:**
   ```bash
   # Must be in project root
   ls -la .env
   ```

2. **Check variable syntax:**
   ```bash
   # No spaces around =
   NEO4J_USER=neo4j  # ✓ Correct
   NEO4J_USER = neo4j  # ✗ Wrong
   ```

3. **Restart services:**
   ```bash
   make docker-down
   make docker-up-dev
   # Environment variables loaded at startup
   ```

4. **Check variable precedence:**
   - System env vars override `.env`
   - Check: `env | grep NEO4J`

5. **Verify in container:**
   ```bash
   docker compose --profile dev exec dagster-webserver env | grep NEO4J
   ```

## Diagnostic Commands

### Service Status

```bash
# All services
docker compose --profile dev ps

# Specific service
docker compose --profile dev ps neo4j

# With logs
docker compose --profile dev ps --format json
```

### View Logs

```bash
# All services
docker compose --profile dev logs

# Specific service
make docker-logs SERVICE=neo4j
make docker-logs SERVICE=dagster-webserver

# Follow logs
docker compose --profile dev logs -f

# Last 100 lines
docker compose --profile dev logs --tail=100
```

### Container Inspection

```bash
# Container details
docker compose --profile dev exec neo4j env

# Container resources
docker stats

# Container shell
docker compose --profile dev exec neo4j sh
```

### Network Diagnostics

```bash
# Check ports
lsof -i :3000
lsof -i :7474
lsof -i :7687

# Test connectivity
nc -zv localhost 7687
curl http://localhost:3000/server_info
```

## Getting Help

If you're still stuck:

1. **Check logs:**
   ```bash
   make docker-logs SERVICE=<service>
   ```

2. **Run diagnostics:**
   ```bash
   make docker-check-prerequisites
   make docker-verify
   ```

3. **Review documentation:**
   - [Docker Quick Start](docker-quickstart.md)
   - [Environment Setup](docker-env-setup.md)
   - [Containerization Guide](../deployment/containerization.md)

4. **Check GitHub issues:**
   - Search existing issues
   - Create new issue with:
     - Error messages
     - Logs output
     - Steps to reproduce

## Prevention Tips

1. **Always check prerequisites first:**
   ```bash
   make docker-check-prerequisites
   ```

2. **Verify setup after changes:**
   ```bash
   make docker-verify
   ```

3. **Keep Docker updated:**
   - Update Docker Desktop regularly
   - Check for Docker updates

4. **Monitor resources:**
   - Ensure sufficient disk space
   - Allocate enough RAM/CPU to Docker

5. **Use version control:**
   - Don't commit `.env` (it's gitignored)
   - Document environment setup in team docs

---

**Still need help?** Check the [Docker Quick Start](docker-quickstart.md) or [Containerization Guide](../deployment/containerization.md) for more information.

