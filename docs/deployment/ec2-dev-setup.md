# EC2 Development Environment

Run the full SBIR Analytics stack on an EC2 instance instead of a local machine. DuckDB is the primary data store — Neo4j is available as an opt-in graph layer.

## Architecture

```text
┌─────────────────────────────────────────────────────┐
│  EC2 t3.medium  (4 GB / 2 vCPU / 50 GB gp3)        │
│                                                      │
│  ┌──────────────────┐  ┌─────────────────────────┐  │
│  │ dagster-webserver │  │ dagster-daemon          │  │
│  │ :3000             │  │                         │  │
│  └──────────────────┘  └─────────────────────────┘  │
│  ┌──────────────────┐  ┌─────────────────────────┐  │
│  │ etl-runner        │  │ tools                   │  │
│  └──────────────────┘  └─────────────────────────┘  │
│                                                      │
│  Data: DuckDB (data/processed/sbir.duckdb)           │
│  Storage: S3 via instance role                       │
│                                                      │
│  ┌─ opt-in (--profile neo4j) ──────────────────────┐│
│  │  neo4j :7474/:7687  │  neodash :5005            ││
│  └─────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────┘
```

## Quick Start

### Option A: CDK (recommended)

```bash
cd infrastructure/cdk

# Deploy the EC2 dev instance
cdk deploy sbir-analytics-ec2-dev \
  --context key_pair_name=your-key-pair \
  --context allowed_ssh_cidr=YOUR_IP/32

# Connect via SSM (no SSH key needed)
aws ssm start-session --target <instance-id> --region us-east-2
```

### Option B: Existing EC2 instance

```bash
# On the EC2 instance:
curl -sSL https://raw.githubusercontent.com/hollomancer/sbir-analytics/main/scripts/dev/setup-ec2-dev.sh | bash
```

### Start the stack

```bash
cd ~/sbir-analytics

# DuckDB-only (default, no Neo4j)
docker compose --profile ec2-dev up -d --build

# With Neo4j graph layer
docker compose --profile ec2-dev --profile neo4j up -d --build
```

Open Dagster UI at `http://<instance-ip>:3000`.

## Profiles

| Command | What runs |
|---------|-----------|
| `--profile ec2-dev` | Dagster + ETL + DuckDB |
| `--profile ec2-dev --profile neo4j` | Above + Neo4j + NeoDash |
| `--profile dev` | Local dev (same as ec2-dev, for laptops) |
| `--profile ci` | CI testing |

## Why EC2 instead of local?

| | Local dev | EC2 dev |
|---|---|---|
| **Resources** | Limited by laptop | Tunable (t3.medium to t3.xlarge) |
| **S3 access** | Needs AWS credentials | Instance role (zero config) |
| **Long jobs** | Ties up your machine | Runs in background |
| **Collaboration** | One developer | Share instance URL |
| **Cost** | Free | ~$30/month (t3.medium) |

## Why DuckDB-first?

The containerized stack no longer requires Neo4j to run ETL pipelines. DuckDB handles:

- SBIR award extraction and validation
- USAspending enrichment
- Patent data processing
- CET classification
- Transition detection analytics

Neo4j remains available for graph-specific operations (relationship traversal, path queries, visualization) when you add `--profile neo4j`. This gives you:

- **Faster startup** — no waiting for Neo4j health checks
- **Lower memory** — DuckDB uses ~100 MB vs Neo4j's 1.5 GB
- **Simpler debugging** — one fewer service to troubleshoot
- **Self-contained** — no external database dependency

## CDK Context Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `instance_type` | `t3.medium` | EC2 instance type |
| `key_pair_name` | (none) | SSH key pair (optional with SSM) |
| `allowed_ssh_cidr` | `0.0.0.0/0` | IP range for SSH/UI access |
| `volume_size_gb` | `50` | EBS volume size |
| `vpc_id` | default VPC | VPC to launch in |

## Instance Sizing

| Instance | RAM | vCPU | Monthly | Good for |
|----------|-----|------|---------|----------|
| t3.small | 2 GB | 2 | ~$15 | Light ETL, exploration |
| t3.medium | 4 GB | 2 | ~$30 | Standard development |
| t3.large | 8 GB | 2 | ~$60 | Full pipeline + Neo4j |
| t3.xlarge | 16 GB | 4 | ~$120 | ML training + everything |

## Connecting

```bash
# SSM Session Manager (no SSH key needed)
aws ssm start-session --target <instance-id> --region us-east-2

# SSH (if key_pair_name was set)
ssh -i ~/.ssh/your-key.pem ec2-user@<public-ip>

# Port forwarding (Dagster UI on localhost)
ssh -L 3000:localhost:3000 ec2-user@<public-ip>
```

## Related

- [Deployment Comparison](deployment-comparison.md) — EC2 vs Batch cost analysis
- [Docker Guide](docker.md) — Container configuration reference
- [Containerization](containerization.md) — Docker architecture overview
