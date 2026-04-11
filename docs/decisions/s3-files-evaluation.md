# Evaluation: Amazon S3 Files for SBIR Analytics

**Date:** 2026-04-11
**Status:** Evaluation / Not Recommended (at this time)

## What Is S3 Files?

Amazon S3 Files (GA April 2026) adds a managed NFS v4.2 file system interface on top of
S3 buckets. It provisions a high-performance caching layer backed by Amazon EFS
infrastructure, giving compute resources (EC2, Lambda, ECS, EKS, Fargate) the ability to
mount an S3 bucket as a POSIX-compatible NFS share.

### How It Works

1. **Enable S3 Files** on a bucket via `create-file-system`.
2. **Create a mount target** in your VPC (`create-mount-target`).
3. **NFS mount** from compute using the standard EFS mount helper (`amazon-efs-utils`).
4. Data written via NFS hits a **high-performance EFS-backed cache first**, then syncs to
   S3 in ~60-second batches.
5. Small files (<128 KB default) are served from the cache with **sub-millisecond latency**.
   Large files (>=1 MB) stream directly from S3.
6. Existing S3 API access (boto3 `get_object`/`put_object`) continues to work alongside
   NFS access against the same bucket.

### Key Characteristics

| Property | Detail |
|----------|--------|
| Protocol | NFS v4.1 / v4.2 |
| Consistency | NFS close-to-open; S3 strong read-after-write |
| Write sync delay | ~60 seconds (writes visible via NFS immediately, S3 API after sync) |
| Small file read latency | Sub-millisecond (from EFS cache) |
| Large file read latency | Same as S3 (streams directly) |
| POSIX support | File locking, permissions, read-after-write |
| Pricing (cache layer) | $0.30/GB-month high-perf storage, $0.03/GB reads, $0.06/GB writes |
| Pricing (large reads) | No S3 Files charge; standard S3 pricing applies |

## Current SBIR Analytics S3 Architecture

Our codebase already has mature S3 integration:

- **`sbir_etl/utils/cloud_storage.py`**: S3-first resolution with local fallback
  (`resolve_data_path()`, `resolve_sbir_awards_csv()`)
- **boto3 + cloudpathlib**: `boto3>=1.34.0` and `cloudpathlib[s3]>=0.23.0` in `[cloud]` extra
- **Extractors**: SBIR, USAspending, SAM.gov, and USPTO all support S3 source paths
- **Dagster assets**: Upload results to S3 via `boto3.client('s3').put_object()`
- **CDK StorageStack**: Lifecycle rules, Intelligent Tiering, Glacier transitions
- **Sensor**: `usaspending_refresh_sensor` monitors S3 for new data dumps
- **Config**: `use_s3_first`, `csv_path_s3`, `parquet_path_s3` keys in `config/base.yaml`

### Data Access Pattern

```
S3 bucket (sbir-etl-production-data)
  ↓ boto3 download / cloudpathlib
Local temp cache (/tmp/sbir-analytics-s3-cache/)
  ↓ standard file I/O
DuckDB / pandas / pyarrow
```

## Evaluation Against Our Workload

### Where S3 Files Could Help

1. **Eliminate the download-to-temp step.** Today `_download_s3_to_temp()` downloads full
   files before DuckDB can read them. With S3 Files mounted, DuckDB could read directly
   from the mount path — no temp cache management, no stale cache concerns.

2. **Simplify `cloud_storage.py`.** The entire `resolve_data_path()` / S3-vs-local
   fallback logic could be replaced by a single mount point. Code would just read
   `/mnt/s3-data/raw/awards/...` as a normal file path.

3. **Small file metadata reads.** If we add many small enrichment cache files or
   checkpoint JSONs, the sub-ms latency from the EFS cache would outperform repeated
   boto3 `get_object` calls.

### Why It Doesn't Fit (Yet)

**1. Our files are large, not small.**
The primary data files are CSVs (100+ MB), Parquet files (500+ MB), and database dumps
(multi-GB ZIPs). S3 Files streams large files (>=1 MB) directly from S3 with no caching
benefit. Our current boto3 download + local read approach has identical throughput for
these workloads.

**2. The 60-second write sync delay is a liability.**
Our pipeline writes validated/enriched Parquet files to S3 and then immediately triggers
downstream assets (e.g., Neo4j loading) that may read them. A 60-second window where
writes are visible via NFS but not via S3 API creates a consistency hazard — especially
since our Dagster sensors and some assets use the S3 API directly.

**3. Adds VPC and networking complexity.**
S3 Files requires a mount target in your VPC, security group configuration, and the EFS
mount helper on every compute instance. Our current setup uses standard boto3 calls that
work from any environment (EC2, Lambda, GitHub Actions, local dev) with just IAM
credentials. NFS mounts don't work in Lambda (except via EFS mount targets with
VPC-attached Lambda), and they add operational surface area for a small team.

**4. Additional cost with unclear ROI.**
The $0.30/GB-month cache layer charge is on top of standard S3 costs. For our workload
(dominated by large sequential reads), the cache rarely activates. We'd pay more for
infrastructure without measurable performance improvement.

**5. Breaks local development parity.**
Developers currently run the pipeline locally with `use_s3_first: false` against files
in `data/raw/`. An NFS-mount-dependent architecture would require either:
- A mock filesystem / local mount emulation
- Maintaining the current dual-path code anyway (negating the simplification benefit)

**6. DuckDB has native S3 support we haven't enabled.**
DuckDB can read from `s3://` paths directly via its `httpfs` extension — without any
filesystem mount. If we want to skip the download step, enabling DuckDB's native S3
support is simpler, cheaper, and works everywhere (local + cloud) with just IAM config:
```sql
INSTALL httpfs;
LOAD httpfs;
SET s3_region='us-east-2';
SELECT * FROM read_csv_auto('s3://sbir-etl-production-data/raw/awards/.../award_data.csv');
```

## Alternatives That Solve the Same Problems Better

| Goal | S3 Files | Better Alternative |
|------|----------|-------------------|
| Skip download-to-temp | NFS mount | DuckDB `httpfs` extension (native S3 reads) |
| Simplify path resolution | Mount path | Consolidate config; fewer fallback branches |
| Fast small-file access | EFS cache | S3 Express One Zone (single-digit ms, no NFS) |
| Shared mutable filesystem | NFS mount | Not needed — our pipeline is write-once, read-many |

## Recommendation

**Do not adopt S3 Files at this time.** The feature solves problems we don't have
(shared mutable file access, small-file read latency) while introducing problems we'd
need to manage (write sync delay, VPC networking, cost overhead, broken dev parity).

### If Revisiting Later

S3 Files would become more relevant if:
- We add interactive/agentic workloads that need shared mutable file access across
  multiple concurrent compute instances
- We move to an ECS/EKS deployment where NFS mounts are a natural fit
- We accumulate many small metadata/cache files that benefit from sub-ms reads

### Recommended Next Steps Instead

1. **Evaluate DuckDB `httpfs`** for direct S3 reads — eliminates the temp download step
   with zero infrastructure changes.
2. **Evaluate S3 Express One Zone** if we need lower-latency object access for
   enrichment cache files.
3. **Simplify `cloud_storage.py`** — the current fallback logic has grown organically and
   could benefit from consolidation regardless of S3 Files.

## Sources

- [AWS Blog: Launching S3 Files](https://aws.amazon.com/blogs/aws/launching-s3-files-making-s3-buckets-accessible-as-file-systems/)
- [The New Stack: S3 Files Filesystem](https://thenewstack.io/aws-s3-files-filesystem/)
- [S3 Files vs Mountpoint vs s3fs-fuse](https://computingforgeeks.com/s3-files-vs-mountpoint-vs-s3fs/)
- [S3 Files Guide: Setup, Performance, Pricing](https://computingforgeeks.com/amazon-s3-files-guide-setup-performance-pricing/)
- [S3 Files GA: Compared with EFS](https://dev.classmethod.jp/en/articles/amazon-s3-files-ga-mount-and-compare-efs/)
- [Last Week in AWS: S3 Is Not a Filesystem](https://www.lastweekinaws.com/blog/s3-is-not-a-filesystem-but-now-theres-one-in-front-of-it/)
- [S3 Files Pricing, Use Cases & Comparison](https://lushbinary.com/blog/amazon-s3-files-guide-pricing-use-cases-efs-fsx-comparison/)
- [AWS Docs: Working with S3 Files](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-files.html)
