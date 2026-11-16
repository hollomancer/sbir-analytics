# ModernBERT Bayesian MoE proposal — superseded

**Disposition:** Superseded on 2026-11-14

The original `modernbert-analysis-layer` spec proposed a three-stage Bayesian
mixture-of-experts pipeline for classification, similarity, and embedding. It
also proposed LoRA expert pools, variational routing, calibrated uncertainty,
dynamic expert creation, FAISS, cohesion metrics, and dedicated monitoring.

No implementation, validation study, operating owner, or current research
priority supported that design. Keeping hundreds of lines of prospective
interfaces in an active maintenance spec made the repository describe a system
that did not exist.

The active spec now covers the implemented exploratory C2 path: ModernBERT
award and patent embeddings, brute-force cosine similarity, coverage checks,
and four bounded reliability follow-ups. Git history preserves the detailed
proposal before this supersession record.

Reactivation requires a new spec with:

- a current research-question anchor and target epistemic tier;
- evidence that the existing single-model path is insufficient;
- measurable validation and promotion criteria;
- a compute and operating-cost owner; and
- an explicit decision on how outputs may and may not support claims.
