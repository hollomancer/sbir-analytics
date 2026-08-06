# Enrichment

Per-source integration notes for the enrichers. The reusable patterns these
follow are a durable contract and live in
[steering/enrichment-patterns.md](../steering/enrichment-patterns.md); this
directory records how individual sources behave.

| Document | Source |
|---|---|
| [Enricher catalog](enricher-catalog.md) | All enrichers, what each adds |
| [SAM.gov entity integration](sam-gov-integration.md) | SAM.gov |
| [USAspending iterative refresh](usaspending-iterative-refresh.md) | USAspending |
| [Enhanced name matching](enhanced-matching.md) | Company-name matching behaviour |

Company-name normalization and similarity are a shared primitive, not an
enricher concern — see the
[company identity contract](../steering/company-identity.md).
