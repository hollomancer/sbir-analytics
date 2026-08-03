# SBIR → DIB Network Explorer

Static, dependency-free browser explorer for the identifier-verified SBIR
awardee-to-DoD-prime-family network.

## Build the browser payload

Materialize the supply network first, then export its Parquet edges:

```bash
uv run python scripts/data/export_sbir_dib_network_web.py
```

The generated `data/network.json` is intentionally ignored. It contains the
full local analysis slice and can be regenerated from the source artifacts.

## Run locally

From this directory:

```bash
python -m http.server 8080
```

Open <http://localhost:8080>. A local web server is required because browsers
do not permit `fetch()` of the generated JSON from a `file://` page.

## Interaction model

- The overview ranks verified prime-family edges by persistence and reported
  amount instead of rendering all relationships as an unreadable hairball.
- Search can locate any supplier or prime in the full payload and open its ego
  network.
- Persistence, density, NSF SBIR-only, and CET supply-chain screening controls
  change the visible network.
- Selecting a node shows its observed relationships and supplier exposure
  screen, including NSF SBIR award history when present. NSF matches are review
  candidates; no visualization state establishes dependency or criticality.

The CET supply-chain screen combines a specific NSF award's title/topic/abstract
classification with the versioned defense-supply-chain crosswalk. It is an
auditable prioritization aid, not evidence that the award's technology was used
on the observed subcontract or that the supplier is irreplaceable.
