# USAspending Download Issues - Root Cause Analysis

## Problem Summary

The script `scripts/usaspending/download_database.py` fails when downloading large files (~20GB) due to connection instability. Errors include:
- `IncompleteRead` - Connection breaks mid-stream
- `BrokenPipeError` - Connection closed unexpectedly
- `TimeoutError` - Connection idle timeout

## Root Causes

### 1. **Connection Instability for Long Downloads**
- Downloading 20GB in a single connection takes hours
- Network equipment (proxies, routers, firewalls) may timeout long connections
- Server may close idle connections
- Local network may be unstable

### 2. **No Resume Capability**
- When connection breaks, download restarts from beginning
- All progress is lost (e.g., if 14GB downloaded and connection breaks, restart from 0GB)
- No HTTP Range request support to resume from byte offset

### 3. **Architectural Limitation**
- Current approach: Single streaming connection for entire file
- Inherently fragile for multi-hour downloads
- Retries help but are inefficient (must restart entire download)

## Current Mitigations

The script currently includes:
- ✅ HTTP-level retries (urllib3)
- ✅ Download-level retries (up to 10 attempts)
- ✅ Chunk-level S3 upload retries
- ✅ Large timeouts (24 hour read timeout)
- ❌ **No resume capability**

## Recommended Solutions

### Option 1: Use Tools with Built-in Resume (Recommended for Quick Fix)

Use `wget` or `curl` which have robust resume capability:

```bash
# Download with resume capability
wget --continue --timeout=3600 --tries=10 \
  https://files.usaspending.gov/database_download/usaspending-db-subset_20251106.zip

# Then upload to S3
aws s3 cp usaspending-db-subset_20251106.zip s3://bucket/path/ --multipart-upload
```

### Option 2: Implement HTTP Range Requests (Best Long-term Solution)

Modify the script to support resume:
1. Track bytes downloaded (save to checkpoint file)
2. Use HTTP `Range: bytes=START-END` header to resume
3. Append to existing chunks instead of restarting

**Implementation sketch:**
```python
# Check if partial download exists
checkpoint_file = Path(f"{s3_key}.checkpoint")
if checkpoint_file.exists():
    bytes_downloaded = int(checkpoint_file.read_text())
    headers["Range"] = f"bytes={bytes_downloaded}-"

# After each chunk, update checkpoint
checkpoint_file.write_text(str(total_size))
```

### Option 3: Use Cloud Instance (EC2/Fargate)

Run download on EC2 instance:
- Better network stability
- No local network issues
- Can run unattended
- Existing Lambda handler could be adapted

### Option 4: Use S3 Transfer Acceleration or Direct Transfer

If USAspending data is available in S3 bucket:
- Direct S3-to-S3 copy (fast, reliable)
- Use S3 Transfer Acceleration
- No download required

## Immediate Workaround

For now, the script will retry up to 10 times. If it continues to fail:
1. Run on a more stable network (EC2 instance, better WiFi)
2. Use `wget` with `--continue` flag (manual download, then upload)
3. Consider downloading during off-peak hours when network is more stable

## References

- HTTP Range requests: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Range_requests
- wget resume: `wget --continue`
- AWS S3 multipart uploads: Already implemented in script
