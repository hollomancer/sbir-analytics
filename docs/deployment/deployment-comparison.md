# Deployment Options Comparison

Quick guide to choosing the right deployment approach for sbir-analytics-ml location.

## TL;DR - Quick Decision Tree

```text
How often do ML jobs run?
│
├─ Constantly (multiple times per hour)
│  └─> Choose: EC2 Always-On
│     Cost: ~$30/mo
│     Setup: ⭐⭐⭐⭐⭐ Simple
│
├─ Frequently (daily, multiple per day)
│  └─> Choose: EC2 Always-On or AWS Batch
│     Cost: Similar (~$20-30/mo)
│     Setup: EC2 easier
│
└─ Infrequently (weekly, few per day)
   └─> Choose: AWS Batch with Spot
      Cost: ~$11-15/mo
      Setup: ⭐⭐⭐ Moderate
```

## Detailed Comparison

### Option 1: EC2 Always-On (Configured)

```text
┌──────────────────────────────────┐
│   t3.small EC2 Instance          │
│   Dagster Agent (always running) │
│   ~$15/month                     │
└──────────────────────────────────┘
```

**Best for:**

- Learning/getting started (simplest setup)
- Frequent jobs (multiple times per day)
- Predictable workloads
- Need guaranteed availability

**Pros:**

- ✅ Simple setup (one script)
- ✅ No cold start delay
- ✅ Easy to debug (SSH in anytime)
- ✅ Works with all Dagster features

**Cons:**

- ❌ Pay 24/7 even when idle
- ❌ Manual scaling (need bigger instance for parallel jobs)
- ❌ Fixed resources (can't use different sizes per job)

**Costs:**

```text
t3.micro:  ~$7/mo  (1GB RAM)  - Minimal, might struggle with ML
t3.small:  ~$15/mo (2GB RAM)  - ✅ RECOMMENDED for ML agent
t3.medium: ~$30/mo (4GB RAM)  - If running many parallel jobs
t3.large:  ~$60/mo (8GB RAM)  - If jobs are very heavy
```

**Setup time:** ~15 minutes

---

### Option 2: AWS Batch (Alternative)

```text
┌────────────────┐     ┌──────────────────────────────┐
│ t3.micro EC2   │────>│      AWS Batch               │
│ Agent (~$7/mo) │     │  Containers (on-demand)      │
└────────────────┘     │  ~$4-20/mo (with Spot)       │
                       └──────────────────────────────┘
```

**Best for:**

- Infrequent jobs (weekly, few per day)
- Variable resource requirements
- Cost optimization
- Running many parallel jobs

**Pros:**

- ✅ Pay only for job execution time
- ✅ Auto-scaling (1 job or 100 jobs, same config)
- ✅ Spot instances = 70% savings
- ✅ Different instance types per job
- ✅ Better for bursty workloads

**Cons:**

- ❌ More complex setup (IAM roles, compute env, queues)
- ❌ Cold start ~1-2 min
- ❌ Harder to debug (need CloudWatch logs)
- ❌ Spot instances can be interrupted (auto-retries)

**Costs:**

```text
Agent (t3.micro):     ~$7/mo    (always running)
Compute (c5.2xlarge): ~$0.34/hr (on-demand)
Compute (Spot):       ~$0.10/hr (70% cheaper!)

Example monthly costs:
- 10 jobs/week × 1hr × $0.10 = ~$4/mo  → Total: $11/mo
- 50 jobs/week × 1hr × $0.10 = ~$20/mo → Total: $27/mo
- 100 jobs/week × 30min × $0.10 = ~$20/mo → Total: $27/mo
```

**Setup time:** ~1-2 hours

---

## Cost Scenarios

### Scenario 1: Few ML Jobs (10 per week, 1 hour each)

| Approach | Monthly Cost | Break-even |
|----------|-------------|------------|
| EC2 t3.small | $15 | - |
| AWS Batch (on-demand) | $7 + $14 = $21 | ❌ More expensive |
| AWS Batch (Spot 70% off) | $7 + $4 = **$11** | ✅ **$4 savings** |

**Winner:** AWS Batch with Spot

### Scenario 2: Regular ML Jobs (daily, 2 hours each)

| Approach | Monthly Cost | Break-even |
|----------|-------------|------------|
| EC2 t3.small | $15 | - |
| AWS Batch (on-demand) | $7 + $40 = $47 | ❌ More expensive |
| AWS Batch (Spot 70% off) | $7 + $12 = **$19** | ⚠️ Similar |

**Winner:** EC2 (simpler, similar cost)

### Scenario 3: Constant ML Jobs (4 hours per day)

| Approach | Monthly Cost | Break-even |
|----------|-------------|------------|
| EC2 t3.medium | $30 | - |
| AWS Batch (on-demand) | $7 + $80 = $87 | ❌ More expensive |
| AWS Batch (Spot 70% off) | $7 + $24 = **$31** | ⚠️ Similar but complex |

**Winner:** EC2 (much simpler for same cost)

### Scenario 4: Massive Parallel Jobs (100 jobs/week, 30 min each)

| Approach | Monthly Cost | Break-even |
|----------|-------------|------------|
| EC2 t3.large (to handle load) | $60 | - |
| AWS Batch (on-demand) | $7 + $70 = $77 | ⚠️ Similar |
| AWS Batch (Spot 70% off) | $7 + $21 = **$28** | ✅ **$32 savings** |

**Winner:** AWS Batch with Spot (scales automatically)

---

## Feature Comparison

| Feature | EC2 Always-On | AWS Batch |
|---------|---------------|-----------|
| **Setup Complexity** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| **Cold Start** | None | 1-2 min |
| **Scaling** | Manual | Automatic |
| **Cost Idle** | $15-30/mo | $7/mo |
| **Cost Active** | Same | Per-second |
| **Debugging** | SSH + logs | CloudWatch |
| **Spot Instances** | Manual | Built-in |
| **Parallel Jobs** | Limited by instance | Unlimited |
| **Best for Beginners** | ✅ Yes | ❌ No |

---

## My Recommendation

### If you're just getting started

**Choose EC2 (already configured!)**

- Run the setup script
- Get ML jobs working
- Monitor usage for a month
- Migrate to Batch later if needed

### If you have infrequent ML jobs (<20/week)

**Choose AWS Batch**

- ~$11-15/month with Spot
- Scales automatically
- Only pay for what you use

### If you run ML constantly

**Choose EC2**

- Simpler
- No cold starts
- Similar cost to Batch

---

## Migration Path

**Start with EC2** (already set up):

1. Run `scripts/setup-ec2-agent.sh` on t3.small
2. Monitor job frequency and duration for 1-2 weeks
3. Calculate actual usage costs

**Migrate to Batch if**:

- Jobs run <4 hours/day total
- Cost savings >$10/month worth the complexity
- Need to run many parallel jobs

**Migration is easy**:

- Keep same agent EC2 instance
- Add AWS Batch configuration
- Update agent config to use BatchUserCodeLauncher
- Test thoroughly

---

## Current Setup (Already Configured)

You currently have **EC2 configuration ready**:

- ✅ `scripts/setup-ec2-agent.sh` - one-command setup
- ✅ `docs/deployment/usaspending-ec2-automation.md` - EC2 automation guide

To switch to Batch later, you'll have:

- ✅ `docs/deployment/aws-deployment.md` - full guide (just created)

## Decision Helper

Answer these questions:

1. **How often will ML jobs run?**
   - Multiple per hour → EC2
   - Few per day → Either works
   - Few per week → AWS Batch

2. **What's your priority?**
   - Simplicity → EC2
   - Cost optimization → AWS Batch
   - Learning → EC2 first

3. **Do you need parallel execution?**
   - No, sequential is fine → EC2
   - Yes, 10+ jobs at once → AWS Batch

4. **How comfortable are you with AWS?**
   - Beginner → EC2
   - Advanced → Either
   - Expert → AWS Batch

5. **Budget constraint?**
   - <$20/month → AWS Batch
   - <$50/month → Either works
   - No constraint → EC2 (simpler)

---

## Verdict for Your Use Case

Based on typical ML analytics workloads:

**Start with EC2 (t3.small, ~$15/mo)**

Why:

- ✅ Already configured and ready to use
- ✅ Simple setup (15 minutes)
- ✅ Good enough for most ML workloads
- ✅ Easy to debug and maintain
- ✅ Can always migrate to Batch later

**Consider Batch if**:

- Jobs are very infrequent (weekly)
- Budget is tight (<$20/month)
- You're comfortable with AWS complexity

The setup script is ready. Just launch an EC2 instance and run it! 🚀
